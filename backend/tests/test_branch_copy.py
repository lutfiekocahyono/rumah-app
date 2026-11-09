# Branch copy (Salin Harga & Stok Sidoarjo -> Jombang/Jember) tests.
# WARNING: apply test writes real store_stock rows. Run /app/tests/backup/bc_backup.py BEFORE and /app/tests/backup/bc_restore.py AFTER.
import os
import json
import uuid
import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv('/app/backend/.env')
BASE_URL = os.environ.get('EXPO_PUBLIC_BACKEND_URL').rstrip('/')
db = MongoClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]
RULES = [{"store_id": "pgs-jombang", "price_add": 2000, "stock_sub": 3}, {"store_id": "pgs-jember", "price_add": 1000, "stock_sub": 5}]
TIER, BIG, LOW = "pgs-9955", "pgs-10649", "pgs-9947"
CREATED = '/app/tests/backup/created_ids.json'
ALLOW_APPLY = os.environ.get('BC_ALLOW_APPLY') == '1'


def _track(key, val):
    d = json.load(open(CREATED)) if os.path.exists(CREATED) else {}
    d.setdefault(key, []).append(val)
    json.dump(d, open(CREATED, 'w'))


def _login(email, pw):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"login failed {email}")
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def admin():
    return _login("admin@pgs.id", "Admin1234!")


@pytest.fixture(scope="module")
def customer():
    return _login("demo@pgs.id", "Demo1234!")


def _preview(h, rules=RULES):
    r = requests.post(f"{BASE_URL}/api/admin/branch-copy/preview", json={"rules": rules}, headers=h, timeout=120)
    if r.status_code == 200:
        _track("preview_ids", r.json()["preview_id"])
    return r


# --- preview: auth & validation
class TestPreview:
    def test_customer_forbidden(self, customer):
        assert _preview(customer).status_code == 403

    def test_no_auth(self):
        assert _preview({}).status_code in (401, 403)

    def test_invalid_store_official(self, admin):
        r = _preview(admin, [{"store_id": "pgs-official", "price_add": 1, "stock_sub": 0}])
        assert r.status_code == 400

    def test_invalid_store_unknown(self, admin):
        assert _preview(admin, [{"store_id": "toko-xyz", "price_add": 1, "stock_sub": 0}]).status_code == 400

    def test_duplicate_store(self, admin):
        assert _preview(admin, [RULES[0], RULES[0]]).status_code == 400

    def test_preview_counts(self, admin):
        r = _preview(admin)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["preview_id"].startswith("bc_")
        by = {b["store_id"]: b for b in d["branches"]}
        assert set(by) == {"pgs-jombang", "pgs-jember"}
        for b in by.values():
            assert b["total"] == 6618
            for k in ("price_changed", "stock_changed", "unchanged", "zero_stock"):
                assert isinstance(b[k], int)
            assert b["store_name"] and isinstance(b["sample"], list) and len(b["sample"]) <= 30
            s = b["sample"][0]
            add = 2000 if b["store_id"] == "pgs-jombang" else 1000
            assert s["new_price"] == s["sidoarjo_price"] + add
            print(b["store_id"], {k: b[k] for k in ("total", "price_changed", "stock_changed", "unchanged", "zero_stock")})


