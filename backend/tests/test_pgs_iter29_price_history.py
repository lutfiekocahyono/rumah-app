# PGS iteration 29: Riwayat perubahan harga & stok (GET /api/history/price-stock) + log creation per source + import 'URL Foto'/'Maks. Beli'.
import csv
import io
import os
import uuid
from datetime import datetime, timezone

import pytest
import requests
from openpyxl import Workbook
from pymongo import MongoClient

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
IMG = "https://pusatgrosirsidoarjo.com/wp-content/uploads/2023/07/Cetakan-7-Lubang-Cekung-Suggo-300x300.webp"
DESC = "Deskripsi produk uji coba yang cukup panjang untuk validasi riwayat harga dan stok."
SHARED = "pgs-9957"  # PGS catalogue product (no variants) used for branch stock & tier tests - restored afterwards


def _env(k):
    for line in open("/app/backend/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip('"')


DB = MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]
PRODUCTS: list = []
LOG_IDS: list = []
TAG = uuid.uuid4().hex[:5]
START = datetime.now(timezone.utc)


def H(t):
    return {"Authorization": f"Bearer {t}"}


def form(**kw):
    base = {"name": f"TEST_Hist {TAG} {uuid.uuid4().hex[:4]}", "category": "dapur", "subcategory": "peralatan-masak",
            "brand": "TEST", "sku": f"TH-{TAG}", "condition": "new", "status": "active", "description": DESC,
            "images": [IMG], "price": 20000, "discount_price": 15000, "stock": 10, "min_order": 1, "max_order": 0, "weight_grams": 500}
    base.update(kw)
    return base


def vform(**kw):
    opts = [{"name": "Warna", "values": ["Merah", "Biru"]}]
    rows = [{"values": ["Merah"], "price": 12000, "stock": 5, "sku": "R", "active": True},
            {"values": ["Biru"], "price": 14000, "stock": 3, "sku": "B", "active": True}]
    return form(variants_enabled=True, variant_options=opts, variants=rows, discount_price=0, **kw)


def publish(t, data, **kw):
    r = requests.post(f"{API}/product-editor/publish", headers=H(t), json={"data": data, **kw})
    assert r.status_code == 200, r.text
    pid = r.json()["product_id"]
    if pid not in PRODUCTS:
        PRODUCTS.append(pid)
    return pid


def hist(t, **params):
    return requests.get(f"{API}/history/price-stock", headers=H(t), params=params)


def logs(pid):
    return list(DB.price_history.find({"product_id": pid}, {"_id": 0}).sort("at", -1))


def track_shared():
    for d in DB.price_history.find({"product_id": SHARED, "at": {"$gte": START}}, {"log_id": 1}):
        if d["log_id"] not in LOG_IDS:
            LOG_IDS.append(d["log_id"])


@pytest.fixture(scope="module")
def tok():
    t = {}
    for k, (e, p) in {"admin": ("admin@pgs.id", "Admin1234!"), "seller": ("acct1@pgs.id", "Test1234!"),
                      "jombang": ("jombang@pgs.id", "Jombang123!"), "demo": ("demo@pgs.id", "Demo1234!")}.items():
        r = requests.post(f"{API}/auth/login", json={"email": e, "password": p})
        assert r.status_code == 200, r.text
        t[k] = r.json()["token"]
    yield t
    track_shared()
    for pid in PRODUCTS:
        DB.price_history.delete_many({"product_id": pid})
        DB.products.delete_one({"product_id": pid, "name": {"$regex": "^TEST_"}})
    for lid in LOG_IDS:
        DB.price_history.delete_one({"log_id": lid})


@pytest.fixture(scope="module")
def seller_store(tok):
    return DB.stores.find_one({"owner_id": DB.users.find_one({"email": "acct1@pgs.id"})["user_id"]})["store_id"]


# ---------- access ----------
class TestAccess:
    def test_unauth_401(self):
        assert requests.get(f"{API}/history/price-stock").status_code == 401

    def test_customer_403(self, tok):
        assert hist(tok["demo"]).status_code == 403

    def test_branch_other_store_403(self, tok):
        r = hist(tok["jombang"], store_id="pgs-official")
        assert r.status_code == 403 and "sendiri" in r.json()["detail"]

    def test_admin_ok(self, tok):
        r = hist(tok["admin"])
        assert r.status_code == 200 and isinstance(r.json()["items"], list) and isinstance(r.json()["total"], int)


