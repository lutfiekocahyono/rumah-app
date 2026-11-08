"""Riwayat perubahan harga & stok: who changed what, when, before -> after.

Super Admin sees every store; a store owner / branch admin only sees their own store (branch stock of the shared
catalogue is recorded under the branch that changed it)."""
import io
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

SOURCES = {"editor": "Ubah Produk", "bulk": "Edit Massal", "import": "Impor Excel", "stock": "Manajemen Stok", "tiers": "Harga Grosir Manual"}
LABELS = {"price": "Harga jual", "original_price": "Harga normal", "stock": "Stok", "tier_prices": "Harga grosir manual"}
KIND = {"price": "price", "original_price": "price", "tier_prices": "price", "stock": "stock"}


def snap(p: dict) -> dict:
    """The price/stock part of a product document."""
    return {"price": p.get("price", 0), "original_price": p.get("original_price") or p.get("price", 0), "stock": p.get("stock", 0),
            "tier_prices": p.get("tier_prices") or {},
            "variants": {v.get("variant_id"): {"name": v.get("name") or " / ".join(v.get("values", [])), "price": v.get("price", 0),
                                               "stock": v.get("stock", 0)} for v in p.get("variants") or []}}


TIER_LABEL = {"langsung": "Pembeli Langsung", "pengecer": "Pengecer", "reseller": "Reseller"}


def tiers_text(t: dict) -> str:
    parts = [f"{TIER_LABEL.get(k, k)}: " + ", ".join(f"{r['min_qty']}+ Rp{r['price']:,}".replace(",", ".") for r in rows)
             for k, rows in sorted((t or {}).items()) if rows]
    return "; ".join(parts) or "(kosong)"


def diff(before: dict, after: dict) -> list:
    out = []
    bv, av = before.get("variants") or {}, after.get("variants") or {}
    if not av:  # variant products: the per-variant rows say it all
        same_disc = before.get("price") == before.get("original_price") and after.get("price") == after.get("original_price")
        for f in ("original_price", "price", "stock"):
            if f == "original_price" and same_disc:  # no discount: one "Harga jual" row is enough
                continue
            if f in after and before.get(f) != after.get(f):
                out.append({"field": f, "label": LABELS[f], "kind": KIND[f], "variant": "", "before": before.get(f), "after": after[f]})
    for vid, a in av.items():
        b = bv.get(vid)
        for f in ("price", "stock"):
            if b is None or b[f] != a[f]:
                out.append({"field": f, "label": LABELS[f], "kind": KIND[f], "variant": a["name"], "before": b[f] if b else None, "after": a[f]})
    if "variants" in after:
        for vid, b in bv.items():
            if vid not in av:
                out.append({"field": "stock", "label": "Variasi dihapus", "kind": "stock", "variant": b["name"], "before": b["stock"], "after": None})
    if "tier_prices" in after and tiers_text(before.get("tier_prices")) != tiers_text(after["tier_prices"]):
        out.append({"field": "tier_prices", "label": LABELS["tier_prices"], "kind": "price", "variant": "",
                    "before": tiers_text(before.get("tier_prices")), "after": tiers_text(after["tier_prices"])})
    return out


async def record(db, user: dict, store_id: str, product: dict, before: dict, after: dict, source: str) -> None:
    changes = diff(before, after)
    if not changes:
        return
    await db.price_history.insert_one({
        "log_id": f"ph_{uuid.uuid4().hex[:12]}", "product_id": product["product_id"], "product_name": product.get("name", ""),
        "store_id": store_id, "user_id": user.get("user_id"), "user_name": user.get("name") or user.get("email", ""),
        "user_role": user.get("role", ""), "source": source, "changes": changes, "kinds": sorted({c["kind"] for c in changes}),
        "at": datetime.now(timezone.utc)})


