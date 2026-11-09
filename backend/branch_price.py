"""Harga cabang per produk (Mitra PGS Jombang / Jember): harga satuan, harga normal, dan tingkat grosir milik cabang sendiri.

Admin cabang hanya mengubah tokonya sendiri, Super Admin semua cabang. Harga PGS Sidoarjo & cabang lain tidak tersentuh.
Setiap perubahan tercatat di Riwayat Harga & Stok (sumber "Harga Cabang")."""
import asyncio
import io
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Literal, Optional

from fastapi import Depends, File, HTTPException, Response, UploadFile
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from pydantic import BaseModel, Field
from pymongo import UpdateOne

import history
from pricing import CUSTOMER_TYPES, MAX_TIERS, clean_tiers

SOURCE = "branch_price"
BULK_SOURCE = "branch_bulk"
history.SOURCES[SOURCE] = "Harga Cabang"
history.SOURCES[BULK_SOURCE] = "Edit Massal Cabang"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
COLS = ["ID Produk", "Nama Produk", "Harga Sidoarjo (info)", "Harga Cabang", "Harga Coret Cabang",
        "Grosir Pembeli Langsung", "Grosir Pengecer", "Grosir Reseller"]


def adjust_fn(mode: str, value: float):
    """pct: rounded up to Rp100 with integer math (same as Salin ke Cabang); rp: plus/minus rupiah. Never below Rp100 / Rp1."""
    if mode == "pct":
        bp = 10000 + round(value * 100)
        return lambda v: max(100, -(-int(v) * bp // 1_000_000) * 100) if v else 0
    return lambda v: max(1, int(v + value)) if v else 0


def adjust_tiers(tiers: dict, mode: str, value: float, unit: int) -> dict:
    """Grosir rows follow the same change; if rounding to Rp100 would wipe out the grosir discount, round to the rupiah instead."""
    f = adjust_fn(mode, value)
    exact = (lambda v: max(1, -(-int(v) * (10000 + round(value * 100)) // 10000))) if mode == "pct" else f
    out = {}
    for k, rows in (tiers or {}).items():
        out[k] = []
        for x in rows:
            p = f(x["price"])
            if x["min_qty"] > 1 and p >= unit:
                p = min(exact(x["price"]), unit)
            out[k].append({**x, "price": p})
    return out


def tier_text(rows) -> str:
    return "; ".join(f"{r['min_qty']}:{r['price']}" for r in rows or [])


def to_int(v) -> int:
    if v in (None, ""):
        return 0
    try:
        return int(round(float(str(v).replace("Rp", "").replace(".", "").replace(",", ".").strip()))) if isinstance(v, str) else int(round(float(v)))
    except ValueError:
        raise ValueError(f"Angka tidak valid: {v}")


def parse_tiers(v) -> list:
    """'6:20130; 12:19760' -> rows. Empty = no tiers."""
    out = []
    for part in str(v or "").replace(",", ";").split(";"):
        if not part.strip():
            continue
        if ":" not in part:
            raise ValueError(f"Format grosir salah '{part.strip()}', contoh 6:20130; 12:19760")
        q, p = part.split(":", 1)
        out.append({"min_qty": to_int(q), "price": to_int(p)})
    return out


class BulkIn(BaseModel):
    store_id: Optional[str] = None
    mode: Literal["pct", "rp"] = "pct"
    value: float
    tiers: bool = True
    q: str = ""
    product_ids: List[str] = Field(default=[], max_length=10000)


class ApplyIn(BaseModel):
    confirm_down: bool = False  # extra confirmation when branch prices would go DOWN


class TierIn(BaseModel):
    min_qty: int = Field(ge=1, le=99999)
    price: int = Field(ge=1, le=1_000_000_000)


class BranchPriceIn(BaseModel):
    store_id: Optional[str] = None
    price: int = Field(ge=1, le=1_000_000_000)
    original_price: Optional[int] = Field(default=None, ge=0, le=1_000_000_000)
    tier_prices: Dict[str, List[TierIn]] = {}


def register(api, db, get_current_user, seller):
    branches = [s for s in seller.OFFICIAL_IDS if s != seller.PGS_STORE_ID]

    async def branch_for(user: dict, store_id: Optional[str]) -> str:
        if user.get("role") == "admin":
            sid = store_id or branches[0]
            if sid not in branches:
                raise HTTPException(status_code=400, detail="Harga cabang hanya untuk Mitra PGS Jombang / Jember")
            return sid
        s = await db.stores.find_one({"owner_id": user["user_id"], "status": "active"}, {"store_id": 1})
        if not s or s["store_id"] not in branches:
            raise HTTPException(status_code=403, detail="Harga cabang hanya bisa diubah admin cabang mitra atau Super Admin")
        if store_id and store_id != s["store_id"]:
            raise HTTPException(status_code=403, detail="Anda hanya bisa mengubah harga toko Anda sendiri")
        return s["store_id"]

    def view(p: dict, row: Optional[dict]) -> dict:
        own = bool(row and row.get("price"))
        b = row if own else p
        return {"product_id": p["product_id"], "name": p.get("name", ""), "image": p.get("image", ""),
                "sidoarjo": {"price": p.get("price", 0), "original_price": p.get("original_price") or p.get("price", 0), "tier_prices": p.get("tier_prices") or {}},
                "branch": {"price": b.get("price", 0), "original_price": b.get("original_price") or b.get("price", 0), "tier_prices": b.get("tier_prices") or {}},
                "own_price": own, "stock": (row or {}).get("stock", 0), "price_set_at": (row or {}).get("price_set_at")}

    @api.get("/branch-prices")
    async def list_branch_prices(store_id: Optional[str] = None, q: str = "", skip: int = 0, limit: int = 40, user=Depends(get_current_user)):
        sid = await branch_for(user, store_id)
        query: dict = {"store_id": seller.PGS_STORE_ID, "variants.0": {"$exists": False}, "only_branch": None}
        if q.strip():
            query["$or"] = [{"name": {"$regex": re.escape(q.strip()), "$options": "i"}}, {"product_id": q.strip()}]
        docs = await db.products.find(query, {"_id": 0, "product_id": 1, "name": 1, "image": 1, "price": 1, "original_price": 1, "tier_prices": 1}) \
            .sort("name", 1).skip(max(0, skip)).limit(min(max(1, limit), 100)).to_list(100)
        rows = {r["product_id"]: r for r in await db.store_stock.find({"store_id": sid, "product_id": {"$in": [d["product_id"] for d in docs]}}, {"_id": 0}).to_list(100)}
        names = await seller.store_names(db)
        return {"store_id": sid, "store_name": names.get(sid, sid), "items": [view(d, rows.get(d["product_id"])) for d in docs]}

    @api.put("/branch-prices/{product_id}")
    async def set_branch_price(product_id: str, body: BranchPriceIn, user=Depends(get_current_user)):
        sid = await branch_for(user, body.store_id)
        p = await db.products.find_one({"product_id": product_id, "store_id": seller.PGS_STORE_ID, "only_branch": None}, {"_id": 0})
        if not p:
            raise HTTPException(status_code=404, detail="Produk tidak ditemukan di katalog PGS")
        if p.get("variants"):
            raise HTTPException(status_code=400, detail="Produk bervariasi belum bisa diberi harga cabang")
        unknown = set(body.tier_prices) - set(CUSTOMER_TYPES)
        if unknown:
            raise HTTPException(status_code=400, detail=f"Jenis pembeli tidak dikenal: {', '.join(sorted(unknown))}")
        if any(len(v) > MAX_TIERS for v in body.tier_prices.values()):
            raise HTTPException(status_code=400, detail=f"Maksimal {MAX_TIERS} tingkat grosir per jenis pembeli")
        for t, rows in body.tier_prices.items():
            qs = [r.min_qty for r in rows]
            if len(set(qs)) != len(qs):
                raise HTTPException(status_code=400, detail="Jumlah minimal grosir tidak boleh dobel")
        tiers = clean_tiers({k: [r.model_dump() for r in v] for k, v in body.tier_prices.items()})
        orig = max(body.price, body.original_price or body.price)
        row = await db.store_stock.find_one({"store_id": sid, "product_id": product_id}, {"_id": 0}) or {}
        own = bool(row.get("price"))
        before = {"price": row["price"] if own else p.get("price", 0),
                  "original_price": (row.get("original_price") if own else p.get("original_price")) or (row["price"] if own else p.get("price", 0)),
                  "tier_prices": (row.get("tier_prices") if own else p.get("tier_prices")) or {}}
        after = {"price": body.price, "original_price": orig, "tier_prices": tiers}
        await db.store_stock.update_one({"store_id": sid, "product_id": product_id},
                                        {"$set": {**after, "price_set_at": datetime.now(timezone.utc), "manual_price_at": datetime.now(timezone.utc)}, "$setOnInsert": {"stock": 0}}, upsert=True)
        await history.record(db, user, sid, p, before, after, SOURCE)
        new = await db.store_stock.find_one({"store_id": sid, "product_id": product_id}, {"_id": 0})
        return view(p, new)

    # ---------------- Edit Massal Cabang: persen / rupiah / Excel, pratinjau -> konfirmasi ----------------
    def current(p: dict, row: Optional[dict]) -> dict:
        v = view(p, row)["branch"]
        return {"price": v["price"], "original_price": v["original_price"], "tier_prices": v["tier_prices"]}

    async def save_preview(user: dict, sid: str, items: list, errors: list, label: str) -> dict:
        doc = {"preview_id": f"bp_{uuid.uuid4().hex[:10]}", "store_id": sid, "by": user["user_id"], "items": items, "label": label,
               "created_at": datetime.now(timezone.utc), "status": "preview"}
        await db.branch_price_previews.insert_one({**doc})
        up = sum(1 for i in items if i["after"]["price"] > i["before"]["price"])
        downs = [i for i in items if i["after"]["price"] < i["before"]["price"]]
        return {"preview_id": doc["preview_id"], "store_id": sid, "changed": len(items), "up": up, "down": len(downs),
                "down_sample": [{"product_id": i["product_id"], "name": i["name"], "old_price": i["before"]["price"], "new_price": i["after"]["price"]} for i in downs[:10]],
                "errors": errors[:50], "error_count": len(errors), "sample": [{k: i[k] for k in ("product_id", "name", "before", "after")} for i in items[:30]]}

    async def scope_products(q: str, ids: List[str]) -> list:
        query: dict = {"store_id": seller.PGS_STORE_ID, "variants.0": {"$exists": False}, "only_branch": None}
        if ids:
            query["product_id"] = {"$in": ids}
        if q.strip():
            query["name"] = {"$regex": re.escape(q.strip()), "$options": "i"}
        return await db.products.find(query, {"_id": 0, "product_id": 1, "name": 1, "price": 1, "original_price": 1, "tier_prices": 1}).to_list(50000)

    @api.post("/branch-prices/bulk/preview")
    async def bulk_preview(body: BulkIn, user=Depends(get_current_user)):
        sid = await branch_for(user, body.store_id)
        if body.mode == "pct" and not -90 <= body.value <= 100:
            raise HTTPException(status_code=400, detail="Persen harus antara -90 dan 100")
        if body.mode == "rp" and not -100_000_000 <= body.value <= 100_000_000:
            raise HTTPException(status_code=400, detail="Selisih rupiah terlalu besar")
        if body.value == 0:
            raise HTTPException(status_code=400, detail="Isi besar kenaikan / penurunan")
        prods = await scope_products(body.q, body.product_ids)
        rows = {r["product_id"]: r for r in await db.store_stock.find({"store_id": sid, "product_id": {"$in": [p["product_id"] for p in prods]}}, {"_id": 0}).to_list(50000)}
        f = adjust_fn(body.mode, body.value)
        items, errors = [], []
        for p in prods:
            b = current(p, rows.get(p["product_id"]))
            if body.mode == "rp" and body.value < 0 and min([b["price"], *([x["price"] for v in b["tier_prices"].values() for x in v] if body.tiers else [])]) + body.value <= 0:
                errors.append({"row": 0, "product_id": p["product_id"], "reason": f"{p.get('name', '')}: harga{' atau grosirnya' if body.tiers else ''} akan jadi 0 / minus, dilewati"})
                continue
            price = f(b["price"])
            a = {"price": price, "original_price": max(price, f(b["original_price"])),
                 "tier_prices": adjust_tiers(b["tier_prices"], body.mode, body.value, price) if body.tiers else b["tier_prices"]}
            if a != b:
                items.append({"product_id": p["product_id"], "name": p.get("name", ""), "before": b, "after": a})
        how = f"{'+' if body.value >= 0 else ''}{body.value:g}{'%' if body.mode == 'pct' else ' Rp'}"
        return await save_preview(user, sid, items, errors, f"Edit massal {how}")

    @api.get("/branch-prices/export")
    async def bulk_export(store_id: Optional[str] = None, user=Depends(get_current_user)):
        sid = await branch_for(user, store_id)
        prods = await scope_products("", [])
        rows = {r["product_id"]: r for r in await db.store_stock.find({"store_id": sid}, {"_id": 0}).to_list(50000)}
        wb = Workbook()
        ws = wb.active
        ws.title = "Harga Cabang"
        ws.append(COLS)
        for c in ws[1]:
            c.font = Font(bold=True)
        for p in sorted(prods, key=lambda x: x.get("name", "")):
            b = current(p, rows.get(p["product_id"]))
            ws.append([p["product_id"], p.get("name", ""), p.get("price", 0), b["price"], b["original_price"] if b["original_price"] > b["price"] else None,
                       *[tier_text(b["tier_prices"].get(t)) for t in CUSTOMER_TYPES]])
        for col, w in zip("ABCDEFGH", (14, 50, 14, 14, 16, 26, 26, 26)):
            ws.column_dimensions[col].width = w
        buf = io.BytesIO()
        wb.save(buf)
        names = await seller.store_names(db)
        return Response(content=buf.getvalue(), media_type=XLSX,
                        headers={"Content-Disposition": f'attachment; filename="harga-{names.get(sid, sid).lower().replace(" ", "-")}.xlsx"'})

    @api.post("/branch-prices/import")
    async def bulk_import(file: UploadFile = File(...), store_id: Optional[str] = None, user=Depends(get_current_user)):
        sid = await branch_for(user, store_id)
        data = await file.read()
        if len(data) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File terlalu besar (maks 10 MB)")
        try:
            ws = load_workbook(io.BytesIO(data), read_only=True, data_only=True).active
            raw = list(ws.iter_rows(values_only=True))
        except Exception:
            raise HTTPException(status_code=400, detail="File bukan Excel (.xlsx) yang valid. Pakai file dari tombol Unduh Excel")
        if not raw or [str(c or "").strip() for c in raw[0][:len(COLS)]] != COLS:
            raise HTTPException(status_code=400, detail="Kolom tidak sesuai. Unduh Excel harga cabang dulu, ubah, lalu unggah kembali")
        ids = [str(r[0]).strip() for r in raw[1:] if r and r[0]]
        prods = {p["product_id"]: p for p in await scope_products("", ids)}
        rows = {r["product_id"]: r for r in await db.store_stock.find({"store_id": sid, "product_id": {"$in": ids}}, {"_id": 0}).to_list(50000)}
        items, errors = [], []
        for n, r in enumerate(raw[1:], start=2):
            if not r or not r[0]:
                continue
            pid = str(r[0]).strip()
            p = prods.get(pid)
            if not p:
                errors.append({"row": n, "product_id": pid, "reason": "Produk tidak ditemukan / bervariasi"})
                continue
            try:
                price = to_int(r[3])
                orig = to_int(r[4]) if len(r) > 4 and r[4] not in (None, "") else price
                tiers = clean_tiers({t: parse_tiers(r[5 + i] if len(r) > 5 + i else None) for i, t in enumerate(CUSTOMER_TYPES)})
            except ValueError as e:
                errors.append({"row": n, "product_id": pid, "reason": str(e)})
                continue
            if price <= 0:
                errors.append({"row": n, "product_id": pid, "reason": "Harga cabang kosong / 0"})
                continue
            b = current(p, rows.get(pid))
            a = {"price": price, "original_price": max(price, orig), "tier_prices": tiers}
            if a != b:
                items.append({"product_id": pid, "name": p.get("name", ""), "before": b, "after": a})
        return await save_preview(user, sid, items, errors, "Impor Excel harga cabang")

    @api.post("/branch-prices/bulk/{preview_id}/apply")
    async def bulk_apply(preview_id: str, body: Optional[ApplyIn] = None, user=Depends(get_current_user)):
        pre = await db.branch_price_previews.find_one({"preview_id": preview_id}, {"store_id": 1, "by": 1, "items.before.price": 1, "items.after.price": 1})
        if not pre:
            raise HTTPException(status_code=400, detail="Pratinjau tidak ditemukan. Buat pratinjau baru")
        await branch_for(user, pre["store_id"])
        down = sum(1 for i in pre.get("items", []) if i["after"]["price"] < i["before"]["price"])
        if down and not (body and body.confirm_down):
            raise HTTPException(status_code=409, detail=f"{down} harga cabang akan TURUN. Centang konfirmasi harga turun lalu simpan lagi")
        d = await db.branch_price_previews.find_one_and_update(
            {"preview_id": preview_id, "status": "preview", "created_at": {"$gte": datetime.now(timezone.utc) - timedelta(hours=2)}},
            {"$set": {"status": "applied"}}, projection={"_id": 0})
        if not d:
            raise HTTPException(status_code=400, detail="Pratinjau sudah dipakai atau kedaluwarsa. Buat pratinjau baru")
        now = datetime.now(timezone.utc)
        for i in range(0, len(d["items"]), 1000):
            chunk = d["items"][i:i + 1000]
            await db.store_stock.bulk_write([UpdateOne({"store_id": d["store_id"], "product_id": x["product_id"]},
                                                       {"$set": {**x["after"], "price_set_at": now, "manual_price_at": now}, "$setOnInsert": {"stock": 0}}, upsert=True)
                                             for x in chunk], ordered=False)
        logs, notify = [], []
        for x in d["items"]:
            changes = history.diff(x["before"], x["after"])
            if changes:
                logs.append({"log_id": f"ph_{uuid.uuid4().hex[:12]}", "product_id": x["product_id"], "product_name": x["name"], "store_id": d["store_id"],
                             "user_id": user.get("user_id"), "user_name": user.get("name") or user.get("email", ""), "user_role": user.get("role", ""),
                             "source": BULK_SOURCE, "changes": changes, "kinds": sorted({c["kind"] for c in changes}), "at": now})
                notify.append((x, changes))
        for i in range(0, len(logs), 1000):
            await db.price_history.insert_many(logs[i:i + 1000])

        async def tell_buyers():  # hourly digest per buyer; done after the response so big edits don't time out
            import product_notify
            for x, changes in notify:
                p = await db.products.find_one({"product_id": x["product_id"]}, {"_id": 0})
                if p:
                    await product_notify.on_history(db, p, changes, d["store_id"])
        asyncio.create_task(tell_buyers())
        return {"saved": len(d["items"])}
