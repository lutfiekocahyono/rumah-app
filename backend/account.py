"""User account features: verification codes, password flows, profile, addresses, activity, settings, notifications."""
import hashlib
import hmac
import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import httpx
from fastapi import Depends, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, EmailStr, Field
from pymongo import ReturnDocument

import mailer
import storage

log = logging.getLogger("account")
CODE_TTL_MIN = 10
MAX_ATTEMPTS = 5
GENERIC = {"message": "Jika email terdaftar, kode sudah dikirim."}
DEFAULT_SETTINGS = {"notif_order": True, "notif_promo": True, "notif_security": True}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _digest(code: str) -> str:
    return hmac.new(os.environ.get("CODE_PEPPER", "pgs").encode(), code.encode(), hashlib.sha256).hexdigest()


def _hash_pw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def _pw_ok(pw: str, hashed: Optional[str]) -> bool:
    try:
        return bool(hashed) and bcrypt.checkpw(pw.encode(), hashed.encode())
    except Exception:
        return False


def otp_test_mode() -> bool:
    return os.environ.get("OTP_TEST_MODE", "false").lower() == "true"


def normalize_phone(p: str) -> str:
    d = "".join(ch for ch in p if ch.isdigit())
    if d.startswith("0"):
        d = "62" + d[1:]
    elif d.startswith("8"):
        d = "62" + d
    return d


class CodeIn(BaseModel):
    code: str = Field(pattern=r"^[0-9]{6}$")


class EmailIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    email: EmailStr
    code: str = Field(pattern=r"^[0-9]{6}$")
    new_password: str = Field(min_length=8, max_length=128)


class ChangePwIn(BaseModel):
    current_password: str = ""
    new_password: str = Field(min_length=8, max_length=128)


class PhoneIn(BaseModel):
    phone: str = Field(min_length=8, max_length=20)


class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    gender: str = Field(default="", pattern="^(|male|female)$")
    birthdate: str = Field(default="", pattern=r"^(|\d{4}-\d{2}-\d{2})$")


class AddressIn(BaseModel):
    label: str = Field(min_length=1, max_length=30)
    recipient: str = Field(min_length=1, max_length=60)
    phone: str = Field(min_length=6, max_length=20)
    address: str = Field(min_length=5, max_length=300)
    city: str = Field(min_length=2, max_length=60)
    postal_code: str = Field(default="", max_length=10)
    is_default: bool = False


class SettingsIn(BaseModel):
    notif_order: bool = True
    notif_promo: bool = True
    notif_security: bool = True


