"""Automatic shipping cost (RajaOngkir / Komerce) for JNE, J&T, SiCepat with manual-tariff fallback.

The owner enters the API key in Admin > Pengaturan Ongkir; it is stored encrypted in MongoDB and never returned.
"""
import asyncio
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx
from cryptography.fernet import Fernet
from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field

log = logging.getLogger("shipping")
RO_BASE = "https://rajaongkir.komerce.id/api/v1"
AUTO_COURIERS = ("jne", "jnt", "sicepat")
_cache: Dict[tuple, tuple] = {}  # (origin, dest, weight, courier) -> (expires, result)
CACHE_TTL = 1800
RECHECK_SECONDS = 1800  # how long an invalid/limited key is skipped before re-checking


def _eta_id(etd) -> str:
    """RajaOngkir returns '2 day' / '3-5 day' / '1-2 HARI' — always show '2 hari'."""
    s = re.sub(r"(?i)\s*\b(days?|hari)\b\.?", "", str(etd or "")).strip()
    return f"{s} hari" if s else ""


def _fernet() -> Fernet:
    return Fernet(os.environ["KEY_ENCRYPTION_SECRET"].encode())


class OriginIn(BaseModel):
    id: int = Field(gt=0)
    label: str = Field(default="", max_length=200)


class ShippingSettingsIn(BaseModel):
    api_key: Optional[str] = Field(default=None, max_length=300)  # None = keep; "" = remove
    enabled: bool = True
    default_weight_grams: int = Field(default=1000, ge=1, le=100000)
    origins: Dict[str, OriginIn] = {}  # store_id -> origin location


class RatesIn(BaseModel):
    store_id: str
    destination_id: Optional[int] = None


