"""Midtrans Snap + Xendit Invoice helpers.

Midtrans keys are entered by the owner in Admin > Pengaturan Pembayaran (stored encrypted in MongoDB,
never returned). backend/.env MIDTRANS_SERVER_KEY is only a fallback. Xendit keys come from .env.
"""
import base64
import hashlib
import hmac
import os
from datetime import datetime, timezone
from typing import Optional

import httpx
from cryptography.fernet import Fernet
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

# In-memory copy of the admin Midtrans settings (loaded at startup, refreshed on save)
_MT: dict = {"server_key": "", "production": False, "enabled": False, "state": None}


def _fernet() -> Fernet:
    return Fernet(os.environ["KEY_ENCRYPTION_SECRET"].encode())


def midtrans_ready() -> bool:
    if _MT["server_key"]:  # admin key wins; only a key Midtrans confirmed valid is offered to buyers
        return bool(_MT["enabled"]) and _MT["state"] == "valid"
    return bool(os.environ.get("MIDTRANS_SERVER_KEY"))


def xendit_ready() -> bool:
    return bool(os.environ.get("XENDIT_SECRET_KEY"))


def _midtrans_key() -> str:
    # The toggle only hides Midtrans for new checkouts; pending orders still settle with the saved key
    key = _MT["server_key"] or os.environ.get("MIDTRANS_SERVER_KEY", "")
    if not key:
        raise HTTPException(status_code=503, detail="Pembayaran Midtrans belum dikonfigurasi")
    return key


def _midtrans_urls() -> tuple[str, str]:
    prod = _MT["production"] if _MT["server_key"] else os.environ.get("MIDTRANS_IS_PRODUCTION", "false").lower() == "true"
    if prod:
        return "https://app.midtrans.com/snap/v1/transactions", "https://api.midtrans.com/v2"
    return "https://app.sandbox.midtrans.com/snap/v1/transactions", "https://api.sandbox.midtrans.com/v2"


def _midtrans_headers() -> dict:
    token = base64.b64encode(f"{_midtrans_key()}:".encode()).decode()
    return {"Accept": "application/json", "Content-Type": "application/json", "Authorization": f"Basic {token}"}


async def midtrans_create(order: dict) -> dict:
    snap_url, _ = _midtrans_urls()
    items = [
        {"id": i["product_id"][:50], "price": i["price"], "quantity": i["quantity"], "name": i["name"][:50]}
        for i in order["items"]
    ]
    if order.get("shipping_cost"):
        items.append({"id": "ongkir", "price": order["shipping_cost"], "quantity": 1, "name": "Ongkos Kirim"})
    if order.get("discount"):
        items.append({"id": "voucher", "price": -order["discount"], "quantity": 1, "name": f"Voucher {order.get('voucher_code') or ''}"[:50]})
    if order.get("balance_used"):
        items.append({"id": "saldo", "price": -order["balance_used"], "quantity": 1, "name": "Potongan Saldo"})
    ship = order["shipping"]
    payload = {
        "transaction_details": {"order_id": order["order_id"], "gross_amount": order["total"] - order.get("balance_used", 0)},
        "item_details": items,
        "customer_details": {"first_name": ship["full_name"][:50], "phone": ship["phone"][:20],
                              **({"email": order["email"]} if order.get("email") else {})},
        "enabled_payments": ["other_qris", "gopay", "shopeepay", "bca_va", "bni_va", "bri_va", "permata_va", "echannel"],
    }
    async with httpx.AsyncClient(timeout=25) as c:
        r = await c.post(snap_url, json=payload, headers=_midtrans_headers())
    if r.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Midtrans error: {r.text[:300]}")
    data = r.json()
    return {"payment_url": data["redirect_url"], "payment_ref": data["token"]}


async def midtrans_status(order_id: str) -> str | None:
    _, status_url = _midtrans_urls()
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(f"{status_url}/{order_id}/status", headers=_midtrans_headers())
    if r.status_code >= 400:
        return None
    p = r.json()
    if str(p.get("status_code")) == "404":
        return None
    return midtrans_map(p)


