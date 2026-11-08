# PGS iteration 8: COD refund rule, chat unread badges API, real RajaOngkir auto rates + COD test orders per store.
# Run serially: pytest tests/test_pgs_iter8_cod_shipping.py -n 0   (shared module state)
# NEVER prints / reads the RajaOngkir key or key_hint.
import os
import json
import uuid
import asyncio
import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
SHIP = {"full_name": "TEST_Ongkir Buyer", "phone": "081234567890", "address": "Jl. Test No 8", "city": "Surabaya"}
PID = "pgs-9955"
STORES = {"pgs-official": ("sidoarjo@pgs.id", "Sidoarjo123!"), "pgs-jombang": ("jombang@pgs.id", "Jombang123!"),
          "pgs-jember": ("jember@pgs.id", "Jember123!")}
DESTS = {"Gubeng Surabaya": 69243, "Lowokwaru Malang": 46757, "Gambir Jakarta Pusat": 17601}
S = {"rates": {}, "orders": {}}
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


def _stock(store):
    r = requests.get(f"{API}/products/{PID}", headers={"X-Store-Id": store})
    assert r.status_code == 200, r.text
    return r.json()["stock"]


def _order(h, store, courier="jne", **extra):
    hh = {**h, "X-Store-Id": store}
    r = requests.post(f"{API}/cart/items", headers=hh, json={"product_id": PID, "quantity": 1})
    assert r.status_code == 200, r.text
    r = requests.post(f"{API}/checkout", headers=hh, json={**SHIP, "payment_method": "cod", "courier": courier, "store_id": store, **extra})
    assert r.status_code == 200, r.text
    ORDERS.append(r.json()["order_id"])
    return r.json()


def _status(sh, oid, st, **kw):
    r = requests.put(f"{API}/seller/orders/{oid}/status", headers=sh, json={"status": st, **kw})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module", autouse=True)
def setup():
    S["admin"] = _login("admin@pgs.id", "Admin1234!")
    for sid, (e, p) in STORES.items():
        S[sid] = _login(e, p)
    email = f"test_ongkir_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "Test1234!", "name": "TEST_Ongkir"})
    assert r.status_code == 200, r.text
    S["buyer"] = {"Authorization": f"Bearer {r.json()['token']}"}
    S["uid"] = r.json()["user"]["user_id"]
    yield
    with open("/app/test_reports/pytest/iter8_shipping_results.json", "w") as f:
        json.dump({"rates": S["rates"], "orders": S["orders"]}, f, indent=1, default=str)
    uid = S["uid"]
    for oid in ORDERS:  # restore stock of every test order (admin cancel restocks once)
        requests.put(f"{API}/admin/orders/{oid}/status", headers=S["admin"], json={"status": "cancelled"})

    async def clean(db):
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


# --- shipping status / destinations / rates (real RajaOngkir)
class TestShippingAuto:
    def test_status_auto(self):
        r = requests.get(f"{API}/shipping/status")
        assert r.status_code == 200 and r.json() == {"auto": True}, r.text

    def test_destinations(self):
        r = requests.get(f"{API}/shipping/destinations", params={"q": "gubeng"}, headers=S["buyer"])
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["auto"] is True and any(x["id"] == 69243 for x in d["data"]), d
        assert all(isinstance(x["id"], int) and x["label"] for x in d["data"])
        assert requests.get(f"{API}/shipping/destinations", params={"q": "gu"}, headers=S["buyer"]).status_code == 422
        assert set(d) == {"auto", "data"} and all(set(x) == {"id", "label"} for x in d["data"])  # nothing else (no key) leaks

    @pytest.mark.parametrize("store", list(STORES))
    def test_rates_auto_per_store(self, store):
        for label, dest in DESTS.items():
            r = requests.post(f"{API}/shipping/rates", headers=S["buyer"], json={"store_id": store, "destination_id": dest})
            assert r.status_code == 200, r.text
            opts = r.json()
            S["rates"].setdefault(store, {})[label] = [{k: o.get(k) for k in ("code", "name", "cost", "eta", "source")} for o in opts]
            auto = {o["code"]: o for o in opts if o["source"] == "auto"}
            assert {"jne", "jnt", "sicepat"} <= set(auto), f"{store} {label}: {opts}"
            assert all(isinstance(o["cost"], int) and o["cost"] > 0 for o in auto.values())

    def test_rates_manual_fallback(self):
        r = requests.post(f"{API}/shipping/rates", headers=S["buyer"], json={"store_id": "pgs-official"})
        assert r.status_code == 200, r.text
        opts = r.json()
        assert opts and all(o["source"] == "manual" for o in opts), opts
        S["rates"]["pgs-official"]["(no destination)"] = [{k: o.get(k) for k in ("code", "name", "cost", "source")} for o in opts]
        assert requests.post(f"{API}/shipping/rates", headers=S["buyer"], json={"store_id": "nope", "destination_id": 69243}).status_code == 404