# --- apply: writes branch prices/stock, single use, history
@pytest.mark.skipif(not ALLOW_APPLY, reason="apply only with backup (BC_ALLOW_APPLY=1)")
class TestApply:
    def test_apply_and_verify(self, admin):
        ev0, nt0 = db.product_events.count_documents({}), db.notifications.count_documents({})
        src = {p["product_id"]: p for p in db.products.find({"product_id": {"$in": [TIER, BIG, LOW]}}, {"_id": 0})}
        pid = _preview(admin).json()["preview_id"]
        r = requests.post(f"{BASE_URL}/api/admin/branch-copy/{pid}/apply", headers=admin, timeout=300)
        assert r.status_code == 200, r.text
        print("apply:", r.json())
        r2 = requests.post(f"{BASE_URL}/api/admin/branch-copy/{pid}/apply", headers=admin, timeout=60)
        assert r2.status_code == 400
        for sid, add, sub in (("pgs-jombang", 2000, 3), ("pgs-jember", 1000, 5)):
            for prod_id, p in src.items():
                row = db.store_stock.find_one({"store_id": sid, "product_id": prod_id}, {"_id": 0})
                assert row["price"] == p["price"] + add
                assert row["stock"] == max(0, p["stock"] - sub)
                for ct, tiers in p["tier_prices"].items():
                    assert [t["price"] + add for t in tiers] == [t["price"] for t in row["tier_prices"][ct]]
        assert db.store_stock.find_one({"store_id": "pgs-jombang", "product_id": BIG})["stock"] == 9996
        assert db.store_stock.find_one({"store_id": "pgs-jember", "product_id": BIG})["stock"] == 9994
        assert db.store_stock.find_one({"store_id": "pgs-jember", "product_id": LOW})["stock"] == 0
        assert db.product_events.count_documents({}) == ev0
        assert db.notifications.count_documents({}) == nt0
        print("price_history branch_copy rows:", db.price_history.count_documents({"source": "branch_copy"}))

    def test_history_label(self, admin):
        r = requests.get(f"{BASE_URL}/api/history/price-stock", params={"store_id": "pgs-jombang", "product_id": TIER}, headers=admin, timeout=30)
        assert r.status_code == 200
        items = r.json()["items"]
        assert items and items[0]["source"] == "branch_copy" and items[0]["source_label"] == "Salin dari Sidoarjo"
        kinds = {c["kind"] for c in items[0]["changes"]}
        print("changes kinds:", kinds, items[0]["changes"][:3])

    def test_product_detail_branch_price(self):
        sid_p = db.products.find_one({"product_id": TIER})
        for sid, add in (("pgs-jombang", 2000), ("pgs-jember", 1000), ("pgs-official", 0)):
            d = requests.get(f"{BASE_URL}/api/products/{TIER}", headers={"X-Store-Id": sid}, timeout=30).json()
            assert d["price"] == sid_p["price"] + add, (sid, d["price"])
            assert d["price_tiers"][1]["price"] == sid_p["tier_prices"]["langsung"][0]["price"] + add, d["price_tiers"]

    def test_product_list_store_branch_price(self):
        sid_p = db.products.find_one({"product_id": TIER})
        res = {}
        for sid in ("pgs-jombang", "pgs-official"):
            lst = requests.get(f"{BASE_URL}/api/products", params={"store": "pgs-official", "q": sid_p["name"]}, headers={"X-Store-Id": sid}, timeout=30).json()
            res[sid] = next(p["price"] for p in lst if p["product_id"] == TIER)
        assert res == {"pgs-jombang": sid_p["price"] + 2000, "pgs-official": sid_p["price"]}, res

    def test_product_list_home_branch_price(self):
        # home/search (no ?store=) with chosen branch Jombang
        sid_p = db.products.find_one({"product_id": TIER})
        lst = requests.get(f"{BASE_URL}/api/products", params={"q": sid_p["name"]}, headers={"X-Store-Id": "pgs-jombang"}, timeout=30).json()
        price = next(p["price"] for p in lst if p["product_id"] == TIER)
        assert price == sid_p["price"] + 2000, f"home list shows {price}, Jombang price {sid_p['price'] + 2000}"

    def test_cart_jember_price_and_tier(self):
        g = {"X-Guest-Id": f"TEST_guest_{uuid.uuid4().hex[:8]}", "X-Store-Id": "pgs-jember"}
        _track("guest_ids", g["X-Guest-Id"])
        p = db.products.find_one({"product_id": TIER})
        r = requests.post(f"{BASE_URL}/api/cart/items", json={"product_id": TIER, "quantity": 1}, headers=g, timeout=30)
        assert r.status_code == 200, r.text
        line = r.json()["items"][0]
        assert line["store_id"] == "pgs-jember" and line["price"] == p["price"] + 1000, line
        r = requests.post(f"{BASE_URL}/api/cart/items", json={"product_id": TIER, "quantity": 5}, headers=g, timeout=30)
        line = r.json()["items"][0]
        assert line["quantity"] == 6 and line["price"] == p["tier_prices"]["langsung"][0]["price"] + 1000, line

    def test_sidoarjo_change_not_followed(self):
        p = db.products.find_one({"product_id": TIER}, {"price": 1})
        db.products.update_one({"product_id": TIER}, {"$set": {"price": p["price"] + 500}})
        try:
            d = requests.get(f"{BASE_URL}/api/products/{TIER}", headers={"X-Store-Id": "pgs-jombang"}, timeout=30).json()
            o = requests.get(f"{BASE_URL}/api/products/{TIER}", headers={"X-Store-Id": "pgs-official"}, timeout=30).json()
            assert o["price"] == p["price"] + 500
            assert d["price"] == p["price"] + 2000
        finally:
            db.products.update_one({"product_id": TIER}, {"$set": {"price": p["price"]}})
