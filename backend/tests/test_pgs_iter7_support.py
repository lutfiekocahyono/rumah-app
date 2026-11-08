# PGS iteration 7: Saldo (wallet), Komplain & Refund, buyer<->store chat, checkout with saldo.
import os
import uuid
import asyncio
import time
from datetime import datetime, timedelta, timezone
import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
SHIP = {"full_name": "TEST_Komplain Buyer", "phone": "081234567890", "address": "Jl. Test No 7", "city": "Sidoarjo"}
PID = "pgs-9955"
STORE = "pgs-official"
S = {}  # shared state
ORDERS, COMPLAINTS, CONVS = [], [], []


def _db(fn):
    async def run():
        cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
        try:
            return await fn(cli[os.environ["DB_NAME"]])
        finally:
            cli.close()
    return asyncio.run(run())


def _login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _order(h, **extra):
    hh = {**h, "X-Store-Id": STORE}
    r = requests.post(f"{API}/cart/items", headers=hh, json={"product_id": PID, "quantity": 1})
    assert r.status_code == 200, r.text
    r = requests.post(f"{API}/checkout", headers=hh, json={**SHIP, "payment_method": "cod", "courier": "jne", "store_id": STORE, **extra})
    assert r.status_code == 200, r.text
    ORDERS.append(r.json()["order_id"])
    return r.json()


def _ship(sh, oid):
    r = requests.put(f"{API}/seller/orders/{oid}/status", headers=sh, json={"status": "processing"})
    assert r.status_code == 200, r.text
    r = requests.put(f"{API}/seller/orders/{oid}/status", headers=sh, json={"status": "shipped", "tracking_number": "TESTRESI123"})
    assert r.status_code == 200, r.text


@pytest.fixture(scope="module", autouse=True)
def setup():
    S["admin"] = _login("admin@pgs.id", "Admin1234!")
    S["sid"] = _login("sidoarjo@pgs.id", "Sidoarjo123!")
    S["jom"] = _login("jombang@pgs.id", "Jombang123!")
    email = f"test_kmp_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "Test1234!", "name": "TEST_Komplain"})
    assert r.status_code == 200, r.text
    S["buyer"] = {"Authorization": f"Bearer {r.json()['token']}"}
    S["uid"] = r.json()["user"]["user_id"]
    yield
    uid = S["uid"]

    async def clean(db):
        for oid in ORDERS:
            o = await db.orders.find_one({"order_id": oid})
            if o and not o.get("restocked"):
                for i in o["items"]:
                    await db.products.update_one({"product_id": i["product_id"], "stock": {"$ne": 9999}}, {"$inc": {"stock": i["quantity"]}})
        await db.orders.delete_many({"order_id": {"$in": ORDERS}})
        await db.complaints.delete_many({"complaint_id": {"$in": COMPLAINTS}})
        await db.conversations.delete_many({"conv_id": {"$in": CONVS}})
        await db.chat_messages.delete_many({"conv_id": {"$in": CONVS}})
        links = [f"/complaint/{c}" for c in COMPLAINTS] + [f"/chat/{c}" for c in CONVS] + [f"/order/{o}" for o in ORDERS]
        await db.notifications.delete_many({"link": {"$in": links}})
        await db.wallets.delete_many({"user_id": uid})
        await db.wallet_tx.delete_many({"user_id": uid})
        await db.carts.delete_many({"owner": f"user:{uid}"})
        await db.users.delete_many({"user_id": uid})
    _db(clean)


