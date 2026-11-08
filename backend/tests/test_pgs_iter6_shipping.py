# PGS iteration 6: automatic shipping (RajaOngkir/Komerce) settings, encrypted key storage, manual-tariff fallback, checkout.
import os
import uuid
import asyncio
import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
DUMMY = "TEST_dummykey_abcd1234wxyz"
SHIP = {"full_name": "TEST_Ship Buyer", "phone": "081234567890", "address": "Jl. Test No 1", "city": "Sidoarjo"}
MANUAL = {"pickup": 0, "jne": 25000, "jnt": 24000, "sicepat": 22000}
CREATED_ORDERS = []


def _db_call(coro_fn):
    async def run():
        cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
        try:
            return await coro_fn(cli[os.environ["DB_NAME"]])
        finally:
            cli.close()
    return asyncio.run(run())


def _login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def admin():
    return _login("admin@pgs.id", "Admin1234!")


@pytest.fixture(scope="module")
def jombang():
    return _login("jombang@pgs.id", "Jombang123!")


@pytest.fixture(scope="module", autouse=True)
def restore_settings(admin):
    yield
    # always leave the app in manual mode and remove test orders
    requests.put(f"{API}/admin/shipping-settings", headers=admin,
                 json={"api_key": "", "enabled": True, "default_weight_grams": 1000, "origins": {}})
    if CREATED_ORDERS:
        async def rm(db):
            orders = await db.orders.find({"order_id": {"$in": CREATED_ORDERS}}).to_list(50)
            for o in orders:  # give stock back
                for i in o["items"]:
                    p = await db.products.find_one({"product_id": i["product_id"]}, {"stock": 1})
                    if p and p.get("stock", 0) < 9999:
                        await db.products.update_one({"product_id": i["product_id"]}, {"$inc": {"stock": i["quantity"]}, "$set": {"in_stock": True}})
            await db.orders.delete_many({"order_id": {"$in": CREATED_ORDERS}})
            await db.notifications.delete_many({"link": {"$in": [f"/order/{x}" for x in CREATED_ORDERS]}})
        _db_call(rm)


def _put(admin, **kw):
    body = {"enabled": True, "default_weight_grams": 1000, "origins": {}}
    body.update(kw)
    return requests.put(f"{API}/admin/shipping-settings", headers=admin, json=body)


def _assert_manual(lst):
    codes = {c["code"]: c for c in lst}
    assert set(MANUAL) <= set(codes), codes
    for k, v in MANUAL.items():
        assert codes[k]["cost"] == v and codes[k]["source"] == "manual", codes[k]


# --- settings access control & no raw key leak
class TestShippingSettings:
    def test_store_admin_forbidden(self, jombang):
        assert requests.get(f"{API}/admin/shipping-settings", headers=jombang).status_code == 403
        assert requests.put(f"{API}/admin/shipping-settings", headers=jombang, json={"api_key": "x" * 12}).status_code == 403
        assert requests.get(f"{API}/admin/shipping-settings").status_code in (401, 403)

    def test_get_shape_no_key(self, admin):
        _put(admin, api_key="")
        d = requests.get(f"{API}/admin/shipping-settings", headers=admin).json()
        assert d == {"configured": False, "key_hint": "", "enabled": True, "default_weight_grams": 1000, "origins": {}}
        assert requests.get(f"{API}/shipping/status").json() == {"auto": False}

    def test_save_key_encrypted_and_hidden(self, admin):
        r = _put(admin, api_key=DUMMY, default_weight_grams=1500)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["configured"] is True and d["key_hint"] == "••••wxyz" and d["default_weight_grams"] == 1500
        assert DUMMY not in r.text
        g = requests.get(f"{API}/admin/shipping-settings", headers=admin)
        assert DUMMY not in g.text and "api_key" not in g.json()
        doc = _db_call(lambda db: db.settings.find_one({"key": "shipping_api"}, {"_id": 0}))
        assert doc["api_key_enc"] and doc["api_key_enc"] != DUMMY and DUMMY not in str(doc)
        assert requests.get(f"{API}/shipping/status").json() == {"auto": True}

    def test_null_and_omitted_keep_key(self, admin):
        assert _put(admin, api_key=None).json()["configured"] is True
        assert _put(admin).json()["configured"] is True

    def test_validation(self, admin):
        assert _put(admin, default_weight_grams=0).status_code == 422
        assert _put(admin, api_key="x" * 301).status_code == 422

    def test_empty_removes(self, admin):
        d = _put(admin, api_key="").json()
        assert d["configured"] is False and d["key_hint"] == ""
        assert requests.get(f"{API}/shipping/status").json() == {"auto": False}


