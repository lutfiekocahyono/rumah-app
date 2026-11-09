# Branch copy v2 (mode rp/pct, copy_price/copy_stock toggles, manual-price protection) tests.
# WARNING: apply tests write real store_stock rows. Run /app/tests/backup/bc_pct_backup.py BEFORE and bc_pct_restore.py AFTER.
import os, sys, json, math
from decimal import Decimal, ROUND_CEILING
import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv('/app/backend/.env')
sys.path.insert(0, '/app/backend')
BASE_URL = os.environ.get('EXPO_PUBLIC_BACKEND_URL').rstrip('/')
db = MongoClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]
TIER, BIG, LOW = "pgs-9955", "pgs-10649", "pgs-9947"
CREATED = '/app/tests/backup/bc_pct_created.json'
ALLOW_APPLY = os.environ.get('BC_ALLOW_APPLY') == '1'
URL = f"{BASE_URL}/api/admin/branch-copy"


def exact(v, pct):  # spec: ceil(P*(1+pct/100)/100)*100, min 100
    return max(100, int((Decimal(v) * (1 + Decimal(str(pct)) / 100) / 100).to_integral_value(ROUND_CEILING)) * 100) if v else 0


def _track(val):
    d = json.load(open(CREATED)) if os.path.exists(CREATED) else {}
    d.setdefault("preview_ids", []).append(val)
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
def jombang():
    return _login("jombang@pgs.id", "Jombang123!")


def _preview(h, rules):
    r = requests.post(f"{URL}/preview", json={"rules": rules}, headers=h, timeout=180)
    if r.status_code == 200:
        _track(r.json()["preview_id"])
    return r


def _by(r):
    assert r.status_code == 200, r.text
    return {b["store_id"]: b for b in r.json()["branches"]}


def _sid(pid):
    return db.products.find_one({"product_id": pid}, {"_id": 0})


# --- validation of new rule fields
class TestValidation:
    @pytest.mark.parametrize("rule", [{"mode": "xx"}, {"mode": "pct", "price_pct": 101}, {"mode": "pct", "price_pct": -51}])
    def test_invalid(self, admin, rule):
        assert _preview(admin, [{"store_id": "pgs-jember", **rule}]).status_code == 422

    def test_defaults_keep_old_behaviour(self, admin):
        b = _by(_preview(admin, [{"store_id": "pgs-jember", "price_add": 1000, "stock_sub": 5}]))["pgs-jember"]
        for k in ("protected", "protected_overwritten", "big_rise", "protected_sample"):
            assert k in b
        s = b["sample"][0] if b["sample"] else None
        print("defaults:", {k: b[k] for k in ("price_changed", "stock_changed", "unchanged", "protected", "big_rise")})


# --- pct math (unit, exact rounding)
class TestPctMath:
    @pytest.mark.parametrize("pct", [1, 2, 7, 10])
    def test_price_fn_exact(self, pct):
        import branch_copy
        f = branch_copy.price_fn(branch_copy.Rule(store_id="x", mode="pct", price_pct=pct))
        vals = [3000, 6000, 10000, 11000, 30000, 60000, 99, 150, 12345]
        bad = [(v, f(v), exact(v, pct)) for v in vals if f(v) != exact(v, pct)]
        assert not bad, f"float rounding wrong (value, got, expected): {bad}"


# --- preview pct / toggles
class TestPreview:
    def test_pct_preview_values_and_no_stock(self, admin):
        b = _by(_preview(admin, [{"store_id": "pgs-jember", "mode": "pct", "price_pct": 2, "copy_stock": False}]))["pgs-jember"]
        assert b["stock_changed"] == 0 and b["zero_stock"] == 0
        assert b["price_changed"] > 0 and b["sample"]
        for s in b["sample"]:
            assert s["new_price"] == exact(s["sidoarjo_price"], 2), s
            assert s["new_stock"] == s["old_stock"]

    def test_copy_price_false(self, admin):
        b = _by(_preview(admin, [{"store_id": "pgs-jember", "copy_price": False, "copy_stock": True, "stock_sub": 5}]))["pgs-jember"]
        assert b["price_changed"] == 0 and b["protected"] == 0
        for s in b["sample"]:
            assert s["new_price"] == s["old_price"]

    def test_big_rise(self, admin):
        b = _by(_preview(admin, [{"store_id": "pgs-jember", "mode": "pct", "price_pct": 60, "copy_stock": False}]))["pgs-jember"]
        assert b["big_rise"] > 0 and b["big_rise"] == b["price_changed"], (b["big_rise"], b["price_changed"])
        b2 = _by(_preview(admin, [{"store_id": "pgs-jember", "mode": "pct", "price_pct": 2, "copy_stock": False}]))["pgs-jember"]
        print("big_rise pct2:", b2["big_rise"])


