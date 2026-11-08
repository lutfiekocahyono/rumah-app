# PGS iteration 36: chat product card from product page + Accurate Tahap 2 (pull sync preview/apply, sales invoices).
# Requires mock Accurate host: cd /app/backend && python tests/accurate_mock.py 9911 &
import os
import uuid
from datetime import datetime, timezone

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
PID, SKU = "pgs-9957", "SGCTK7CKGD"


def _env(k):
    for line in open("/app/backend/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip('"')


DB = MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]
CREATED_MSGS, CREATED_ORDERS = [], []


def _login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=20)
    if r.status_code != 200:
        pytest.skip(f"login failed for {email}: {r.status_code}")
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def admin():
    return _login("admin@pgs.id", "Admin1234!")


@pytest.fixture(scope="module")
def demo():
    return _login("demo@pgs.id", "Demo1234!")


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    if CREATED_MSGS:
        DB.chat_messages.delete_many({"msg_id": {"$in": CREATED_MSGS}})
    if CREATED_ORDERS:
        DB.orders.delete_many({"order_id": {"$in": CREATED_ORDERS}})
    # revert requested by main agent
    DB.products.update_one({"product_id": PID}, {"$set": {"price": 915000, "original_price": 915000, "discount": 0, "stock": 0, "in_stock": False}, "$unset": {"restocked_at": ""}})
    DB.store_stock.update_one({"store_id": "pgs-jombang", "product_id": PID}, {"$set": {"stock": 0}})
    DB.products.delete_many({"source": "accurate"})
    DB.price_history.delete_many({"source": "accurate"})