def midtrans_map(p: dict) -> str:
    ts = p.get("transaction_status")
    if ts in ("settlement", "capture") and p.get("fraud_status", "accept").lower() == "accept":
        return "paid"
    if ts == "expire":
        return "expired"
    if ts in ("deny", "cancel", "failure"):
        return "failed"
    return "pending"


def midtrans_verify(p: dict) -> bool:
    raw = f'{p.get("order_id")}{p.get("status_code")}{p.get("gross_amount")}{_midtrans_key()}'
    expected = hashlib.sha512(raw.encode()).hexdigest()
    return hmac.compare_digest(expected, str(p.get("signature_key", "")))


def _xendit_key() -> str:
    key = os.environ.get("XENDIT_SECRET_KEY", "")
    if not key:
        raise HTTPException(status_code=503, detail="Pembayaran Xendit belum dikonfigurasi")
    return key


async def xendit_create(order: dict) -> dict:
    payload = {
        "external_id": order["order_id"],
        "amount": order["total"] - order.get("balance_used", 0),
        "currency": "IDR",
        "description": f"Pesanan {order['order_id']} - Pusat Grosir Sidoarjo",
        "invoice_duration": 86400,
        "customer": {"given_names": order["shipping"]["full_name"][:50], "mobile_number": order["shipping"]["phone"][:20]},
        "items": [{"name": i["name"][:100], "quantity": i["quantity"], "price": i["price"]} for i in order["items"]],
        "fees": ([{"type": "Ongkos Kirim", "value": order["shipping_cost"]}] if order.get("shipping_cost") else [])
        + ([{"type": f"Voucher {order.get('voucher_code') or ''}", "value": -order["discount"]}] if order.get("discount") else [])
        + ([{"type": "Potongan Saldo", "value": -order["balance_used"]}] if order.get("balance_used") else []),
    }
    if order.get("email"):
        payload["payer_email"] = order["email"]
    async with httpx.AsyncClient(base_url="https://api.xendit.co", auth=(_xendit_key(), ""), timeout=25) as c:
        r = await c.post("/v2/invoices", json=payload)
    if r.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Xendit error: {r.text[:300]}")
    inv = r.json()
    return {"payment_url": inv["invoice_url"], "payment_ref": inv["id"]}


def xendit_map(status: str) -> str:
    s = (status or "").upper()
    if s in ("PAID", "SETTLED"):
        return "paid"
    if s == "EXPIRED":
        return "expired"
    if s == "FAILED":
        return "failed"
    return "pending"


async def xendit_status(invoice_id: str) -> str | None:
    async with httpx.AsyncClient(base_url="https://api.xendit.co", auth=(_xendit_key(), ""), timeout=20) as c:
        r = await c.get(f"/v2/invoices/{invoice_id}")
    if r.status_code >= 400:
        return None
    return xendit_map(r.json().get("status"))


def xendit_verify(token: str | None) -> bool:
    expected = os.environ.get("XENDIT_WEBHOOK_TOKEN", "")
    return bool(expected) and hmac.compare_digest(expected, token or "")


# ------------------------------------------------------------------ admin settings
class MidtransSettingsIn(BaseModel):
    enabled: bool = True
    production: bool = False
    server_key: Optional[str] = Field(default=None, max_length=200)  # None = keep, "" = remove
    client_key: Optional[str] = Field(default=None, max_length=200)


async def load_config(db) -> None:
    s = await db.settings.find_one({"key": "payment_midtrans"}) or {}
    key = ""
    if s.get("server_key_enc"):
        try:
            key = _fernet().decrypt(s["server_key_enc"].encode()).decode()
        except Exception:
            key = ""
    _MT.update(server_key=key, production=bool(s.get("production")), enabled=bool(s.get("enabled", True)),
               state=(s.get("key_status") or {}).get("state"))