# --- rates: manual without key, manual fallback with invalid key
class TestRatesFallback:
    def test_rates_no_key(self, admin):
        _put(admin, api_key="")
        for sid in ("pgs-official", "pgs-jombang", "pgs-jember"):
            r = requests.post(f"{API}/shipping/rates", headers={"X-Guest-Id": f"TEST_{uuid.uuid4().hex[:8]}"},
                              json={"store_id": sid, "destination_id": 12345})
            assert r.status_code == 200, r.text
            _assert_manual(r.json())

    def test_rates_unknown_store(self):
        r = requests.post(f"{API}/shipping/rates", headers={"X-Guest-Id": "TEST_g"}, json={"store_id": "nope"})
        assert r.status_code == 404

    def test_invalid_key_falls_back(self, admin):
        r = _put(admin, api_key=DUMMY, origins={"pgs-official": {"id": 17473, "label": "TEST origin"}})
        assert r.status_code == 200 and r.json()["origins"]["pgs-official"]["id"] == 17473
        r = requests.post(f"{API}/shipping/rates", headers={"X-Guest-Id": f"TEST_{uuid.uuid4().hex[:8]}"},
                          json={"store_id": "pgs-official", "destination_id": 31555})
        assert r.status_code == 200, r.text
        _assert_manual(r.json())  # no couriers disappear

    def test_destination_search_invalid_key(self, admin):
        _put(admin, api_key=DUMMY)
        r = requests.get(f"{API}/admin/shipping/destinations", headers=admin, params={"q": "sidoarjo"})
        assert r.status_code in (424, 200), r.text
        print("admin destinations with dummy key:", r.status_code, r.text[:200])
        r2 = requests.get(f"{API}/shipping/destinations", headers={"X-Guest-Id": "TEST_g"}, params={"q": "sidoarjo"})
        print("public destinations with dummy key:", r2.status_code, r2.text[:200])

    def test_admin_destinations_no_key(self, admin):
        _put(admin, api_key="")
        assert requests.get(f"{API}/admin/shipping/destinations", headers=admin, params={"q": "sidoarjo"}).status_code == 400
        assert requests.get(f"{API}/shipping/destinations", headers={"X-Guest-Id": "TEST_g"}, params={"q": "sid"}).json() == {"auto": False, "data": []}


# --- checkout with courier + destination fields (COD)
class TestCheckout:
    def _cart(self, gid):
        prods = requests.get(f"{API}/products", params={"limit": 40}).json()
        p = next((x for x in prods if x["stock"] >= 9999), None) or next(x for x in prods if x["stock"] > 2)
        r = requests.post(f"{API}/cart/items", headers={"X-Guest-Id": gid}, json={"product_id": p["product_id"], "quantity": 1})
        assert r.status_code == 200, r.text
        return r.json()

    @pytest.mark.parametrize("dummy_key", [False, True])
    def test_checkout_cod(self, admin, dummy_key):
        _put(admin, api_key=DUMMY if dummy_key else "", origins={"pgs-official": {"id": 17473, "label": "TEST"}} if dummy_key else {})
        gid = f"TEST_{uuid.uuid4().hex[:10]}"
        cart = self._cart(gid)
        r = requests.post(f"{API}/checkout", headers={"X-Guest-Id": gid}, json={
            **SHIP, "payment_method": "cod", "store_id": "pgs-official", "courier": "sicepat",
            "destination_id": 31555, "destination_label": "TEST Kec. Buduran, Sidoarjo"})
        assert r.status_code == 200, r.text
        o = r.json()
        CREATED_ORDERS.append(o["order_id"])
        assert o["shipping_cost"] == 22000 and o["total"] == o["subtotal"] - o["discount"] + 22000
        assert o["shipping"].get("destination_label") == "TEST Kec. Buduran, Sidoarjo"
        doc = _db_call(lambda db: db.orders.find_one({"order_id": o["order_id"]}, {"_id": 0, "courier": 1}))
        assert doc["courier"]["code"] == "sicepat" and doc["courier"]["source"] == "manual"

    def test_checkout_bad_courier(self, admin):
        _put(admin, api_key="")
        gid = f"TEST_{uuid.uuid4().hex[:10]}"
        self._cart(gid)
        r = requests.post(f"{API}/checkout", headers={"X-Guest-Id": gid}, json={**SHIP, "payment_method": "cod", "courier": "zzz"})
        assert r.status_code == 400
        requests.delete(f"{API}/cart", headers={"X-Guest-Id": gid})