# --- COD test orders per store with auto rates, then cancel (stock restored)
class TestCodOrdersAuto:
    @pytest.mark.parametrize("store,courier", [("pgs-official", "jne"), ("pgs-jombang", "jnt"), ("pgs-jember", "sicepat")])
    def test_cod_order_auto_rate_and_cancel(self, store, courier):
        stock0 = _stock(store)
        quoted = next(o for o in S["rates"][store]["Gubeng Surabaya"] if o["code"] == courier)
        o = _order(S["buyer"], store, courier=courier, destination_id=69243)
        S["orders"][store] = {"order_id": o["order_id"], "courier": o["courier"], "subtotal": o["subtotal"],
                              "shipping_cost": o["shipping_cost"], "total": o["total"], "status": o["status"]}
        assert o["status"] == "cod" and o["store_id"] == store
        assert o["shipping_cost"] == quoted["cost"] and o["courier"]["source"] == "auto", (o["courier"], quoted)
        assert o["total"] == o["subtotal"] - o.get("discount", 0) + o["shipping_cost"]
        assert _stock(store) == stock0 - 1
        _status(S[store], o["order_id"], "cancelled")
        S["orders"][store]["final_status"] = "cancelled"
        assert _stock(store) == stock0

    def test_tampered_cost_ignored(self):
        """Client-sent shipping_cost must be ignored (server recalculates)."""
        o = _order(S["buyer"], "pgs-official", courier="jne", destination_id=69243, shipping_cost=1)
        assert o["shipping_cost"] > 1
        _status(S["pgs-official"], o["order_id"], "cancelled")


