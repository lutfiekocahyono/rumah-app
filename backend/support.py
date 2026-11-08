"""Saldo (wallet), komplain & refund, and in-app buyer <-> store chat."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field, StringConstraints
from pymongo import ASCENDING, DESCENDING, IndexModel, ReturnDocument
from pymongo.errors import DuplicateKeyError

COMPLAINT_DAYS = 7
REASONS = {"damaged": "Barang rusak", "wrong_item": "Barang tidak sesuai", "missing": "Barang kurang",
           "not_received": "Barang belum diterima", "other": "Lainnya"}
OPEN = ("open", "escalated")

INDEXES = {
    "wallets": [IndexModel([("user_id", ASCENDING)], name="user_id", unique=True)],
    "wallet_tx": [IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)], name="user_time")],
    "complaints": [IndexModel([("order_id", ASCENDING)], name="order_id", unique=True),
                   IndexModel([("store_id", ASCENDING), ("updated_at", DESCENDING)], name="store_time"),
                   IndexModel([("user_id", ASCENDING), ("updated_at", DESCENDING)], name="user_time")],
    "conversations": [IndexModel([("user_id", ASCENDING), ("store_id", ASCENDING)], name="user_store", unique=True),
                      IndexModel([("store_id", ASCENDING), ("last_at", DESCENDING)], name="store_time")],
    "chat_messages": [IndexModel([("conv_id", ASCENDING), ("created_at", ASCENDING)], name="conv_time")],
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(d: datetime) -> datetime:
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------- wallet helpers
async def balance_of(db, user_id: Optional[str]) -> int:
    if not user_id:
        return 0
    w = await db.wallets.find_one({"user_id": user_id})
    return int((w or {}).get("balance", 0))


async def credit(db, user_id: str, amount: int, kind: str, ref: str, note: str) -> None:
    await db.wallets.update_one({"user_id": user_id}, {"$inc": {"balance": amount}}, upsert=True)
    await db.wallet_tx.insert_one({"tx_id": f"tx_{uuid.uuid4().hex[:12]}", "user_id": user_id, "amount": amount,
                                   "kind": kind, "ref": ref, "note": note, "created_at": _now()})


async def debit(db, user_id: str, amount: int, ref: str) -> bool:
    """Atomically take `amount` from the buyer's saldo; False if not enough."""
    if amount <= 0:
        return True
    ok = await db.wallets.find_one_and_update({"user_id": user_id, "balance": {"$gte": amount}}, {"$inc": {"balance": -amount}})
    if not ok:
        return False
    await db.wallet_tx.insert_one({"tx_id": f"tx_{uuid.uuid4().hex[:12]}", "user_id": user_id, "amount": -amount,
                                   "kind": "payment", "ref": ref, "note": f"Bayar pesanan {ref}", "created_at": _now()})
    return True


async def return_balance_once(db, order_id: str) -> None:
    """Cancelled / expired / failed order: give the used saldo back once."""
    o = await db.orders.find_one_and_update({"order_id": order_id, "balance_used": {"$gt": 0}, "balance_returned": {"$ne": True}},
                                            {"$set": {"balance_returned": True}})
    amount = int(o["balance_used"]) - int(o.get("refunded", 0)) if o else 0  # never return what a complaint already refunded
    if o and o.get("user_id") and amount > 0:
        await credit(db, o["user_id"], amount, "return", order_id, f"Saldo dikembalikan, pesanan {order_id} batal")


def shipped_at(order: dict) -> Optional[datetime]:
    """When the buyer got (or could get) the goods: last 'shipped' step, else completion."""
    at = None
    for h in order.get("status_history") or []:
        if h.get("status") == "shipped" or (h.get("status") == "completed" and at is None):
            at = h.get("at")
    return _aware(at or order.get("completed_at")) if (at or order.get("completed_at")) else None


def paid_amount(order: dict) -> int:
    """What the buyer actually paid. COD cash counts only once the order is completed (cash received)."""
    if order.get("payment_method") == "cod" and order.get("status") != "completed":
        return int(order.get("balance_used", 0))
    return int(order["total"])


# ---------------------------------------------------------------- models
class ComplaintIn(BaseModel):
    order_id: str
    reason: str = Field(pattern="^(damaged|wrong_item|missing|not_received|other)$")
    description: str = Field(min_length=10, max_length=1000)
    refund_amount: int = Field(ge=0)


class TextIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


