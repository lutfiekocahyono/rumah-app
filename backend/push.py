"""Push notification HP lewat Emergent managed push (SuprSend relay).

Default NONAKTIF: tidak ada yang dikirim sampai Super Admin menyalakannya di Admin → Notifikasi Push, setelah aplikasi
dirilis & versi iOS/Android dibuat (kredensial Firebase / Apple diunggah saat build). Kegagalan push tidak pernah
mengganggu notifikasi lonceng/email."""
import logging
import os
from datetime import datetime, timezone

import httpx
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("push")

PUSH_BASE_URL = "https://integrations.emergentagent.com"
KEY = {"key": "push"}
_client: httpx.AsyncClient | None = None


def _http() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(base_url=PUSH_BASE_URL, headers={"X-Push-Key": os.environ.get("EMERGENT_PUSH_KEY", "placeholder")}, timeout=10.0)
    return _client


async def is_enabled(db) -> bool:
    return bool((await db.settings.find_one(KEY) or {}).get("enabled"))


async def send_push(recipients: list[str], data: dict, idempotency_key: str | None = None) -> str:
    """One relay call (max 100 recipients). Returns 'sent' or a short reason; never raises."""
    if not recipients:
        return "no-recipients"
    payload: dict = {"recipients": recipients[:100], "data": data}
    if idempotency_key:
        payload["$idempotency_key"] = idempotency_key
    try:
        resp = await _http().post("/api/v1/push/trigger", json=payload)
        code = resp.json().get("code", "") if resp.headers.get("content-type", "").startswith("application/json") else ""
        if resp.status_code == 401:
            return "key-invalid"
        if code in ("insufficient_credits", "integration_disabled", "daily_limit_reached"):
            logger.warning("Push paused: %s (%s)", code, resp.status_code)
            return code
        if code == "idempotency_key_in_progress":
            return "sent"
        if resp.status_code >= 400:
            logger.warning("Push failed %s %s", resp.status_code, resp.text[:200])
            return f"http-{resp.status_code}"
        return "sent"
    except Exception as e:  # network etc.
        logger.warning("Push error (non-blocking): %s", e)
        return "error"


async def broadcast(db, user_ids: list[str], title: str, message: str, action_url: str, ref: str) -> dict:
    """Send to many users in chunks of 100 when push is enabled. Result is stored for the admin page."""
    if not await is_enabled(db) or not user_ids:
        return {"enabled": False}
    out: dict = {}
    for i in range(0, len(user_ids), 100):
        r = await send_push(user_ids[i:i + 100], {"title": title[:100], "message": message[:300], "action_url": action_url}, f"{ref}-{i}")
        out[r] = out.get(r, 0) + len(user_ids[i:i + 100])
        if r in ("key-invalid", "insufficient_credits", "integration_disabled", "daily_limit_reached"):
            break
    await db.settings.update_one(KEY, {"$set": {"last_send": {"at": datetime.now(timezone.utc), "ref": ref, "title": title, "result": out}}}, upsert=True)
    return out


class RegisterPushIn(BaseModel):
    user_id: str
    platform: str = Field(pattern="^(android|ios)$")
    device_token: str = Field(min_length=10, max_length=4096)


class PushSettingsIn(BaseModel):
    enabled: bool


def register(api, db, get_current_user, require_admin):

    @api.get("/push/config")
    async def push_config():
        """The app only asks for notification permission when push is switched on."""
        return {"enabled": await is_enabled(db)}

    @api.post("/register-push", status_code=201)
    async def register_push(body: RegisterPushIn, user=Depends(get_current_user)):
        if body.user_id != user["user_id"]:
            raise HTTPException(status_code=403, detail="Token hanya bisa didaftarkan untuk akun sendiri")
        if not await is_enabled(db):
            return {"status": "disabled"}
        try:
            resp = await _http().post("/api/v1/push/users/register", json=body.model_dump())
        except Exception:
            raise HTTPException(status_code=502, detail="Layanan push tidak tersedia")
        if resp.status_code == 401:
            raise HTTPException(status_code=500, detail="Kunci push belum aktif (aktif otomatis setelah aplikasi dirilis)")
        if resp.status_code >= 500:
            raise HTTPException(status_code=502, detail="Layanan push tidak tersedia")
        if resp.status_code >= 400:
            raise HTTPException(status_code=400, detail="Token perangkat ditolak")
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"push_registered_at": datetime.now(timezone.utc), "push_platform": body.platform}})
        return {"status": "registered"}

    @api.get("/admin/push")
    async def push_status(_=Depends(require_admin)):
        s = await db.settings.find_one(KEY, {"_id": 0}) or {}
        return {"enabled": bool(s.get("enabled")), "key_ready": os.environ.get("EMERGENT_PUSH_KEY", "placeholder") not in ("", "placeholder"),
                "devices": await db.users.count_documents({"push_registered_at": {"$exists": True}}), "last_send": s.get("last_send"),
                "updated_at": s.get("updated_at")}

    @api.put("/admin/push")
    async def push_set(body: PushSettingsIn, admin=Depends(require_admin)):
        await db.settings.update_one(KEY, {"$set": {"enabled": body.enabled, "updated_at": datetime.now(timezone.utc), "updated_by": admin["user_id"]}}, upsert=True)
        return await push_status(admin)
