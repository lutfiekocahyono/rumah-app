# PGS iteration 5: 3 official stores (PGS Sidoarjo / Mitra PGS Jombang / Mitra PGS Jember) with per-branch stock,
# store-admin accounts, per-store couriers (manual tariffs), store-scoped cart/checkout, store order flow, revenue reports.
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
PW = "TestPass123!"
SHIP = {"full_name": "TEST_Buyer", "phone": "081234567890", "address": "Jl. Test No 1", "city": "Jombang"}
CRED = {"admin": ("admin@pgs.id", "Admin1234!"), "sidoarjo": ("sidoarjo@pgs.id", "Sidoarjo123!"),
        "jombang": ("jombang@pgs.id", "Jombang123!"), "jember": ("jember@pgs.id", "Jember123!")}


def H(t, store=None):
    h = {"Authorization": f"Bearer {t}"}
    if store:
        h["X-Store-Id"] = store
    return h


def _login(k):
    r = requests.post(f"{API}/auth/login", json={"email": CRED[k][0], "password": CRED[k][1]})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def tok():
    return {k: _login(k) for k in CRED}


@pytest.fixture(scope="module")
def buyer():
    email = f"test_br_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": PW, "name": "TEST Branch Buyer"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _inv(t, q="", skip=0):
    r = requests.get(f"{API}/seller/inventory", headers=H(t), params={"q": q, "skip": skip})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def finite(tok):
    """A shared-catalog product with finite stock (5..9000) at Jombang; stock restored on teardown (Jombang+Jember)."""
    for skip in range(0, 2000, 40):
        for it in _inv(tok["jombang"], skip=skip):
            if not it["own"] and 5 <= it["stock"] < 9000:
                jem = next((x for x in _inv(tok["jember"], q=it["name"]) if x["product_id"] == it["product_id"]), None)
                orig = {"jombang": it["stock"], "jember": jem["stock"] if jem else 0}
                yield {**it, "orig": orig}
                for k, v in orig.items():
                    requests.put(f"{API}/seller/inventory/{it['product_id']}", headers=H(tok[k]), json={"stock": v})
                return
    pytest.skip("no finite-stock product found")


# --- official stores & product context
class TestOfficialStores:
    def test_official_order(self):
        r = requests.get(f"{API}/official-stores")
        assert r.status_code == 200
        assert [s["store_id"] for s in r.json()] == ["pgs-official", "pgs-jombang", "pgs-jember"]
        assert [s["name"] for s in r.json()] == ["PGS Sidoarjo", "Mitra PGS Jombang", "Mitra PGS Jember"]
        assert all(s["official"] for s in r.json())

    def test_products_store_context(self):
        d = requests.get(f"{API}/products", params={"limit": 5}).json()
        assert len(d) == 5 and all(p["store_name"] == "PGS Sidoarjo" for p in d)
        j = requests.get(f"{API}/products", params={"limit": 5}, headers={"X-Store-Id": "pgs-jombang"}).json()
        assert len(j) == 5 and all(p["store_name"] == "Mitra PGS Jombang" for p in j)

    def test_product_detail_branch_stock(self, tok, finite):
        p = requests.get(f"{API}/products/{finite['product_id']}", headers={"X-Store-Id": "pgs-jombang"}).json()
        assert p["stock"] == finite["orig"]["jombang"] and p["store_name"] == "Mitra PGS Jombang"