# ---------- editor ----------
class TestEditor:
    def test_edit_price_stock_logged(self, tok, seller_store):
        pid = publish(tok["seller"], form())
        assert logs(pid) == []  # creation is not a change
        data = requests.get(f"{API}/product-editor/products/{pid}", headers=H(tok["seller"])).json()["data"]
        data.update(discount_price=18000, stock=7)
        publish(tok["seller"], data, product_id=pid)
        lg = logs(pid)
        assert len(lg) == 1
        l = lg[0]
        assert l["source"] == "editor" and l["user_name"] == "Akun Satu" and l["store_id"] == seller_store
        ch = {c["field"]: (c["before"], c["after"]) for c in l["changes"]}
        assert ch == {"price": (15000, 18000), "stock": (10, 7)}, ch
        assert l["kinds"] == ["price", "stock"]
        # republish with no changes -> no new log
        data = requests.get(f"{API}/product-editor/products/{pid}", headers=H(tok["seller"])).json()["data"]
        publish(tok["seller"], data, product_id=pid)
        assert len(logs(pid)) == 1
        # API: seller sees it with labels
        r = hist(tok["seller"], product_id=pid)
        assert r.status_code == 200 and r.json()["total"] == 1
        it = r.json()["items"][0]
        assert it["source_label"] == "Ubah Produk" and it["store_name"] and "_id" not in it

    def test_seller_only_own_store(self, tok, seller_store):
        r = hist(tok["seller"], limit=100)
        assert r.status_code == 200 and all(i["store_id"] == seller_store for i in r.json()["items"])
        assert hist(tok["seller"], store_id="pgs-official").status_code == 403


# ---------- bulk ----------
class TestBulk:
    def test_bulk_simple_and_variant(self, tok):
        sp = publish(tok["seller"], form(discount_price=0))
        vp = publish(tok["seller"], vform())
        r = requests.post(f"{API}/product-editor/bulk", headers=H(tok["seller"]),
                          json={"product_ids": [sp, vp], "price_mode": "set", "price_value": 30000, "stock_mode": "set", "stock_value": 50})
        assert r.status_code == 200 and r.json()["updated"] == 2, r.text
        l = logs(sp)[0]
        assert l["source"] == "bulk"
        ch = {c["field"]: (c["before"], c["after"]) for c in l["changes"]}
        assert ch.get("stock") == (10, 50) and ch.get("price") == (20000, 30000), ch
        lv = logs(vp)[0]
        variants = {(c["variant"], c["field"]): (c["before"], c["after"]) for c in lv["changes"]}
        assert ("Merah", "stock") in variants and variants[("Merah", "stock")] == (5, 50), variants
        assert variants.get(("Biru", "price")) == (14000, 30000), variants
        assert all(c["variant"] for c in lv["changes"]), lv["changes"]
        # same bulk again -> nothing changed -> no new log
        requests.post(f"{API}/product-editor/bulk", headers=H(tok["seller"]),
                      json={"product_ids": [sp], "price_mode": "set", "price_value": 30000, "stock_mode": "set", "stock_value": 50})
        assert len(logs(sp)) == 1


# ---------- import ----------
def xlsx(prod_rows, var_rows=None):
    wb = Workbook()
    ws = wb.active
    ws.title = "Produk"
    for r in prod_rows:
        ws.append(r)
    if var_rows:
        v = wb.create_sheet("Variasi")
        for r in var_rows:
            v.append(r)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def imp(t, data, name, commit, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"):
    return requests.post(f"{API}/product-editor/import", headers=H(t), params={"commit": str(commit).lower()},
                         files={"file": (name, data, mime)}, timeout=120)


class TestImport:
    def test_import_logs_product_and_variant(self, tok):
        sp = publish(tok["seller"], form())
        vp = publish(tok["seller"], vform())
        vid = DB.products.find_one({"product_id": vp})["variants"][0]
        data = xlsx([["ID Produk (jangan diubah)", "Stok", "Harga Diskon"], [sp, 3, 16000]],
                    [["ID Produk", "ID Variasi (jangan diubah)", "Harga", "Stok"], [vp, vid["variant_id"], 13000, vid["stock"]]])
        r = imp(tok["seller"], data, "h.xlsx", True)
        assert r.status_code == 200, r.text
        l = logs(sp)[0]
        assert l["source"] == "import"
        ch = {c["field"]: (c["before"], c["after"]) for c in l["changes"]}
        assert ch == {"stock": (10, 3), "price": (15000, 16000)}, ch
        lv = logs(vp)
        assert len(lv) == 1 and lv[0]["source"] == "import"
        assert [(c["variant"], c["field"], c["before"], c["after"]) for c in lv[0]["changes"]] == [(vid["name"] or "Merah", "price", 12000, 13000)]
        # commit=false writes no log
        imp(tok["seller"], xlsx([["ID Produk (jangan diubah)", "Stok"], [sp, 99]]), "h.xlsx", False)
        assert len(logs(sp)) == 1

    def test_url_foto_maks_beli_headers(self, tok):
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["Nama Produk", "Kategori", "Harga Normal", "Berat (gram)", "URL Foto", "Deskripsi", "Maks. Beli"])
        w.writerow([f"TEST_Hist CSV {TAG}", "Dapur", "25000", "500", IMG, DESC, "4"])
        r = imp(tok["seller"], buf.getvalue().encode(), "f.csv", False, "text/csv")
        assert r.status_code == 200, r.text
        cols = {c["header"]: c["field"] for c in r.json()["columns"]}
        assert cols["URL Foto"] == "images" and cols["Maks. Beli"] == "max_order", cols
        assert r.json()["missing"] == [] and r.json()["counts"]["create"] == 1, r.json()