# --- complaint eligibility
class TestComplaintCreate:
    def test_not_shipped_rejected(self):
        o = _order(S["buyer"])
        S["o1"] = o
        r = requests.post(f"{API}/complaints", headers=S["buyer"], json={"order_id": o["order_id"], "reason": "damaged", "description": "Barang rusak parah sekali", "refund_amount": 1000})
        assert r.status_code == 400, r.text

    def test_other_user_order_404(self):
        r = requests.post(f"{API}/complaints", headers=S["jom"], json={"order_id": S["o1"]["order_id"], "reason": "damaged", "description": "Barang rusak parah sekali", "refund_amount": 0})
        assert r.status_code == 404

    def test_validation_and_create(self):
        oid = S["o1"]["order_id"]
        _ship(S["sid"], oid)
        b = {"order_id": oid, "reason": "damaged", "description": "Barang rusak parah sekali", "refund_amount": S["o1"]["total"] + 1}
        assert requests.post(f"{API}/complaints", headers=S["buyer"], json=b).status_code == 400
        assert requests.post(f"{API}/complaints", headers=S["buyer"], json={**b, "description": "short", "refund_amount": 1}).status_code == 422
        assert requests.post(f"{API}/complaints", headers=S["buyer"], json={**b, "reason": "bad", "refund_amount": 1}).status_code == 422
        r = requests.post(f"{API}/complaints", headers=S["buyer"], json={**b, "refund_amount": 5000})
        assert r.status_code == 200, r.text
        c = r.json()
        COMPLAINTS.append(c["complaint_id"])
        S["cid"] = c["complaint_id"]
        assert c["status"] == "open" and c["viewer"] == "buyer" and c["refund_amount"] == 5000
        assert c["store_id"] == STORE and len(c["messages"]) == 1 and c["can_reply"] and not c["can_decide"]
        od = requests.get(f"{API}/orders/{oid}", headers=S["buyer"])
        assert od.status_code == 200 and od.json().get("complaint_id") == c["complaint_id"], od.text[:300]

    def test_duplicate(self):
        r = requests.post(f"{API}/complaints", headers=S["buyer"], json={"order_id": S["o1"]["order_id"], "reason": "other", "description": "Lagi komplain dua kali", "refund_amount": 0})
        assert r.status_code == 400

    def test_expired_7_days(self):
        o = _order(S["buyer"])
        _ship(S["sid"], o["order_id"])
        old = datetime.now(timezone.utc) - timedelta(days=8)

        async def age(db):
            await db.orders.update_one({"order_id": o["order_id"], "status_history.status": "shipped"}, {"$set": {"status_history.$[].at": old}})
        _db(age)
        r = requests.post(f"{API}/complaints", headers=S["buyer"], json={"order_id": o["order_id"], "reason": "missing", "description": "Barang kurang satu pcs", "refund_amount": 0})
        assert r.status_code == 400 and "7" in r.json()["detail"], r.text


# --- access + lists
class TestComplaintAccess:
    def test_views(self):
        cid = S["cid"]
        assert requests.get(f"{API}/complaints/{cid}", headers=S["sid"]).json()["viewer"] == "store"
        assert requests.get(f"{API}/complaints/{cid}", headers=S["admin"]).json()["viewer"] == "admin"
        assert requests.get(f"{API}/complaints/{cid}", headers=S["jom"]).status_code == 404
        assert requests.get(f"{API}/complaints/KMP-NOPE0000", headers=S["buyer"]).status_code == 404

    def test_lists(self):
        cid = S["cid"]
        assert cid in [c["complaint_id"] for c in requests.get(f"{API}/complaints", headers=S["buyer"]).json()]
        st = requests.get(f"{API}/seller/complaints?status=active", headers=S["sid"])
        assert st.status_code == 200 and cid in [c["complaint_id"] for c in st.json()]
        jm = requests.get(f"{API}/seller/complaints", headers=S["jom"]).json()
        assert cid not in [c["complaint_id"] for c in jm]
        ad = requests.get(f"{API}/admin/complaints", headers=S["admin"])
        assert ad.status_code == 200 and cid in [c["complaint_id"] for c in ad.json()]
        assert requests.get(f"{API}/admin/complaints", headers=S["sid"]).status_code in (401, 403)
        assert requests.get(f"{API}/seller/complaints", headers=S["buyer"]).status_code == 403


