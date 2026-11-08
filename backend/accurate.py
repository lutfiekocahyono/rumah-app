"""Accurate Online integration — Tahap 1: pengaturan kunci API, uji koneksi, pratinjau baca-saja.

Kunci API diisi pemilik di halaman Admin (bukan lewat chat) dan disimpan terenkripsi.
Tahap ini TIDAK PERNAH menulis ke Accurate: setiap endpoint save/delete ditolak oleh klien.
Arah sinkron yang direncanakan: Accurate -> PGS (produk, harga, stok per cabang/gudang),
PGS -> Accurate (pesanan online jadi faktur penjualan) — tahap berikutnya, dengan konfirmasi."""
import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

ACCOUNT_HOST = "https://account.accurate.id"
WIB = timezone(timedelta(hours=7))
KEY = {"key": "accurate"}


def _fernet() -> Fernet:
    return Fernet(os.environ["KEY_ENCRYPTION_SECRET"].encode())


def _hint(v: str) -> str:
    return f"••••{v[-4:]}" if v else ""


class AccurateClient:
    """Signed requests (Bearer API token + X-Api-Timestamp + HMAC-SHA256 signature). Read-only in phase 1."""

    def __init__(self, token: str, secret: str, host: Optional[str] = None, session: Optional[str] = None):
        self.token, self.secret, self.host, self.session = token, secret, host, session

    def headers(self) -> Dict[str, str]:
        ts = datetime.now(WIB).strftime("%d/%m/%Y %H:%M:%S")
        sig = base64.b64encode(hmac.new(self.secret.encode(), ts.encode(), hashlib.sha256).digest()).decode()
        h = {"Authorization": f"Bearer {self.token}", "X-Api-Timestamp": ts, "X-Api-Signature": sig}
        if self.session:
            h["X-Session-ID"] = self.session
        return h

    async def call(self, method: str, path: str, params: Optional[dict] = None) -> dict:
        if any(w in path for w in ("save.do", "delete.do", "bulk-save", "transfer")):
            raise HTTPException(status_code=403, detail="Tahap 1 hanya membaca data Accurate (tidak ada perubahan di Accurate)")
        base = ACCOUNT_HOST if path.startswith("/api/") else self.host
        if not base:
            raise HTTPException(status_code=400, detail="Jalankan Uji Koneksi dulu")
        async with httpx.AsyncClient(timeout=25, follow_redirects=False) as x:
            try:
                r = await x.request(method, base + path, headers=self.headers(), params=params)
                if r.status_code == 308 and method == "GET" and r.headers.get("location"):  # database moved host
                    self.host = r.headers["location"].split("/accurate")[0]
                    r = await x.request(method, self.host + path, headers=self.headers(), params=params)
            except httpx.HTTPError as e:
                raise HTTPException(status_code=502, detail=f"Tidak bisa menghubungi Accurate: {e.__class__.__name__}")
        if r.status_code in (401, 403):
            raise HTTPException(status_code=400, detail="Kunci API ditolak Accurate. Periksa API Token & Signature Secret, dan izin (scope) aplikasinya")
        try:
            data = r.json()
        except ValueError:
            raise HTTPException(status_code=502, detail=f"Respon Accurate tidak valid (HTTP {r.status_code})")
        if r.status_code >= 400 or data.get("s") is False:
            d = data.get("d")
            msg = "; ".join(d) if isinstance(d, list) else (d if isinstance(d, str) else data.get("error_description") or f"HTTP {r.status_code}")
            raise HTTPException(status_code=502, detail=f"Accurate: {msg}")
        return data


class SettingsIn(BaseModel):
    api_token: str = Field(default="", max_length=500)  # blank = keep the saved one
    signature_secret: str = Field(default="", max_length=500)
    database_id: str = Field(default="", max_length=40)


class WarehouseMapIn(BaseModel):
    warehouse_map: Dict[str, str] = {}  # PGS store_id -> nama gudang Accurate