def register(api, db, get_current_user):
    WIB = timezone(timedelta(hours=7))

    async def build_query(user: dict, store_id, product_id, q: str, kind: str, date_from: str, date_to: str) -> dict:
        query: dict = {}
        if user.get("role") == "admin":
            if store_id:
                query["store_id"] = store_id
        else:
            s = await db.stores.find_one({"owner_id": user["user_id"], "status": "active"}, {"store_id": 1})
            if not s:
                raise HTTPException(status_code=403, detail="Riwayat hanya untuk pemilik toko atau Super Admin")
            if store_id and store_id != s["store_id"]:
                raise HTTPException(status_code=403, detail="Anda hanya bisa melihat riwayat toko Anda sendiri")
            query["store_id"] = s["store_id"]
        if product_id:
            query["product_id"] = product_id
        if q.strip():
            query["product_name"] = {"$regex": re.escape(q.strip()), "$options": "i"}
        if kind in ("price", "stock"):
            query["kinds"] = kind
        rng = {}
        try:  # dates are WIB calendar days, inclusive
            if date_from:
                rng["$gte"] = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=WIB).astimezone(timezone.utc)
            if date_to:
                rng["$lt"] = (datetime.strptime(date_to, "%Y-%m-%d").replace(tzinfo=WIB) + timedelta(days=1)).astimezone(timezone.utc)
        except ValueError:
            raise HTTPException(status_code=400, detail="Format tanggal harus TTTT-BB-HH")
        if rng.get("$gte") and rng.get("$lt") and rng["$gte"] >= rng["$lt"]:
            raise HTTPException(status_code=400, detail="Tanggal awal harus sebelum tanggal akhir")
        if rng:
            query["at"] = rng
        return query

    async def decorate(docs: list) -> list:
        names = {s["store_id"]: s["name"] for s in await db.stores.find({"store_id": {"$in": list({d["store_id"] for d in docs})}},
                                                                         {"store_id": 1, "name": 1}).to_list(500)}
        for d in docs:
            d["store_name"] = names.get(d["store_id"], d["store_id"])
            d["source_label"] = SOURCES.get(d["source"], d["source"])
        return docs

    @api.get("/history/price-stock")
    async def price_stock_history(store_id: Optional[str] = None, product_id: Optional[str] = None, q: str = "", kind: str = "",
                                  date_from: str = "", date_to: str = "",
                                  skip: int = 0, limit: int = Query(default=30, le=100), user=Depends(get_current_user)):
        query = await build_query(user, store_id, product_id, q, kind, date_from, date_to)
        total = await db.price_history.count_documents(query)
        docs = await db.price_history.find(query, {"_id": 0}).sort("at", -1).skip(max(0, skip)).limit(limit).to_list(limit)
        return {"total": total, "items": await decorate(docs)}

    @api.get("/history/price-stock/export")
    async def export_history(store_id: Optional[str] = None, product_id: Optional[str] = None, q: str = "", kind: str = "",
                             date_from: str = "", date_to: str = "", user=Depends(get_current_user)):
        """Monthly report: one Excel row per change (before -> after, selisih), filtered like the list."""
        query = await build_query(user, store_id, product_id, q, kind, date_from, date_to)
        docs = await decorate(await db.price_history.find(query, {"_id": 0}).sort("at", 1).to_list(50000))
        data = await run_in_threadpool(build_history_xlsx, docs, date_from, date_to)
        scope = query.get("store_id") or "semua-toko"
        name = f"riwayat-harga-stok-{scope}-{date_from or 'awal'}-sd-{date_to or 'sekarang'}.xlsx"
        return Response(content=data, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{name}"'})

    def build_history_xlsx(docs: list, date_from: str, date_to: str) -> bytes:
        wb = Workbook()
        ws = wb.active
        ws.title = "Riwayat"
        cols = ["Tanggal", "Jam (WIB)", "Toko", "Produk", "ID Produk", "Variasi", "Perubahan", "Sebelum", "Sesudah", "Selisih", "Oleh", "Peran", "Sumber"]
        ws.append(cols)
        for c in ws[1]:
            c.font, c.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="F97316")
        ws.freeze_panes = "A2"
        roles = {"admin": "Super Admin", "seller": "Pemilik toko", "store_admin": "Admin cabang"}
        for d in docs:
            at = d["at"].replace(tzinfo=timezone.utc).astimezone(WIB) if d["at"].tzinfo is None else d["at"].astimezone(WIB)
            for c in d["changes"]:
                b, a = c.get("before"), c.get("after")
                delta = a - b if isinstance(a, (int, float)) and isinstance(b, (int, float)) else None
                ws.append([at.strftime("%Y-%m-%d"), at.strftime("%H:%M"), d["store_name"], d["product_name"], d["product_id"],
                           c.get("variant") or "", c["label"], b, a, delta, d.get("user_name", ""),
                           roles.get(d.get("user_role"), d.get("user_role", "")), d["source_label"]])
                if c["kind"] == "price":
                    for col in (8, 9, 10):
                        ws.cell(ws.max_row, col).number_format = '"Rp"#,##0;-"Rp"#,##0'
        for col, w in zip("ABCDEFGHIJKLM", (12, 10, 20, 40, 14, 16, 20, 14, 14, 12, 20, 14, 18)):
            ws.column_dimensions[col].width = w
        s = wb.create_sheet("Ringkasan")
        s.append(["Periode", f"{date_from or 'awal'} s/d {date_to or 'sekarang'}"])
        s.append(["Jumlah catatan", len(docs)])
        s.append(["Jumlah perubahan", sum(len(d["changes"]) for d in docs)])
        s.append(["Perubahan harga", sum(1 for d in docs for c in d["changes"] if c["kind"] == "price")])
        s.append(["Perubahan stok", sum(1 for d in docs for c in d["changes"] if c["kind"] == "stock")])
        s.append(["Produk berbeda", len({d["product_id"] for d in docs})])
        s.column_dimensions["A"].width, s.column_dimensions["B"].width = 22, 40
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()
