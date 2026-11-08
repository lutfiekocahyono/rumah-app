# PGS iteration 30: per-product wholesale (harga grosir) tiers in rupiah per customer category; global /admin/pricing removed.
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
CRED = {"admin": ("admin@pgs.id", "Admin1234!"), "seller": ("acct1@pgs.id", "Test1234!"), "demo": ("demo@pgs.id", "Demo1234!")}
PRODUCTS: list = []
TIERS = {"langsung": [{"min_qty": 6, "price": 9000}, {"min_qty": 12, "price": 8500}], "reseller": [{"min_qty": 1, "price": 9500}]}


def H(t):
    return {"Authorization": f"Bearer {t}"}


def form(**kw):
    base = {"name": f"TEST_Grosir {uuid.uuid4().hex[:5]}", "category": "dapur", "subcategory": "peralatan-masak",
            "brand": "TEST", "sku": "TSKU", "condition": "new", "status": "active", "description": DESC,
            "images": [IMG], "price": 10000, "discount_price": 0, "stock": 50, "min_order": 1, "max_order": 0, "weight_grams": 500}
    base.update(kw)
    return base


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
        DB.price_history.delete_many({"product_id": pid})


def publish(t, data, **kw):
    r = requests.post(f"{API}/product-editor/publish", headers=H(t), json={"data": data, **kw})
    if r.status_code == 200:
        PRODUCTS.append(r.json()["product_id"])
    return r


def get_p(pid, t=None):
    r = requests.get(f"{API}/products/{pid}", headers=H(t) if t else {})
    assert r.status_code == 200, r.text
    return r.json()


# ---------- migration ----------
class TestMigration:
    def test_all_official_simple_products_migrated(self):
        q = {"store_id": "pgs-official", "variants": {"$in": [[], None]}}
        total = DB.products.count_documents(q)
        missing = DB.products.count_documents({**q, "$or": [{"tier_prices": {"$exists": False}}, {"tier_prices": {}}]})
        print("official simple", total, "missing tiers", missing)
        assert total >= 6618 and missing == 0
        assert DB.settings.find_one({"key": "pricing_per_product"}) and not DB.settings.find_one({"key": "pricing"})

    def test_pgs_9849_tiers(self):
        p = get_p("pgs-9849")
        assert p["price"] == 167000
        m = {r["min_qty"]: r for r in p["price_matrix"]}
        assert (m[1]["langsung"], m[6]["langsung"], m[12]["langsung"]) == (167000, 163660, 160320), m
        assert m[1]["pengecer"] == 161990 and m[1]["reseller"] == 158650 and m[12]["reseller"] == 152304, m
        assert [t["price"] for t in p["price_tiers"]] == [167000, 163660, 160320]
        assert p["price_min"] == 160320 and p["price_max"] == 167000  # guest = Pembeli Langsung: own category range only
        raw = DB.products.find_one({"product_id": "pgs-9849"}, {"_id": 0, "price": 1, "original_price": 1})
        assert raw["price"] == 167000 and raw["original_price"] >= 167000


# ---------- global pricing removed ----------
class TestGlobalRemoved:
    def test_admin_pricing_gone(self, tok):
        assert requests.get(f"{API}/admin/pricing", headers=H(tok["admin"])).status_code in (404, 405)
        assert requests.put(f"{API}/admin/pricing", headers=H(tok["admin"]), json={}).status_code in (404, 405)


