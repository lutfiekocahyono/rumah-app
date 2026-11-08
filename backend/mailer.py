"""Transactional email via Emergent managed email (Resend). Fixed server-side templates only."""
import ipaddress
import logging
import os
import re
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException

logger = logging.getLogger("mailer")

EMAIL_BASE_URL = "https://integrations.emergentagent.com"

_SHORTENERS = ("bit.ly", "tinyurl.com", "t.co", "is.gd", "cutt.ly", "goo.gl", "rebrand.ly")
_CRED_ASK = ("reply with your password", "reply with the code", "send your password", "cvv",
             "send us your password", "enter your password below", "confirm your card number",
             "your full card number", "seed phrase", "recovery phrase", "verify your card",
             "social security number", "confirm your bank details")
_HOSTISH = re.compile(r"\b(?:https?://)?((?:[a-z0-9-]+\.)+[a-z]{2,})", re.I)


def _host_ok(host: str) -> bool:
    if not host or "xn--" in host:
        return False
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass
    return not any(host == s or host.endswith("." + s) for s in _SHORTENERS)


def _same_site(shown: str, real: str) -> bool:
    return shown == real or real.endswith("." + shown) or shown.endswith("." + real)


class _EmailScan(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags, self.urls, self.anchors = set(), [], []
        self._href, self._text = None, []

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag.lower())
        self.urls += [v for k, v in attrs if k.lower() in ("href", "src") and v]
        if tag.lower() == "a":
            self._href = dict((k.lower(), v) for k, v in attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            self.anchors.append((self._href, "".join(self._text)))
            self._href, self._text = None, []


def _assert_safe_email(subject: str, html: str) -> None:
    scan = _EmailScan()
    scan.feed(html)
    if scan.tags & {"form", "input", "textarea", "select"}:
        raise ValueError("No forms or input fields in email (G2)")
    body = f"{subject}\n{html}".lower()
    for p in _CRED_ASK:
        if p in body:
            raise ValueError(f"Email asks the recipient for credentials: {p!r} (G2)")
    for url in scan.urls:
        low = url.strip().lower()
        if low.startswith(("mailto:", "tel:", "cid:", "#")):
            continue
        if not low.startswith("https://"):
            raise ValueError(f"Email links/assets must be absolute https: {url!r} (G3)")
        host = urlparse(low).hostname or ""
        if not _host_ok(host) or urlparse(low).username is not None:
            raise ValueError(f"Shortened, numeric-host or credential-bearing URL: {url!r} (G3)")
    for href, text in scan.anchors:
        real = urlparse(href.strip().lower()).hostname or ""
        if not real:
            continue
        for m in _HOSTISH.finditer(text):
            if not _same_site(m.group(1).lower(), real):
                raise ValueError(f"Anchor text {m.group(1)!r} != real link host {real!r} (G3)")


async def send_email(*, to: str, subject: str, html: str) -> str | None:
    _assert_safe_email(subject, html)
    payload = {"to": [to], "subject": subject, "html": html, "from_name": os.environ["EMAIL_FROM_NAME"]}
    if os.environ.get("EMAIL_REPLY_TO"):
        payload["contact_email"] = os.environ["EMAIL_REPLY_TO"]
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{EMAIL_BASE_URL}/api/v1/email/send",
                                     headers={"X-Email-Key": os.environ["EMERGENT_EMAIL_KEY"]}, json=payload)
        resp.raise_for_status()
        return resp.json().get("id")
    except httpx.HTTPStatusError as e:
        try:
            code = e.response.json().get("code", "")
        except ValueError:
            code = ""
        if code == "undeliverable_recipient":
            raise HTTPException(status_code=400, detail="Alamat email ini tidak bisa menerima pesan")
        if code in ("insufficient_credits", "integration_disabled", "daily_limit_reached"):
            logger.warning("Email paused: %s (%s)", code, e.response.status_code)
            raise HTTPException(status_code=503, detail="Email sedang tidak tersedia, coba lagi nanti")
        logger.error("Email send failed: %s %s", e.response.status_code, e.response.text[:300])
        raise HTTPException(status_code=502, detail="Gagal mengirim email")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Email send error: %s", e)
        raise HTTPException(status_code=500, detail="Gagal mengirim email")


def _wrap(name: str, body_html: str) -> str:
    brand = escape(os.environ["EMAIL_FROM_NAME"])
    return (
        '<table role="presentation" width="100%" style="background:#F9FAFB"><tr><td align="center" style="padding:24px">'
        '<table role="presentation" width="480" style="background:#FFFFFF;border-radius:12px;font-family:Arial,sans-serif;color:#111827">'
        f'<tr><td style="background:#F15A24;color:#FFFFFF;padding:16px 24px;font-size:18px;font-weight:bold;border-radius:12px 12px 0 0">{brand}</td></tr>'
        f'<tr><td style="padding:24px"><p>Halo {escape(name)},</p>{body_html}'
        f'<p style="font-size:12px;color:#6B7280;margin-top:24px">Email ini dikirim otomatis oleh {brand}. '
        'Kami tidak pernah meminta password atau data kartu Anda lewat email.</p></td></tr></table></td></tr></table>'
    )


def _code_block(code: str) -> str:
    return (f'<p style="font-size:32px;font-weight:bold;letter-spacing:8px;color:#F15A24;margin:16px 0">{escape(code)}</p>'
            '<p>Kode berlaku 10 menit. Jangan bagikan kode ini kepada siapa pun.</p>')


async def send_verify_code(to: str, name: str, code: str) -> None:
    await send_email(to=to, subject="Kode verifikasi email Anda",
                     html=_wrap(name, "<p>Gunakan kode berikut di aplikasi untuk memverifikasi email Anda:</p>" + _code_block(code)))


async def send_reset_code(to: str, name: str, code: str) -> None:
    await send_email(to=to, subject="Kode atur ulang password",
                     html=_wrap(name, "<p>Kami menerima permintaan atur ulang password. Masukkan kode ini di aplikasi:</p>"
                                + _code_block(code) + "<p>Abaikan email ini jika Anda tidak memintanya.</p>"))


async def send_password_changed(to: str, name: str) -> None:
    await send_email(to=to, subject="Password Anda telah diubah",
                     html=_wrap(name, "<p>Password akun Anda baru saja diubah. Jika ini bukan Anda, segera atur ulang password lewat aplikasi.</p>"))