class DecideIn(BaseModel):
    action: str = Field(pattern="^(refund|reject|resolve)$")
    amount: int = Field(default=0, ge=0)
    note: str = Field(default="", max_length=500)


class ChatStartIn(BaseModel):
    store_id: str
    order_id: Optional[str] = None
    product_id: Optional[str] = None  # buyer asks about a product before ordering


class SellerChatStartIn(BaseModel):
    order_id: str


class QuickReplyIn(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


# {produk} {harga} {pembeli} {toko} are filled in by the chat screen from the conversation
DEFAULT_REPLIES = [
    ("Stok tersedia", "Halo Kak {pembeli}, stok {produk} masih tersedia di {toko}. Silakan langsung dipesan ya, terima kasih 🙏"),
    ("Stok habis", "Mohon maaf Kak {pembeli}, stok {produk} sedang kosong di {toko}. Kami kabari lagi begitu barang datang ya."),
    ("Harga grosir", "Harga {produk}: {harga} Kak. Ada harga grosir: makin banyak jumlah yang dibeli, harga per barang makin murah. Rincian harga per jumlah bisa dilihat di halaman produk."),
    ("Jam ambil di toko", "Pesanan Ambil di Toko bisa diambil Senin–Sabtu pukul 08.00–16.00 di {toko}, tanpa ongkir. Tunjukkan kode QR pesanan ke kasir ya Kak."),
    ("Ongkir", "Ongkir dihitung otomatis saat checkout sesuai alamat dan kurir yang dipilih Kak. Bisa juga pilih Ambil di Toko supaya tanpa ongkir."),
]


def register(api, db, get_current_user, require_admin, notify_user, log_activity):

    async def store_of(user: dict) -> Optional[dict]:
        return await db.stores.find_one({"owner_id": user["user_id"], "status": "active"}, {"_id": 0})

    async def require_seller(user=Depends(get_current_user)) -> dict:
        s = await store_of(user)
        if not s:
            raise HTTPException(status_code=403, detail="Toko Anda belum aktif")
        return {"user": user, "store": s}

    # ============================================================ wallet
    @api.get("/wallet")
    async def my_wallet(user=Depends(get_current_user)):
        tx = await db.wallet_tx.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
        return {"balance": await balance_of(db, user["user_id"]), "transactions": tx}

    # ============================================================ complaints
    async def _complaint_for(cid: str, user: dict) -> tuple[dict, str]:
        c = await db.complaints.find_one({"complaint_id": cid}, {"_id": 0})
        if not c:
            raise HTTPException(status_code=404, detail="Komplain tidak ditemukan")
        if c["user_id"] == user["user_id"]:
            return c, "buyer"
        if user.get("role") == "admin":
            return c, "admin"
        s = await store_of(user)
        if s and s["store_id"] == c["store_id"]:
            return c, "store"
        raise HTTPException(status_code=404, detail="Komplain tidak ditemukan")

    def _out(c: dict, viewer: str, paid: Optional[int] = None) -> dict:
        refundable = max(0, (c.get("order_total", 0) if paid is None else paid) - c.get("refunded", 0))
        cod_unpaid = paid is not None and paid < c.get("order_total", 0)
        return {**c, "reason_label": REASONS.get(c["reason"], c["reason"]), "viewer": viewer, "refundable": refundable, "cod_unpaid": cod_unpaid,
                "can_decide": (viewer == "store" and c["status"] == "open") or (viewer == "admin" and c["status"] in OPEN),
                "can_escalate": viewer == "buyer" and c["status"] == "rejected" and not c.get("escalated_once"),
                "can_reply": c["status"] in OPEN}

    @api.post("/complaints")
    async def create_complaint(body: ComplaintIn, user=Depends(get_current_user)):
        o = await db.orders.find_one({"order_id": body.order_id, "user_id": user["user_id"]})
        if not o:
            raise HTTPException(status_code=404, detail="Pesanan tidak ditemukan")
        if o["status"] not in ("shipped", "completed"):
            raise HTTPException(status_code=400, detail="Komplain bisa diajukan setelah pesanan dikirim")
        at = shipped_at(o)
        if not at or _now() - at > timedelta(days=COMPLAINT_DAYS):
            raise HTTPException(status_code=400, detail=f"Batas waktu komplain {COMPLAINT_DAYS} hari sudah lewat")
        if await db.complaints.find_one({"order_id": body.order_id}):
            raise HTTPException(status_code=400, detail="Pesanan ini sudah pernah dikomplain")
        if body.refund_amount > o["total"]:
            raise HTTPException(status_code=400, detail="Nominal refund melebihi total pesanan")
        doc = {"complaint_id": f"KMP-{uuid.uuid4().hex[:8].upper()}", "order_id": o["order_id"], "store_id": o["store_id"],
               "store_name": o.get("store_name", ""), "user_id": user["user_id"], "user_name": user.get("name") or user["email"],
               "reason": body.reason, "description": body.description.strip(), "refund_amount": body.refund_amount,
               "order_total": o["total"], "refunded": 0, "status": "open", "decision": None,
               "messages": [{"by": "buyer", "name": user.get("name") or user["email"], "text": body.description.strip(), "at": _now()}],
               "created_at": _now(), "updated_at": _now()}
        try:
            await db.complaints.insert_one({**doc})
        except Exception:
            raise HTTPException(status_code=400, detail="Pesanan ini sudah pernah dikomplain")
        await db.orders.update_one({"order_id": o["order_id"]}, {"$set": {"complaint_id": doc["complaint_id"]}})
        store = await db.stores.find_one({"store_id": o["store_id"]}, {"owner_id": 1})
        if store:
            await notify_user(store["owner_id"], "order", "Komplain baru",
                              f"Pembeli mengajukan komplain untuk pesanan {o['order_id']}.", f"/complaint/{doc['complaint_id']}")
        await log_activity(user["user_id"], "order", f"Mengajukan komplain {doc['complaint_id']} untuk {o['order_id']}")
        return _out(doc, "buyer")

    @api.get("/complaints")
    async def my_complaints(user=Depends(get_current_user)):
        docs = await db.complaints.find({"user_id": user["user_id"]}, {"_id": 0, "messages": 0}).sort("updated_at", -1).to_list(200)
        return [_out({**d, "messages": []}, "buyer") for d in docs]

    @api.get("/seller/complaints")
    async def store_complaints(status: Optional[str] = None, ctx=Depends(require_seller)):
        q: dict = {"store_id": ctx["store"]["store_id"]}
        if status:
            q["status"] = {"$in": list(OPEN)} if status == "active" else status
        docs = await db.complaints.find(q, {"_id": 0, "messages": 0}).sort("updated_at", -1).to_list(300)
        return [_out({**d, "messages": []}, "store") for d in docs]

    @api.get("/admin/complaints")
    async def admin_complaints(status: Optional[str] = None, store_id: Optional[str] = None, _=Depends(require_admin)):
        q: dict = {}
        if status:
            q["status"] = {"$in": list(OPEN)} if status == "active" else status
        if store_id:
            q["store_id"] = store_id
        docs = await db.complaints.find(q, {"_id": 0, "messages": 0}).sort("updated_at", -1).to_list(500)
        return [_out({**d, "messages": []}, "admin") for d in docs]

    @api.get("/complaints/{cid}")
    async def get_complaint(cid: str, user=Depends(get_current_user)):
        c, viewer = await _complaint_for(cid, user)
        return _out(c, viewer, await _paid(c))

    async def _paid(c: dict) -> int:
        o = await db.orders.find_one({"order_id": c["order_id"]}, {"_id": 0, "payment_method": 1, "status": 1, "total": 1, "balance_used": 1})
        return paid_amount(o) if o else 0

    async def _notify_other(c: dict, viewer: str, title: str, body: str) -> None:
        link = f"/complaint/{c['complaint_id']}"
        if viewer != "buyer":
            await notify_user(c["user_id"], "order", title, body, link)
        if viewer != "store":
            s = await db.stores.find_one({"store_id": c["store_id"]}, {"owner_id": 1})
            if s:
                await notify_user(s["owner_id"], "order", title, body, link)

    @api.post("/complaints/{cid}/messages")
    async def reply_complaint(cid: str, body: TextIn, user=Depends(get_current_user)):
        c, viewer = await _complaint_for(cid, user)
        if c["status"] not in OPEN:
            raise HTTPException(status_code=400, detail="Komplain sudah ditutup")
        name = {"buyer": user.get("name") or "Pembeli", "store": c["store_name"], "admin": "Admin PGS"}[viewer]
        res = await db.complaints.find_one_and_update(
            {"complaint_id": cid}, {"$push": {"messages": {"by": viewer, "name": name, "text": body.text.strip(), "at": _now()}},
                                    "$set": {"updated_at": _now()}}, projection={"_id": 0}, return_document=ReturnDocument.AFTER)
        await _notify_other(c, viewer, "Balasan komplain", f"{name}: {body.text.strip()[:80]}")
        return _out(res, viewer, await _paid(c))

    @api.post("/complaints/{cid}/escalate")
    async def escalate(cid: str, body: TextIn, user=Depends(get_current_user)):
        c, viewer = await _complaint_for(cid, user)
        if not _out(c, viewer)["can_escalate"]:
            raise HTTPException(status_code=400, detail="Komplain tidak bisa diteruskan")
        res = await db.complaints.find_one_and_update(
            {"complaint_id": cid, "status": "rejected"},
            {"$set": {"status": "escalated", "escalated_once": True, "updated_at": _now()},
             "$push": {"messages": {"by": "buyer", "name": user.get("name") or "Pembeli", "text": f"[Diteruskan ke Admin PGS] {body.text.strip()}", "at": _now()}}},
            projection={"_id": 0}, return_document=ReturnDocument.AFTER)
        if not res:
            raise HTTPException(status_code=400, detail="Komplain tidak bisa diteruskan")
        for a in await db.users.find({"role": "admin"}, {"user_id": 1}).to_list(20):
            await notify_user(a["user_id"], "order", "Komplain diteruskan ke Anda", f"Komplain {cid} ({c['store_name']}) butuh keputusan.", f"/complaint/{cid}")
        return _out(res, viewer, await _paid(c))

    @api.post("/complaints/{cid}/decide")
    async def decide(cid: str, body: DecideIn, user=Depends(get_current_user)):
        c, viewer = await _complaint_for(cid, user)
        if not _out(c, viewer)["can_decide"]:
            raise HTTPException(status_code=403, detail="Anda tidak bisa memutuskan komplain ini")
        paid = await _paid(c)
        refundable = max(0, paid - c.get("refunded", 0))
        amount = body.amount if body.action == "refund" else 0
        if body.action == "refund" and refundable <= 0:
            raise HTTPException(status_code=400, detail="Pesanan COD belum dibayar, belum bisa direfund ke saldo")
        if body.action == "refund" and not (0 < amount <= refundable):
            raise HTTPException(status_code=400, detail=f"Nominal refund harus 1 – {refundable}")
        if body.action == "reject" and not body.note.strip():
            raise HTTPException(status_code=400, detail="Tulis alasan penolakan")
        status = {"refund": "refunded", "reject": "rejected", "resolve": "resolved"}[body.action]
        by = "Admin PGS" if viewer == "admin" else c["store_name"]
        res = await db.complaints.find_one_and_update(
            {"complaint_id": cid, "status": c["status"]},
            {"$set": {"status": status, "updated_at": _now(), "decision": {"action": body.action, "amount": amount, "note": body.note.strip(), "by": by, "at": _now()}},
             "$inc": {"refunded": amount}}, projection={"_id": 0}, return_document=ReturnDocument.AFTER)
        if not res:
            raise HTTPException(status_code=409, detail="Komplain sudah diproses, muat ulang")
        if amount:
            await credit(db, c["user_id"], amount, "refund", c["order_id"], f"Refund komplain {cid} ({c['order_id']})")
            await db.orders.update_one({"order_id": c["order_id"]}, {"$inc": {"refunded": amount}})
        msg = {"refund": f"Refund Rp{amount:,} masuk ke Saldo Anda.".replace(",", "."),
               "reject": f"Komplain ditolak: {body.note.strip()}", "resolve": "Komplain dinyatakan selesai."}[body.action]
        await _notify_other(c, viewer, f"Komplain {cid} diputuskan", msg)
        await log_activity(user["user_id"], "order", f"Memutuskan komplain {cid}: {status}")
        return _out(res, viewer, paid)

    # ============================================================ quick replies (per cabang)
    async def _replies(store_id: str) -> list:
        try:  # _id is unique, so only one request ever seeds; deleting all later stays deleted
            await db.quick_replies_seeded.insert_one({"_id": store_id, "at": _now()})
            await db.quick_replies.insert_many([{"reply_id": f"qr_{uuid.uuid4().hex[:10]}", "store_id": store_id, "title": t, "text": x,
                                                 "order": n, "created_at": _now()} for n, (t, x) in enumerate(DEFAULT_REPLIES)])
        except DuplicateKeyError:
            pass
        return await db.quick_replies.find({"store_id": store_id}, {"_id": 0, "store_id": 0}).sort([("order", 1), ("created_at", 1)]).to_list(100)

    @api.get("/seller/quick-replies")
    async def quick_replies(ctx=Depends(require_seller)):
        return {"items": await _replies(ctx["store"]["store_id"])}

    @api.post("/seller/quick-replies")
    async def quick_reply_add(body: QuickReplyIn, ctx=Depends(require_seller)):
        sid = ctx["store"]["store_id"]
        items = await _replies(sid)
        if len(items) >= 50:
            raise HTTPException(status_code=400, detail="Maksimal 50 balasan cepat")
        r = {"reply_id": f"qr_{uuid.uuid4().hex[:10]}", "store_id": sid, "title": body.title.strip(), "text": body.text.strip(),
             "order": max([i.get("order", 0) for i in items], default=-1) + 1, "created_at": _now()}
        await db.quick_replies.insert_one({**r})
        return {k: v for k, v in r.items() if k != "store_id"}

    @api.put("/seller/quick-replies/{reply_id}")
    async def quick_reply_edit(reply_id: str, body: QuickReplyIn, ctx=Depends(require_seller)):
        r = await db.quick_replies.find_one_and_update({"reply_id": reply_id, "store_id": ctx["store"]["store_id"]},
                                                       {"$set": {"title": body.title.strip(), "text": body.text.strip()}},
                                                       projection={"_id": 0, "store_id": 0}, return_document=ReturnDocument.AFTER)
        if not r:
            raise HTTPException(status_code=404, detail="Balasan cepat tidak ditemukan")
        return r

    @api.delete("/seller/quick-replies/{reply_id}")
    async def quick_reply_delete(reply_id: str, ctx=Depends(require_seller)):
        res = await db.quick_replies.delete_one({"reply_id": reply_id, "store_id": ctx["store"]["store_id"]})
        if not res.deleted_count:
            raise HTTPException(status_code=404, detail="Balasan cepat tidak ditemukan")
        return {"ok": True}

    # ============================================================ chat
    async def _conv_for(conv_id: str, user: dict) -> tuple[dict, str]:
        c = await db.conversations.find_one({"conv_id": conv_id}, {"_id": 0})
        if not c:
            raise HTTPException(status_code=404, detail="Chat tidak ditemukan")
        if c["user_id"] == user["user_id"]:
            return c, "user"
        s = await store_of(user)
        if s and s["store_id"] == c["store_id"]:
            return c, "store"
        raise HTTPException(status_code=404, detail="Chat tidak ditemukan")

    async def _open_conv(user_doc: dict, store: dict) -> dict:
        c = await db.conversations.find_one({"user_id": user_doc["user_id"], "store_id": store["store_id"]}, {"_id": 0})
        if c:
            return c
        c = {"conv_id": f"cv_{uuid.uuid4().hex[:12]}", "user_id": user_doc["user_id"], "user_name": user_doc.get("name") or user_doc["email"],
             "store_id": store["store_id"], "store_name": store["name"], "last_text": "", "last_at": _now(),
             "unread_user": 0, "unread_store": 0, "created_at": _now()}
        try:
            await db.conversations.insert_one({**c})
        except Exception:  # created concurrently
            c = await db.conversations.find_one({"user_id": user_doc["user_id"], "store_id": store["store_id"]}, {"_id": 0})
        return c

    @api.post("/chats")
    async def start_chat(body: ChatStartIn, user=Depends(get_current_user)):
        store = await db.stores.find_one({"store_id": body.store_id, "status": "active"}, {"_id": 0})
        if not store:
            raise HTTPException(status_code=404, detail="Toko tidak ditemukan")
        if store["owner_id"] == user["user_id"]:
            raise HTTPException(status_code=400, detail="Ini toko Anda sendiri")
        product = body.product_id and await db.products.find_one(
            {"product_id": body.product_id, "store_id": {"$in": [body.store_id, "pgs-official"]}},
            {"_id": 0, "product_id": 1, "name": 1, "image": 1, "price": 1, "sku": 1})
        if not product and not await db.orders.find_one({"user_id": user["user_id"], "store_id": body.store_id}, {"_id": 1}):
            raise HTTPException(status_code=403, detail="Chat tersedia setelah Anda memesan di toko ini")
        c = await _open_conv(user, store)
        if product:  # tell the store which product the buyer is looking at (once, unless they switch product)
            last = await db.chat_messages.find_one({"conv_id": c["conv_id"]}, {"_id": 0, "product": 1}, sort=[("created_at", -1)])
            if not last or (last.get("product") or {}).get("product_id") != product["product_id"]:
                await _post(c, "user", f"Halo, saya ingin bertanya tentang produk ini:\n{product['name']}", product)
                c = await db.conversations.find_one({"conv_id": c["conv_id"]}, {"_id": 0})
        return c

    @api.post("/seller/chats")
    async def seller_start_chat(body: SellerChatStartIn, ctx=Depends(require_seller)):
        o = await db.orders.find_one({"order_id": body.order_id, "store_id": ctx["store"]["store_id"]})
        if not o or not o.get("user_id"):
            raise HTTPException(status_code=400, detail="Pembeli tamu tidak bisa di-chat")
        buyer = await db.users.find_one({"user_id": o["user_id"]}, {"_id": 0, "user_id": 1, "name": 1, "email": 1})
        if not buyer:
            raise HTTPException(status_code=404, detail="Pembeli tidak ditemukan")
        return await _open_conv(buyer, ctx["store"])

    @api.get("/chats")
    async def my_chats(user=Depends(get_current_user)):
        return await db.conversations.find({"user_id": user["user_id"]}, {"_id": 0}).sort("last_at", -1).to_list(200)

    @api.get("/seller/chats")
    async def store_chats(ctx=Depends(require_seller)):
        return await db.conversations.find({"store_id": ctx["store"]["store_id"]}, {"_id": 0}).sort("last_at", -1).to_list(300)

    @api.get("/chats/unread")
    async def chat_unread(user=Depends(get_current_user)):
        mine = await db.conversations.aggregate([{"$match": {"user_id": user["user_id"]}},
                                                 {"$group": {"_id": None, "n": {"$sum": "$unread_user"}}}]).to_list(1)
        s = await store_of(user)
        store = await db.conversations.aggregate([{"$match": {"store_id": s["store_id"]}},
                                                  {"$group": {"_id": None, "n": {"$sum": "$unread_store"}}}]).to_list(1) if s else []
        return {"buyer": mine[0]["n"] if mine else 0, "store": store[0]["n"] if store else 0}

    @api.get("/chats/{conv_id}")
    async def chat_thread(conv_id: str, after: Optional[str] = None, user=Depends(get_current_user)):
        c, me = await _conv_for(conv_id, user)
        q: dict = {"conv_id": conv_id}
        if after:
            try:
                q["created_at"] = {"$gt": _aware(datetime.fromisoformat(after.replace("Z", "+00:00")))}
            except ValueError:
                pass
        msgs = await db.chat_messages.find(q, {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)
        if c[f"unread_{me}"]:
            await db.conversations.update_one({"conv_id": conv_id}, {"$set": {f"unread_{me}": 0}})
        return {"conversation": {**c, f"unread_{me}": 0}, "me": me, "messages": list(reversed(msgs))}

    @api.post("/chats/{conv_id}/messages")
    async def send_message(conv_id: str, body: TextIn, user=Depends(get_current_user)):
        c, me = await _conv_for(conv_id, user)
        text = body.text.strip()
        if not text:
            raise HTTPException(status_code=400, detail="Pesan kosong")
        return await _post(c, me, text)

    async def _post(c: dict, me: str, text: str, product: Optional[dict] = None) -> dict:
        conv_id = c["conv_id"]
        m = {"msg_id": f"m_{uuid.uuid4().hex[:12]}", "conv_id": conv_id, "sender": me, "text": text, "created_at": _now()}
        if product:
            m["product"] = {"product_id": product["product_id"], "name": product["name"], "image": product.get("image", ""),
                            "price": product.get("price", 0), "sku": product.get("sku", "")}
        await db.chat_messages.insert_one({**m})
        other = "store" if me == "user" else "user"
        await db.conversations.update_one({"conv_id": conv_id}, {"$set": {"last_text": text[:120], "last_at": m["created_at"], "last_sender": me},
                                                                 "$inc": {f"unread_{other}": 1}})
        if not c[f"unread_{other}"]:  # first unread only, avoid spamming the inbox
            if other == "user":
                await notify_user(c["user_id"], "order", f"Pesan dari {c['store_name']}", text[:100], f"/chat/{conv_id}")
            else:
                s = await db.stores.find_one({"store_id": c["store_id"]}, {"owner_id": 1})
                if s:
                    await notify_user(s["owner_id"], "order", f"Pesan dari {c['user_name']}", text[:100], f"/chat/{conv_id}")
        return m