# ---------- branch stock & tiers on the shared catalogue ----------
class TestSharedCatalogue:
    def test_branch_stock_logged_under_branch(self, tok):
        row = DB.store_stock.find_one({"store_id": "pgs-jombang", "product_id": SHARED})
        orig = (row or {}).get("stock", 0)
        try:
            r = requests.put(f"{API}/seller/inventory/{SHARED}", headers=H(tok["jombang"]), json={"stock": orig + 7})
            assert r.status_code == 200, r.text
            track_shared()
            l = DB.price_history.find_one({"product_id": SHARED, "source": "stock", "at": {"$gte": START}}, sort=[("at", -1)])
            assert l["store_id"] == "pgs-jombang" and l["user_name"] == "Admin Mitra PGS Jombang"
            assert [(c["field"], c["before"], c["after"]) for c in l["changes"]] == [("stock", orig, orig + 7)]
            # same value -> no log
            n = DB.price_history.count_documents({"product_id": SHARED})
            requests.put(f"{API}/seller/inventory/{SHARED}", headers=H(tok["jombang"]), json={"stock": orig + 7})
            assert DB.price_history.count_documents({"product_id": SHARED}) == n
            # jombang list only shows pgs-jombang
            r = hist(tok["jombang"], limit=100)
            assert r.status_code == 200 and r.json()["total"] >= 1 and all(i["store_id"] == "pgs-jombang" for i in r.json()["items"])
            assert any(i["product_id"] == SHARED for i in r.json()["items"])
            assert r.json()["items"][0]["source_label"] == "Manajemen Stok"
            # admin filter by store
            r = hist(tok["admin"], store_id="pgs-jombang", product_id=SHARED)
            assert r.status_code == 200 and r.json()["total"] >= 1
            assert hist(tok["admin"], store_id="pgs-official", product_id=SHARED, kind="stock").json()["total"] == 0
        finally:
            requests.put(f"{API}/seller/inventory/{SHARED}", headers=H(tok["jombang"]), json={"stock": orig})
            track_shared()
        assert (DB.store_stock.find_one({"store_id": "pgs-jombang", "product_id": SHARED}) or {}).get("stock", 0) == orig

    def test_tiers_logged_and_restored(self, tok):
        pytest.skip("/admin/products/{id}/tiers removed in iter30; tier history covered by editor publish tests (iter30)")
        orig = requests.get(f"{API}/admin/products/{SHARED}/tiers", headers=H(tok["admin"])).json()["tier_prices"]
        new = {**orig, "reseller": [{"min_qty": 12, "price": 9000}]}
        try:
            r = requests.put(f"{API}/admin/products/{SHARED}/tiers", headers=H(tok["admin"]), json={"tier_prices": new})
            assert r.status_code == 200, r.text
            track_shared()
            l = DB.price_history.find_one({"product_id": SHARED, "source": "tiers", "at": {"$gte": START}}, sort=[("at", -1)])
            assert l and l["kinds"] == ["price"] and l["changes"][0]["field"] == "tier_prices"
            assert "12+ Rp9.000" in l["changes"][0]["after"], l["changes"]
            assert l["store_id"] == "pgs-official"
        finally:
            requests.put(f"{API}/admin/products/{SHARED}/tiers", headers=H(tok["admin"]), json={"tier_prices": orig})
            track_shared()
        assert DB.products.find_one({"product_id": SHARED})["tier_prices"] == orig

    def test_tiers_unchanged_no_log(self, tok):
        pytest.skip("/admin/products/{id}/tiers removed in iter30")
        orig = requests.get(f"{API}/admin/products/{SHARED}/tiers", headers=H(tok["admin"])).json()["tier_prices"]
        n = DB.price_history.count_documents({"product_id": SHARED})
        requests.put(f"{API}/admin/products/{SHARED}/tiers", headers=H(tok["admin"]), json={"tier_prices": orig})
        track_shared()
        assert DB.price_history.count_documents({"product_id": SHARED}) == n


# ---------- filters / pagination ----------
class TestFilters:
    def test_kind_q_pagination(self, tok):
        r = hist(tok["admin"], kind="price", limit=100)
        assert r.status_code == 200 and all("price" in i["kinds"] for i in r.json()["items"])
        r = hist(tok["admin"], kind="stock", limit=100)
        assert all("stock" in i["kinds"] for i in r.json()["items"])
        r = hist(tok["admin"], q=f"test_hist {TAG}")
        assert r.json()["total"] >= 4 and all(TAG in i["product_name"] for i in r.json()["items"])
        tot = r.json()["total"]
        p1 = hist(tok["admin"], q=f"TEST_Hist {TAG}", limit=2, skip=0).json()["items"]
        p2 = hist(tok["admin"], q=f"TEST_Hist {TAG}", limit=2, skip=2).json()["items"]
        assert len(p1) == 2 and {i["log_id"] for i in p1}.isdisjoint({i["log_id"] for i in p2}) and len(p2) == min(2, tot - 2)
        ats = [i["at"] for i in p1 + p2]
        assert ats == sorted(ats, reverse=True)
        assert hist(tok["admin"], limit=101).status_code == 422
