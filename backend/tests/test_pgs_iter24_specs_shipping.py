# PGS iteration 24: product editor phase 2 (specs, weight/dimensions, shipping rules, pre-order) + re-verify 3 phase-1 bugs.
import os
import uuid

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
IMG = "https://pusatgrosirsidoarjo.com/wp-content/uploads/2023/07/Cetakan-7-Lubang-Cekung-Suggo-300x300.webp"
DESC = "Deskripsi **tebal** produk uji coba yang cukup panjang untuk validasi.\n- poin satu\n- poin dua"


def _env(k):
    for line in open("/app/backend/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip('"')


DB = MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]
CRED = {"sidoarjo": ("sidoarjo@pgs.id", "Sidoarjo123!"), "admin": ("admin@pgs.id", "Admin1234!"),
        "acct1": ("acct1@pgs.id", "Test1234!")}
PRODUCTS: list = []


def H(t):
    return {"Authorization": f"Bearer {t}"}


def form(**kw):
    base = {"name": f"TEST_Spek {uuid.uuid4().hex[:5]}", "category": "dapur", "subcategory": "peralatan-masak",
            "brand": "TEST", "condition": "new", "status": "active", "description": DESC, "images": [IMG],
            "price": 20000, "stock": 20, "min_order": 1, "max_order": 0, "weight_grams": 700}
    base.update(kw)
    return base


def publish(t, data, product_id=None):
    return requests.post(f"{API}/product-editor/publish", headers=H(t), json={"product_id": product_id, "data": data})


@pytest.fixture(scope="module")
def tok():
    t = {}
    for k, (e, p) in CRED.items():
        r = requests.post(f"{API}/auth/login", json={"email": e, "password": p})
        assert r.status_code == 200, r.text
        t[k] = r.json()["token"]
    yield t
    for pid in PRODUCTS:
        DB.products.delete_one({"product_id": pid, "name": {"$regex": "^TEST_"}})


@pytest.fixture()
def buyer():
    r = requests.post(f"{API}/auth/register", json={"email": f"test_pe24_{uuid.uuid4().hex[:8]}@example.com",
                                                    "password": "TestPass123!", "name": "TEST PE24"})
    assert r.status_code == 200, r.text
    t = r.json()["token"]
    yield t
    requests.delete(f"{API}/cart", headers=H(t))
    uid = DB.users.find_one({"email": r.json()["user"]["email"]}, {"user_id": 1})
    if uid:
        DB.users.delete_one({"user_id": uid["user_id"]})


# ---- Bug re-verification ----
class TestBugs:
    def test_bug3_imported_category(self, tok):
        r = requests.get(f"{API}/product-editor/products/pgs-9955", headers=H(tok["sidoarjo"]))
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["category"] == "dapur" and d["subcategory"] == "peralatan-masak", d

    def test_bug1_inactive_removed_from_cart_and_checkout(self, tok, buyer):
        data = form()
        r = publish(tok["sidoarjo"], data)
        assert r.status_code == 200, r.text
        pid = r.json()["product_id"]
        PRODUCTS.append(pid)
        r = requests.post(f"{API}/cart/items", headers=H(buyer), json={"product_id": pid, "quantity": 1})
        assert r.status_code == 200, r.text
        assert any(i["product_id"] == pid for i in r.json()["items"])
        r = publish(tok["sidoarjo"], {**data, "status": "inactive"}, product_id=pid)
        assert r.status_code == 200 and r.json()["status"] == "inactive", r.text
        cart = requests.get(f"{API}/cart", headers=H(buyer)).json()
        assert not any(i["product_id"] == pid for i in cart["items"]), cart
        r = requests.post(f"{API}/checkout", headers=H(buyer), json={"full_name": "TEST", "phone": "081234567",
                          "payment_method": "cod", "store_id": "pgs-official", "courier": "pickup"})
        assert r.status_code == 400, r.text


# ---- Publish validation (phase 2) ----
class TestValidation:
    @pytest.mark.parametrize("kw,key", [
        ({"weight_grams": 0}, "weight_grams"),
        ({"length_cm": 10, "width_cm": 0, "height_cm": 5}, "dimensions"),
        ({"ship_regular": False, "ship_cargo": False}, "shipping"),
        ({"preorder": True, "preorder_days": 0}, "preorder_days"),
    ])
    def test_publish_422(self, tok, kw, key):
        r = publish(tok["sidoarjo"], form(**kw))
        assert r.status_code == 422, r.text
        assert key in r.json()["detail"]["errors"], r.json()

    def test_preorder_days_over_90_rejected(self, tok):
        r = publish(tok["sidoarjo"], form(preorder=True, preorder_days=91))
        assert r.status_code == 422, r.text


