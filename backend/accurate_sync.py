"""Accurate Online Tahap 2.

A. Tarik dari Accurate -> PGS: harga jual (katalog bersama) & stok per cabang (gudang yang dipetakan), plus barang baru
   (dibuat nonaktif). Selalu lewat pratinjau; tidak ada yang tersimpan sebelum pemilik menekan Terapkan.
B. Kirim pesanan online -> Accurate sebagai faktur penjualan, satu per satu, hanya setelah pemilik konfirmasi.
   Nomor faktur = nomor pesanan PGS, jadi pesanan yang sama tidak bisa masuk dua kali."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

import history
import seller
from accurate import INVOICE_SAVE, KEY, load_settings, make_client

WIB = timezone(timedelta(hours=7))
PAGE_SIZE = 100
MAX_PAGES = 150  # 15.000 barang
INVOICE_OK = ("paid", "processing", "shipped", "completed")  # COD masuk setelah selesai (uang diterima)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def change_key(c: dict) -> str:
    return f"{c['product_id']}:{c['field']}:{c.get('store_id') or ''}"


class PreviewIn(BaseModel):
    prices: bool = True
    stocks: bool = True
    new_products: bool = False


class ApplyIn(BaseModel):
    skip: List[str] = []  # change keys the owner unticked
    skip_new: List[str] = []  # Accurate item codes not to create


class InvoiceSettingsIn(BaseModel):
    customer_no: str = Field(min_length=1, max_length=60)
    shipping_item_no: str = Field(default="", max_length=60)


class SendIn(BaseModel):
    confirm: bool


def register(api, db, require_admin):

    async def fetch_items(c, warehouse: str = "") -> List[dict]:
        out: List[dict] = []
        for page in range(1, MAX_PAGES + 1):
            params = {"fields": "id,no,name,unitPrice,availableToSell,itemType,unit1Name", "sp.page": page, "sp.pageSize": PAGE_SIZE}
            if warehouse:
                params["warehouseName"] = warehouse
            data = await c.call("GET", "/accurate/api/item/list.do", params)
            out += [i for i in data.get("d") or [] if i.get("no")]
            if page >= int((data.get("sp") or {}).get("pageCount") or 1):
                break
        return out

    # ============================================================ A. tarik dari Accurate
    @api.post("/admin/accurate/sync/preview")
    async def sync_preview(body: PreviewIn, admin=Depends(require_admin)):
        s = await load_settings(db)
        if not s.get("last_test_ok"):
            raise HTTPException(status_code=400, detail="Jalankan Uji Koneksi dulu")
        wmap = s.get("warehouse_map") or {}
        if body.stocks and not wmap:
            raise HTTPException(status_code=400, detail="Petakan cabang ke gudang Accurate dulu untuk mengambil stok")
        c = await make_client(db)
        items = await fetch_items(c)
        by_no = {i["no"]: i for i in items}
        products = await db.products.find({"store_id": seller.PGS_STORE_ID, "sku": {"$in": list(by_no)}},
                                          {"_id": 0, "product_id": 1, "name": 1, "sku": 1, "price": 1, "stock": 1, "variants": 1}).to_list(len(by_no) + 10)
        matched = {p["sku"]: p for p in products}
        changes, skipped = [], []
        for p in products:
            if p.get("variants"):
                skipped.append({"sku": p["sku"], "name": p["name"], "reason": "Punya variasi, atur lewat Ubah Produk"})
        plain = [p for p in products if not p.get("variants")]
        if body.prices:
            for p in plain:
                price = by_no[p["sku"]].get("unitPrice")
                if price is not None and int(round(price)) > 0 and int(round(price)) != p.get("price", 0):
                    changes.append({"product_id": p["product_id"], "name": p["name"], "sku": p["sku"], "field": "price",
                                    "store_id": "", "before": p.get("price", 0), "after": int(round(price))})
        if body.stocks:
            names = await seller.store_names(db)
            for sid, wh in wmap.items():
                stock_of = {i["no"]: i.get("availableToSell") for i in await fetch_items(c, wh)}
                if sid == seller.PGS_STORE_ID:
                    current = {p["product_id"]: p.get("stock", 0) for p in plain}
                else:
                    current = await seller.branch_stocks(db, sid, [p["product_id"] for p in plain])
                for p in plain:
                    st = stock_of.get(p["sku"])
                    if st is None:
                        continue
                    st, before = max(0, int(st)), current.get(p["product_id"], 0)
                    if st != before:
                        changes.append({"product_id": p["product_id"], "name": p["name"], "sku": p["sku"], "field": "stock",
                                        "store_id": sid, "store_name": names.get(sid, sid), "warehouse": wh, "before": before, "after": st})
        new = []
        if body.new_products:
            new = [{"no": i["no"], "name": i.get("name") or i["no"], "price": int(round(i.get("unitPrice") or 0)),
                    "unit": i.get("unit1Name") or ""} for i in items
                   if i["no"] not in matched and i.get("itemType") in (None, "INVENTORY") and i.get("name")]
        for ch in changes:
            ch["key"] = change_key(ch)
        doc = {"preview_id": f"acs_{uuid.uuid4().hex[:12]}", "created_at": _now(), "by": admin["user_id"], "status": "preview",
               "options": body.model_dump(), "changes": changes, "new_items": new, "skipped": skipped,
               "accurate_total": len(items), "matched": len(matched)}
        await db.accurate_sync.insert_one({**doc})
        return preview_out(doc)

    def preview_out(d: dict) -> dict:
        ch = d["changes"]
        return {k: d.get(k) for k in ("preview_id", "created_at", "status", "options", "accurate_total", "matched", "result")} | {
            "counts": {"price": sum(c["field"] == "price" for c in ch), "stock": sum(c["field"] == "stock" for c in ch),
                       "new": len(d["new_items"]), "skipped": len(d["skipped"])},
            "changes": ch[:500], "new_items": d["new_items"][:300], "skipped": d["skipped"][:100], "truncated": len(ch) > 500 or len(d["new_items"]) > 300}

    @api.get("/admin/accurate/sync/{preview_id}")
    async def sync_get(preview_id: str, _=Depends(require_admin)):
        d = await db.accurate_sync.find_one({"preview_id": preview_id}, {"_id": 0})
        if not d:
            raise HTTPException(status_code=404, detail="Pratinjau tidak ditemukan")
        return preview_out(d)

    @api.post("/admin/accurate/sync/{preview_id}/apply")
    async def sync_apply(preview_id: str, body: ApplyIn, admin=Depends(require_admin)):
        d = await db.accurate_sync.find_one_and_update(
            {"preview_id": preview_id, "status": "preview", "created_at": {"$gte": _now() - timedelta(hours=2)}},
            {"$set": {"status": "applying"}}, projection={"_id": 0})
        if not d:
            raise HTTPException(status_code=400, detail="Pratinjau sudah dipakai atau kedaluwarsa (2 jam). Buat pratinjau baru")
        skip = set(body.skip)
        done = {"price": 0, "stock": 0, "new": 0, "conflict": 0}
        actor = {**admin, "name": f"{admin.get('name') or admin.get('email', '')} (Accurate)"}
        for ch in d["changes"]:
            if ch["key"] in skip:
                continue
            p = await db.products.find_one({"product_id": ch["product_id"]}, {"_id": 0})
            if not p:
                continue
            if ch["field"] == "price":
                if p.get("price", 0) != ch["before"]:
                    done["conflict"] += 1  # changed in PGS after the preview: leave it
                    continue
                orig = p.get("original_price") or 0
                orig = ch["after"] if orig <= ch["after"] or orig == ch["before"] else orig
                disc = round((orig - ch["after"]) * 100 / orig) if orig > ch["after"] else 0
                await db.products.update_one({"product_id": p["product_id"], "price": ch["before"]},
                                             {"$set": {"price": ch["after"], "original_price": orig, "discount": disc, "updated_at": _now()}})
                await history.record(db, actor, seller.PGS_STORE_ID, p, history.snap(p),
                                     {"price": ch["after"], "original_price": orig}, "accurate")
                done["price"] += 1
            else:
                sid = ch["store_id"]
                if sid == seller.PGS_STORE_ID:
                    res = await db.products.update_one({"product_id": p["product_id"], "stock": ch["before"]},
                                                       {"$set": {"stock": ch["after"], "in_stock": ch["after"] > 0, "updated_at": _now()}})
                else:
                    q = {"store_id": sid, "product_id": p["product_id"]}
                    row = await db.store_stock.find_one(q, {"stock": 1})
                    if (row or {}).get("stock", 0) != ch["before"]:
                        done["conflict"] += 1
                        continue
                    res = await db.store_stock.update_one(q, {"$set": {"stock": ch["after"]}}, upsert=True)
                if not (res.modified_count or res.upserted_id):
                    done["conflict"] += 1
                    continue
                if ch["after"] > ch["before"]:
                    await db.products.update_one({"product_id": p["product_id"]}, {"$set": {"restocked_at": _now()}})
                await history.record(db, actor, sid, p, {"stock": ch["before"]}, {"stock": ch["after"]}, "accurate")
                done["stock"] += 1
        skip_new = set(body.skip_new)
        store = await db.stores.find_one({"store_id": seller.PGS_STORE_ID}, {"name": 1})
        for it in d["new_items"]:
            if it["no"] in skip_new or await db.products.find_one({"sku": it["no"], "store_id": seller.PGS_STORE_ID}, {"_id": 1}):
                continue
            await db.products.insert_one({
                "product_id": f"acc-{uuid.uuid4().hex[:10]}", "name": it["name"][:200], "sku": it["no"], "barcode": "",
                "price": it["price"], "original_price": it["price"], "discount": 0, "stock": 0, "in_stock": False,
                "status": "inactive", "category": "", "categories": [], "image": "", "images": [], "description": "",
                "store_id": seller.PGS_STORE_ID, "store_name": (store or {}).get("name", "PGS Sidoarjo"), "rating": 0, "sold": 0,
                "views": 0, "source": "accurate", "created_at": _now(), "updated_at": _now()})
            done["new"] += 1
        await db.accurate_sync.update_one({"preview_id": preview_id}, {"$set": {"status": "applied", "applied_at": _now(), "result": done}})
        await db.settings.update_one(KEY, {"$set": {"last_sync_at": _now()}})
        return {"preview_id": preview_id, "result": done}

    # ============================================================ B. faktur penjualan
    @api.put("/admin/accurate/invoice-settings")
    async def invoice_settings(body: InvoiceSettingsIn, _=Depends(require_admin)):
        await db.settings.update_one(KEY, {"$set": {"customer_no": body.customer_no.strip(), "shipping_item_no": body.shipping_item_no.strip()}}, upsert=True)
        s = await load_settings(db)
        return {"customer_no": s["customer_no"], "shipping_item_no": s.get("shipping_item_no", "")}

    def eligible(o: dict) -> bool:
        return o["status"] in INVOICE_OK and (o.get("payment_method") != "cod" or o["status"] == "completed")

    def inv_state(o: dict) -> dict:
        return o.get("accurate_invoice") or {"status": "none"}

    @api.get("/admin/accurate/orders")
    async def invoice_orders(sent: bool = False, page: int = 1, _=Depends(require_admin)):
        q: dict = {"status": {"$in": list(INVOICE_OK)}, "$or": [{"payment_method": {"$ne": "cod"}}, {"status": "completed"}]}
        q["accurate_invoice.status"] = "sent" if sent else {"$ne": "sent"}
        total = await db.orders.count_documents(q)
        docs = await db.orders.find(q, {"_id": 0, "order_id": 1, "store_name": 1, "store_id": 1, "total": 1, "status": 1, "created_at": 1,
                                        "payment_method": 1, "shipping.full_name": 1, "accurate_invoice": 1, "items": 1}) \
            .sort("created_at", -1).skip((max(1, page) - 1) * 20).limit(20).to_list(20)
        return {"total": total, "page": max(1, page), "items": [{**{k: v for k, v in o.items() if k != "items"}, "item_count": len(o.get("items") or []),
                                                                  "buyer": (o.get("shipping") or {}).get("full_name", ""), "accurate_invoice": inv_state(o)} for o in docs]}

    async def build_invoice(o: dict) -> dict:
        s = await load_settings(db)
        problems, lines = [], []
        if not s.get("customer_no"):
            problems.append("Isi Kode Pelanggan Accurate di pengaturan faktur")
        wh = (s.get("warehouse_map") or {}).get(o["store_id"])
        if not wh:
            problems.append(f"Cabang {o.get('store_name', o['store_id'])} belum dipetakan ke gudang Accurate")
        for i in o["items"]:
            p = await db.products.find_one({"product_id": i["product_id"]}, {"sku": 1, "variants": 1}) or {}
            sku = p.get("sku", "")
            if i.get("variant_id"):
                sku = next((v.get("sku") for v in p.get("variants") or [] if v.get("variant_id") == i["variant_id"] and v.get("sku")), sku)
            if not sku:
                problems.append(f"{i['name']} belum punya SKU (kode barang Accurate)")
            lines.append({"item_no": sku, "name": i["name"] + (f" ({i['variant_name']})" if i.get("variant_name") else ""),
                          "quantity": i["quantity"], "unit_price": i["price"], "warehouse": wh or "", "amount": i["price"] * i["quantity"]})
        notes = []
        ship = int(o.get("shipping_cost") or 0) if (o.get("courier") or {}).get("code") != "pickup" else 0
        if ship and s.get("shipping_item_no"):
            lines.append({"item_no": s["shipping_item_no"], "name": "Ongkos kirim", "quantity": 1, "unit_price": ship, "warehouse": "", "amount": ship})
        elif ship:
            notes.append("Ongkir tidak masuk faktur (isi Kode Barang Ongkir untuk menyertakannya)")
        discount = int(o.get("discount") or 0)
        created = o["created_at"] if o["created_at"].tzinfo else o["created_at"].replace(tzinfo=timezone.utc)
        if not eligible(o):
            problems.append("Pesanan belum dibayar / belum selesai (COD)")
        return {"order_id": o["order_id"], "number": o["order_id"], "customer_no": s.get("customer_no", ""),
                "date": created.astimezone(WIB).strftime("%d/%m/%Y"), "store_name": o.get("store_name", ""),
                "buyer": (o.get("shipping") or {}).get("full_name", ""), "lines": lines, "discount": discount,
                "total": sum(x["amount"] for x in lines) - discount, "order_total": o["total"], "notes": notes, "problems": problems,
                "description": f"Pesanan online PGS {o['order_id']} - {(o.get('shipping') or {}).get('full_name', '')}".strip(" -"),
                "accurate_invoice": inv_state(o)}

    async def order_or_404(order_id: str) -> dict:
        o = await db.orders.find_one({"order_id": order_id}, {"_id": 0})
        if not o:
            raise HTTPException(status_code=404, detail="Pesanan tidak ditemukan")
        return o

    @api.get("/admin/accurate/invoice/{order_id}")
    async def invoice_preview(order_id: str, _=Depends(require_admin)):
        return await build_invoice(await order_or_404(order_id))

    @api.post("/admin/accurate/invoice/{order_id}")
    async def invoice_send(order_id: str, body: SendIn, admin=Depends(require_admin)):
        if not body.confirm:
            raise HTTPException(status_code=400, detail="Konfirmasi dulu sebelum mengirim faktur")
        inv = await build_invoice(await order_or_404(order_id))
        if inv["problems"]:
            raise HTTPException(status_code=400, detail="; ".join(inv["problems"]))
        locked = await db.orders.find_one_and_update(
            {"order_id": order_id, "$or": [{"accurate_invoice.status": {"$nin": ["sent", "sending"]}},  # a send that died >5 min ago may retry
                                           {"accurate_invoice.status": "sending", "accurate_invoice.at": {"$lt": _now() - timedelta(minutes=5)}}]},
            {"$set": {"accurate_invoice": {"status": "sending", "at": _now(), "by": admin["user_id"]}}})
        if not locked:
            raise HTTPException(status_code=409, detail="Faktur pesanan ini sudah/ sedang dikirim ke Accurate")
        form = {"customerNo": inv["customer_no"], "transDate": inv["date"], "number": inv["number"], "description": inv["description"][:250]}
        for n, ln in enumerate(inv["lines"]):
            form |= {f"detailItem[{n}].itemNo": ln["item_no"], f"detailItem[{n}].quantity": str(ln["quantity"]),
                     f"detailItem[{n}].unitPrice": str(ln["unit_price"]), f"detailItem[{n}].detailName": ln["name"][:100]}
            if ln["warehouse"]:
                form[f"detailItem[{n}].warehouseName"] = ln["warehouse"]
        if inv["discount"]:
            form["cashDiscount"] = str(inv["discount"])
        try:
            c = await make_client(db)
            data = await c.call("POST", INVOICE_SAVE, form=form)
        except HTTPException as e:
            if "sudah" in str(e.detail).lower() and ("dipakai" in str(e.detail).lower() or "digunakan" in str(e.detail).lower()):
                # number = order id already exists: an earlier attempt reached Accurate (e.g. reply timed out) -> it is there
                data = {"r": {"number": inv["number"]}}
            else:
                await db.orders.update_one({"order_id": order_id}, {"$set": {"accurate_invoice": {"status": "failed", "error": e.detail, "at": _now(), "by": admin["user_id"]}}})
                raise
        except Exception as e:
            await db.orders.update_one({"order_id": order_id}, {"$set": {"accurate_invoice": {"status": "failed", "error": e.__class__.__name__, "at": _now(), "by": admin["user_id"]}}})
            raise
        r = data.get("r") or {}
        state = {"status": "sent", "number": r.get("number") or inv["number"], "id": r.get("id"), "at": _now(), "by": admin["user_id"],
                 "total": inv["total"]}
        await db.orders.update_one({"order_id": order_id}, {"$set": {"accurate_invoice": state}})
        return {**inv, "accurate_invoice": state}
