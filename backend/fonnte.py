"""Pengaturan WhatsApp Fonnte oleh Super Admin: token (terenkripsi), nomor pemilik, uji koneksi, uji kirim OTP.

Token dari halaman Admin dipakai lebih dulu; kalau kosong, FONNTE_TOKEN di .env. Tanpa token, OTP tetap mode uji (kode di layar)."""
import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Optional

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, HTTPException
from pydantic import BaseModel

log = logging.getLogger(__name__)
KEY = {"key": "fonnte"}
SEND_URL = "https://api.fonnte.com/send"
DEVICE_URL = "https://api.fonnte.com/device"
_db = None


def _fernet() -> Fernet:
    return Fernet(os.environ["KEY_ENCRYPTION_SECRET"].encode())


async def _settings() -> dict:
    return (await _db.settings.find_one(KEY, {"_id": 0}) or {}) if _db is not None else {}


async def get_token() -> tuple[str, str]:
    """(token, sumber): sumber 'admin' (halaman Admin), 'env', atau '' bila belum ada."""
    s = await _settings()
    if s.get("token_enc"):
        try:
            return _fernet().decrypt(s["token_enc"].encode()).decode(), "admin"
        except InvalidToken:
            log.error("Fonnte token cannot be decrypted")
    env = os.environ.get("FONNTE_TOKEN", "")
    return env, ("env" if env else "")


async def owner_whatsapp() -> str:
    s = await _settings()
    return s["owner_whatsapp"] if "owner_whatsapp" in s else os.environ.get("OWNER_WHATSAPP", "")  # cleared in Admin = no WA


def otp_test_mode(source: str) -> bool:
    """Token dari Admin = kirim asli. Token .env mengikuti OTP_TEST_MODE. Tanpa token = mode uji."""
    if source == "admin":
        return False
    return not source or os.environ.get("OTP_TEST_MODE", "false").lower() == "true"


async def send(token: str, target: str, message: str) -> dict:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(SEND_URL, headers={"Authorization": token}, data={"target": target, "message": message, "countryCode": "62"})
    try:
        body = r.json()
    except ValueError:
        body = {"status": False, "reason": f"HTTP {r.status_code}"}
    if r.is_error:
        body["status"] = False
    return body


class FonnteIn(BaseModel):
    token: Optional[str] = None  # None = tidak diubah, "" = hapus
    owner_whatsapp: Optional[str] = None


class TestIn(BaseModel):
    token: Optional[str] = None  # uji token yang baru diketik sebelum disimpan


class TestOtpIn(BaseModel):
    phone: str


def register(api, db, require_admin, normalize_phone):
    global _db
    _db = db

    async def status() -> dict:
        s = await _settings()
        token, src = await get_token()
        return {"has_token": bool(token), "source": src, "token_hint": f"••••{token[-4:]}" if token else "",
                "owner_whatsapp": await owner_whatsapp(), "otp_mode": "uji" if otp_test_mode(src) else "asli",
                "updated_at": s.get("updated_at"), "last_test": s.get("last_test")}

    @api.get("/admin/fonnte")
    async def get_fonnte(_=Depends(require_admin)):
        return await status()

    @api.put("/admin/fonnte")
    async def put_fonnte(body: FonnteIn, admin=Depends(require_admin)):
        upd: dict = {"updated_at": datetime.now(timezone.utc), "updated_by": admin["user_id"]}
        if body.token is not None:
            t = body.token.strip()
            if t and not 10 <= len(t) <= 200:
                raise HTTPException(status_code=400, detail="Token Fonnte tidak valid")
            upd["token_enc"] = _fernet().encrypt(t.encode()).decode() if t else ""
            upd["last_test"] = None
        if body.owner_whatsapp is not None:
            p = normalize_phone(body.owner_whatsapp) if body.owner_whatsapp.strip() else ""
            if p and (not p.startswith("62") or not 10 <= len(p) <= 15):
                raise HTTPException(status_code=400, detail="Nomor WhatsApp pemilik tidak valid")
            upd["owner_whatsapp"] = p
        await db.settings.update_one(KEY, {"$set": upd}, upsert=True)
        return await status()

    @api.post("/admin/fonnte/test")
    async def test_fonnte(body: TestIn, _=Depends(require_admin)):
        token = (body.token or "").strip() or (await get_token())[0]
        if not token:
            raise HTTPException(status_code=400, detail="Isi token Fonnte dulu")
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.post(DEVICE_URL, headers={"Authorization": token})
            d = r.json()
        except Exception:
            log.exception("Fonnte device check failed")
            raise HTTPException(status_code=502, detail="Tidak bisa menghubungi Fonnte, coba lagi")
        ok = bool(d.get("status"))
        out = {"ok": ok, "reason": d.get("reason", ""), "device": d.get("device", ""), "device_status": d.get("device_status", ""),
               "name": d.get("name", ""), "quota": str(d.get("quota", "")), "expired": d.get("expired", ""), "package": d.get("package", "")}
        if not body.token:
            await db.settings.update_one(KEY, {"$set": {"last_test": {**out, "at": datetime.now(timezone.utc)}}}, upsert=True)
        return out

    @api.post("/admin/fonnte/test-otp")
    async def test_otp(body: TestOtpIn, _=Depends(require_admin)):
        phone = normalize_phone(body.phone)
        if not phone.startswith("62") or not 10 <= len(phone) <= 15:
            raise HTTPException(status_code=400, detail="Nomor HP tidak valid")
        token, _src = await get_token()
        if not token:
            raise HTTPException(status_code=400, detail="Token Fonnte belum diisi. OTP masih mode uji (kode tampil di layar)")
        code = f"{secrets.randbelow(1000000):06d}"
        try:
            d = await send(token, phone, f"[UJI] Kode verifikasi Pusat Grosir Sidoarjo: {code}\nIni pesan uji dari halaman Admin.")
        except Exception:
            log.exception("Fonnte test OTP failed")
            raise HTTPException(status_code=502, detail="Tidak bisa menghubungi Fonnte, coba lagi")
        if not d.get("status"):
            raise HTTPException(status_code=400, detail=f"Fonnte menolak: {d.get('reason') or 'cek token & status perangkat'}")
        return {"ok": True, "phone": phone, "code": code, "message": f"Pesan uji berisi kode {code} dikirim ke WhatsApp {phone}"}