def register(api, db, require_admin, get_owner, official_ids, couriers_of):

    async def settings() -> dict:
        return await db.settings.find_one({"key": "shipping_api"}, {"_id": 0}) or {}

    async def api_key() -> Optional[str]:
        s = await settings()
        if not s.get("enabled", True) or not s.get("api_key_enc"):
            return None
        try:
            return _fernet().decrypt(s["api_key_enc"].encode()).decode()
        except Exception:
            log.error("cannot decrypt shipping key")
            return None

    def _public(s: dict) -> dict:
        enc = s.get("api_key_enc")
        return {"configured": bool(enc), "key_hint": s.get("key_hint", ""), "enabled": s.get("enabled", True),
                "default_weight_grams": s.get("default_weight_grams", 1000), "origins": s.get("origins", {}),
                "key_status": s.get("key_status") if enc else None}

    def _classify(status: int, text: str) -> Optional[dict]:
        """Map a RajaOngkir error to a key status; None = not a key problem."""
        t = text.lower()
        if "api key" in t or "apikey" in t or status in (401, 403):
            return {"state": "invalid", "message": "Kunci ditolak RajaOngkir (tidak valid atau sudah dinonaktifkan)"}
        if status == 429 or re.search(r"quota|kuota|rate limit|limit exceeded|exceeded|too many", t):
            return {"state": "limited", "message": "Kunci valid, tetapi kuota/batas harian RajaOngkir habis"}
        return None

    async def _set_status(st: dict) -> dict:
        st = {**st, "checked_at": datetime.now(timezone.utc)}
        await db.settings.update_one({"key": "shipping_api"}, {"$set": {"key_status": st}})
        return st

    async def _verify(key: str) -> dict:
        """Cheap real call (1 destination search) to prove the key works."""
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(f"{RO_BASE}/destination/domestic-destination", params={"search": "sidoarjo", "limit": 1, "offset": 0}, headers={"key": key})
        except Exception:
            return await _set_status({"state": "unknown", "message": "Tidak bisa menghubungi RajaOngkir, coba lagi nanti"})
        if r.status_code < 400 or r.status_code == 404:
            return await _set_status({"state": "valid", "message": "Kunci valid dan terhubung ke RajaOngkir"})
        return await _set_status(_classify(r.status_code, r.text) or {"state": "unknown", "message": f"RajaOngkir error {r.status_code}, coba lagi nanti"})

    async def usable_key() -> Optional[str]:
        """Key for buyer-facing quotes. A key marked invalid/limited is skipped (manual tariff),
        but re-checked automatically every RECHECK_SECONDS so a reset quota / fixed key recovers alone."""
        key = await api_key()
        if not key:
            return None
        st = (await settings()).get("key_status") or {}
        if st.get("state") in ("invalid", "limited"):
            at = st.get("checked_at")
            at = at.replace(tzinfo=timezone.utc) if at and at.tzinfo is None else at
            if at and (datetime.now(timezone.utc) - at).total_seconds() < RECHECK_SECONDS:
                return None
            if (await _verify(key))["state"] in ("invalid", "limited"):
                return None
        return key

    @api.post("/admin/shipping/verify-key")
    async def verify_key(_=Depends(require_admin)):
        key = await api_key()
        if not key:
            raise HTTPException(status_code=400, detail="Isi API key ongkir dulu")
        await _verify(key)
        return _public(await settings())

    @api.get("/admin/shipping-settings")
    async def get_shipping_settings(_=Depends(require_admin)):
        return _public(await settings())

    @api.put("/admin/shipping-settings")
    async def put_shipping_settings(body: ShippingSettingsIn, _=Depends(require_admin)):
        upd: dict = {"key": "shipping_api", "enabled": body.enabled, "default_weight_grams": body.default_weight_grams,
                     "origins": {k: v.model_dump() for k, v in body.origins.items() if k in official_ids}}
        if body.api_key is not None:
            k = body.api_key.strip()
            upd["api_key_enc"] = _fernet().encrypt(k.encode()).decode() if k else None
            upd["key_hint"] = f"••••{k[-4:]}" if k else ""
        await db.settings.update_one({"key": "shipping_api"}, {"$set": upd}, upsert=True)
        _cache.clear()
        if body.api_key is not None:
            if body.api_key.strip():
                await _verify(body.api_key.strip())  # check the new key right away
            else:
                await db.settings.update_one({"key": "shipping_api"}, {"$unset": {"key_status": ""}})
        return _public(await settings())

    async def _search(q: str, key: str) -> list:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{RO_BASE}/destination/domestic-destination", params={"search": q, "limit": 10, "offset": 0}, headers={"key": key})
        if r.status_code == 404:
            return []
        if r.status_code >= 400:
            log.warning("RajaOngkir search %s: %s", r.status_code, r.text[:200])
            if st := _classify(r.status_code, r.text):
                await _set_status(st)
            raise HTTPException(status_code=424, detail="Pencarian lokasi gagal, periksa API key ongkir")
        return [{"id": d.get("id"), "label": d.get("label") or ", ".join(
            str(d.get(k)) for k in ("subdistrict_name", "district_name", "city_name", "province_name") if d.get(k))}
            for d in (r.json().get("data") or [])]

    @api.get("/shipping/status")
    async def shipping_status():
        return {"auto": bool(await usable_key())}

    @api.get("/shipping/destinations")
    async def destinations(q: str = Query(min_length=3, max_length=80), _owner=Depends(get_owner)):
        key = await usable_key()
        if not key:
            return {"auto": False, "data": []}
        return {"auto": True, "data": await _search(q.strip(), key)}

    @api.get("/admin/shipping/destinations")
    async def admin_destinations(q: str = Query(min_length=3, max_length=80), _=Depends(require_admin)):
        key = await api_key()
        if not key:
            raise HTTPException(status_code=400, detail="Isi API key ongkir dulu")
        return await _search(q.strip(), key)

    async def _one(client, key, origin, dest, weight, courier) -> Optional[dict]:
        ck = (origin, dest, weight, courier)
        hit = _cache.get(ck)
        if hit and hit[0] > time.time():
            return hit[1]
        try:
            r = await client.post(f"{RO_BASE}/calculate/domestic-cost", headers={"key": key},
                                  data={"origin": str(origin), "destination": str(dest), "weight": str(weight), "courier": courier, "price": "lowest"})
            if r.status_code >= 400 and r.status_code != 404:
                log.warning("RajaOngkir cost %s: %s", r.status_code, r.text[:200])
                if st := _classify(r.status_code, r.text):
                    await _set_status(st)
                return "error"  # API problem -> caller falls back to manual tariff
            services = (r.json().get("data") or []) if r.status_code < 400 else []
        except Exception:
            log.exception("RajaOngkir cost failed")
            return "error"
        best = min((s for s in services if s.get("cost")), key=lambda s: s["cost"], default=None)
        res = {"cost": int(best["cost"]), "eta": _eta_id(best.get("etd")), "service": str(best.get("service") or "")} if best else None
        _cache[ck] = (time.time() + CACHE_TTL, res)
        return res

    async def cart_rules(items: List[dict]) -> tuple:
        """Billable weight (grams; volumetric L×W×H/6000 kg when bigger) and the courier rules of the products."""
        s = await settings()
        default_w = int(s.get("default_weight_grams", 1000))
        ids = [i["product_id"] for i in items]
        prods = {p["product_id"]: p for p in await db.products.find({"product_id": {"$in": ids}}, {
            "_id": 0, "product_id": 1, "weight_grams": 1, "length_cm": 1, "width_cm": 1, "height_cm": 1,
            "couriers": 1, "ship_regular": 1, "ship_cargo": 1}).to_list(len(ids) or 1)}
        weight, allowed, regular, cargo = 0, None, True, bool(items)
        for i in items:
            p = prods.get(i["product_id"], {})
            vol = (p.get("length_cm") or 0) * (p.get("width_cm") or 0) * (p.get("height_cm") or 0) / 6  # cm³/6000 kg -> grams
            weight += max(int(p.get("weight_grams") or default_w), int(vol)) * max(1, i["quantity"])
            if p.get("couriers"):
                allowed = set(p["couriers"]) if allowed is None else allowed & set(p["couriers"])
            regular = regular and p.get("ship_regular", True)
            cargo = cargo and p.get("ship_cargo", False)
        return max(1, weight), allowed, regular, cargo

    async def quote(store: dict, destination_id: Optional[int], items: List[dict]) -> List[dict]:
        """Courier options for a store and these cart items. JNE/J&T/SiCepat use the API when key + origin + destination exist.
        Products can limit couriers; cargo couriers only when every product allows cargo."""
        weight, allowed, regular, cargo = await cart_rules(items)

        def ok(c: dict) -> bool:
            if c["code"] == "pickup":
                return True
            if allowed is not None and c["code"] not in allowed:
                return False
            return cargo if is_cargo(c) else regular
        manual = [dict(c, source="manual") for c in couriers_of(store) if c.get("active", True) and ok(c)]
        s = await settings()
        key = await usable_key()
        origin = (s.get("origins") or {}).get(store["store_id"], {}).get("id")
        if not (key and origin and destination_id):
            return manual
        auto_codes = [c["code"] for c in manual if c["code"] in AUTO_COURIERS]
        async with httpx.AsyncClient(timeout=12) as client:
            results = await asyncio.gather(*[_one(client, key, origin, destination_id, weight, code) for code in auto_codes])
        live = dict(zip(auto_codes, results))
        out = []
        for c in manual:
            if c["code"] in live and live[c["code"]] != "error":
                if live[c["code"]]:
                    r = live[c["code"]]
                    out.append({**c, "cost": r["cost"], "eta": r["eta"] or c.get("eta", ""),
                                "name": f"{c['name'].split(' ')[0]} {r['service']}".strip() if r["service"] else c["name"], "source": "auto"})
                # courier not serving this route -> hidden
            else:
                out.append(c)
        return out

    @api.post("/shipping/rates")
    async def rates(body: RatesIn, owner: str = Depends(get_owner)):
        store = await db.stores.find_one({"store_id": body.store_id, "status": "active"})
        if not store:
            raise HTTPException(status_code=404, detail="Toko tidak ditemukan")
        cart = await db.carts.find_one({"owner": owner}) or {}
        items = [i for i in cart.get("items", []) if i.get("store_id", "pgs-official") == body.store_id]
        return await quote(store, body.destination_id, items)

    async def origin_label(store_id: str) -> Optional[str]:
        return ((await settings()).get("origins") or {}).get(store_id, {}).get("label")

    return quote, origin_label


def is_cargo(c: dict) -> bool:
    """Cargo couriers are recognised by name/code (e.g. 'JNE Trucking (JTR)', 'Indah Cargo', 'Kargo')."""
    t = f"{c.get('code', '')} {c.get('name', '')}".lower()
    return any(w in t for w in ("cargo", "kargo", "trucking", "jtr"))