# --- messages / decide / escalate / refund
class TestComplaintFlow:
    def test_messages(self):
        cid = S["cid"]
        r = requests.post(f"{API}/complaints/{cid}/messages", headers=S["sid"], json={"text": "Mohon kirim detail"})
        assert r.status_code == 200 and r.json()["messages"][-1]["by"] == "store"
        r = requests.post(f"{API}/complaints/{cid}/messages", headers=S["buyer"], json={"text": "Kardus penyok"})
        assert r.status_code == 200 and r.json()["messages"][-1]["by"] == "buyer"
        assert requests.post(f"{API}/complaints/{cid}/messages", headers=S["jom"], json={"text": "x"}).status_code == 404
        assert requests.post(f"{API}/complaints/{cid}/messages", headers=S["buyer"], json={"text": ""}).status_code == 422

    def test_escalate_before_reject(self):
        assert requests.post(f"{API}/complaints/{S['cid']}/escalate", headers=S["buyer"], json={"text": "tolong"}).status_code == 400

    def test_decide_rules(self):
        cid = S["cid"]
        assert requests.post(f"{API}/complaints/{cid}/decide", headers=S["buyer"], json={"action": "refund", "amount": 100}).status_code == 403
        assert requests.post(f"{API}/complaints/{cid}/decide", headers=S["jom"], json={"action": "reject", "note": "x"}).status_code == 404
        assert requests.post(f"{API}/complaints/{cid}/decide", headers=S["sid"], json={"action": "reject", "note": "  "}).status_code == 400
        r = requests.post(f"{API}/complaints/{cid}/decide", headers=S["sid"], json={"action": "reject", "note": "TEST_Foto tidak ada"})
        assert r.status_code == 200 and r.json()["status"] == "rejected" and r.json()["can_reply"] is False
        assert requests.post(f"{API}/complaints/{cid}/decide", headers=S["sid"], json={"action": "resolve"}).status_code == 403
        assert requests.post(f"{API}/complaints/{cid}/messages", headers=S["buyer"], json={"text": "hmm"}).status_code == 400
        assert requests.get(f"{API}/complaints/{cid}", headers=S["buyer"]).json()["can_escalate"] is True

    def test_escalate(self):
        cid = S["cid"]
        assert requests.post(f"{API}/complaints/{cid}/escalate", headers=S["sid"], json={"text": "x"}).status_code == 400
        r = requests.post(f"{API}/complaints/{cid}/escalate", headers=S["buyer"], json={"text": "Mohon admin bantu"})
        assert r.status_code == 200 and r.json()["status"] == "escalated" and r.json()["can_escalate"] is False
        assert requests.post(f"{API}/complaints/{cid}/decide", headers=S["sid"], json={"action": "resolve"}).status_code == 403
        assert requests.get(f"{API}/complaints/{cid}", headers=S["admin"]).json()["can_decide"] is True

    def test_admin_refund_wallet(self):
        cid = S["cid"]
        refundable = requests.get(f"{API}/complaints/{cid}", headers=S["admin"]).json()["refundable"]
        assert refundable == S["o1"]["total"]
        assert requests.post(f"{API}/complaints/{cid}/decide", headers=S["admin"], json={"action": "refund", "amount": 0}).status_code == 400
        assert requests.post(f"{API}/complaints/{cid}/decide", headers=S["admin"], json={"action": "refund", "amount": refundable + 1}).status_code == 400
        r = requests.post(f"{API}/complaints/{cid}/decide", headers=S["admin"], json={"action": "refund", "amount": 5000, "note": "TEST ok"})
        assert r.status_code == 200 and r.json()["status"] == "refunded" and r.json()["refunded"] == 5000
        assert r.json()["decision"]["by"] == "Admin PGS"
        w = requests.get(f"{API}/wallet", headers=S["buyer"]).json()
        assert w["balance"] == 5000
        assert w["transactions"][0]["kind"] == "refund" and w["transactions"][0]["amount"] == 5000
        assert requests.post(f"{API}/complaints/{cid}/escalate", headers=S["buyer"], json={"text": "lagi"}).status_code == 400
        assert requests.post(f"{API}/complaints/{cid}/decide", headers=S["admin"], json={"action": "refund", "amount": 1}).status_code == 403


# --- checkout with saldo
class TestSaldoCheckout:
    def test_partial_balance_and_cancel_return(self):
        o = _order(S["buyer"], use_balance=True)
        assert o.get("balance_used") == 5000, o
        assert o["payment_method"] == "cod" and o["status"] == "cod"
        assert requests.get(f"{API}/wallet", headers=S["buyer"]).json()["balance"] == 0
        r = requests.put(f"{API}/seller/orders/{o['order_id']}/status", headers=S["sid"], json={"status": "cancelled"})
        assert r.status_code == 200, r.text
        w = requests.get(f"{API}/wallet", headers=S["buyer"]).json()
        assert w["balance"] == 5000 and w["transactions"][0]["kind"] == "return"
        requests.put(f"{API}/seller/orders/{o['order_id']}/status", headers=S["sid"], json={"status": "cancelled"})
        assert requests.get(f"{API}/wallet", headers=S["buyer"]).json()["balance"] == 5000

    def test_saldo_method_insufficient(self):
        hh = {**S["buyer"], "X-Store-Id": STORE}
        requests.post(f"{API}/cart/items", headers=hh, json={"product_id": PID, "quantity": 1})
        r = requests.post(f"{API}/checkout", headers=hh, json={**SHIP, "payment_method": "saldo", "courier": "jne", "store_id": STORE})
        assert r.status_code == 400, r.text

    def test_full_coverage(self):
        uid = S["uid"]

        async def topup(db):
            await db.wallets.update_one({"user_id": uid}, {"$inc": {"balance": 10_000_000}}, upsert=True)
        _db(topup)
        o = _order(S["buyer"], use_balance=True)
        assert o["payment_method"] == "saldo" and o["status"] == "paid" and o["balance_used"] == o["total"], o
        assert requests.get(f"{API}/wallet", headers=S["buyer"]).json()["balance"] == 10_005_000 - o["total"]
        S["paid_order"] = o["order_id"]
        r = requests.put(f"{API}/seller/orders/{o['order_id']}/status", headers=S["sid"], json={"status": "processing"})
        assert r.status_code == 200

    def test_guest_cannot_use_balance(self):
        gid = f"guest_TEST_{uuid.uuid4().hex[:8]}"
        g = {"X-Guest-Id": gid, "X-Store-Id": STORE}
        requests.post(f"{API}/cart/items", headers=g, json={"product_id": PID, "quantity": 1})
        r = requests.post(f"{API}/checkout", headers=g, json={**SHIP, "payment_method": "cod", "courier": "jne", "store_id": STORE, "use_balance": True})
        assert r.status_code == 400
        requests.delete(f"{API}/cart", headers=g)