def _msgs(h, conv_id):
    r = requests.get(f"{API}/chats/{conv_id}", headers=h, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["messages"]


# ---------------- Chat product card
class TestChatProductCard:
    def test_card_added_once_then_new_on_switch(self, demo):
        r = requests.post(f"{API}/chats", json={"store_id": "pgs-jombang", "product_id": PID}, headers=demo, timeout=20)
        assert r.status_code == 200, r.text
        conv = r.json()["conv_id"]
        m = _msgs(demo, conv)
        last = m[-1]
        CREATED_MSGS.append(last["msg_id"])
        name = DB.products.find_one({"product_id": PID})["name"]
        assert last["product"]["product_id"] == PID and last["product"]["name"] == name
        assert name in last["text"] and last["sender"] == "user"
        assert last["product"]["sku"] == SKU and last["product"]["price"] > 0
        n = len(m)
        # same product again -> no duplicate
        r = requests.post(f"{API}/chats", json={"store_id": "pgs-jombang", "product_id": PID}, headers=demo, timeout=20)
        assert r.status_code == 200 and r.json()["conv_id"] == conv
        assert len(_msgs(demo, conv)) == n
        # different product -> new card
        r = requests.post(f"{API}/chats", json={"store_id": "pgs-jombang", "product_id": "pgs-9955"}, headers=demo, timeout=20)
        assert r.status_code == 200
        m2 = _msgs(demo, conv)
        assert len(m2) == n + 1 and m2[-1]["product"]["product_id"] == "pgs-9955"
        CREATED_MSGS.append(m2[-1]["msg_id"])

    def test_product_from_other_store_rejected_card(self, demo):
        # product not in store/pgs-official -> no card; user has no orders w/ fake store -> 404 store
        r = requests.post(f"{API}/chats", json={"store_id": "no-such-store", "product_id": PID}, headers=demo, timeout=20)
        assert r.status_code == 404


# ---------------- Accurate sync (pull)
class TestAccurateSync:
    def test_non_admin_forbidden(self, demo):
        assert requests.post(f"{API}/admin/accurate/sync/preview", json={}, headers=demo, timeout=20).status_code == 403
        assert requests.get(f"{API}/admin/accurate/orders", headers=demo, timeout=20).status_code == 403
        assert requests.post(f"{API}/admin/accurate/invoice/X", json={"confirm": True}, headers=demo, timeout=20).status_code == 403

    def test_preview_apply_skip_reapply(self, admin):
        r = requests.post(f"{API}/admin/accurate/sync/preview", json={"prices": True, "stocks": True, "new_products": True}, headers=admin, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["counts"]["price"] == 1 and d["counts"]["stock"] == 2 and d["counts"]["new"] == 1, d["counts"]
        price = next(c for c in d["changes"] if c["field"] == "price")
        assert price["product_id"] == PID and price["before"] == 915000 and price["after"] == 920000
        stocks = {c["store_id"]: c for c in d["changes"] if c["field"] == "stock"}
        assert stocks["pgs-official"]["after"] == 7 and stocks["pgs-jombang"]["after"] == 3
        assert d["new_items"][0]["no"] == "ACC-NEW-001"
        # nothing saved yet
        assert DB.products.find_one({"product_id": PID})["price"] == 915000
        # GET preview
        assert requests.get(f"{API}/admin/accurate/sync/{d['preview_id']}", headers=admin, timeout=20).json()["counts"] == d["counts"]
        skip = stocks["pgs-jombang"]["key"]
        r = requests.post(f"{API}/admin/accurate/sync/{d['preview_id']}/apply", json={"skip": [skip]}, headers=admin, timeout=60)
        assert r.status_code == 200, r.text
        res = r.json()["result"]
        assert res == {"price": 1, "stock": 1, "new": 1, "conflict": 0}, res
        p = DB.products.find_one({"product_id": PID})
        assert p["price"] == 920000 and p["stock"] == 7 and p["original_price"] == 920000 and p["discount"] == 0
        assert (DB.store_stock.find_one({"store_id": "pgs-jombang", "product_id": PID}) or {}).get("stock", 0) == 0
        # re-apply -> 400
        r = requests.post(f"{API}/admin/accurate/sync/{d['preview_id']}/apply", json={"skip": []}, headers=admin, timeout=20)
        assert r.status_code == 400
        assert DB.price_history.count_documents({"source": "accurate", "product_id": PID}) >= 2
        newp = DB.products.find_one({"source": "accurate", "sku": "ACC-NEW-001"})
        assert newp and newp["status"] == "inactive" and newp["stock"] == 0

    def test_new_product_hidden_publicly(self):
        newp = DB.products.find_one({"source": "accurate", "sku": "ACC-NEW-001"})
        if not newp:
            pytest.skip("no new product")
        r = requests.get(f"{API}/products", params={"q": "Barang Baru Accurate"}, timeout=20)
        assert r.status_code == 200
        body = r.json()
        items = body if isinstance(body, list) else body.get("items") or body.get("products") or []
        assert all(i.get("product_id") != newp["product_id"] for i in items)
        assert requests.get(f"{API}/products/{newp['product_id']}", timeout=20).status_code == 404

    def test_preview_bad_id_404(self, admin):
        assert requests.get(f"{API}/admin/accurate/sync/acs_nope", headers=admin, timeout=20).status_code == 404


# ---------------- Accurate invoices (push)
def _mk_order(store_id, store_name, pid, name, status="paid", pm="transfer"):
    oid = f"TEST_ORD_{uuid.uuid4().hex[:8].upper()}"
    DB.orders.insert_one({"order_id": oid, "user_id": "TEST_u", "items": [{"product_id": pid, "name": name, "price": 213000, "quantity": 2}],
                          "subtotal": 426000, "shipping_cost": 10000, "discount": 6000, "total": 430000, "store_id": store_id, "store_name": store_name,
                          "courier": {"code": "jne"}, "shipping": {"full_name": "TEST Buyer"}, "payment_method": pm, "status": status,
                          "created_at": datetime.now(timezone.utc)})
    CREATED_ORDERS.append(oid)
    return oid


class TestAccurateInvoices:
    def test_invoice_settings(self, admin):
        r = requests.put(f"{API}/admin/accurate/invoice-settings", json={"customer_no": "C.00001", "shipping_item_no": "ONGKIR"}, headers=admin, timeout=20)
        assert r.status_code == 200 and r.json() == {"customer_no": "C.00001", "shipping_item_no": "ONGKIR"}
        assert requests.put(f"{API}/admin/accurate/invoice-settings", json={"customer_no": ""}, headers=admin, timeout=20).status_code == 422

    def test_send_flow(self, admin):
        oid = _mk_order("pgs-jombang", "Mitra PGS Jombang", "pgs-9955", "Casserole 32 Cm Suggo SG-CS32")
        r = requests.get(f"{API}/admin/accurate/orders", params={"sent": "false"}, headers=admin, timeout=20)
        assert r.status_code == 200 and any(o["order_id"] == oid for o in r.json()["items"])
        pv = requests.get(f"{API}/admin/accurate/invoice/{oid}", headers=admin, timeout=20).json()
        assert pv["problems"] == [] and pv["lines"][0]["item_no"] == "SGCS32" and pv["lines"][0]["warehouse"] == "GUDANG JOMBANG"
        assert pv["lines"][-1]["item_no"] == "ONGKIR" and pv["total"] == 426000 + 10000 - 6000
        assert requests.post(f"{API}/admin/accurate/invoice/{oid}", json={"confirm": False}, headers=admin, timeout=20).status_code == 400
        r = requests.post(f"{API}/admin/accurate/invoice/{oid}", json={"confirm": True}, headers=admin, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["accurate_invoice"]["status"] == "sent" and r.json()["accurate_invoice"]["number"] == oid
        assert requests.post(f"{API}/admin/accurate/invoice/{oid}", json={"confirm": True}, headers=admin, timeout=20).status_code == 409
        sent = requests.get(f"{API}/admin/accurate/orders", params={"sent": "true"}, headers=admin, timeout=20).json()["items"]
        assert any(o["order_id"] == oid for o in sent)
        unsent = requests.get(f"{API}/admin/accurate/orders", params={"sent": "false"}, headers=admin, timeout=20).json()["items"]
        assert all(o["order_id"] != oid for o in unsent)
        # mock received the form
        inv = [i for i in requests.get("http://127.0.0.1:9911/accurate/api/_invoices", timeout=5).json() if i.get("number") == oid]
        assert inv and inv[0]["detailItem[0].warehouseName"] == "GUDANG JOMBANG" and inv[0]["cashDiscount"] == "6000"

    def test_problems_block_send(self, admin):
        oid = _mk_order("pgs-jember", "Mitra PGS Jember", "p-rice-01", "Rice Cooker Digital 1.8L")
        pv = requests.get(f"{API}/admin/accurate/invoice/{oid}", headers=admin, timeout=20).json()
        assert len(pv["problems"]) == 2, pv["problems"]
        r = requests.post(f"{API}/admin/accurate/invoice/{oid}", json={"confirm": True}, headers=admin, timeout=20)
        assert r.status_code == 400 and "SKU" in r.json()["detail"]
        assert "accurate_invoice" not in DB.orders.find_one({"order_id": oid})

    def test_cod_not_completed_ineligible(self, admin):
        oid = _mk_order("pgs-official", "PGS Sidoarjo", "pgs-9955", "Casserole", status="shipped", pm="cod")
        unsent = requests.get(f"{API}/admin/accurate/orders", params={"sent": "false"}, headers=admin, timeout=20).json()["items"]
        assert all(o["order_id"] != oid for o in unsent)
        assert requests.post(f"{API}/admin/accurate/invoice/{oid}", json={"confirm": True}, headers=admin, timeout=20).status_code == 400

    def test_unknown_order_404(self, admin):
        assert requests.get(f"{API}/admin/accurate/invoice/NOPE-1", headers=admin, timeout=20).status_code == 404


# ---------------- Edge cases: conflict after preview, Accurate rejection -> failed & retryable
class TestAccurateEdges:
    def test_conflict_when_changed_after_preview(self, admin):
        DB.products.update_one({"product_id": PID}, {"$set": {"price": 915000, "original_price": 915000, "discount": 0}})
        d = requests.post(f"{API}/admin/accurate/sync/preview", json={"prices": True, "stocks": False, "new_products": False}, headers=admin, timeout=60).json()
        assert d["counts"]["price"] == 1
        DB.products.update_one({"product_id": PID}, {"$set": {"price": 915500}})
        try:
            res = requests.post(f"{API}/admin/accurate/sync/{d['preview_id']}/apply", json={}, headers=admin, timeout=60).json()["result"]
            assert res["conflict"] == 1 and res["price"] == 0
            assert DB.products.find_one({"product_id": PID})["price"] == 915500
        finally:
            DB.products.update_one({"product_id": PID}, {"$set": {"price": 915000}})

    def test_duplicate_number_means_already_in_accurate(self, admin):
        """An earlier attempt reached Accurate (reply lost): Accurate rejects the same number -> order is marked sent, not stuck."""
        oid = _mk_order("pgs-jombang", "Mitra PGS Jombang", "pgs-9955", "Casserole 32 Cm Suggo SG-CS32")
        requests.post("http://127.0.0.1:9911/accurate/api/sales-invoice/save.do", data={"number": oid}, timeout=5)
        r = requests.post(f"{API}/admin/accurate/invoice/{oid}", json={"confirm": True}, headers=admin, timeout=30)
        assert r.status_code == 200, r.text
        st = DB.orders.find_one({"order_id": oid})["accurate_invoice"]
        assert st["status"] == "sent" and st["number"] == oid

    def test_stale_sending_lock_can_retry(self, admin):
        from datetime import datetime, timedelta, timezone
        oid = _mk_order("pgs-jombang", "Mitra PGS Jombang", "pgs-9955", "Casserole 32 Cm Suggo SG-CS32")
        DB.orders.update_one({"order_id": oid}, {"$set": {"accurate_invoice": {"status": "sending", "at": datetime.now(timezone.utc)}}})
        assert requests.post(f"{API}/admin/accurate/invoice/{oid}", json={"confirm": True}, headers=admin, timeout=30).status_code == 409
        DB.orders.update_one({"order_id": oid}, {"$set": {"accurate_invoice.at": datetime.now(timezone.utc) - timedelta(minutes=10)}})
        r = requests.post(f"{API}/admin/accurate/invoice/{oid}", json={"confirm": True}, headers=admin, timeout=30)
        assert r.status_code == 200, r.text
