# PGS iteration 19: /products/count, home-settings {kota} subtitle, seller COD pickup expires_at in order list.
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
PID = "pgs-9955"
STORE = "pgs-official"


def _env(k):
    for line in open("/app/backend/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip('"')


DB = MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]


def H(t, store=None):
    h = {"Authorization": f"Bearer {t}"}
    if store:
        h["X-Store-Id"] = store
    return h


def _login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin():
    return _login("admin@pgs.id", "Admin1234!")


@pytest.fixture(scope="module")
def store_admin():
    return _login("sidoarjo@pgs.id", "Sidoarjo123!")


# ---------- /products/count ----------
class TestProductCount:
    def test_count_shape_and_value(self):
        r = requests.get(f"{API}/products/count")
        assert r.status_code == 200, r.text
        d = r.json()
        assert isinstance(d.get("count"), int) and d["count"] > 0
        hidden = [s["store_id"] for s in DB.stores.find({"status": {"$ne": "active"}}, {"store_id": 1})]
        assert d["count"] == DB.products.count_documents({"store_id": {"$nin": hidden}})

    def test_count_not_shadowed_and_ignores_store_header(self):
        a = requests.get(f"{API}/products/count").json()["count"]
        b = requests.get(f"{API}/products/count", headers={"X-Store-Id": "pgs-jombang"}).json()["count"]
        assert a == b

    def test_product_detail_still_works(self):
        r = requests.get(f"{API}/products/{PID}")
        assert r.status_code == 200 and r.json()["product_id"] == PID


# ---------- /home-settings {kota} ----------
class TestHomeKota:
    def test_subtitle_has_kota(self):
        fs = requests.get(f"{API}/home-settings").json()["free_shipping"]
        assert "{kota}" in fs["subtitle"], fs
        assert "Area Sidoarjo" not in fs["subtitle"]

    def test_legacy_sidoarjo_text_rewritten_on_read(self, admin):
        orig = requests.get(f"{API}/home-settings").json()
        raw = DB.settings.find_one({"key": "home"}, {"_id": 0})
        body = {"free_shipping": {k: orig["free_shipping"][k] for k in ("enabled", "title", "subtitle", "min_purchase")},
                "recommend_mode": orig["recommend_mode"]}
        try:
            legacy = {**body, "free_shipping": {**body["free_shipping"], "subtitle": "Area Sidoarjo & sekitarnya, min. belanja Rp500.000"}}
            r = requests.put(f"{API}/admin/home-settings", headers=H(admin), json=legacy)
            assert r.status_code == 200, r.text
            sub = requests.get(f"{API}/home-settings").json()["free_shipping"]["subtitle"]
            assert sub == "Area {kota} & sekitarnya, min. belanja Rp500.000"
            # custom text without {kota} is kept as-is
            custom = {**body, "free_shipping": {**body["free_shipping"], "subtitle": "TEST_ Khusus Surabaya"}}
            requests.put(f"{API}/admin/home-settings", headers=H(admin), json=custom)
            assert requests.get(f"{API}/home-settings").json()["free_shipping"]["subtitle"] == "TEST_ Khusus Surabaya"
        finally:
            if raw is not None:
                DB.settings.replace_one({"key": "home"}, raw)
            else:
                DB.settings.delete_one({"key": "home"})


# ---------- seller order list: COD pickup expires_at ----------
class TestCodExpiry:
    @pytest.fixture()
    def cod_order(self, store_admin):
        email = f"test_iter19_{uuid.uuid4().hex[:8]}@example.com"
        r = requests.post(f"{API}/auth/register", json={"email": email, "password": "TestPass123!", "name": "TEST Iter19"})
        assert r.status_code == 200, r.text
        t = r.json()["token"]
        assert requests.post(f"{API}/cart/items", headers=H(t, STORE), json={"product_id": PID, "quantity": 1}).status_code == 200
        r = requests.post(f"{API}/checkout", headers=H(t), json={
            "full_name": "TEST Buyer19", "phone": "081234567890", "address": "", "city": "", "payment_method": "cod",
            "store_id": STORE, "courier": "pickup"})
        assert r.status_code == 200, r.text
        o = r.json()
        yield o
        requests.put(f"{API}/seller/orders/{o['order_id']}/status", headers=H(store_admin), json={"status": "cancelled"})

    def test_seller_list_has_expires_at(self, cod_order, store_admin):
        assert cod_order["status"] == "cod" and cod_order["expires_at"]
        lst = requests.get(f"{API}/seller/orders", params={"status": "new"}, headers=H(store_admin)).json()
        mine = [o for o in lst if o["order_id"] == cod_order["order_id"]]
        assert mine and mine[0]["expires_at"]
        exp = mine[0]["expires_at"]
        print("expires_at serialized:", exp)
        # must carry a timezone so devices outside UTC compute hours-left correctly
        assert exp.endswith("Z") or "+" in exp[10:], f"expires_at has no timezone: {exp}"

    def test_urgent_expiry_value(self, cod_order, store_admin):
        soon = datetime.now(timezone.utc) + timedelta(hours=3)
        DB.orders.update_one({"order_id": cod_order["order_id"]}, {"$set": {"expires_at": soon}})
        lst = requests.get(f"{API}/seller/orders", params={"status": "new"}, headers=H(store_admin)).json()
        o = next(o for o in lst if o["order_id"] == cod_order["order_id"])
        exp = o["expires_at"].replace("Z", "+00:00")
        dt = datetime.fromisoformat(exp)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        assert abs((dt - soon).total_seconds()) < 5
