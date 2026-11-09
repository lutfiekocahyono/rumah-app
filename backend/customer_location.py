"""Lokasi pelanggan (hanya dari yang mengizinkan) + Analisa Pelanggan untuk Super Admin.

Satu dokumen per pelanggan/tamu (posisi terakhir), plus riwayat ringkas (maks 1 titik per 30 menit, simpan 90 hari)."""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, Header, HTTPException
from pydantic import BaseModel, Field

STAFF = {"admin", "store_admin"}


class LocationIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    accuracy: Optional[float] = Field(default=None, ge=0, le=100000)
    platform: str = Field(default="", max_length=20)


def register(api, db, *, get_owner, require_admin):
    @api.post("/location")
    async def save_location(body: LocationIn, owner: str = Depends(get_owner), x_guest_id: Optional[str] = Header(default=None)):
        now = datetime.now(timezone.utc)
        doc = {"lat": body.lat, "lng": body.lng, "accuracy": body.accuracy, "platform": body.platform, "updated_at": now}
        if owner.startswith("user:"):
            u = await db.users.find_one({"user_id": owner[5:]}, {"_id": 0, "role": 1, "name": 1, "email": 1, "phone": 1, "customer_type": 1})
            if not u:
                raise HTTPException(status_code=401, detail="Sesi berakhir, silakan masuk lagi")
            if u.get("role") in STAFF:
                return {"saved": False}  # owner & branch staff are not customers
            doc.update(user_id=owner[5:], guest=False, name=u.get("name") or "", email=u.get("email") or "", phone=u.get("phone") or "",
                       customer_type=u.get("customer_type") or "langsung")
            if x_guest_id:  # same phone, now signed in: drop its guest point
                await db.customer_locations.delete_one({"owner": f"guest:{x_guest_id}"})
        else:
            doc.update(guest=True, name="Tamu", email="", phone="")
        prev = await db.customer_locations.find_one_and_update({"owner": owner}, {"$set": doc, "$setOnInsert": {"first_seen": now}, "$inc": {"pings": 1}},
                                                               upsert=True, projection={"history_at": 1})
        if not prev or not prev.get("history_at") or prev["history_at"] < now.replace(tzinfo=None) - timedelta(minutes=30):
            await db.location_history.insert_one({"owner": owner, "lat": body.lat, "lng": body.lng, "at": now})
            await db.customer_locations.update_one({"owner": owner}, {"$set": {"history_at": now}})
        return {"saved": True}

    @api.get("/admin/customer-locations")
    async def customer_locations(days: int = 0, guests: bool = True, _=Depends(require_admin)):
        q: dict = {}
        now = datetime.now(timezone.utc)
        if days > 0:
            q["updated_at"] = {"$gte": now - timedelta(days=days)}
        if not guests:
            q["guest"] = False
        rows = await db.customer_locations.find(q, {"_id": 0, "history_at": 0}).sort("updated_at", -1).to_list(20000)
        ids = [r["user_id"] for r in rows if r.get("user_id")]
        orders = {o["_id"]: o for o in await db.orders.aggregate([
            {"$match": {"user_id": {"$in": ids}, "status": {"$nin": ["cancelled", "expired", "failed"]}}},
            {"$group": {"_id": "$user_id", "n": {"$sum": 1}, "total": {"$sum": "$total"}}}]).to_list(20000)}
        for r in rows:
            o = orders.get(r.get("user_id"), {})
            r["orders"], r["spent"] = o.get("n", 0), o.get("total", 0)
            r["owner"] = r["owner"].split(":")[0] + ":" + r["owner"].split(":", 1)[1][-6:]  # do not expose full guest ids
        all_q = db.customer_locations
        stats = {
            "total": await all_q.count_documents({}),
            "customers": await all_q.count_documents({"guest": False}),
            "guests": await all_q.count_documents({"guest": True}),
            "active_24h": await all_q.count_documents({"updated_at": {"$gte": now - timedelta(hours=24)}}),
            "active_7d": await all_q.count_documents({"updated_at": {"$gte": now - timedelta(days=7)}}),
            "buyers": sum(1 for r in rows if r["orders"]),
        }
        return {"stats": stats, "items": rows}