# ---- Product API fields + specs filtering ----
class TestProductFields:
    def test_specs_and_shipping_fields_persist(self, tok):
        specs = {"material": "Stainless", "color": "Silver", "warranty": "1 tahun", "bogus": "x", "extra": "  "}
        r = publish(tok["sidoarjo"], form(specs=specs, length_cm=20, width_cm=10, height_cm=5,
                                          preorder=True, preorder_days=7, processing_days=3))
        assert r.status_code == 200, r.text
        pid = r.json()["product_id"]
        PRODUCTS.append(pid)
        p = requests.get(f"{API}/products/{pid}").json()
        assert p.get("specs") == {"material": "Stainless", "color": "Silver", "warranty": "1 tahun"}, p.get("specs")
        assert (p.get("weight_grams"), p.get("length_cm"), p.get("width_cm"), p.get("height_cm")) == (700, 20, 10, 5)
        assert p.get("preorder") is True and p.get("preorder_days") == 7 and p.get("processing_days") == 3
        e = requests.get(f"{API}/product-editor/products/{pid}", headers=H(tok["sidoarjo"])).json()["data"]
        assert e["specs"]["material"] == "Stainless" and e["preorder_days"] == 7 and e["weight_grams"] == 700

    def test_context_shipping(self, tok):
        r = requests.get(f"{API}/product-editor/context", headers=H(tok["sidoarjo"]))
        assert r.status_code == 200
        sh = r.json()["shipping"]["pgs-official"]
        assert "origin" in sh and isinstance(sh["pickup"], bool)
        assert all({"code", "name", "cargo"} <= set(c) for c in sh["couriers"]) and sh["couriers"]
        assert not any(c["code"] == "pickup" for c in sh["couriers"])


# ---- Shipping rules via /shipping/rates ----
class TestShippingRules:
    def test_product_couriers_limit(self, tok, buyer):
        r = publish(tok["sidoarjo"], form(couriers=["jne"]))
        assert r.status_code == 200, r.text
        pid = r.json()["product_id"]
        PRODUCTS.append(pid)
        assert requests.post(f"{API}/cart/items", headers=H(buyer), json={"product_id": pid, "quantity": 1}).status_code == 200
        rates = requests.post(f"{API}/shipping/rates", headers=H(buyer), json={"store_id": "pgs-official"}).json()
        codes = {c["code"] for c in rates}
        assert codes <= {"pickup", "jne"} and "jne" in codes, codes

    def test_cargo_rules(self, tok, buyer):
        """Temporarily add a cargo courier to acct1's store, restore afterwards."""
        st = DB.stores.find_one({"owner_id": DB.users.find_one({"email": "acct1@pgs.id"})["user_id"]})
        if not st or st.get("status") != "active":
            pytest.skip("acct1 store not active")
        sid, had, orig = st["store_id"], "couriers" in st, st.get("couriers")
        base = requests.get(f"{API}/seller/couriers", headers=H(tok["acct1"])).json()
        try:
            new = [c for c in base] + [{"code": "indahcargo", "name": "Indah Cargo", "cost": 50000, "eta": "3-5 hari", "active": True}]
            r = requests.put(f"{API}/seller/couriers", headers=H(tok["acct1"]), json={"couriers": new})
            assert r.status_code == 200, r.text
            ctx = requests.get(f"{API}/product-editor/context", headers=H(tok["acct1"])).json()["shipping"][sid]
            assert any(c["code"] == "indahcargo" and c["cargo"] for c in ctx["couriers"]), ctx
            # A: regular only -> no cargo
            a = publish(tok["acct1"], form(ship_regular=True, ship_cargo=False))
            assert a.status_code == 200, a.text
            pa = a.json()["product_id"]
            PRODUCTS.append(pa)
            # B: cargo only -> cargo, no regular
            b = publish(tok["acct1"], form(ship_regular=False, ship_cargo=True))
            assert b.status_code == 200, b.text
            pb = b.json()["product_id"]
            PRODUCTS.append(pb)
            requests.post(f"{API}/cart/items", headers=H(buyer), json={"product_id": pb, "quantity": 1})
            codes = {c["code"] for c in requests.post(f"{API}/shipping/rates", headers=H(buyer), json={"store_id": sid}).json()}
            assert "indahcargo" in codes and not codes & {"jne", "jnt", "sicepat"}, codes
            # add A too -> cargo hidden (A has no cargo), regular hidden (B has no regular)
            requests.post(f"{API}/cart/items", headers=H(buyer), json={"product_id": pa, "quantity": 1})
            codes = {c["code"] for c in requests.post(f"{API}/shipping/rates", headers=H(buyer), json={"store_id": sid}).json()}
            assert "indahcargo" not in codes and not codes & {"jne", "jnt", "sicepat"}, codes
        finally:
            if had:
                DB.stores.update_one({"store_id": sid}, {"$set": {"couriers": orig}})
            else:
                DB.stores.update_one({"store_id": sid}, {"$unset": {"couriers": ""}})