# --- chat
class TestChat:
    def test_start_rules(self):
        assert requests.post(f"{API}/chats", headers=S["buyer"], json={"store_id": "pgs-jombang"}).status_code == 403
        assert requests.post(f"{API}/chats", headers=S["buyer"], json={"store_id": "nope-store"}).status_code == 404
        assert requests.post(f"{API}/chats", headers=S["sid"], json={"store_id": STORE}).status_code == 400
        r = requests.post(f"{API}/chats", headers=S["buyer"], json={"store_id": STORE})
        assert r.status_code == 200 and r.json()["store_id"] == STORE
        S["conv"] = r.json()["conv_id"]
        CONVS.append(S["conv"])
        assert requests.post(f"{API}/chats", headers=S["buyer"], json={"store_id": STORE}).json()["conv_id"] == S["conv"]
        r = requests.post(f"{API}/seller/chats", headers=S["sid"], json={"order_id": S["o1"]["order_id"]})
        assert r.status_code == 200 and r.json()["conv_id"] == S["conv"]
        assert requests.post(f"{API}/seller/chats", headers=S["jom"], json={"order_id": S["o1"]["order_id"]}).status_code in (400, 404)

    def test_messages_unread_after(self):
        cv = S["conv"]
        base_unread = requests.get(f"{API}/chats/unread", headers=S["sid"]).json()["store"]
        m1 = requests.post(f"{API}/chats/{cv}/messages", headers=S["buyer"], json={"text": "Halo toko"})
        assert m1.status_code == 200 and m1.json()["sender"] == "user"
        assert requests.get(f"{API}/chats/unread", headers=S["sid"]).json()["store"] == base_unread + 1
        assert cv in [c["conv_id"] for c in requests.get(f"{API}/seller/chats", headers=S["sid"]).json()]
        assert cv in [c["conv_id"] for c in requests.get(f"{API}/chats", headers=S["buyer"]).json()]
        t = requests.get(f"{API}/chats/{cv}", headers=S["sid"]).json()
        assert t["me"] == "store" and t["messages"][-1]["text"] == "Halo toko"
        assert requests.get(f"{API}/chats/unread", headers=S["sid"]).json()["store"] == base_unread
        assert requests.get(f"{API}/chats/{cv}", headers=S["jom"]).status_code == 404
        assert requests.post(f"{API}/chats/{cv}/messages", headers=S["jom"], json={"text": "x"}).status_code == 404
        assert requests.post(f"{API}/chats/{cv}/messages", headers=S["sid"], json={"text": "   "}).status_code == 400
        time.sleep(0.05)
        m2 = requests.post(f"{API}/chats/{cv}/messages", headers=S["sid"], json={"text": "Halo kak"})
        assert m2.status_code == 200
        assert requests.get(f"{API}/chats/unread", headers=S["buyer"]).json()["buyer"] == 1
        after = requests.get(f"{API}/chats/{cv}", headers=S["buyer"]).json()["messages"][0]["created_at"]
        assert requests.get(f"{API}/chats/unread", headers=S["buyer"]).json()["buyer"] == 0
        r = requests.get(f"{API}/chats/{cv}", headers=S["buyer"], params={"after": after}).json()
        assert [m["text"] for m in r["messages"]] == ["Halo kak"], r["messages"]
        # aware timestamp returned by POST used as cursor
        r = requests.get(f"{API}/chats/{cv}", headers=S["buyer"], params={"after": m2.json()["created_at"]}).json()
        assert r["messages"] == [], r["messages"]