async def _verify_midtrans(key: str, production: bool) -> dict:
    """Ask Midtrans for a non-existent order: valid key -> 404, bad key -> 401."""
    base = "https://api.midtrans.com/v2" if production else "https://api.sandbox.midtrans.com/v2"
    token = base64.b64encode(f"{key}:".encode()).decode()
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{base}/pgs-key-check/status", headers={"Accept": "application/json", "Authorization": f"Basic {token}"})
        code = str((r.json() if r.headers.get("content-type", "").startswith("application/json") else {}).get("status_code") or r.status_code)
    except Exception:
        return {"state": "unknown", "message": "Tidak bisa menghubungi Midtrans, coba lagi nanti"}
    if code in ("404", "200", "201", "407"):
        return {"state": "valid", "message": f"Server key valid untuk mode {'Production' if production else 'Sandbox'}"}
    if code == "401":
        other = "Production" if not production else "Sandbox"
        return {"state": "invalid", "message": f"Server key ditolak Midtrans. Pastikan key dari mode yang sama (bukan key {other})"}
    return {"state": "unknown", "message": f"Midtrans menjawab kode {code}, coba lagi nanti"}


def register_settings(api, db, require_admin):
    def _public(s: dict) -> dict:
        enc = s.get("server_key_enc")
        return {"configured": bool(enc), "key_hint": s.get("key_hint", "") if enc else "", "client_key": s.get("client_key", ""),
                "enabled": s.get("enabled", True), "production": bool(s.get("production")),
                "key_status": s.get("key_status") if enc else None, "ready": midtrans_ready()}

    async def _get() -> dict:
        return await db.settings.find_one({"key": "payment_midtrans"}, {"_id": 0}) or {}

    async def _check() -> None:
        await load_config(db)
        if _MT["server_key"]:
            st = await _verify_midtrans(_MT["server_key"], _MT["production"])
            await db.settings.update_one({"key": "payment_midtrans"}, {"$set": {"key_status": {**st, "checked_at": datetime.now(timezone.utc)}}})
            _MT["state"] = st["state"]

    @api.get("/admin/payment-settings")
    async def get_payment_settings(_=Depends(require_admin)):
        return _public(await _get())

    @api.put("/admin/payment-settings")
    async def put_payment_settings(body: MidtransSettingsIn, _=Depends(require_admin)):
        cur = await _get()
        upd: dict = {"key": "payment_midtrans", "enabled": body.enabled, "production": body.production}
        if body.client_key is not None:
            upd["client_key"] = body.client_key.strip()
        if body.server_key is not None:
            k = body.server_key.strip()
            upd["server_key_enc"] = _fernet().encrypt(k.encode()).decode() if k else None
            upd["key_hint"] = f"••••{k[-4:]}" if k else ""
        await db.settings.update_one({"key": "payment_midtrans"}, {"$set": upd}, upsert=True)
        if (body.server_key is not None and body.server_key.strip()) or bool(cur.get("production")) != body.production:
            await _check()  # new key or mode switch -> verify right away
        else:
            await load_config(db)
            if body.server_key == "":
                await db.settings.update_one({"key": "payment_midtrans"}, {"$unset": {"key_status": ""}})
                _MT["state"] = None
        return _public(await _get())

    @api.post("/admin/payment/verify-midtrans")
    async def verify_midtrans(_=Depends(require_admin)):
        if not (await _get()).get("server_key_enc"):
            raise HTTPException(status_code=400, detail="Isi Server Key Midtrans dulu")
        await _check()
        return _public(await _get())

    @api.get("/payments/methods")
    async def payment_methods():
        return {"midtrans": midtrans_ready(), "xendit": xendit_ready(), "cod": True,
                "midtrans_sandbox": not (_MT["production"] if _MT["server_key"] else os.environ.get("MIDTRANS_IS_PRODUCTION", "false").lower() == "true")}