# ---------- publish / validation ----------
class TestEditor:
    def test_no_tiers_single_row(self, tok):
        r = publish(tok["seller"], form())
        assert r.status_code == 200, r.text
        p = get_p(r.json()["product_id"])
        assert p["price_tiers"] == [{"min_qty": 1, "price": 10000}] and p["price_min"] == p["price_max"] == 10000

    def test_tiers_per_type(self, tok):
        r = publish(tok["seller"], form(tier_prices=TIERS))
        assert r.status_code == 200, r.text
        pid = r.json()["product_id"]
        m = {x["min_qty"]: x for x in get_p(pid)["price_matrix"]}
        assert m[1] == {"min_qty": 1, "langsung": 10000, "pengecer": 10000, "reseller": 9500}, m
        assert m[6]["pengecer"] == 9000 and m[12]["pengecer"] == 8500  # pengecer falls back to langsung table
        assert m[12]["reseller"] == 9500
        p = get_p(pid, tok["demo"])
        assert [t["price"] for t in p["price_tiers"]] == [10000, 9000, 8500]
        assert p["price_min"] == 8500 and p["price_max"] == 10000
        # editor returns the tiers
        e = requests.get(f"{API}/product-editor/products/{pid}", headers=H(tok["seller"]))
        assert e.status_code == 200, e.text
        assert e.json()["data"]["tier_prices"] == TIERS
        pytest.shared_pid = pid

    def test_cart_unit_price_by_qty(self, tok):
        pid = pytest.shared_pid
        me = requests.get(f"{API}/auth/me", headers=H(tok["demo"])).json()
        assert me.get("customer_type", "langsung") == "langsung", me
        h = H(tok["demo"])
        try:
            r = requests.post(f"{API}/cart/items", headers=h, json={"product_id": pid, "quantity": 1})
            assert r.status_code == 200, r.text
            seen = {}
            for q in (1, 5, 6, 11, 12, 20):
                c = requests.put(f"{API}/cart/items/{pid}", headers=h, json={"quantity": q}).json()
                it = next(i for i in c["items"] if i["product_id"] == pid)
                seen[q] = (it["price"], (it.get("next_tier") or {}).get("min_qty"))
            print(seen)
            assert {q: v[0] for q, v in seen.items()} == {1: 10000, 5: 10000, 6: 9000, 11: 9000, 12: 8500, 20: 8500}
            assert seen[1][1] == 6 and seen[6][1] == 12 and seen[12][1] is None
        finally:
            requests.delete(f"{API}/cart/items/{pid}", headers=h)

    @pytest.mark.parametrize("tiers,typ", [
        ({"langsung": [{"min_qty": 6, "price": 9000}, {"min_qty": 6, "price": 8000}]}, "langsung"),
        ({"pengecer": [{"min_qty": 6, "price": 50}]}, "pengecer"),
        ({"langsung": [{"min_qty": 6, "price": 8000}, {"min_qty": 12, "price": 9000}]}, "langsung"),
        ({"langsung": [{"min_qty": 6, "price": 11000}]}, "langsung"),  # more expensive than harga jual
        ({"reseller": [{"min_qty": 1, "price": 9000}, {"min_qty": 12, "price": 9500}]}, "reseller"),
    ])
    def test_validation_422(self, tok, tiers, typ):
        r = publish(tok["seller"], form(tier_prices=tiers))
        assert r.status_code == 422, r.text
        print(r.json())
        assert f"tiers.{typ}" in str(r.json())

    def test_variant_product_ignores_tiers(self, tok):
        opts = [{"name": "Warna", "values": ["Merah"]}]
        rows = [{"values": ["Merah"], "price": 12000, "stock": 5, "sku": "R", "active": True}]
        r = publish(tok["seller"], form(variants_enabled=True, variant_options=opts, variants=rows, tier_prices=TIERS))
        assert r.status_code == 200, r.text
        assert DB.products.find_one({"product_id": r.json()["product_id"]})["tier_prices"] == {}

    def test_migrated_product_editor_has_tiers(self, tok):
        r = requests.get(f"{API}/product-editor/products/pgs-9849", headers=H(tok["admin"]))
        assert r.status_code == 200, r.text
        tp = r.json()["data"]["tier_prices"]
        assert {x["min_qty"]: x["price"] for x in tp["langsung"]} == {6: 163660, 12: 160320}, tp
        assert tp["reseller"][0] == {"min_qty": 1, "price": 158650}


# ---------- bulk ----------
class TestBulk:
    def test_bulk_up_pct_scales_tiers_and_history(self, tok):
        r = publish(tok["seller"], form(tier_prices=TIERS))
        assert r.status_code == 200, r.text
        pid = r.json()["product_id"]
        b = requests.post(f"{API}/product-editor/bulk", headers=H(tok["seller"]),
                          json={"product_ids": [pid], "price_mode": "up_pct", "price_value": 10})
        assert b.status_code == 200 and b.json()["updated"] == 1, b.text
        d = DB.products.find_one({"product_id": pid})
        assert d["price"] == 11000
        assert d["tier_prices"]["langsung"] == [{"min_qty": 6, "price": 9900}, {"min_qty": 12, "price": 9350}], d["tier_prices"]
        assert d["tier_prices"]["reseller"] == [{"min_qty": 1, "price": 10450}]
        h = list(DB.price_history.find({"product_id": pid, "source": "bulk"}, {"_id": 0}))
        fields = [c["field"] for l in h for c in l.get("changes", [])]
        print(h)
        assert "tier_prices" in fields, h
