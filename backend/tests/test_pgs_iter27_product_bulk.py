# PGS iteration 27: Product editor Tahap 3 - list, bulk edit price/stock/status, duplicate, Excel export/template/import.
import io
import os
import uuid

import pytest
import requests
from openpyxl import Workbook, load_workbook
from pymongo import MongoClient

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
IMG = "https://pusatgrosirsidoarjo.com/wp-content/uploads/2023/07/Cetakan-7-Lubang-Cekung-Suggo-300x300.webp"
DESC = "Deskripsi produk uji coba yang cukup panjang untuk validasi impor dan edit massal."


def _env(k):
    for line in open("/app/backend/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip('"')


DB = MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]
PRODUCTS: list = []
DRAFTS: list = []
TAG = uuid.uuid4().hex[:5]


def H(t):
    return {"Authorization": f"Bearer {t}"}


def form(**kw):
    base = {"name": f"TEST_Bulk {TAG} {uuid.uuid4().hex[:4]}", "category": "dapur", "subcategory": "peralatan-masak",
            "brand": "TEST", "sku": f"TSKU-{TAG}", "condition": "new", "status": "active", "description": DESC,
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
    PRODUCTS.append(r.json()["product_id"])
    return r.json()["product_id"]


def prod(pid):
    return DB.products.find_one({"product_id": pid}, {"_id": 0})


def bulk(t, ids, **kw):
    return requests.post(f"{API}/product-editor/bulk", headers=H(t), json={"product_ids": ids, **kw})


@pytest.fixture(scope="module")
def tok():
    t = {}
    for k, (e, p) in {"admin": ("admin@pgs.id", "Admin1234!"), "seller": ("acct1@pgs.id", "Test1234!")}.items():
        r = requests.post(f"{API}/auth/login", json={"email": e, "password": p})
        assert r.status_code == 200, r.text
        t[k] = r.json()["token"]
    yield t
    for pid in PRODUCTS:
        DB.products.delete_one({"product_id": pid, "name": {"$regex": "^TEST_"}})
    for did in DRAFTS:
        DB.product_drafts.delete_one({"draft_id": did})


@pytest.fixture(scope="module")
def store(tok):
    r = requests.get(f"{API}/product-editor/context", headers=H(tok["seller"]))
    assert r.status_code == 200
    return r.json()["stores"][0]["store_id"]


# ---------- list ----------
class TestList:
    def test_admin_list_pgs(self, tok):
        r = requests.get(f"{API}/product-editor/products", headers=H(tok["admin"]), params={"store_id": "pgs-official", "limit": 5})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["store_id"] == "pgs-official" and d["total"] > 100 and len(d["items"]) == 5
        assert {"product_id", "name", "price", "stock", "status", "variants"} <= set(d["items"][0])

    def test_seller_list_filters_search(self, tok, store):
        pid = publish(tok["seller"], form(sku=f"FLT-{TAG}", stock=0, status="inactive"))
        g = lambda **p: requests.get(f"{API}/product-editor/products", headers=H(tok["seller"]), params=p).json()
        assert g()["store_id"] == store
        assert pid in [i["product_id"] for i in g(q=f"FLT-{TAG}")["items"]]
        assert pid in [i["product_id"] for i in g(q=f"TEST_Bulk {TAG}")["items"]]
        assert pid in [i["product_id"] for i in g(status="inactive", q=TAG)["items"]]
        assert pid in [i["product_id"] for i in g(status="empty", q=TAG)["items"]]
        assert pid not in [i["product_id"] for i in g(status="active", q=TAG)["items"]]
        assert all(i["store_id"] == store for i in g(limit=50)["items"])

    def test_seller_cannot_list_other_store(self, tok, store):
        r = requests.get(f"{API}/product-editor/products", headers=H(tok["seller"]), params={"store_id": "pgs-official"})
        assert r.json()["store_id"] == store


# ---------- bulk ----------
class TestBulk:
    def test_validation(self, tok):
        pid = publish(tok["seller"], form())
        assert bulk(tok["seller"], [pid]).status_code == 400
        assert bulk(tok["seller"], [pid], price_mode="down_pct", price_value=100).status_code == 400
        assert bulk(tok["seller"], [pid], price_mode="up_pct", price_value=501).status_code == 400
        assert bulk(tok["seller"], [pid], price_mode="up_pct", price_value=0).status_code == 400
        assert bulk(tok["seller"], [pid], price_mode="set", price_value=50).status_code == 400
        assert bulk(tok["seller"], [], status="active").status_code == 422
        assert bulk(tok["seller"], [pid], price_mode="bogus", price_value=5).status_code == 422

    def test_price_modes_with_discount(self, tok):
        pid = publish(tok["seller"], form(price=20000, discount_price=15000))
        r = bulk(tok["seller"], [pid], price_mode="up_pct", price_value=10)
        assert r.json() == {"updated": 1, "skipped": []}, r.text
        p = prod(pid)
        assert p["original_price"] == 22000 and p["price"] == 16500, p
        bulk(tok["seller"], [pid], price_mode="down", price_value=2000)
        p = prod(pid)
        assert p["original_price"] == 20000 and p["price"] == 14500, p
        # set: normal price below discount drops discount
        bulk(tok["seller"], [pid], price_mode="set", price_value=10000)
        p = prod(pid)
        assert p["price"] == 10000 and (p.get("original_price") or 10000) == 10000, p
        bulk(tok["seller"], [pid], price_mode="down_pct", price_value=50)
        assert prod(pid)["price"] == 5000
        bulk(tok["seller"], [pid], price_mode="up", price_value=1000)
        assert prod(pid)["price"] == 6000

    def test_price_below_100_skipped(self, tok):
        pid = publish(tok["seller"], form(price=500, discount_price=0))
        r = bulk(tok["seller"], [pid, "nonexistent_x"], price_mode="down", price_value=450)
        d = r.json()
        assert d["updated"] == 0 and len(d["skipped"]) == 2, d
        assert prod(pid)["price"] == 500

    def test_stock_and_status(self, tok):
        pid = publish(tok["seller"], form(stock=10))
        bulk(tok["seller"], [pid], stock_mode="add", stock_value=5)
        assert prod(pid)["stock"] == 15
        bulk(tok["seller"], [pid], stock_mode="sub", stock_value=100)
        p = prod(pid)
        assert p["stock"] == 0 and p["in_stock"] is False
        bulk(tok["seller"], [pid], stock_mode="set", stock_value=7, status="inactive")
        p = prod(pid)
        assert p["stock"] == 7 and p["status"] == "inactive"
        bulk(tok["seller"], [pid], status="active")
        assert prod(pid)["status"] == "active" and prod(pid)["stock"] == 7

    def test_variants(self, tok):
        pid = publish(tok["seller"], vform())
        r = bulk(tok["seller"], [pid], price_mode="up", price_value=1000, stock_mode="add", stock_value=2)
        assert r.json()["updated"] == 1, r.text
        vs = prod(pid)["variants"]
        assert sorted(v["price"] for v in vs) == [13000, 15000]
        assert sorted(v["stock"] for v in vs) == [5, 7]
        assert prod(pid)["stock"] == 12
        r = bulk(tok["seller"], [pid], price_mode="down", price_value=12950)
        assert r.json()["updated"] == 0 and r.json()["skipped"]

    def test_admin_bulk_other_store_product_not_found(self, tok):
        pid = publish(tok["seller"], form())
        r = requests.post(f"{API}/product-editor/bulk", headers=H(tok["admin"]),
                          json={"product_ids": [pid], "store_id": "pgs-official", "status": "inactive"})
        assert r.json()["updated"] == 0 and prod(pid)["status"] == "active"


# ---------- duplicate ----------
class TestDuplicate:
    def test_duplicate_variant_product(self, tok, store):
        pid = publish(tok["seller"], vform())
        r = requests.post(f"{API}/product-editor/products/{pid}/duplicate", headers=H(tok["seller"]))
        assert r.status_code == 200, r.text
        d = r.json()
        DRAFTS.append(d["draft_id"])
        assert d["product_id"] is None and d["store_id"] == store
        assert d["data"]["name"].endswith("(Salinan)") and d["data"]["sku"] == ""
        assert len(d["data"]["variants"]) == 2 and all(v["variant_id"] == "" and v["sku"] == "" for v in d["data"]["variants"])
        g = requests.get(f"{API}/product-editor/drafts/{d['draft_id']}", headers=H(tok["seller"]))
        assert g.status_code == 200 and g.json()["data"]["name"] == d["data"]["name"]
        # publishing the copy creates a separate product and removes the draft
        np = publish(tok["seller"], g.json()["data"], draft_id=d["draft_id"])
        assert np != pid
        assert requests.get(f"{API}/product-editor/drafts/{d['draft_id']}", headers=H(tok["seller"])).status_code == 404
        assert all(v.get("variant_id") for v in prod(np)["variants"])

    def test_duplicate_other_store_404(self, tok):
        any_pgs = DB.products.find_one({"store_id": "pgs-official"}, {"product_id": 1})
        r = requests.post(f"{API}/product-editor/products/{any_pgs['product_id']}/duplicate", headers=H(tok["seller"]))
        assert r.status_code == 404


# ---------- export / import ----------
def xlsx_bytes(wb):
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def imp(t, data, commit, name="f.xlsx"):
    return requests.post(f"{API}/product-editor/import", headers=H(t), params={"commit": str(commit).lower()},
                         files={"file": (name, data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})


class TestExcel:
    def test_template(self, tok):
        r = requests.get(f"{API}/product-editor/export", headers=H(tok["seller"]), params={"template": "true"})
        assert r.status_code == 200 and "template-impor-produk.xlsx" in r.headers.get("content-disposition", "")
        wb = load_workbook(io.BytesIO(r.content))
        assert wb.sheetnames == ["Produk", "Variasi", "Panduan", "Kategori"]
        assert wb["Produk"].max_row == 2 and wb["Kategori"].max_row > 2

    def test_admin_export_pgs(self, tok):
        r = requests.get(f"{API}/product-editor/export", headers=H(tok["admin"]), params={"store_id": "pgs-official"}, timeout=120)
        assert r.status_code == 200, r.text[:300]
        wb = load_workbook(io.BytesIO(r.content), read_only=True)
        assert wb.sheetnames == ["Produk", "Variasi", "Panduan", "Kategori"]

    def test_import_roundtrip(self, tok, store):
        p1 = publish(tok["seller"], form(price=30000, discount_price=0, stock=4, sku=f"IMP1-{TAG}"))
        p2 = publish(tok["seller"], form(price=40000, discount_price=0, stock=6, sku=f"IMP2-{TAG}"))
        pv = publish(tok["seller"], vform(sku=f"IMPV-{TAG}"))
        r = requests.get(f"{API}/product-editor/export", headers=H(tok["seller"]))
        assert r.status_code == 200
        wb = load_workbook(io.BytesIO(r.content))
        ws, vs = wb["Produk"], wb["Variasi"]
        hdr = [c.value for c in ws[1]]
        col = {h: i for i, h in enumerate(hdr)}
        keep = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            if row[0] in (p1, p2, pv):
                keep.append(list(row))
        assert len(keep) == 3
        vkeep = [list(r) for r in vs.iter_rows(min_row=2, values_only=True) if r[0] == pv]
        assert len(vkeep) == 2
        out = Workbook()
        o = out.active
        o.title = "Produk"
        o.append(hdr)
        for row in keep:
            if row[0] == p1:
                row[col["Harga Normal*"]] = 35000
                row[col["Stok"]] = 9
            o.append(row)
        o.append(["unknown_id_x", "", "TEST_Unknown"])
        cat = DB.categories.find_one({"category_id": "dapur"})["name"]
        new_full = [None, f"NEW-{TAG}", f"TEST_Imp Baru {TAG}", cat, "", "B", "baru", "aktif", "", 25000, None, 3, 1, 0, 700,
                    None, None, None, IMG, DESC]
        new_draft = [None, "", f"TEST_Imp Draft {TAG}", cat, "", "", "", "", "", 25000]
        o.append(new_full)
        o.append(new_draft)
        v = out.create_sheet("Variasi")
        v.append([c.value for c in vs[1]])
        vkeep[0][5] = 11111
        vkeep[0][6] = 42
        for row in vkeep:
            v.append(row)
        data = xlsx_bytes(out)
        before = DB.products.count_documents({"store_id": store})
        dbefore = DB.product_drafts.count_documents({"owner": store})
        # preview: no writes
        r = imp(tok["seller"], data, False)
        assert r.status_code == 200, r.text
        c = r.json()["counts"]
        assert r.json()["committed"] is False
        assert c == {"update": 3, "same": 2, "create": 1, "draft": 1, "skip": 1}, r.json()
        assert prod(p1)["price"] == 30000 and DB.products.count_documents({"store_id": store}) == before
        assert DB.product_drafts.count_documents({"owner": store}) == dbefore
        # commit
        r = imp(tok["seller"], data, True)
        assert r.status_code == 200 and r.json()["counts"] == c, r.text
        p = prod(p1)
        assert p["price"] == 35000 and p["stock"] == 9
        assert prod(p2)["price"] == 40000
        vv = {x["variant_id"]: x for x in prod(pv)["variants"]}
        assert vv[vkeep[0][1]]["price"] == 11111 and vv[vkeep[0][1]]["stock"] == 42
        created = DB.products.find_one({"name": f"TEST_Imp Baru {TAG}", "store_id": store}, {"_id": 0})
        assert created and created["price"] == 25000 and created.get("weight_grams") == 700
        PRODUCTS.append(created["product_id"])
        dr = DB.product_drafts.find_one({"owner": store, "data.name": f"TEST_Imp Draft {TAG}"})
        assert dr
        DRAFTS.append(dr["draft_id"])

    def test_reject_non_xlsx(self, tok):
        r = imp(tok["seller"], b"a,b,c", False, name="f.csv")
        assert r.status_code == 400
        r = imp(tok["seller"], b"not an excel", False, name="f.xlsx")
        assert r.status_code == 400
        empty = Workbook()
        r = imp(tok["seller"], xlsx_bytes(empty), False)
        assert r.status_code == 400
