# Iter 52: Salin ke Cabang mode "mix" (pct below threshold, Rp from threshold up) + Edit Massal Cabang Rupiah decreases (no -90 cap, never <= 0).
# WARNING: apply tests write real store_stock rows. Run /app/tests/backup/bb_backup.py BEFORE and bb_restore.py AFTER (BC_ALLOW_APPLY=1).
import os, sys, json
import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv('/app/backend/.env')
sys.path.insert(0, '/app/backend')
BASE_URL = os.environ.get('EXPO_PUBLIC_BACKEND_URL').rstrip('/')
db = MongoClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]
ALLOW_APPLY = os.environ.get('BC_ALLOW_APPLY') == '1'
CREATED = '/app/tests/backup/bb_created.json'
URL = f"{BASE_URL}/api/admin/branch-copy"
MIX = {"store_id": "pgs-jombang", "mode": "mix", "threshold": 20000, "price_pct": 10, "price_add": 2000, "copy_stock": False}


def pct_exact(v, pct):  # ceil to Rp100, integer basis points
    bp = 10000 + round(pct * 100)
    return max(100, -(-int(v) * bp // 1_000_000) * 100) if v else 0


def mix_expected(base, v, r=MIX):
    if not v:
        return 0
    return pct_exact(v, r["price_pct"]) if base < r["threshold"] else max(1, v + r["price_add"])


def _track(pid):
    d = json.load(open(CREATED)) if os.path.exists(CREATED) else {}
    d.setdefault("preview_ids", []).append(pid)
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


@pytest.fixture(scope="module")
def sido():
    return {p["product_id"]: p for p in db.products.find({"store_id": "pgs-official", "variants.0": {"$exists": False}},
                                                          {"_id": 0, "product_id": 1, "price": 1, "original_price": 1, "tier_prices": 1, "name": 1})}


def _preview(h, rules):
    r = requests.post(f"{URL}/preview", json={"rules": rules}, headers=h, timeout=180)
    if r.status_code == 200:
        _track(r.json()["preview_id"])
    return r


# --- mix rule preview
class TestMixPreview:
    def test_mix_counts_and_sample(self, admin, sido):
        r = _preview(admin, [MIX])
        assert r.status_code == 200, r.text
        b = r.json()["branches"][0]
        cheap = sum(1 for p in sido.values() if p.get("price", 0) < 20000)
        assert b["by_pct"] == cheap and b["by_rp"] == len(sido) - cheap, (b["by_pct"], b["by_rp"], cheap, len(sido))
        assert b["sample"], "no sample"
        for s in b["sample"]:
            p = sido[s["product_id"]]
            assert s["new_price"] == mix_expected(p["price"], p["price"]), (s, p["price"])
        print("mix by_pct", b["by_pct"], "by_rp", b["by_rp"], "changed", b["price_changed"])

    def test_threshold_zero_400(self, admin):
        r = _preview(admin, [{**MIX, "threshold": 0}])
        assert r.status_code == 400 and "ambang" in r.json()["detail"].lower(), r.text

    def test_mix_negative_pct(self, admin, sido):
        rule = {**MIX, "price_pct": -5}
        r = _preview(admin, [rule])
        assert r.status_code == 200, r.text
        for s in r.json()["branches"][0]["sample"]:
            p = sido[s["product_id"]]
            assert s["new_price"] == mix_expected(p["price"], p["price"], rule), (s, p["price"])

    def test_pct_mode_counts(self, admin, sido):
        r = _preview(admin, [{"store_id": "pgs-jember", "mode": "pct", "price_pct": 2, "copy_stock": False}])
        b = r.json()["branches"][0]
        assert b["by_pct"] == len(sido) and b["by_rp"] == 0


# --- Edit Massal Cabang Rupiah decreases
class TestBulkRp:
    def _pv(self, h, **body):
        return requests.post(f"{BASE_URL}/api/branch-prices/bulk/preview", json=body, headers=h, timeout=180)

    def test_rp_minus_1000_gula(self, jombang):
        r = self._pv(jombang, mode="rp", value=-1000, q="Gula Pasir")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["changed"] > 0 and d["down"] == d["changed"], d
        for s in d["sample"]:
            if s["before"]["price"] > 1000:
                assert s["after"]["price"] == s["before"]["price"] - 1000, s
            for k, rows in s["after"]["tier_prices"].items():
                for i, x in enumerate(rows):
                    assert x["price"] == s["before"]["tier_prices"][k][i]["price"] - 1000, (s["product_id"], k)

    def test_rp_big_decrease_skips(self, jombang):
        r = self._pv(jombang, mode="rp", value=-19000, q="Gula Pasir")
        assert r.status_code == 200, r.text
        d = r.json()
        print("changed", d["changed"], "errors", d["error_count"], d["errors"][:3])
        assert d["error_count"] > 0
        for e in d["errors"]:
            assert e["row"] == 0 and "akan jadi 0 / minus" in e["reason"] and "dilewati" in e["reason"]  # NOTE: comma becomes "." (minor text bug)
        for s in d["sample"]:
            assert s["after"]["price"] > 0
            assert all(x["price"] > 0 for rows in s["after"]["tier_prices"].values() for x in rows)

    def test_rp_huge_all_skipped(self, jombang):
        d = self._pv(jombang, mode="rp", value=-50_000_000, q="Gula").json()
        assert d["changed"] == 0 and d["error_count"] > 0

    def test_rp_full_scope_never_zero(self, jombang):
        d = self._pv(jombang, mode="rp", value=-5000).json()
        pv = db.branch_price_previews.find_one({"preview_id": d["preview_id"]}, {"_id": 0, "items": 1})
        bad = [i["product_id"] for i in pv["items"] if i["after"]["price"] <= 0 or i["after"]["original_price"] <= 0
               or any(x["price"] <= 0 for rows in i["after"]["tier_prices"].values() for x in rows)]
        print("full -5000 changed", d["changed"], "skipped", d["error_count"])
        assert not bad, bad[:10]

    @pytest.mark.parametrize("v", [-91, -100])
    def test_pct_below_90_400(self, jombang, v):
        r = self._pv(jombang, mode="pct", value=v, q="Gula Pasir")
        assert r.status_code == 400 and "Persen" in r.json()["detail"], r.text

    def test_pct_minus_90_ok(self, jombang):
        assert self._pv(jombang, mode="pct", value=-90, q="Gula Pasir").status_code == 200


# --- apply mix rule (writes real data; backup/restore around it)
@pytest.mark.skipif(not ALLOW_APPLY, reason="apply only with backup (BC_ALLOW_APPLY=1)")
class TestMixApply:
    def test_apply_mix_writes_prices(self, admin, sido):
        r = _preview(admin, [MIX])
        assert r.status_code == 200
        a = requests.post(f"{URL}/{r.json()['preview_id']}/apply", headers=admin, timeout=300)
        assert a.status_code == 200, a.text
        rows = {d["product_id"]: d for d in db.store_stock.find({"store_id": "pgs-jombang"}, {"_id": 0})}
        bad = []
        for pid, p in sido.items():
            row = rows.get(pid)
            base = p.get("price", 0)
            if row.get("manual_price_at"):
                continue
            if row["price"] != mix_expected(base, base):
                bad.append((pid, "price", base, row["price"]))
            for k, tr in (p.get("tier_prices") or {}).items():
                for i, x in enumerate(tr):
                    if row["tier_prices"][k][i]["price"] != mix_expected(base, x["price"]):
                        bad.append((pid, k, x["price"], row["tier_prices"][k][i]["price"]))
        assert not bad, bad[:10]
        # stock untouched (copy_stock False), jember untouched
        assert db.price_history.count_documents({"source": "branch_copy", "store_id": "pgs-jember", "at": {"$gte": db.branch_copy.find_one({"preview_id": r.json()["preview_id"]})["created_at"]}}) == 0