# --- store admin
class TestStoreAdmin:
    @pytest.mark.parametrize("k,sid", [("sidoarjo", "pgs-official"), ("jombang", "pgs-jombang"), ("jember", "pgs-jember")])
    def test_me_store(self, tok, k, sid):
        me = requests.get(f"{API}/auth/me", headers=H(tok[k])).json()
        assert me.get("role") == "store_admin", me
        s = requests.get(f"{API}/me/store", headers=H(tok[k])).json()
        assert s["store_id"] == sid and s["status"] == "active" and s["official"] is True

    def test_inventory_search_paging(self, tok):
        a, b = _inv(tok["jombang"]), _inv(tok["jombang"], skip=40)
        assert len(a) == 40 and len(b) == 40 and a[0]["product_id"] != b[0]["product_id"]
        name = a[3]["name"][:8]
        assert all(name.lower() in x["name"].lower() for x in _inv(tok["jombang"], q=name))

    def test_stock_edit_branch_isolated(self, tok, finite):
        pid = finite["product_id"]
        r = requests.put(f"{API}/seller/inventory/{pid}", headers=H(tok["jombang"]), json={"stock": 7})
        assert r.status_code == 200 and r.json()["stock"] == 7
        assert requests.get(f"{API}/products/{pid}", headers={"X-Store-Id": "pgs-jombang"}).json()["stock"] == 7
        assert requests.get(f"{API}/products/{pid}", headers={"X-Store-Id": "pgs-jember"}).json()["stock"] == finite["orig"]["jember"]
        requests.put(f"{API}/seller/inventory/{pid}", headers=H(tok["jombang"]), json={"stock": finite["orig"]["jombang"]})

    def test_stock_negative_rejected(self, tok, finite):
        r = requests.put(f"{API}/seller/inventory/{finite['product_id']}", headers=H(tok["jombang"]), json={"stock": -1})
        assert r.status_code == 422

    def test_customer_cannot_seller(self, buyer):
        assert requests.get(f"{API}/seller/inventory", headers=H(buyer)).status_code == 403


# --- couriers
class TestCouriers:
    def test_couriers_crud(self, tok):
        h = H(tok["jombang"])
        orig = requests.get(f"{API}/seller/couriers", headers=h).json()
        assert {"pickup", "jne", "jnt", "sicepat"} <= {c["code"] for c in orig}
        try:
            new = [{**c, "cost": 11111} if c["code"] == "jne" else ({**c, "active": False} if c["code"] == "sicepat" else c) for c in orig]
            r = requests.put(f"{API}/seller/couriers", headers=h, json={"couriers": new})
            assert r.status_code == 200, r.text
            pub = requests.get(f"{API}/stores/pgs-jombang/couriers").json()
            assert "sicepat" not in [c["code"] for c in pub]
            assert next(c for c in pub if c["code"] == "jne")["cost"] == 11111
            # jember untouched
            assert next(c for c in requests.get(f"{API}/stores/pgs-jember/couriers").json() if c["code"] == "jne")["cost"] != 11111
            dup = requests.put(f"{API}/seller/couriers", headers=h, json={"couriers": [orig[0], orig[0]]})
            assert dup.status_code == 400
        finally:
            requests.put(f"{API}/seller/couriers", headers=h, json={"couriers": orig})

    def test_admin_couriers(self, tok):
        h = H(tok["admin"])
        orig = requests.get(f"{API}/admin/stores/pgs-jember/couriers", headers=h).json()
        try:
            new = [{**c, "cost": 23456} if c["code"] == "jnt" else c for c in orig]
            assert requests.put(f"{API}/admin/stores/pgs-jember/couriers", headers=h, json={"couriers": new}).status_code == 200
            assert next(c for c in requests.get(f"{API}/seller/couriers", headers=H(tok["jember"])).json() if c["code"] == "jnt")["cost"] == 23456
            assert requests.put(f"{API}/admin/stores/pgs-jember/couriers", headers=h, json={"couriers": [orig[0], orig[0]]}).status_code == 400
            assert requests.get(f"{API}/admin/stores/pgs-jember/couriers", headers=H(tok["jombang"])).status_code == 403
        finally:
            requests.put(f"{API}/admin/stores/pgs-jember/couriers", headers=h, json={"couriers": orig})