# --- protection + apply (writes; restore afterwards)
@pytest.mark.skipif(not ALLOW_APPLY, reason="apply only with backup (BC_ALLOW_APPLY=1)")
class TestProtectionApply:
    def test_01_manual_put_sets_flag(self, jombang):
        p = _sid(TIER)
        r = requests.put(f"{BASE_URL}/api/branch-prices/{TIER}", json={"price": p["price"] + 2500, "tier_prices": {}}, headers=jombang, timeout=30)
        assert r.status_code == 200, r.text
        row = db.store_stock.find_one({"store_id": "pgs-jombang", "product_id": TIER})
        assert row.get("manual_price_at") and row["price"] == p["price"] + 2500

    def test_02_preview_protected(self, admin):
        p = _sid(TIER)
        b = _by(_preview(admin, [{"store_id": "pgs-jombang", "mode": "pct", "price_pct": 2, "copy_stock": False}]))["pgs-jombang"]
        assert b["protected"] == 1 and b["protected_overwritten"] == 0
        ps = b["protected_sample"][0]
        assert ps["product_id"] == TIER and ps["branch_price"] == p["price"] + 2500 and ps["would_be"] == exact(p["price"], 2), ps
        b2 = _by(_preview(admin, [{"store_id": "pgs-jombang", "mode": "pct", "price_pct": 2, "copy_stock": False, "overwrite_manual": True}]))["pgs-jombang"]
        assert b2["protected"] == 0 and b2["protected_overwritten"] == 1

    def test_03_apply_pct_keeps_protected(self, admin):
        stock_before = {d["product_id"]: d["stock"] for d in db.store_stock.find({"store_id": "pgs-jombang", "product_id": {"$in": [TIER, BIG, LOW]}})}
        pid = _preview(admin, [{"store_id": "pgs-jombang", "mode": "pct", "price_pct": 2, "copy_stock": False}]).json()["preview_id"]
        r = requests.post(f"{URL}/{pid}/apply", headers=admin, timeout=300)
        assert r.status_code == 200, r.text
        assert requests.post(f"{URL}/{pid}/apply", headers=admin, timeout=60).status_code == 400
        tp = db.products.find_one({"store_id": "pgs-official", "tier_prices.langsung.0": {"$exists": True}, "product_id": {"$ne": TIER}, "variants.0": {"$exists": False}})
        for prod in (BIG, LOW, tp["product_id"]):
            p, row = _sid(prod), db.store_stock.find_one({"store_id": "pgs-jombang", "product_id": prod})
            assert row["price"] == exact(p["price"], 2), (prod, row["price"], p["price"])
            assert row["original_price"] == max(row["price"], exact(p.get("original_price") or p["price"], 2))
            for ct, tiers in (p.get("tier_prices") or {}).items():
                assert [exact(t["price"], 2) for t in tiers] == [t["price"] for t in row["tier_prices"][ct]], (prod, ct)
            if prod in stock_before:
                assert row["stock"] == stock_before[prod]
        row = db.store_stock.find_one({"store_id": "pgs-jombang", "product_id": TIER})
        assert row["price"] == _sid(TIER)["price"] + 2500 and row.get("manual_price_at")
        h = db.price_history.find_one({"source": "branch_copy", "store_id": "pgs-jombang", "product_id": BIG}, sort=[("at", -1)])
        assert h and all(c["field"] in ("price", "original_price", "tier_prices") for c in h["changes"]), h and h["changes"]

    def test_04_protected_stock_still_copied(self, admin):
        p = _sid(TIER)
        db.store_stock.update_one({"store_id": "pgs-jombang", "product_id": TIER}, {"$set": {"stock": 77}})
        pid = _preview(admin, [{"store_id": "pgs-jombang", "mode": "rp", "price_add": 2000, "copy_stock": True, "stock_sub": 3}]).json()["preview_id"]
        assert requests.post(f"{URL}/{pid}/apply", headers=admin, timeout=300).status_code == 200
        row = db.store_stock.find_one({"store_id": "pgs-jombang", "product_id": TIER})
        assert row["price"] == p["price"] + 2500 and row["stock"] == max(0, p["stock"] - 3) and row.get("manual_price_at")
        h = db.price_history.find_one({"source": "branch_copy", "store_id": "pgs-jombang", "product_id": TIER}, sort=[("at", -1)])
        assert [c["field"] for c in h["changes"]] == ["stock"], h["changes"]

    def test_05_overwrite_manual(self, admin):
        p = _sid(TIER)
        b = _by(_preview(admin, [{"store_id": "pgs-jombang", "price_add": 2000, "copy_stock": False, "overwrite_manual": True}]))
        assert b["pgs-jombang"]["protected_overwritten"] == 1
        pid = list(json.load(open(CREATED))["preview_ids"])[-1]
        assert requests.post(f"{URL}/{pid}/apply", headers=admin, timeout=300).status_code == 200
        row = db.store_stock.find_one({"store_id": "pgs-jombang", "product_id": TIER})
        assert row["price"] == p["price"] + 2000 and "manual_price_at" not in row
        h = db.price_history.find_one({"source": "branch_copy", "store_id": "pgs-jombang", "product_id": TIER}, sort=[("at", -1)])
        assert all(c["field"] != "stock" for c in h["changes"]), h["changes"]
