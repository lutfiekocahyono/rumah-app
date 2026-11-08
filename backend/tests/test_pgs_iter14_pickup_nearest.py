# PGS iteration 14: ruparupa-style multi-branch — stock at all branches, nearest store suggestion,
# cart move between branches, pickup ("Ambil di toko") checkout, seller store address/pickup hours.
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
PID = "pgs-9955"
GUBENG = "GUBENG, GUBENG, SURABAYA, JAWA TIMUR, 60281"
PATRANG = "PATRANG, PATRANG, JEMBER, JAWA TIMUR"
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


def _new_buyer():
    email = f"test_pick_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "TestPass123!", "name": "TEST Pickup Buyer"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture()
def buyer():
    t = _new_buyer()
    yield t
    requests.delete(f"{API}/cart", headers=H(t))


def _stock(t, pid=PID):
    r = requests.get(f"{API}/products/{pid}/availability")
    return {s["store_id"]: s["stock"][pid] for s in r.json()["stores"]}


# ---------- availability ----------
class TestAvailability:
    def test_gubeng_nearest_official(self):
        r = requests.get(f"{API}/products/{PID}/availability", params={"area": GUBENG})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["located"] is True and d["suggested"] == "pgs-official"
        ids = [s["store_id"] for s in d["stores"]]
        assert set(ids) == {"pgs-official", "pgs-jombang", "pgs-jember"}
        assert ids[0] == "pgs-official"
        dists = [s["distance_km"] for s in d["stores"]]
        assert dists == sorted(dists)
        for s in d["stores"]:
            for k in ("store_id", "name", "city", "address", "pickup_hours", "stock", "available", "distance_km"):
                assert k in s, f"missing {k} in {s}"
            assert isinstance(s["stock"][PID], int)

    def test_patrang_nearest_jember(self):
        d = requests.get(f"{API}/products/{PID}/availability", params={"area": PATRANG}).json()
        assert d["suggested"] == "pgs-jember" and d["stores"][0]["store_id"] == "pgs-jember"
        assert d["stores"][0]["distance_km"] < 20

    def test_no_area(self):
        d = requests.get(f"{API}/products/{PID}/availability").json()
        assert d["located"] is False and d["suggested"] is None
        assert all(s["distance_km"] is None for s in d["stores"]) and len(d["stores"]) == 3

    def test_unknown_area(self):
        d = requests.get(f"{API}/products/{PID}/availability", params={"area": "ZZZ, QQQ"}).json()
        assert d["located"] is False and d["suggested"] is None

    def test_404(self):
        assert requests.get(f"{API}/products/nope-xyz/availability").status_code == 404


# ---------- suggest ----------
class TestSuggest:
    def test_suggest_skips_out_of_stock_nearest(self, tok):
        orig = _stock(None)["pgs-jember"]
        try:
            r = requests.put(f"{API}/seller/inventory/{PID}", headers=H(tok["jember"]), json={"stock": 0})
            assert r.status_code == 200, r.text
            d = requests.post(f"{API}/stores/suggest", json={"area": PATRANG, "product_ids": [PID], "quantities": [1]}).json()
            assert d["stores"][0]["store_id"] == "pgs-jember" and d["stores"][0]["available"] is False
            assert d["suggested"] == "pgs-official", d
        finally:
            requests.put(f"{API}/seller/inventory/{PID}", headers=H(tok["jember"]), json={"stock": orig})
        assert _stock(None)["pgs-jember"] == orig

    def test_suggest_qty_exceeds_all(self):
        d = requests.post(f"{API}/stores/suggest", json={"area": GUBENG, "product_ids": [PID], "quantities": [99999]}).json()
        assert d["suggested"] is None and all(not s["available"] for s in d["stores"])

    def test_suggest_qty_covers(self):
        d = requests.post(f"{API}/stores/suggest", json={"area": "Kota Malang", "product_ids": [PID], "quantities": [2]}).json()
        assert d["located"] is True and d["suggested"] == "pgs-official"


