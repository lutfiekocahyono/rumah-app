# PGS iteration 34: pickup QR "PGSAMBIL-<code>" accepted by cashier lookup (non-digits stripped), order exposes pickup_code.
import os

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
PID = "pgs-9955"
STORE = "pgs-official"
CRED = {"admin": ("admin@pgs.id", "Admin1234!"), "jombang": ("jombang@pgs.id", "Jombang123!"), "sidoarjo": ("sidoarjo@pgs.id", "Sidoarjo123!"),
        "demo": ("demo@pgs.id", "Demo1234!")}


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


@pytest.fixture(scope="module")
def tok():
    out = {}
    for k, (e, p) in CRED.items():
        r = requests.post(f"{API}/auth/login", json={"email": e, "password": p})
        assert r.status_code == 200, r.text
        out[k] = r.json()["token"]
    return out


@pytest.fixture(scope="module")
def pickup(tok):
    before = DB.products.find_one({"product_id": PID}, {"_id": 0, "stock": 1, "sold": 1})
    t = tok["demo"]
    saved_cart = requests.get(f"{API}/cart", headers=H(t, STORE)).json()
    requests.delete(f"{API}/cart", headers=H(t))
    r = requests.post(f"{API}/cart/items", headers=H(t, STORE), json={"product_id": PID, "quantity": 1})
    assert r.status_code == 200, r.text
    r = requests.post(f"{API}/checkout", headers=H(t), json={"full_name": "TEST_QR Pickup", "phone": "081234567890", "payment_method": "cod",
                                                              "store_id": STORE, "courier": "pickup"})
    assert r.status_code == 200, r.text
    o = r.json()
    yield o
    DB.orders.delete_one({"order_id": o["order_id"]})
    DB.notifications.delete_many({"order_id": o["order_id"]})
    DB.products.update_one({"product_id": PID}, {"$set": before})
    for it in saved_cart.get("items", []):
        requests.post(f"{API}/cart/items", headers=H(t, it.get("store_id") or STORE), json={"product_id": it["product_id"], "quantity": it["quantity"],
                                                                                           **({"variant_id": it["variant_id"]} if it.get("variant_id") else {})})


class TestPickupQR:
    def test_order_has_6_digit_code(self, tok, pickup):
        g = requests.get(f"{API}/orders/{pickup['order_id']}", headers=H(tok["demo"]))
        assert g.status_code == 200
        d = g.json()
        assert d["courier"]["code"] == "pickup" and d["status"] == "cod"
        assert d["pickup_code"].isdigit() and len(d["pickup_code"]) == 6

    @pytest.mark.parametrize("fmt", ["PGSAMBIL-{c}", "pgsambil-{c}", " PGSAMBIL-{c} ", "{c}"])
    def test_lookup_qr_formats_admin(self, tok, pickup, fmt):
        r = requests.post(f"{API}/seller/pickup/lookup", headers=H(tok["admin"]), json={"code": fmt.format(c=pickup["pickup_code"])})
        assert r.status_code == 200, r.text
        assert r.json()["order_id"] == pickup["order_id"] and r.json()["status"] == "cod"
        assert "_id" not in r.json()

    def test_lookup_qr_store_admin(self, tok, pickup):
        r = requests.post(f"{API}/seller/pickup/lookup", headers=H(tok["sidoarjo"]), json={"code": f"PGSAMBIL-{pickup['pickup_code']}"})
        assert r.status_code == 200 and r.json()["order_id"] == pickup["order_id"]

    def test_lookup_qr_other_branch_404(self, tok, pickup):
        r = requests.post(f"{API}/seller/pickup/lookup", headers=H(tok["jombang"]), json={"code": f"PGSAMBIL-{pickup['pickup_code']}"})
        assert r.status_code == 404

    def test_lookup_qr_customer_403(self, tok, pickup):
        r = requests.post(f"{API}/seller/pickup/lookup", headers=H(tok["demo"]), json={"code": f"PGSAMBIL-{pickup['pickup_code']}"})
        assert r.status_code == 403

    def test_lookup_qr_no_digits_404(self, tok):
        r = requests.post(f"{API}/seller/pickup/lookup", headers=H(tok["admin"]), json={"code": "PGSAMBIL-"})
        assert r.status_code == 404

    def test_lookup_does_not_mutate(self, tok, pickup):
        g = requests.get(f"{API}/orders/{pickup['order_id']}", headers=H(tok["demo"]))
        assert g.json()["status"] == "cod"