# --- COD refund rule
class TestCodRefundRule:
    def test_cod_unpaid_then_completed(self):
        sh = S["pgs-official"]
        o = _order(S["buyer"], "pgs-official")
        _status(sh, o["order_id"], "processing")
        _status(sh, o["order_id"], "shipped", tracking_number="TESTRESI8")
        r = requests.post(f"{API}/complaints", headers=S["buyer"], json={"order_id": o["order_id"], "reason": "damaged", "description": "Barang rusak parah sekali", "refund_amount": 5000})
        assert r.status_code == 200, r.text
        cid = r.json()["complaint_id"]
        COMPLAINTS.append(cid)
        for who in ("buyer", "pgs-official", "admin"):
            c = requests.get(f"{API}/complaints/{cid}", headers=S[who]).json()
            assert c["refundable"] == 0 and c["cod_unpaid"] is True, (who, c["refundable"], c["cod_unpaid"])
        r = requests.post(f"{API}/complaints/{cid}/decide", headers=sh, json={"action": "refund", "amount": 5000})
        assert r.status_code == 400 and "COD belum dibayar" in r.json()["detail"], r.text
        assert requests.get(f"{API}/wallet", headers=S["buyer"]).json()["balance"] == 0
        _status(sh, o["order_id"], "completed")
        c = requests.get(f"{API}/complaints/{cid}", headers=S["buyer"]).json()
        assert c["refundable"] == o["total"] and c["cod_unpaid"] is False, c
        r = requests.post(f"{API}/complaints/{cid}/decide", headers=sh, json={"action": "refund", "amount": o["total"] + 1})
        assert r.status_code == 400, r.text
        r = requests.post(f"{API}/complaints/{cid}/decide", headers=sh, json={"action": "refund", "amount": 5000})
        assert r.status_code == 200 and r.json()["status"] == "refunded" and r.json()["refundable"] == o["total"] - 5000, r.text
        w = requests.get(f"{API}/wallet", headers=S["buyer"]).json()
        assert w["balance"] == 5000 and w["transactions"][0]["kind"] == "refund"
        S["refunded_order"] = o

    def test_cod_partial_balance_refundable_only_saldo(self):
        """COD + saldo 5000 used, shipped -> refundable is only the saldo portion."""
        sh = S["pgs-official"]
        o = _order(S["buyer"], "pgs-official", use_balance=True)
        assert o["balance_used"] == 5000 and o["payment_method"] == "cod", o
        _status(sh, o["order_id"], "processing")
        _status(sh, o["order_id"], "shipped", tracking_number="TESTRESI9")
        r = requests.post(f"{API}/complaints", headers=S["buyer"], json={"order_id": o["order_id"], "reason": "missing", "description": "Barang kurang satu pcs", "refund_amount": 9000})
        assert r.status_code == 200, r.text
        cid = r.json()["complaint_id"]
        COMPLAINTS.append(cid)
        c = requests.get(f"{API}/complaints/{cid}", headers=sh).json()
        assert c["refundable"] == 5000 and c["cod_unpaid"] is True, c
        assert requests.post(f"{API}/complaints/{cid}/decide", headers=sh, json={"action": "refund", "amount": 5001}).status_code == 400
        r = requests.post(f"{API}/complaints/{cid}/decide", headers=sh, json={"action": "refund", "amount": 5000})
        assert r.status_code == 200, r.text
        assert requests.get(f"{API}/wallet", headers=S["buyer"]).json()["balance"] == 5000
        # store admin cannot cancel a shipped order; super admin can -> no double saldo return
        assert requests.put(f"{API}/seller/orders/{o['order_id']}/status", headers=sh, json={"status": "cancelled"}).status_code == 400
        r = requests.put(f"{API}/admin/orders/{o['order_id']}/status", headers=S["admin"], json={"status": "cancelled"})
        assert r.status_code == 200, r.text
        assert requests.get(f"{API}/wallet", headers=S["buyer"]).json()["balance"] == 5000


# --- chat + unread counters
class TestChatUnread:
    def test_unread_flow(self):
        sh = S["pgs-official"]
        oid = S["refunded_order"]["order_id"]
        r = requests.post(f"{API}/chats", headers=S["buyer"], json={"store_id": "pgs-official", "order_id": oid})
        assert r.status_code == 200, r.text
        cv = r.json()["conv_id"]
        CONVS.append(cv)
        assert requests.post(f"{API}/seller/chats", headers=sh, json={"order_id": oid}).json()["conv_id"] == cv
        assert requests.get(f"{API}/chats/unread", headers=S["buyer"]).json() == {"buyer": 0, "store": 0}
        base_store = requests.get(f"{API}/chats/unread", headers=sh).json()["store"]
        m1 = requests.post(f"{API}/chats/{cv}/messages", headers=S["buyer"], json={"text": "TEST_halo toko"}).json()
        assert requests.get(f"{API}/chats/unread", headers=sh).json()["store"] == base_store + 1
        requests.post(f"{API}/chats/{cv}/messages", headers=sh, json={"text": "TEST_halo kak 1"})
        requests.post(f"{API}/chats/{cv}/messages", headers=sh, json={"text": "TEST_halo kak 2"})
        assert requests.get(f"{API}/chats/unread", headers=S["buyer"]).json()["buyer"] == 2
        # buyer polls after own message -> must see both store messages
        t = requests.get(f"{API}/chats/{cv}", headers=S["buyer"], params={"after": m1["created_at"]}).json()
        assert [m["text"] for m in t["messages"]] == ["TEST_halo kak 1", "TEST_halo kak 2"], t["messages"]
        assert requests.get(f"{API}/chats/unread", headers=S["buyer"]).json()["buyer"] == 0
        requests.get(f"{API}/chats/{cv}", headers=sh)
        assert requests.get(f"{API}/chats/unread", headers=sh).json()["store"] == base_store
        assert any(c["conv_id"] == cv for c in requests.get(f"{API}/chats", headers=S["buyer"]).json())
        assert requests.get(f"{API}/chats/{cv}", headers=S["pgs-jombang"]).status_code == 404
        assert requests.get(f"{API}/chats/unread").status_code == 401