# ---------- cart move ----------
class TestCartMove:
    def test_move_basic_and_cap(self, buyer, tok):
        r = requests.post(f"{API}/cart/items", headers=H(buyer, "pgs-official"), json={"product_id": PID, "quantity": 3})
        assert r.status_code == 200, r.text
        r = requests.post(f"{API}/cart/move", headers=H(buyer), json={"from_store_id": "pgs-official", "to_store_id": "pgs-jember"})
        assert r.status_code == 200, r.text
        assert r.json() == {"moved": 1, "skipped": []}
        cart = requests.get(f"{API}/cart", headers=H(buyer)).json()
        it = [i for i in cart["items"] if i["product_id"] == PID]
        assert len(it) == 1 and it[0]["store_id"] == "pgs-jember" and it[0]["quantity"] == 3

    def test_move_caps_qty_to_stock(self, buyer, tok):
        orig = _stock(None)["pgs-jember"]
        requests.post(f"{API}/cart/items", headers=H(buyer, "pgs-official"), json={"product_id": PID, "quantity": 5})
        try:
            requests.put(f"{API}/seller/inventory/{PID}", headers=H(tok["jember"]), json={"stock": 2})
            r = requests.post(f"{API}/cart/move", headers=H(buyer), json={"from_store_id": "pgs-official", "to_store_id": "pgs-jember"})
            assert r.status_code == 200 and r.json()["moved"] == 1
            it = next(i for i in requests.get(f"{API}/cart", headers=H(buyer)).json()["items"] if i["product_id"] == PID)
            assert it["quantity"] == 2 and it["store_id"] == "pgs-jember"
        finally:
            requests.put(f"{API}/seller/inventory/{PID}", headers=H(tok["jember"]), json={"stock": orig})

    def test_move_skips_out_of_stock(self, buyer, tok):
        orig = _stock(None)["pgs-jember"]
        requests.post(f"{API}/cart/items", headers=H(buyer, "pgs-official"), json={"product_id": PID, "quantity": 1})
        try:
            requests.put(f"{API}/seller/inventory/{PID}", headers=H(tok["jember"]), json={"stock": 0})
            r = requests.post(f"{API}/cart/move", headers=H(buyer), json={"from_store_id": "pgs-official", "to_store_id": "pgs-jember"})
            assert r.status_code == 200 and r.json() == {"moved": 0, "skipped": [PID]}
            it = next(i for i in requests.get(f"{API}/cart", headers=H(buyer)).json()["items"] if i["product_id"] == PID)
            assert it["store_id"] == "pgs-official"
        finally:
            requests.put(f"{API}/seller/inventory/{PID}", headers=H(tok["jember"]), json={"stock": orig})

    def test_move_back_to_official(self, buyer):
        requests.post(f"{API}/cart/items", headers=H(buyer, "pgs-jember"), json={"product_id": PID, "quantity": 1})
        r = requests.post(f"{API}/cart/move", headers=H(buyer), json={"from_store_id": "pgs-jember", "to_store_id": "pgs-official"})
        assert r.status_code == 200 and r.json()["moved"] == 1
        it = [i for i in requests.get(f"{API}/cart", headers=H(buyer)).json()["items"] if i["product_id"] == PID]
        assert len(it) == 1 and it[0]["store_id"] == "pgs-official"

    def test_move_rejects(self, buyer):
        bad = [{"from_store_id": "pgs-official", "to_store_id": "pgs-official"},
               {"from_store_id": "pgs-official", "to_store_id": "st_c789b1a7c3"},
               {"from_store_id": "pgs-official", "to_store_id": "pgs-jember"}]  # empty cart
        for b in bad:
            r = requests.post(f"{API}/cart/move", headers=H(buyer), json=b)
            assert r.status_code == 400, (b, r.text)

    def test_move_rejects_branch_exclusive(self, buyer, tok):
        cats = requests.get(f"{API}/categories").json()
        cat = cats[0]["category_id"]
        r = requests.post(f"{API}/seller/products", headers=H(tok["jember"]), json={
            "name": "TEST_Exclusive Jember", "category": cat, "price": 1000, "stock": 5, "images": ["https://example.com/a.jpg"]})
        assert r.status_code == 200, r.text
        pid = r.json()["product_id"]
        try:
            r = requests.post(f"{API}/cart/items", headers=H(buyer, "pgs-jember"), json={"product_id": pid, "quantity": 1})
            assert r.status_code == 200, r.text
            r = requests.post(f"{API}/cart/move", headers=H(buyer), json={"from_store_id": "pgs-jember", "to_store_id": "pgs-official"})
            assert r.status_code == 400, r.text
        finally:
            requests.delete(f"{API}/cart", headers=H(buyer))
            requests.delete(f"{API}/seller/products/{pid}", headers=H(tok["jember"]))


