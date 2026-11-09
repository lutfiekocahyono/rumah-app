# Edit Massal Cabang (branch bulk price: pct/rp/Excel -> preview -> apply) + Salin ke Cabang negative pct.
# WARNING: apply tests write real store_stock rows. Run /app/tests/backup/bb_backup.py BEFORE and bb_restore.py AFTER.
import io
import json
import os
import sys
from decimal import Decimal, ROUND_CEILING

import pytest
import requests
from dotenv import load_dotenv
from openpyxl import Workbook, load_workbook
from pymongo import MongoClient

sys.path.insert(0, '/app/backend')
load_dotenv('/app/backend/.env')
BASE_URL = os.environ.get('EXPO_PUBLIC_BACKEND_URL').rstrip('/')
API = f"{BASE_URL}/api"
db = MongoClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]
J, JEM, OFF = "pgs-jombang", "pgs-jember", "pgs-official"
ALLOW_APPLY = os.environ.get('BC_ALLOW_APPLY') == '1'
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def exact(v, pct):  # spec: ceil(P*(1+pct/100)/100)*100, min 100
    return max(100, int((Decimal(v) * (1 + Decimal(str(pct)) / 100) / 100).to_integral_value(ROUND_CEILING)) * 100) if v else 0


def _login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"login failed {email}")
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def jombang():
    return _login("jombang@pgs.id", "Jombang123!")


@pytest.fixture(scope="module")
def jember():
    return _login("jember@pgs.id", "Jember123!")


@pytest.fixture(scope="module")
def sidoarjo():
    return _login("sidoarjo@pgs.id", "Sidoarjo123!")


@pytest.fixture(scope="module")
def admin():
    return _login("admin@pgs.id", "Admin1234!")


@pytest.fixture(scope="module")
def prods():
    """2 active non-variant Sidoarjo products with tiers that jombang has a priced row for."""
    out = []
    for p in db.products.find({"store_id": OFF, "status": "active", "variants.0": {"$exists": False}, "tier_prices.langsung.0": {"$exists": True}},
                              {"_id": 0, "product_id": 1, "name": 1, "price": 1, "tier_prices": 1}).limit(200):
        r = db.store_stock.find_one({"store_id": J, "product_id": p["product_id"], "price": {"$gt": 0}, "tier_prices.langsung.0": {"$exists": True}})
        if r:
            out.append(p)
        if len(out) == 2:
            break
    assert len(out) == 2, "need 2 products with tiers"
    return out


def _row(sid, pid):
    return db.store_stock.find_one({"store_id": sid, "product_id": pid}, {"_id": 0})


def _pv(h, **body):
    return requests.post(f"{API}/branch-prices/bulk/preview", json=body, headers=h, timeout=180)


# --- access control
class TestAccess:
    def test_other_store_403(self, jombang, prods):
        assert _pv(jombang, store_id=JEM, mode="pct", value=5, product_ids=[prods[0]["product_id"]]).status_code == 403

    def test_sidoarjo_403(self, sidoarjo, prods):
        assert _pv(sidoarjo, mode="pct", value=5, product_ids=[prods[0]["product_id"]]).status_code == 403

    def test_no_token_401(self, prods):
        r = requests.post(f"{API}/branch-prices/bulk/preview", json={"mode": "pct", "value": 5}, timeout=30)
        assert r.status_code in (401, 403)

    def test_admin_official_400(self, admin, prods):
        assert _pv(admin, store_id=OFF, mode="pct", value=5, product_ids=[prods[0]["product_id"]]).status_code == 400


# --- validation
class TestValidation:
    @pytest.mark.parametrize("body,code", [({"mode": "pct", "value": 101}, 400), ({"mode": "pct", "value": 0}, 400),
                                           ({"mode": "rp", "value": 0}, 400), ({"mode": "pct", "value": -91}, (400, 422))])
    def test_bad(self, jombang, prods, body, code):
        r = _pv(jombang, product_ids=[prods[0]["product_id"]], **body)
        assert r.status_code in (code if isinstance(code, tuple) else (code,)), (r.status_code, r.text)

    def test_rp_down_1000_allowed(self, jombang, prods):
        """UI 'Turunkan Rp 1000' sends value -1000 -> must be accepted."""
        r = _pv(jombang, mode="rp", value=-1000, product_ids=[prods[0]["product_id"]])
        assert r.status_code == 200, (r.status_code, r.text[:300])


