# PGS iteration 28: Excel/CSV import column matching (WooCommerce website format), template with examples + Petunjuk Kolom.
import io
import os
import uuid

import pytest
import requests
from openpyxl import load_workbook
from pymongo import MongoClient

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
IMG = "https://pusatgrosirsidoarjo.com/wp-content/uploads/2023/07/Cetakan-7-Lubang-Cekung-Suggo-300x300.webp"
TAG = uuid.uuid4().hex[:5]


def _env(k):
    for line in open("/app/backend/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip('"')


DB = MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]
CREATED: list = []
DRAFT_NAMES: list = []

WOO_HDR = ["ID", "Type", "SKU", "Name", "Published", "Short description", "Description", "Stock", "Sale price",
           "Regular price", "Categories", "Images", "Weight (kg)", "Length (cm)", "Width (cm)", "Height (cm)", "Tags"]
HTML_DESC = "<p>Panci <strong>anti lengket</strong> &amp; tahan panas untuk dapur rumah tangga.</p><ul><li>Bahan aluminium</li><li>Gagang kayu</li></ul>"


def H(t):
    return {"Authorization": f"Bearer {t}"}


def csv_text(rows, delim=","):
    out = io.StringIO()
    import csv
    w = csv.writer(out, delimiter=delim)
    w.writerow(WOO_HDR)
    for r in rows:
        w.writerow(r)
    return out.getvalue().encode("utf-8-sig")


def woo_rows():
    return [
        # existing website product -> update/same
        ["9849", "simple", "DBLP32HC", "Happy Call Double Pan 32 cm", "1", "", "", "", "", "167000", "Dapur > Peralatan Masak", "", "", "", "", "", "tag1"],
        # new product, inactive, comma weight, dotted price, HTML desc
        ["", "simple", f"TSKU-W1-{TAG}", f"TEST_Woo Panci {TAG}", "0", "", HTML_DESC, "12", "", "25.000", "Dapur > Peralatan Masak", IMG, "1,5", "30", "30", "10", "x"],
        # variation row -> skipped
        ["99999", "variation", "", "TEST_Var row", "1", "", "", "", "", "10000", "", "", "", "", "", "", ""],
    ]


def imp(t, data, name, commit=False, store_id=None, mime="text/csv"):
    params = {"commit": str(commit).lower()}
    if store_id:
        params["store_id"] = store_id
    return requests.post(f"{API}/product-editor/import", headers=H(t), params=params,
                         files={"file": (name, data, mime)}, timeout=120)


@pytest.fixture(scope="module")
def tok():
    t = {}
    for k, (e, p) in {"admin": ("admin@pgs.id", "Admin1234!"), "seller": ("acct1@pgs.id", "Test1234!")}.items():
        r = requests.post(f"{API}/auth/login", json={"email": e, "password": p})
        assert r.status_code == 200, r.text
        t[k] = r.json()["token"]
    yield t
    for pid in CREATED:
        DB.price_history.delete_many({"product_id": pid, "product_name": {"$regex": "^TEST_"}})  # iter29: history logs of test products
        DB.products.delete_one({"product_id": pid, "name": {"$regex": "^TEST_"}})
    for n in DRAFT_NAMES:
        DB.product_drafts.delete_many({"data.name": n})


@pytest.fixture(scope="module")
def store(tok):
    r = requests.get(f"{API}/product-editor/context", headers=H(tok["seller"]))
    return r.json()["stores"][0]["store_id"]


@pytest.fixture(scope="module")
def template(tok):
    r = requests.get(f"{API}/product-editor/export", headers=H(tok["seller"]), params={"template": "true"}, timeout=60)
    assert r.status_code == 200, r.text[:300]
    return r.content