# --- cart, checkout and store order flow
class TestCartCheckoutFlow:
    def test_full_flow(self, tok, buyer, finite):
        pid, hj = finite["product_id"], H(buyer, "pgs-jombang")
        requests.delete(f"{API}/cart", headers=H(buyer))
        requests.put(f"{API}/seller/inventory/{pid}", headers=H(tok["jombang"]), json={"stock": 5})
        c = requests.post(f"{API}/cart/items", headers=hj, json={"product_id": pid, "quantity": 50}).json()
        it = next(i for i in c["items"] if i["product_id"] == pid)
        assert it["store_id"] == "pgs-jombang" and it["store_name"] == "Mitra PGS Jombang" and it["quantity"] == 5  # capped
        # second product from Sidoarjo -> multi-store cart
        other = requests.get(f"{API}/products", params={"limit": 10}).json()
        op = next(p for p in other if p["product_id"] != pid and p["stock"] > 0)
        c = requests.post(f"{API}/cart/items", headers=H(buyer), json={"product_id": op["product_id"], "quantity": 1}).json()
        assert {i["store_id"] for i in c["items"]} == {"pgs-jombang", "pgs-official"}
        body = {**SHIP, "payment_method": "cod", "courier": "jne"}
        assert requests.post(f"{API}/checkout", headers=H(buyer), json=body).status_code == 400  # multi-store w/o store_id
        assert requests.post(f"{API}/checkout", headers=H(buyer), json={**body, "store_id": "pgs-jombang", "courier": "xxx"}).status_code in (400, 409)  # 409 since iter10 shipping guard
        requests.put(f"{API}/cart/items/{pid}", headers=H(buyer), json={"quantity": 2})
        jne = next(c for c in requests.get(f"{API}/stores/pgs-jombang/couriers").json() if c["code"] == "jne")
        r = requests.post(f"{API}/checkout", headers=H(buyer), json={**body, "store_id": "pgs-jombang"})
        assert r.status_code == 200, r.text
        o = r.json()
        oid = o["order_id"]
        assert o["store_id"] == "pgs-jombang" and o["store_name"] == "Mitra PGS Jombang" and o["courier"]["code"] == "jne"
        assert o["shipping_cost"] == jne["cost"] and o["total"] == o["subtotal"] - o["discount"] + jne["cost"]
        cart = requests.get(f"{API}/cart", headers=H(buyer)).json()
        assert [i["product_id"] for i in cart["items"]] == [op["product_id"]]  # only jombang items removed
        assert requests.get(f"{API}/products/{pid}", headers={"X-Store-Id": "pgs-jombang"}).json()["stock"] == 3
        assert requests.get(f"{API}/products/{pid}", headers={"X-Store-Id": "pgs-jember"}).json()["stock"] == finite["orig"]["jember"]
        # store isolation
        assert requests.get(f"{API}/seller/orders/{oid}", headers=H(tok["jember"])).status_code == 404
        assert requests.put(f"{API}/seller/orders/{oid}/status", headers=H(tok["jember"]), json={"status": "processing"}).status_code == 404
        hs = H(tok["jombang"])
        assert oid in [x["order_id"] for x in requests.get(f"{API}/seller/orders", headers=hs, params={"status": "new"}).json()]
        assert requests.post(f"{API}/orders/{oid}/confirm", headers=H(buyer)).status_code == 400  # not shipped yet
        assert requests.put(f"{API}/seller/orders/{oid}/status", headers=hs, json={"status": "shipped", "tracking_number": "X"}).status_code == 400
        assert requests.put(f"{API}/seller/orders/{oid}/status", headers=hs, json={"status": "processing"}).status_code == 200
        r = requests.put(f"{API}/seller/orders/{oid}/status", headers=hs, json={"status": "completed"})
        assert r.status_code == 400  # non-pickup must be shipped first
        r = requests.put(f"{API}/seller/orders/{oid}/status", headers=hs, json={"status": "shipped"})
        assert r.status_code == 400 and r.json()["detail"] == "Masukkan nomor resi"
        r = requests.put(f"{API}/seller/orders/{oid}/status", headers=hs, json={"status": "shipped", "tracking_number": "jp123test"})
        assert r.status_code == 200 and r.json()["tracking_number"] == "JP123TEST"
        r = requests.post(f"{API}/orders/{oid}/confirm", headers=H(buyer))
        assert r.status_code == 200 and r.json()["status"] == "completed"
        assert [h["status"] for h in r.json()["status_history"]] == ["cod", "processing", "shipped", "completed"]
        n = requests.get(f"{API}/notifications", headers=H(buyer)).json()
        txt = str(n)
        assert "sedang dikirim" in txt and "JP123TEST" in txt
        rep = requests.get(f"{API}/seller/report", headers=hs).json()
        assert rep["revenue_completed"] >= o["total"] and "by_status" in rep and "daily" in rep and "top_products" in rep
        assert any(t["product_id"] == pid for t in rep["top_products"]) or len(rep["top_products"]) == 5
        requests.delete(f"{API}/cart", headers=H(buyer))

    def test_pickup_and_cancel(self, tok, buyer, finite):
        pid = finite["product_id"]
        hs = H(tok["jombang"])
        requests.put(f"{API}/seller/inventory/{pid}", headers=hs, json={"stock": 6})
        requests.post(f"{API}/cart/items", headers=H(buyer, "pgs-jombang"), json={"product_id": pid, "quantity": 2})
        o = requests.post(f"{API}/checkout", headers=H(buyer), json={**SHIP, "payment_method": "cod", "courier": "pickup"}).json()
        assert o["shipping_cost"] == 0 and o["total"] == o["subtotal"]
        assert requests.put(f"{API}/seller/orders/{o['order_id']}/status", headers=hs, json={"status": "processing"}).status_code == 200
        r = requests.put(f"{API}/seller/orders/{o['order_id']}/status", headers=hs, json={"status": "completed"})
        assert r.status_code == 200 and r.json()["status"] == "completed"
        # cancel restores stock
        requests.post(f"{API}/cart/items", headers=H(buyer, "pgs-jombang"), json={"product_id": pid, "quantity": 3})
        o2 = requests.post(f"{API}/checkout", headers=H(buyer), json={**SHIP, "payment_method": "cod", "courier": "pickup"}).json()
        assert requests.get(f"{API}/products/{pid}", headers={"X-Store-Id": "pgs-jombang"}).json()["stock"] == 1
        r = requests.put(f"{API}/seller/orders/{o2['order_id']}/status", headers=hs, json={"status": "cancelled"})
        assert r.status_code == 200
        assert requests.get(f"{API}/products/{pid}", headers={"X-Store-Id": "pgs-jombang"}).json()["stock"] == 4
        # double cancel doesn't double restock
        assert requests.put(f"{API}/seller/orders/{o2['order_id']}/status", headers=hs, json={"status": "cancelled"}).status_code == 400

    def test_unlimited_stock_not_decremented(self, tok, buyer):
        it = next((x for s in range(0, 400, 40) for x in _inv(tok["jember"], skip=s) if x["stock"] == 9999), None)
        if not it:
            pytest.skip("no 9999 item")
        requests.post(f"{API}/cart/items", headers=H(buyer, "pgs-jember"), json={"product_id": it["product_id"], "quantity": 1})
        o = requests.post(f"{API}/checkout", headers=H(buyer), json={**SHIP, "payment_method": "cod", "courier": "pickup", "store_id": "pgs-jember"})
        assert o.status_code == 200, o.text
        assert requests.get(f"{API}/products/{it['product_id']}", headers={"X-Store-Id": "pgs-jember"}).json()["stock"] == 9999
        requests.put(f"{API}/seller/orders/{o.json()['order_id']}/status", headers=H(tok["jember"]), json={"status": "cancelled"})


# --- reports
class TestReports:
    def test_admin_report(self, tok):
        r = requests.get(f"{API}/admin/report", headers=H(tok["admin"]))
        assert r.status_code == 200
        d = r.json()
        assert "revenue_completed" in d["all"]
        ids = [s["store_id"] for s in d["stores"]]
        assert {"pgs-official", "pgs-jombang", "pgs-jember"} <= set(ids)
        assert d["all"]["revenue_completed"] >= sum(s["revenue_completed"] for s in d["stores"] if s["store_id"] in ("pgs-jombang", "pgs-jember"))
        assert requests.get(f"{API}/admin/report", headers=H(tok["jombang"])).status_code == 403