# ---------- pickup checkout ----------
class TestPickupCheckout:
    def test_pickup_order_routes_to_jember(self, buyer, tok):
        before = _stock(None)["pgs-jember"]
        requests.post(f"{API}/cart/items", headers=H(buyer, "pgs-official"), json={"product_id": PID, "quantity": 1})
        r = requests.post(f"{API}/cart/move", headers=H(buyer), json={"from_store_id": "pgs-official", "to_store_id": "pgs-jember"})
        assert r.status_code == 200
        r = requests.post(f"{API}/checkout", headers=H(buyer), json={
            "full_name": "TEST_Buyer", "phone": "081234567890", "address": "Jl. Test No 1", "city": "Jember",
            "payment_method": "cod", "store_id": "pgs-jember", "courier": "pickup", "expected_shipping_cost": 0})
        assert r.status_code == 200, r.text
        o = r.json()
        try:
            assert o["store_id"] == "pgs-jember" and o["shipping_cost"] == 0 and o["total"] == o["subtotal"]
            assert _stock(None)["pgs-jember"] == before - 1
            so = requests.get(f"{API}/seller/orders", headers=H(tok["jember"])).json()
            so = so if isinstance(so, list) else so.get("items", so.get("orders", []))
            assert any(x["order_id"] == o["order_id"] for x in so)
            so2 = requests.get(f"{API}/seller/orders", headers=H(tok["sidoarjo"])).json()
            so2 = so2 if isinstance(so2, list) else so2.get("items", so2.get("orders", []))
            assert not any(x["order_id"] == o["order_id"] for x in so2)
        finally:
            r = requests.put(f"{API}/seller/orders/{o['order_id']}/status", headers=H(tok["jember"]), json={"status": "cancelled"})
            assert r.status_code == 200, r.text
        assert _stock(None)["pgs-jember"] == before


# ---------- seller store address / pickup hours ----------
class TestStoreAddress:
    def test_edit_store_requires_phone_for_branch_without_phone(self, tok):
        # Jombang/Jember seeded with phone '' -> store edit form must ask for a phone (422 otherwise)
        s = requests.get(f"{API}/me/store", headers=H(tok["jember"])).json()
        body = {k: s.get(k) or "" for k in ("name", "description", "city", "phone", "logo", "address", "pickup_hours")}
        r = requests.put(f"{API}/me/store", headers=H(tok["jember"]), json=body)
        assert r.status_code in (200, 422)

    def test_edit_store_address_hours(self, tok):
        s = requests.get(f"{API}/me/store", headers=H(tok["sidoarjo"])).json()
        orig = {k: s.get(k) or "" for k in ("name", "description", "city", "phone", "logo", "address", "pickup_hours")}
        try:
            r = requests.put(f"{API}/me/store", headers=H(tok["sidoarjo"]), json={**orig, "address": "TEST_Jl. Raya Sidoarjo 1", "pickup_hours": "TEST 08.00-17.00"})
            assert r.status_code == 200, r.text
            st = next(x for x in requests.get(f"{API}/official-stores").json() if x["store_id"] == "pgs-official")
            assert st["address"] == "TEST_Jl. Raya Sidoarjo 1" and st["pickup_hours"] == "TEST 08.00-17.00"
            av = requests.get(f"{API}/products/{PID}/availability").json()
            assert next(x for x in av["stores"] if x["store_id"] == "pgs-official")["address"] == "TEST_Jl. Raya Sidoarjo 1"
        finally:
            r = requests.put(f"{API}/me/store", headers=H(tok["sidoarjo"]), json=orig)
            assert r.status_code == 200, r.text
        st = next(x for x in requests.get(f"{API}/official-stores").json() if x["store_id"] == "pgs-official")
        assert (st["address"] or "") == orig["address"]