def register(api, db, get_current_user, user_out, make_token):
    """Attach account routes to the /api router. Returns helpers used elsewhere."""

    async def rate_limit(action: str, identity: str, limit: int, window_s: int) -> None:
        key = hashlib.sha256(f"{action}:{identity.lower()}".encode()).hexdigest()
        t = _now()
        doc = await db.rate_limits.find_one_and_update(
            {"_id": key, "expires_at": {"$gt": t}}, {"$inc": {"count": 1}}, return_document=ReturnDocument.AFTER)
        if not doc:
            await db.rate_limits.replace_one({"_id": key}, {"count": 1, "expires_at": t + timedelta(seconds=window_s)}, upsert=True)
            return
        if doc["count"] > limit:
            raise HTTPException(status_code=429, detail="Terlalu banyak percobaan, coba lagi nanti")

    async def issue_code(user_id: str, purpose: str, extra: Optional[dict] = None) -> str:
        code = f"{secrets.randbelow(1_000_000):06d}"
        await db.one_time_codes.update_many({"user_id": user_id, "purpose": purpose, "used_at": None}, {"$set": {"used_at": _now()}})
        await db.one_time_codes.insert_one({"user_id": user_id, "purpose": purpose, "code_hash": _digest(code), "attempts": 0,
                                            "used_at": None, "created_at": _now(),
                                            "expires_at": _now() + timedelta(minutes=CODE_TTL_MIN), **(extra or {})})
        return code

    async def consume_code(user_id: str, purpose: str, code: str) -> dict:
        doc = await db.one_time_codes.find_one_and_update(
            {"user_id": user_id, "purpose": purpose, "used_at": None, "expires_at": {"$gt": _now()}, "attempts": {"$lt": MAX_ATTEMPTS}},
            {"$inc": {"attempts": 1}}, return_document=ReturnDocument.AFTER)
        if not doc or not hmac.compare_digest(doc["code_hash"], _digest(code)):
            raise HTTPException(status_code=400, detail="Kode salah atau sudah kedaluwarsa")
        await db.one_time_codes.update_one({"_id": doc["_id"]}, {"$set": {"used_at": _now()}})
        return doc

    async def log_activity(user_id: Optional[str], action: str, detail: str = "") -> None:
        if user_id:
            await db.activity_logs.insert_one({"log_id": uuid.uuid4().hex[:12], "user_id": user_id, "action": action,
                                               "detail": detail, "created_at": _now()})

    async def notify_user(user_id: Optional[str], kind: str, title: str, body: str, link: str = "") -> None:
        """kind: order | promo | security. Respects the user's notification settings."""
        if not user_id:
            return
        u = await db.users.find_one({"user_id": user_id}, {"settings": 1})
        if u is None or not {**DEFAULT_SETTINGS, **(u.get("settings") or {})}.get(f"notif_{kind}", True):
            return
        await db.notifications.insert_one({"notif_id": uuid.uuid4().hex[:12], "user_id": user_id, "kind": kind, "title": title,
                                           "body": body, "link": link, "read": False, "created_at": _now()})

    async def broadcast_promo(title: str, body: str, link: str = "") -> None:
        users = await db.users.find({"role": {"$ne": "admin"}, "settings.notif_promo": {"$ne": False}}, {"user_id": 1}).to_list(20000)
        docs = [{"notif_id": uuid.uuid4().hex[:12], "user_id": u["user_id"], "kind": "promo", "title": title, "body": body,
                 "link": link, "read": False, "created_at": _now()} for u in users]
        if docs:
            await db.notifications.insert_many(docs)

    async def security_event(user: dict, title: str, body: str) -> None:
        await log_activity(user["user_id"], "security", title)
        await notify_user(user["user_id"], "security", title, body, "/account/settings")

    # ---------------- email verification ----------------
    @api.post("/auth/verify-email/request")
    async def verify_email_request(user=Depends(get_current_user)):
        if user.get("email_verified"):
            return {"message": "Email sudah terverifikasi"}
        await rate_limit("verify-email", user["user_id"], 5, 3600)
        code = await issue_code(user["user_id"], "email_verify")
        await mailer.send_verify_code(user["email"], user.get("name") or user["email"], code)
        return {"message": f"Kode dikirim ke {user['email']}"}

    @api.post("/auth/verify-email/confirm")
    async def verify_email_confirm(body: CodeIn, user=Depends(get_current_user)):
        await rate_limit("verify-email-confirm", user["user_id"], 10, 600)
        await consume_code(user["user_id"], "email_verify", body.code)
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"email_verified": True}})
        await security_event(user, "Email terverifikasi", f"Email {user['email']} berhasil diverifikasi.")
        return user_out({**user, "email_verified": True})

    # ---------------- phone OTP (WhatsApp) ----------------
    @api.post("/auth/phone/request")
    async def phone_request(body: PhoneIn, user=Depends(get_current_user)):
        phone = normalize_phone(body.phone)
        if not phone.startswith("62") or not 10 <= len(phone) <= 15:
            raise HTTPException(status_code=400, detail="Nomor HP tidak valid")
        if await db.users.find_one({"phone": phone, "phone_verified": True, "user_id": {"$ne": user["user_id"]}}):
            raise HTTPException(status_code=400, detail="Nomor HP sudah dipakai akun lain")
        await rate_limit("phone-otp", user["user_id"], 5, 3600)
        code = await issue_code(user["user_id"], "phone_verify", {"phone": phone})
        token = os.environ.get("FONNTE_TOKEN", "")
        if otp_test_mode() or not token:
            return {"message": "Mode uji: kode ditampilkan di layar", "phone": phone, "dev_code": code}
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                await c.post("https://api.fonnte.com/send", headers={"Authorization": token}, data={
                    "target": phone, "message": f"Kode verifikasi Pusat Grosir Sidoarjo: {code}\nBerlaku 10 menit. Jangan bagikan kode ini."})
        except Exception:
            log.exception("Fonnte OTP failed")
            raise HTTPException(status_code=502, detail="Gagal mengirim WhatsApp, coba lagi")
        return {"message": f"Kode dikirim ke WhatsApp {phone}", "phone": phone}

    @api.post("/auth/phone/confirm")
    async def phone_confirm(body: CodeIn, user=Depends(get_current_user)):
        await rate_limit("phone-confirm", user["user_id"], 10, 600)
        doc = await consume_code(user["user_id"], "phone_verify", body.code)
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"phone": doc["phone"], "phone_verified": True}})
        await security_event(user, "Nomor HP terverifikasi", f"Nomor {doc['phone']} terhubung ke akun Anda.")
        return user_out({**user, "phone": doc["phone"], "phone_verified": True})

    # ---------------- forgot / change password ----------------
    @api.post("/auth/password-reset/request")
    async def reset_request(body: EmailIn, request: Request):
        email = body.email.lower()
        await rate_limit("reset-email", email, 3, 3600)
        await rate_limit("reset-ip", request.client.host if request.client else "x", 20, 3600)
        user = await db.users.find_one({"email": email})
        if user:
            code = await issue_code(user["user_id"], "password_reset")
            await mailer.send_reset_code(email, user.get("name") or email, code)
        return GENERIC

    @api.post("/auth/password-reset/confirm")
    async def reset_confirm(body: ResetIn):
        email = body.email.lower()
        await rate_limit("reset-confirm", email, 5, 600)
        user = await db.users.find_one({"email": email})
        if not user:
            raise HTTPException(status_code=400, detail="Kode salah atau sudah kedaluwarsa")
        await consume_code(user["user_id"], "password_reset", body.code)
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"password_hash": _hash_pw(body.new_password),
                                                                          "email_verified": True}, "$inc": {"auth_version": 1}})
        await security_event(user, "Password diatur ulang", "Password akun Anda diatur ulang lewat Lupa Password.")
        try:
            await mailer.send_password_changed(email, user.get("name") or email)
        except HTTPException:
            pass
        return {"message": "Password berhasil diubah, silakan masuk"}

    @api.post("/auth/password/change")
    async def change_password(body: ChangePwIn, current=Depends(get_current_user)):
        u = await db.users.find_one({"user_id": current["user_id"]})
        if u.get("password_hash") and not _pw_ok(body.current_password, u["password_hash"]):
            raise HTTPException(status_code=400, detail="Password saat ini salah")
        if body.current_password and body.current_password == body.new_password:
            raise HTTPException(status_code=400, detail="Password baru harus berbeda")
        res = await db.users.find_one_and_update({"user_id": u["user_id"]}, {
            "$set": {"password_hash": _hash_pw(body.new_password)}, "$inc": {"auth_version": 1}},
            return_document=ReturnDocument.AFTER)
        await security_event(u, "Password diubah", "Password akun Anda baru saja diubah.")
        try:
            await mailer.send_password_changed(u["email"], u.get("name") or u["email"])
        except HTTPException:
            pass
        return {"token": make_token(res["user_id"], res.get("auth_version", 0)), "user": user_out(res)}

    # ---------------- profile & avatar ----------------
    @api.put("/me/profile")
    async def update_profile(body: ProfileIn, user=Depends(get_current_user)):
        res = await db.users.find_one_and_update({"user_id": user["user_id"]}, {"$set": {
            "name": body.name.strip(), "gender": body.gender, "birthdate": body.birthdate}},
            projection={"_id": 0, "password_hash": 0}, return_document=ReturnDocument.AFTER)
        await log_activity(user["user_id"], "profile", "Profil diperbarui")
        return user_out(res)

    @api.post("/me/avatar")
    async def upload_avatar(file: UploadFile = File(...), user=Depends(get_current_user)):
        if not (file.content_type or "").startswith("image/"):
            raise HTTPException(status_code=400, detail="File harus berupa gambar")
        data = await file.read()
        if len(data) > 5 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Ukuran foto maksimal 5 MB")
        ext = (file.filename or "a.jpg").rsplit(".", 1)[-1].lower()[:5] or "jpg"
        path = f"{storage.APP_NAME}/avatars/{user['user_id']}/{uuid.uuid4().hex}.{ext}"
        try:
            res = await run_in_threadpool(storage.put_object, path, data, file.content_type)
        except Exception:
            log.exception("avatar upload failed")
            raise HTTPException(status_code=502, detail="Upload gagal, coba lagi")
        await db.uploads.insert_one({"storage_path": res["path"], "owner_id": user["user_id"], "content_type": file.content_type,
                                     "original_filename": file.filename, "size": len(data), "is_deleted": False, "created_at": _now()})
        url = f"/api/files/{res['path']}"
        out = await db.users.find_one_and_update({"user_id": user["user_id"]}, {"$set": {"picture": url}},
                                                 projection={"_id": 0, "password_hash": 0}, return_document=ReturnDocument.AFTER)
        await log_activity(user["user_id"], "profile", "Foto profil diganti")
        return user_out(out)

    # ---------------- addresses ----------------
    async def _addresses(uid: str) -> list:
        return await db.addresses.find({"user_id": uid}, {"_id": 0}).sort([("is_default", -1), ("created_at", -1)]).to_list(50)

    @api.get("/me/addresses")
    async def list_addresses(user=Depends(get_current_user)):
        return await _addresses(user["user_id"])

    @api.post("/me/addresses")
    async def add_address(body: AddressIn, user=Depends(get_current_user)):
        uid = user["user_id"]
        if await db.addresses.count_documents({"user_id": uid}) >= 20:
            raise HTTPException(status_code=400, detail="Maksimal 20 alamat")
        first = await db.addresses.count_documents({"user_id": uid}) == 0
        if body.is_default or first:
            await db.addresses.update_many({"user_id": uid}, {"$set": {"is_default": False}})
        await db.addresses.insert_one({**body.model_dump(), "is_default": body.is_default or first,
                                       "address_id": f"ad_{uuid.uuid4().hex[:10]}", "user_id": uid, "created_at": _now()})
        await log_activity(uid, "address", f"Alamat '{body.label}' ditambahkan")
        return await _addresses(uid)

    @api.put("/me/addresses/{address_id}")
    async def edit_address(address_id: str, body: AddressIn, user=Depends(get_current_user)):
        uid = user["user_id"]
        if body.is_default:
            await db.addresses.update_many({"user_id": uid}, {"$set": {"is_default": False}})
        res = await db.addresses.update_one({"user_id": uid, "address_id": address_id}, {"$set": body.model_dump(exclude={"is_default"} if not body.is_default else None)})
        if res.matched_count == 0:
            raise HTTPException(status_code=404, detail="Alamat tidak ditemukan")
        return await _addresses(uid)

    @api.delete("/me/addresses/{address_id}")
    async def delete_address(address_id: str, user=Depends(get_current_user)):
        uid = user["user_id"]
        d = await db.addresses.find_one_and_delete({"user_id": uid, "address_id": address_id})
        if d and d.get("is_default"):
            nxt = await db.addresses.find_one({"user_id": uid}, sort=[("created_at", -1)])
            if nxt:
                await db.addresses.update_one({"_id": nxt["_id"]}, {"$set": {"is_default": True}})
        return await _addresses(uid)

    # ---------------- activity, settings, notifications ----------------
    @api.get("/me/activity")
    async def my_activity(user=Depends(get_current_user)):
        logs = await db.activity_logs.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
        act = await db.activity.find_one({"owner": f"user:{user['user_id']}"}) or {}
        ids = list(reversed(act.get("recent", [])))[:20]
        prods = {p["product_id"]: p for p in await db.products.find({"product_id": {"$in": ids}},
                 {"_id": 0, "product_id": 1, "name": 1, "image": 1, "price": 1}).to_list(20)}
        return {"logs": logs, "recently_viewed": [prods[i] for i in ids if i in prods]}

    @api.get("/me/settings")
    async def get_settings(user=Depends(get_current_user)):
        return {**DEFAULT_SETTINGS, **(user.get("settings") or {})}

    @api.put("/me/settings")
    async def put_settings(body: SettingsIn, user=Depends(get_current_user)):
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"settings": body.model_dump()}})
        await log_activity(user["user_id"], "settings", "Pengaturan notifikasi diubah")
        return body.model_dump()

    @api.get("/notifications")
    async def list_notifications(user=Depends(get_current_user)):
        return await db.notifications.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)

    @api.get("/notifications/unread-count")
    async def unread_count(user=Depends(get_current_user)):
        return {"count": await db.notifications.count_documents({"user_id": user["user_id"], "read": False})}

    @api.post("/notifications/read-all")
    async def read_all(user=Depends(get_current_user)):
        await db.notifications.update_many({"user_id": user["user_id"], "read": False}, {"$set": {"read": True}})
        return {"ok": True}

    @api.post("/notifications/{notif_id}/read")
    async def read_one(notif_id: str, user=Depends(get_current_user)):
        await db.notifications.update_one({"user_id": user["user_id"], "notif_id": notif_id}, {"$set": {"read": True}})
        return {"ok": True}

    return {"rate_limit": rate_limit, "log_activity": log_activity, "notify_user": notify_user,
            "broadcast_promo": broadcast_promo}