# --- preview math
class TestPreview:
    def test_pct_up_tiers(self, jombang, prods):
        r = _pv(jombang, mode="pct", value=7, tiers=True, product_ids=[p["product_id"] for p in prods])
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["changed"] == 2 and d["up"] == 2 and d["down"] == 0 and len(d["sample"]) == 2
        for s in d["sample"]:
            row = _row(J, s["product_id"])
            assert s["before"]["price"] == row["price"]  # from current branch price
            assert s["after"]["price"] == exact(row["price"], 7), s
            for t, rows in s["before"]["tier_prices"].items():
                assert [x["price"] for x in s["after"]["tier_prices"][t]] == [exact(x["price"], 7) for x in rows]

    def test_pct_down_no_tiers(self, jombang, prods):
        d = _pv(jombang, mode="pct", value=-10, tiers=False, product_ids=[p["product_id"] for p in prods]).json()
        assert d["down"] == 2 and d["up"] == 0
        for s in d["sample"]:
            assert s["after"]["price"] == exact(s["before"]["price"], -10)
            assert s["after"]["tier_prices"] == s["before"]["tier_prices"]

    def test_rp_up(self, jombang, prods):
        d = _pv(jombang, mode="rp", value=500, product_ids=[prods[0]["product_id"]]).json()
        s = d["sample"][0]
        assert s["after"]["price"] == s["before"]["price"] + 500

    def test_q_scope(self, jombang, prods):
        name = prods[0]["name"]
        d = _pv(jombang, mode="pct", value=5, q=name).json()
        assert d["changed"] >= 1 and all(name.lower() in s["name"].lower() for s in d["sample"])

    def test_admin_jember(self, admin, prods):
        d = _pv(admin, store_id=JEM, mode="pct", value=5, product_ids=[prods[0]["product_id"]]).json()
        assert d["store_id"] == JEM and d["changed"] == 1


# --- Excel export / import
def _export(h):
    r = requests.get(f"{API}/branch-prices/export", headers=h, timeout=180)
    assert r.status_code == 200, r.text[:200]
    return r


def _upload(h, data, name="x.xlsx", mime=XLSX):
    return requests.post(f"{API}/branch-prices/import", headers=h, files={"file": (name, data, mime)}, timeout=180)


def _wb_bytes(wb):
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


@pytest.fixture(scope="module")
def exported(jombang):
    return _export(jombang).content


class TestExcel:
    def test_export_columns(self, exported, prods):
        ws = load_workbook(io.BytesIO(exported)).active
        rows = list(ws.iter_rows(values_only=True))
        assert list(rows[0]) == ["ID Produk", "Nama Produk", "Harga Sidoarjo (info)", "Harga Cabang", "Harga Coret Cabang",
                                 "Grosir Pembeli Langsung", "Grosir Pengecer", "Grosir Reseller"]
        r = next(x for x in rows if x[0] == prods[0]["product_id"])
        st = _row(J, prods[0]["product_id"])
        assert r[3] == st["price"]
        assert r[5] == "; ".join(f"{t['min_qty']}:{t['price']}" for t in st["tier_prices"]["langsung"])
        print("rows:", len(rows) - 1, "sample:", r)

    def test_unchanged_zero(self, jombang, exported):
        d = _upload(jombang, exported).json()
        print("unchanged import:", d["changed"], d["error_count"], d["errors"][:3], [s["product_id"] for s in d["sample"][:3]])
        assert d["changed"] == 0 and d["error_count"] == 0

    def test_edit_and_errors(self, jombang, exported, prods):
        wb = load_workbook(io.BytesIO(exported))
        ws = wb.active
        idx = {ws.cell(r, 1).value: r for r in range(2, ws.max_row + 1)}
        r0 = idx[prods[0]["product_id"]]
        ws.cell(r0, 4).value = ws.cell(r0, 4).value + 1000
        r1 = idx[prods[1]["product_id"]]
        ws.cell(r1, 6).value = "abc"
        other = [r for r in idx.values() if r not in (r0, r1)]
        ws.cell(other[0], 4).value = 0
        ws.cell(other[1], 1).value = "TEST_unknown_id"
        d = _upload(jombang, _wb_bytes(wb)).json()
        print("edited import:", d["changed"], d["errors"])
        assert d["changed"] == 1 and d["sample"][0]["product_id"] == prods[0]["product_id"]
        rows = {e["row"] for e in d["errors"]}
        assert {r1, other[0], other[1]} <= rows and d["error_count"] == 3

    def test_wrong_columns_400(self, jombang):
        wb = Workbook()
        wb.active.append(["A", "B"])
        assert _upload(jombang, _wb_bytes(wb)).status_code == 400

    def test_not_xlsx_400(self, jombang):
        assert _upload(jombang, b"hello,world", "x.csv", "text/csv").status_code == 400


