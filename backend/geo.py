"""Pencarian lokasi untuk pin peta (OpenStreetMap Nominatim, gratis tanpa kunci). Lewat server supaya
User-Agent sesuai kebijakan Nominatim dan hasil di-cache."""
import asyncio
import time

import httpx
from fastapi import Depends, HTTPException

NOMINATIM = "https://nominatim.openstreetmap.org"
HEADERS = {"User-Agent": "PusatGrosirSidoarjo/1.0 (marketplace app)", "Accept-Language": "id"}
_cache: dict = {}
_lock = asyncio.Lock()
_last = [0.0]


async def _get(path: str, params: dict):
    key = (path, tuple(sorted(params.items())))
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < 86400:
        return hit[1]
    async with _lock:  # Nominatim policy: at most 1 request per second from this server
        wait = 1.0 - (time.time() - _last[0])
        if wait > 0:
            await asyncio.sleep(wait)
        _last[0] = time.time()
        return await _fetch(key, path, params)


async def _fetch(key, path: str, params: dict):
    try:
        async with httpx.AsyncClient(timeout=10, headers=HEADERS) as c:
            r = await c.get(f"{NOMINATIM}{path}", params={**params, "format": "jsonv2"})
            r.raise_for_status()
            data = r.json()
    except Exception:
        raise HTTPException(status_code=502, detail="Layanan peta sedang sibuk, coba lagi")
    if len(_cache) > 2000:
        _cache.clear()
    _cache[key] = (time.time(), data)
    return data


def register(api, get_current_user):
    @api.get("/geo/search")
    async def geo_search(q: str, _user=Depends(get_current_user)):
        q = q.strip()[:120]
        if len(q) < 3:
            return []
        rows = await _get("/search", {"q": q, "countrycodes": "id", "limit": 6})
        return [{"label": r.get("display_name", ""), "lat": float(r["lat"]), "lng": float(r["lon"])} for r in rows]

    @api.get("/geo/reverse")
    async def geo_reverse(lat: float, lng: float, _user=Depends(get_current_user)):
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            raise HTTPException(status_code=400, detail="Koordinat tidak valid")
        r = await _get("/reverse", {"lat": round(lat, 5), "lon": round(lng, 5), "zoom": 18})
        return {"label": r.get("display_name", "") if isinstance(r, dict) else ""}
