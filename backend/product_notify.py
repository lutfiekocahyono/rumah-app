"""Notifikasi info produk ke semua pembeli: produk baru, harga, stok, keterangan/foto.

Perubahan dicatat sebagai product_events, lalu digabung jadi SATU ringkasan per pembeli paling sering 1x per jam
(lonceng di aplikasi + email). Impor Excel / sinkron Accurate ribuan produk tetap hanya 1 notifikasi."""
import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from html import escape
from typing import Optional

from fastapi import Depends, HTTPException

import mailer

logger = logging.getLogger("product_notify")

INTERVAL = timedelta(hours=1)
CHECK_EVERY_S = 300
INFO_FIELDS = ("name", "description", "images", "image", "video", "specs", "category", "subcategory", "brand", "condition",
               "weight_grams", "variant_options", "min_order", "preorder")
KIND_TEXT = {"new": "produk baru", "price": "harga berubah", "restock": "stok tersedia lagi", "stock": "stok diperbarui", "info": "info diperbarui"}
DIGEST_KEY = {"key": "product_digest"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _idr(n) -> str:
    return f"Rp{int(n or 0):,}".replace(",", ".")


def _visible(p: dict) -> bool:
    return p.get("status", "active") == "active"


async def _event(db, p: dict, kind: str, before=None, after=None, store_id: str = "") -> None:
    await db.product_events.insert_one({"product_id": p["product_id"], "name": p.get("name", ""), "image": p.get("image", ""),
                                        "kind": kind, "before": before, "after": after, "store_id": store_id or p.get("store_id", ""),
                                        "at": _now(), "digest_id": None})


async def on_new(db, p: dict) -> None:
    if _visible(p):
        await _event(db, p, "new", after=p.get("price"))


async def on_info(db, old: dict, new: dict) -> None:
    """Keterangan, foto, nama, spesifikasi, dll. berubah (harga/stok lewat history.record)."""
    merged = {**old, **new}
    if not _visible(merged):
        return
    if not _visible(old):  # baru diaktifkan = baru tampil untuk pembeli
        return await _event(db, merged, "new", after=merged.get("price"))
    if any(f in new and new[f] != old.get(f) for f in INFO_FIELDS):
        await _event(db, merged, "info")


async def on_history(db, product: dict, changes: list, store_id: str) -> None:
    """Dipanggil dari history.record (setelah produk disimpan) untuk setiap perubahan harga/stok."""
    cur = await db.products.find_one({"product_id": product["product_id"]}, {"status": 1}) or {"status": "deleted"}
    if not _visible(product) or not _visible(cur):  # hidden in the same save: buyers must not hear about it
        return
    for c in changes:
        if c.get("variant"):
            continue  # variant rows are summarised by the product-level price/stock below
        if c["field"] == "price":
            await _event(db, product, "price", c["before"], c["after"], store_id)
        elif c["field"] == "stock" and c["after"] is not None:
            restock = (c["before"] or 0) <= 0 < c["after"]
            await _event(db, product, "restock" if restock else "stock", c["before"], c["after"], store_id)
    if any(c.get("variant") for c in changes) and not any(not c.get("variant") for c in changes):
        kinds = {c["kind"] for c in changes}
        await _event(db, product, "price" if "price" in kinds else "stock", None, None, store_id)


def _summarise(events: list) -> list:
    items: dict = {}
    for e in events:
        it = items.setdefault(e["product_id"], {"product_id": e["product_id"], "name": e["name"], "image": e["image"], "kinds": [],
                                                 "price_before": None, "price_after": None, "restock_stores": []})
        it["name"], it["image"] = e["name"] or it["name"], e["image"] or it["image"]
        if e["kind"] not in it["kinds"]:
            it["kinds"].append(e["kind"])
        if e["kind"] == "price" and e.get("after") is not None:
            if it["price_before"] is None:
                it["price_before"] = e["before"]
            it["price_after"] = e["after"]
        if e["kind"] == "restock" and e["store_id"] not in it["restock_stores"]:
            it["restock_stores"].append(e["store_id"])
    for it in items.values():
        if "new" in it["kinds"]:  # a brand-new product: "baru" says it all
            it["kinds"] = ["new"]
        elif "restock" in it["kinds"] and "stock" in it["kinds"]:
            it["kinds"].remove("stock")
        if it["price_before"] is not None and it["price_before"] == it["price_after"]:
            it["kinds"] = [k for k in it["kinds"] if k != "price"] or ["info"]
    order = {"new": 0, "price": 1, "restock": 2, "info": 3, "stock": 4}
    return sorted(items.values(), key=lambda i: min(order[k] for k in i["kinds"]))


def change_text(it: dict, stores: dict) -> str:
    parts = []
    for k in it["kinds"]:
        if k == "new":
            parts.append(f"Produk baru · {_idr(it['price_after'])}" if it.get("price_after") else "Produk baru")
        elif k == "price" and it["price_after"] is not None and it["price_before"] is not None:
            parts.append(f"Harga {'turun' if it['price_after'] < it['price_before'] else 'naik'} {_idr(it['price_before'])} → {_idr(it['price_after'])}")
        elif k == "price":
            parts.append("Harga variasi diperbarui")
        elif k == "restock":
            parts.append("Tersedia lagi" + (f" di {', '.join(stores.get(s, s) for s in it['restock_stores'][:3])}" if it["restock_stores"] else ""))
        else:
            parts.append({"stock": "Stok diperbarui", "info": "Keterangan / foto diperbarui"}[k])
    return " · ".join(parts)


def headline(items: list) -> tuple[str, str]:
    if len(items) == 1:
        it = items[0]
        k = it["kinds"][0]
        title = {"new": f"Produk baru: {it['name']}", "price": f"Harga {it['name']} berubah", "restock": f"{it['name']} tersedia lagi",
                 "stock": f"Stok {it['name']} diperbarui", "info": f"Info {it['name']} diperbarui"}[k]
        return title[:120], ""
    counts: dict = {}
    for it in items:
        for k in it["kinds"]:
            counts[k] = counts.get(k, 0) + 1
    title = "Update produk: " + ", ".join(f"{n} {KIND_TEXT[k]}" for k, n in sorted(counts.items(), key=lambda x: -x[1])[:3])
    names = ", ".join(i["name"] for i in items[:3]) + (f", dan {len(items) - 3} lainnya" if len(items) > 3 else "")
    return title[:120], names[:300]


def register(api, db, require_admin, get_current_user):

    async def recipients() -> list:
        return await db.users.find({"role": "customer"}, {"_id": 0, "user_id": 1, "email": 1, "name": 1, "settings": 1, "email_verified": 1}).to_list(100000)

    async def send_emails(digest: dict, users: list, stores: dict) -> dict:
        rows = "".join(f'<tr><td style="padding:8px 0;border-bottom:1px solid #E5E7EB"><b>{escape(i["name"])}</b><br>'
                       f'<span style="color:#6B7280;font-size:13px">{escape(change_text(i, stores))}</span></td></tr>' for i in digest["items"][:20])
        more = f'<p style="color:#6B7280">…dan {len(digest["items"]) - 20} produk lainnya.</p>' if len(digest["items"]) > 20 else ""
        body = (f'<p>{escape(digest["title"])}</p><table role="presentation" width="100%">{rows}</table>{more}'
                '<p>Buka aplikasi Pusat Grosir Sidoarjo untuk melihat detailnya.</p>'
                '<p style="font-size:12px;color:#6B7280">Tidak ingin email ini? Matikan "Email info produk" di Akun → Pengaturan.</p>')
        sent = failed = 0
        for u in users:
            try:
                await mailer.send_email(to=u["email"], subject=digest["title"][:100], html=mailer._wrap(u.get("name") or "Pelanggan", body))
                sent += 1
            except HTTPException as e:
                failed += 1
                if e.status_code == 503:  # quota / paused: stop this round
                    logger.warning("product digest email paused after %s", sent)
                    break
            except Exception:
                failed += 1
                logger.exception("product digest email failed")
        return {"sent": sent, "failed": failed}

    async def run_digest(force: bool = False) -> Optional[dict]:
        state = await db.settings.find_one(DIGEST_KEY) or {}
        last = state.get("last_at")
        if last and not force and _now() - (last if last.tzinfo else last.replace(tzinfo=timezone.utc)) < INTERVAL:
            return None
        events = await db.product_events.find({"digest_id": None}).sort("at", 1).to_list(50000)
        if not events:
            return None
        digest_id = f"pd_{uuid.uuid4().hex[:10]}"
        claimed = await db.product_events.update_many({"_id": {"$in": [e["_id"] for e in events]}, "digest_id": None}, {"$set": {"digest_id": digest_id}})
        if not claimed.modified_count:
            return None
        await db.settings.update_one(DIGEST_KEY, {"$set": {"last_at": _now()}}, upsert=True)
        items = _summarise(events)
        title, body = headline(items)
        stores = {s["store_id"]: s["name"] for s in await db.stores.find({}, {"store_id": 1, "name": 1}).to_list(1000)}
        if not body:
            body = change_text(items[0], stores)
        link = f"/product/{items[0]['product_id']}" if len(items) == 1 else f"/product-updates/{digest_id}"
        users = await recipients()
        bell = [u for u in users if (u.get("settings") or {}).get("notif_product", True)]
        if bell:
            now = _now()
            await db.notifications.insert_many([{"notif_id": uuid.uuid4().hex[:12], "user_id": u["user_id"], "kind": "product", "title": title,
                                                 "body": body, "link": link, "read": False, "created_at": now} for u in bell])
        mail_to = [u for u in users if u.get("email") and u.get("email_verified") and (u.get("settings") or {}).get("email_product", True)]
        digest = {"digest_id": digest_id, "title": title, "body": body, "items": items, "created_at": _now(), "bell": len(bell), "email_planned": len(mail_to)}
        await db.product_digests.insert_one({**digest})
        result = await send_emails(digest, mail_to, stores)
        await db.product_digests.update_one({"digest_id": digest_id}, {"$set": {"email": result}})
        logger.info("product digest %s: %s products, %s bell, email %s", digest_id, len(items), len(bell), result)
        return {k: v for k, v in digest.items() if k != "items"} | {"products": len(items), "email": result}

    async def loop():
        while True:
            try:
                await run_digest()
            except Exception:
                logger.exception("product digest failed")
            await asyncio.sleep(CHECK_EVERY_S)

    @api.get("/product-updates/{digest_id}")
    async def digest_detail(digest_id: str, _=Depends(get_current_user)):
        d = await db.product_digests.find_one({"digest_id": digest_id}, {"_id": 0})
        if not d:
            raise HTTPException(status_code=404, detail="Update produk tidak ditemukan")
        stores = {s["store_id"]: s["name"] for s in await db.stores.find({}, {"store_id": 1, "name": 1}).to_list(1000)}
        live = {p["product_id"] for p in await db.products.find({"product_id": {"$in": [i["product_id"] for i in d["items"][:500]]},
                                                                "status": {"$ne": "inactive"}}, {"product_id": 1}).to_list(500)}
        return {"digest_id": digest_id, "title": d["title"], "created_at": d["created_at"],
                "items": [{**i, "change": change_text(i, stores)} for i in d["items"][:500] if i["product_id"] in live]}

    @api.get("/admin/product-digest")
    async def digest_status(_=Depends(require_admin)):
        state = await db.settings.find_one(DIGEST_KEY, {"_id": 0}) or {}
        last = await db.product_digests.find_one({}, {"_id": 0, "items": 0}, sort=[("created_at", -1)])
        return {"pending_events": await db.product_events.count_documents({"digest_id": None}), "last_at": state.get("last_at"), "last": last}

    @api.post("/admin/product-digest/run")
    async def digest_run(_=Depends(require_admin)):
        """Kirim ringkasan sekarang tanpa menunggu jadwal per jam."""
        return await run_digest(force=True) or {"sent": False, "detail": "Tidak ada perubahan produk yang menunggu"}

    return loop