# --- branch copy negative pct
class TestBranchCopyNegative:
    @pytest.mark.parametrize("pct", [-5, -10, -50])
    def test_preview_negative(self, admin, pct):
        r = requests.post(f"{API}/admin/branch-copy/preview", json={"rules": [{"store_id": JEM, "mode": "pct", "price_pct": pct, "copy_stock": False}]},
                          headers=admin, timeout=180)
        assert r.status_code == 200, r.text[:200]
        db.branch_copy.delete_one({"preview_id": r.json()["preview_id"]})
        b = r.json()["branches"][0]
        for s in b["sample"]:
            assert s["new_price"] == exact(s["sidoarjo_price"], pct), s

    def test_minus51_422(self, admin):
        r = requests.post(f"{API}/admin/branch-copy/preview", json={"rules": [{"store_id": JEM, "mode": "pct", "price_pct": -51}]}, headers=admin, timeout=60)
        assert r.status_code == 422

    def test_rounding_unit(self):
        import branch_copy
        import branch_price
        f = lambda pct: branch_copy.price_fn(branch_copy.Rule(store_id="x", mode="pct", price_pct=pct))
        assert f(10)(3000) == 3300 and f(7)(30000) == 32100
        assert branch_price.adjust_fn("pct", 10)(3000) == 3300 and branch_price.adjust_fn("pct", 7)(30000) == 32100
        for pct in (-5, -10, -33, -50, 2.5):
            for v in (3000, 6000, 30000, 12345, 99, 150):
                assert f(pct)(v) == exact(v, pct) == branch_price.adjust_fn("pct", pct)(v), (pct, v)


# --- apply (writes; restore afterwards)
@pytest.mark.skipif(not ALLOW_APPLY, reason="apply only with backup (BC_ALLOW_APPLY=1)")
class TestApply:
    def test_apply_flow(self, jombang, jember, admin, prods):
        ids = [p["product_id"] for p in prods]
        b_j = {i: _row(J, i) for i in ids}
        b_m = {i: _row(JEM, i) for i in ids}
        b_o = {i: db.products.find_one({"product_id": i}, {"_id": 0, "price": 1, "tier_prices": 1}) for i in ids}
        ph0 = db.price_history.count_documents({"source": "branch_bulk", "store_id": J})
        d = _pv(jombang, mode="pct", value=7, tiers=True, product_ids=ids).json()
        assert d["changed"] == 2
        pid = d["preview_id"]
        assert requests.post(f"{API}/branch-prices/bulk/{pid}/apply", headers=jember, timeout=60).status_code == 403
        r = requests.post(f"{API}/branch-prices/bulk/{pid}/apply", headers=jombang, timeout=120)
        assert r.status_code == 200 and r.json()["saved"] == 2, r.text
        assert requests.post(f"{API}/branch-prices/bulk/{pid}/apply", headers=jombang, timeout=60).status_code == 400
        for i in ids:
            n = _row(J, i)
            assert n["price"] == exact(b_j[i]["price"], 7)
            assert n["stock"] == b_j[i]["stock"] and n.get("manual_price_at")
            assert n["tier_prices"]["langsung"][0]["price"] == exact(b_j[i]["tier_prices"]["langsung"][0]["price"], 7)
            assert _row(JEM, i) == b_m[i]
            assert db.products.find_one({"product_id": i}, {"_id": 0, "price": 1, "tier_prices": 1}) == b_o[i]
            pj = requests.get(f"{API}/products/{i}", headers={"X-Store-Id": J}, timeout=30).json()
            pm = requests.get(f"{API}/products/{i}", headers={"X-Store-Id": JEM}, timeout=30).json()
            po = requests.get(f"{API}/products/{i}", headers={"X-Store-Id": OFF}, timeout=30).json()
            assert pj["price"] == n["price"] and pm["price"] == b_m[i]["price"] and po["price"] == b_o[i]["price"], (pj["price"], pm["price"], po["price"])
        assert db.price_history.count_documents({"source": "branch_bulk", "store_id": J}) == ph0 + 2
        h = requests.get(f"{API}/history/price-stock", headers=jombang, params={"store_id": J}, timeout=60)
        print("history api:", h.status_code, str(h.json())[:400] if h.status_code == 200 else h.text[:200])

    def test_apply_import(self, jombang, prods):
        wb = load_workbook(io.BytesIO(_export(jombang).content))
        ws = wb.active
        pid = prods[1]["product_id"]
        r = next(r for r in range(2, ws.max_row + 1) if ws.cell(r, 1).value == pid)
        ws.cell(r, 4).value = 12345
        ws.cell(r, 6).value = "6:12000; 12:11000"
        d = _upload(jombang, _wb_bytes(wb)).json()
        assert d["changed"] == 1, d
        a = requests.post(f"{API}/branch-prices/bulk/{d['preview_id']}/apply", headers=jombang, timeout=60)
        assert a.status_code == 200 and a.json()["saved"] == 1
        n = _row(J, pid)
        assert n["price"] == 12345 and [t["price"] for t in n["tier_prices"]["langsung"]] == [12000, 11000]