# ---------- template ----------
class TestTemplate:
    def test_sheets(self, template):
        wb = load_workbook(io.BytesIO(template))
        assert wb.sheetnames == ["Produk", "Petunjuk Kolom", "Variasi", "Panduan", "Kategori"]

    def test_example_rows(self, template):
        ws = load_workbook(io.BytesIO(template))["Produk"]
        hdr = [c.value for c in ws[1]]
        assert hdr[-1] == "Link Produk di Website (info)"
        rows = [r for r in ws.iter_rows(min_row=2, values_only=True)]
        assert len(rows) == 2
        for r in rows:
            assert str(r[1]).startswith("CONTOH-") and r[2] and r[3] and r[9] and r[18] and len(r[19] or "") >= 30
            assert not r[0]  # no product id

    def test_petunjuk_kolom(self, template):
        wb = load_workbook(io.BytesIO(template))
        hdr = [c.value for c in wb["Produk"][1]]
        pk = [r for r in wb["Petunjuk Kolom"].iter_rows(values_only=True)]
        assert list(pk[0]) == ["Kolom", "Wajib (produk baru)", "Format / isi", "Contoh"]
        assert [r[0] for r in pk[1:]] == hdr
        assert all(r[1] in ("Ya", "Tidak") and r[2] and r[3] for r in pk[1:])

    def test_import_unmodified_template(self, tok, template, store):
        before = DB.products.count_documents({"store_id": store})
        r = imp(tok["seller"], template, "template.xlsx", True, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["counts"]["skip"] == 2 and j["counts"]["create"] == 0 and j["counts"]["draft"] == 0, j["counts"]
        assert j["missing"] == []
        assert all(c["field"] for c in j["columns"]), [c for c in j["columns"] if not c["field"]]
        assert {c["sheet"] for c in j["columns"]} == {"Produk", "Variasi"}
        assert DB.products.count_documents({"store_id": store}) == before


# ---------- normal export permalink ----------
class TestExport:
    def test_admin_export_permalink(self, tok):
        r = requests.get(f"{API}/product-editor/export", headers=H(tok["admin"]), params={"store_id": "pgs-official"}, timeout=180)
        assert r.status_code == 200
        ws = load_workbook(io.BytesIO(r.content), read_only=True)["Produk"]
        it = ws.iter_rows(values_only=True)
        hdr = list(next(it))
        i = hdr.index("Link Produk di Website (info)")
        for row in it:
            if row[0] == "pgs-9849":
                assert row[i] == "https://pusatgrosirsidoarjo.com/distributor/happy-call-double-pan-32-cm/"
                return
        pytest.fail("pgs-9849 not in export")


# ---------- WooCommerce CSV ----------
class TestWooCsv:
    def test_mapping_and_preview_admin(self, tok):
        snap = DB.products.find_one({"product_id": "pgs-9849"}, {"_id": 0})
        before = DB.products.count_documents({})
        r = imp(tok["admin"], csv_text(woo_rows()), "wc-product-export.csv", False, store_id="pgs-official")
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["format"] == "csv" and j["committed"] is False
        m = {c["header"]: c["field"] for c in j["columns"]}
        assert m["ID"] == "product_id" and m["Type"] == "type" and m["Name"] == "name" and m["Published"] == "status"
        assert m["Regular price"] == "price" and m["Sale price"] == "discount_price" and m["Categories"] == "category"
        assert m["Weight (kg)"] == "weight_kg" and m["Images"] == "images" and m["Short description"] == "short_description"
        assert m["Tags"] is None
        assert j["missing"] == []
        rows = {x["row"]: x for x in j["rows"]}
        assert rows[2]["action"] in ("same", "update"), rows[2]
        assert rows[3]["action"] == "create", rows[3]
        assert rows[4]["action"] == "skip" and "variasi" in rows[4]["message"].lower()
        assert DB.products.count_documents({}) == before
        after = DB.products.find_one({"product_id": "pgs-9849"}, {"_id": 0})
        assert after.get("updated_at") == snap.get("updated_at") and after["price"] == snap["price"]

    def test_commit_creates_seller(self, tok, store):
        r = imp(tok["seller"], csv_text(woo_rows()[1:]), "wc.csv", True)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["counts"]["create"] == 1 and j["counts"]["skip"] == 1, j
        p = DB.products.find_one({"name": f"TEST_Woo Panci {TAG}", "store_id": store}, {"_id": 0})
        assert p, "created product not found"
        CREATED.append(p["product_id"])
        assert p["price"] == 25000 and p["weight_grams"] == 1500 and p["status"] == "inactive"
        assert p["category"] in ("dapur", "peralatan-masak") and p.get("subcategory", "peralatan-masak") in ("peralatan-masak", "")
        assert "<" not in p["description"] and "&amp;" not in p["description"] and "anti lengket" in p["description"]
        assert p.get("sku") == f"TSKU-W1-{TAG}"

    def test_semicolon_csv(self, tok, store):
        rows = woo_rows()[1:2]
        rows[0][3] = f"TEST_Woo Semi {TAG}"
        rows[0][2] = f"TSKU-S1-{TAG}"
        r = imp(tok["seller"], csv_text(rows, ";"), "semi.csv", False)
        assert r.status_code == 200, r.text
        j = r.json()
        assert sum(1 for c in j["columns"] if c["field"]) == 16
        assert j["rows"][0]["action"] == "create", j["rows"]
        assert DB.products.count_documents({"name": f"TEST_Woo Semi {TAG}"}) == 0

    def test_missing_required(self, tok):
        data = f"Name,Regular price,Categories,Description\nTEST_Miss {TAG},20000,Dapur,{'x' * 40}\n".encode()
        DRAFT_NAMES.append(f"TEST_Miss {TAG}")
        r = imp(tok["seller"], data, "m.csv", False)
        assert r.status_code == 200, r.text
        j = r.json()
        assert len(j["missing"]) == 2, j["missing"]
        assert j["rows"][0]["action"] == "draft"

    def test_unrecognized_csv_400(self, tok):
        r = imp(tok["seller"], b"foo,bar\n1,2\n", "x.csv", False)
        assert r.status_code == 400