def register(api, db, require_admin):

    async def load() -> dict:
        return await db.settings.find_one(KEY, {"_id": 0}) or {}

    async def client() -> AccurateClient:
        s = await load()
        if not s.get("api_token"):
            raise HTTPException(status_code=400, detail="Isi API Token & Signature Secret Accurate dulu")
        try:
            f = _fernet()
            return AccurateClient(f.decrypt(s["api_token"].encode()).decode(), f.decrypt(s["signature_secret"].encode()).decode(),
                                  s.get("host"), s.get("session"))
        except InvalidToken:
            raise HTTPException(status_code=400, detail="Kunci tersimpan tidak bisa dibaca, simpan ulang kuncinya")

    def public(s: dict) -> dict:
        return {"configured": bool(s.get("api_token")), "token_hint": s.get("token_hint", ""), "secret_hint": s.get("secret_hint", ""),
                "database_id": s.get("database_id", ""), "database_name": s.get("database_name", ""), "host": s.get("host", ""),
                "last_test_at": s.get("last_test_at"), "last_test_ok": s.get("last_test_ok"), "last_test_message": s.get("last_test_message", ""),
                "warehouse_map": s.get("warehouse_map", {}), "updated_at": s.get("updated_at"),
                "phase": 1, "write_enabled": False}

    @api.get("/admin/accurate/settings")
    async def get_settings(_=Depends(require_admin)):
        return public(await load())

    @api.put("/admin/accurate/settings")
    async def save_settings(body: SettingsIn, admin=Depends(require_admin)):
        s, f = await load(), _fernet()
        upd: dict = {"database_id": body.database_id.strip(), "updated_at": datetime.now(timezone.utc), "updated_by": admin["user_id"]}
        tok, sec = body.api_token.strip(), body.signature_secret.strip()
        if not s.get("api_token") and not (tok and sec):
            raise HTTPException(status_code=400, detail="API Token dan Signature Secret wajib diisi")
        if tok:
            upd |= {"api_token": f.encrypt(tok.encode()).decode(), "token_hint": _hint(tok)}
        if sec:
            upd |= {"signature_secret": f.encrypt(sec.encode()).decode(), "secret_hint": _hint(sec)}
        if tok or sec:  # new keys: the old host/session/test result no longer apply
            upd |= {"host": "", "session": "", "last_test_ok": None, "last_test_message": "", "database_name": ""}
        await db.settings.update_one(KEY, {"$set": upd}, upsert=True)
        return public(await load())

    @api.delete("/admin/accurate/settings")
    async def delete_settings(_=Depends(require_admin)):
        await db.settings.delete_one(KEY)
        return public({})

    @api.post("/admin/accurate/test")
    async def test_connection(_=Depends(require_admin)):
        c = await client()
        now = datetime.now(timezone.utc)
        try:
            data = await c.call("POST", "/api/api-token.do")
            d = data.get("d") or {}
            dbs = d.get("database") or d.get("data") or {}
            if isinstance(dbs, list):  # token linked to several databases: use the chosen one
                want = (await load()).get("database_id")
                dbs = next((x for x in dbs if str(x.get("id")) == want), dbs[0] if dbs else {})
            host = dbs.get("host") or d.get("host")
            if not host:
                raise HTTPException(status_code=502, detail="Accurate tidak mengirim alamat database. Pastikan token terhubung ke satu database")
            info = {"host": host.rstrip("/"), "session": d.get("session") or dbs.get("session") or "",
                    "database_name": dbs.get("alias") or dbs.get("name") or "", "last_test_at": now, "last_test_ok": True,
                    "last_test_message": f"Terhubung ke {dbs.get('alias') or dbs.get('name') or 'database Accurate'}"}
            if dbs.get("id") and not (await load()).get("database_id"):
                info["database_id"] = str(dbs["id"])
            await db.settings.update_one(KEY, {"$set": info})
        except HTTPException as e:
            await db.settings.update_one(KEY, {"$set": {"last_test_at": now, "last_test_ok": False, "last_test_message": e.detail}})
            raise
        return public(await load())

    @api.get("/admin/accurate/warehouses")
    async def warehouses(_=Depends(require_admin)):
        c = await client()
        data = await c.call("GET", "/accurate/api/warehouse/list.do", {"fields": "id,name,description,suspended", "sp.pageSize": 100})
        return {"items": [{"id": w.get("id"), "name": w.get("name", ""), "description": w.get("description") or "", "suspended": bool(w.get("suspended"))}
                          for w in data.get("d") or []]}

    @api.put("/admin/accurate/warehouse-map")
    async def save_map(body: WarehouseMapIn, _=Depends(require_admin)):
        stores = {s["store_id"] for s in await db.stores.find({"store_id": {"$in": list(body.warehouse_map)}}, {"store_id": 1}).to_list(100)}
        clean = {k: v.strip()[:100] for k, v in body.warehouse_map.items() if k in stores and v.strip()}
        await db.settings.update_one(KEY, {"$set": {"warehouse_map": clean}}, upsert=True)
        return public(await load())

    @api.get("/admin/accurate/items")
    async def items_preview(page: int = 1, warehouse: str = "", _=Depends(require_admin)):
        """Read-only preview of Accurate items with selling price (and stock of one warehouse if chosen)."""
        c = await client()
        params = {"fields": "id,no,name,unitPrice,unit1Name,availableToSell,itemType", "sp.page": max(1, page), "sp.pageSize": 25}
        if warehouse:
            params["warehouseName"] = warehouse
        data = await c.call("GET", "/accurate/api/item/list.do", params)
        sp = data.get("sp") or {}
        items = [{"id": i.get("id"), "no": i.get("no", ""), "name": i.get("name", ""), "price": i.get("unitPrice"), "unit": i.get("unit1Name", ""),
                  "stock": i.get("availableToSell"), "type": i.get("itemType", "")} for i in data.get("d") or []]
        nos = [i["no"] for i in items if i["no"]]
        linked = {p["sku"]: p["product_id"] for p in await db.products.find({"sku": {"$in": nos}}, {"sku": 1, "product_id": 1}).to_list(100)}
        for i in items:
            i["pgs_product_id"] = linked.get(i["no"])  # matched by Accurate item code = PGS SKU
        return {"items": items, "page": sp.get("page", page), "page_count": sp.get("pageCount", 1), "total": sp.get("rowCount", len(items))}
