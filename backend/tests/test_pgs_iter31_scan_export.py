# PGS iteration 31: history date filters + Excel export, product lookup by code (scan), cashier pickup lookup/complete.
import io
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from openpyxl import load_workbook
from pymongo import MongoClient

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
PID = "pgs-9955"
STORE = "pgs-official"
IMG = "https://pusatgrosirsidoarjo.com/wp-content/uploads/2023/07/Cetakan-7-Lubang-Cekung-Suggo-300x300.webp"
DESC = "Deskripsi produk uji coba yang cukup panjang untuk validasi scan barcode produk."
CRED = {"admin": ("admin@pgs.id", "Admin1234!"), "jombang": ("jombang@pgs.id", "Jombang123!"), "sidoarjo": ("sidoarjo@pgs.id", "Sidoarjo123!"),
        "seller": ("acct1@pgs.id", "Test1234!"), "demo": ("demo@pgs.id", "Demo1234!")}
WIB = timezone(timedelta(hours=7))
TODAY = datetime.now(WIB).strftime("%Y-%m-%d")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


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


# ---------- history list date filters ----------
class TestHistoryDates:
    def test_today_inclusive(self, tok):
        r = requests.get(f"{API}/history/price-stock", headers=H(tok["admin"]), params={"date_from": TODAY, "date_to": TODAY, "limit": 100})
        assert r.status_code == 200, r.text
        start = datetime.strptime(TODAY, "%Y-%m-%d").replace(tzinfo=WIB).astimezone(timezone.utc).replace(tzinfo=None)
        for it in r.json()["items"]:
            at = datetime.fromisoformat(str(it["at"]).replace("Z", "+00:00")).replace(tzinfo=None)
            assert start <= at < start + timedelta(days=1)

    def test_future_range_empty(self, tok):
        r = requests.get(f"{API}/history/price-stock", headers=H(tok["admin"]), params={"date_from": "2099-01-01", "date_to": "2099-01-31"})
        assert r.status_code == 200 and r.json()["total"] == 0

    @pytest.mark.parametrize("params", [{"date_from": "2026/01/01"}, {"date_to": "abc"}, {"date_from": "2026-13-01"}])
    def test_invalid_date_400(self, tok, params):
        r = requests.get(f"{API}/history/price-stock", headers=H(tok["admin"]), params=params)
        assert r.status_code == 400, r.text

    def test_from_after_to_400(self, tok):
        r = requests.get(f"{API}/history/price-stock", headers=H(tok["admin"]), params={"date_from": "2026-02-01", "date_to": "2026-01-01"})
        assert r.status_code == 400

    def test_same_day_ok(self, tok):
        r = requests.get(f"{API}/history/price-stock", headers=H(tok["admin"]), params={"date_from": "2026-01-01", "date_to": "2026-01-01"})
        assert r.status_code == 200


# ---------- Excel export ----------
def _wb(r):
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith(XLSX)
    assert "attachment" in r.headers.get("content-disposition", "")
    return load_workbook(io.BytesIO(r.content))


class TestExport:
    def test_admin_all_stores(self, tok):
        r = requests.get(f"{API}/history/price-stock/export", headers=H(tok["admin"]), params={"date_from": "2025-01-01", "date_to": TODAY})
        wb = _wb(r)
        assert wb.sheetnames == ["Riwayat", "Ringkasan"]
        hdr = [c.value for c in wb["Riwayat"][1]]
        assert hdr[7:10] == ["Sebelum", "Sesudah", "Selisih"]
        lst = requests.get(f"{API}/history/price-stock", headers=H(tok["admin"]), params={"date_from": "2025-01-01", "date_to": TODAY}).json()
        summ = {row[0].value: row[1].value for row in wb["Ringkasan"].iter_rows()}
        assert summ["Jumlah catatan"] == lst["total"]
        assert wb["Riwayat"].max_row - 1 == summ["Jumlah perubahan"]
        assert "semua-toko" in r.headers["content-disposition"]
        # Selisih = Sesudah - Sebelum for numeric rows
        for row in list(wb["Riwayat"].iter_rows(min_row=2, values_only=True))[:200]:
            if isinstance(row[7], (int, float)) and isinstance(row[8], (int, float)):
                assert row[9] == row[8] - row[7]

    def test_admin_store_filter(self, tok):
        r = requests.get(f"{API}/history/price-stock/export", headers=H(tok["admin"]), params={"store_id": "pgs-jombang"})
        wb = _wb(r)
        names = {row[2] for row in wb["Riwayat"].iter_rows(min_row=2, values_only=True)}
        assert len(names) <= 1
        assert "pgs-jombang" in r.headers["content-disposition"]

    def test_branch_admin_own_store(self, tok):
        r = requests.get(f"{API}/history/price-stock/export", headers=H(tok["jombang"]))
        wb = _wb(r)
        jname = DB.stores.find_one({"store_id": "pgs-jombang"})["name"]
        for row in wb["Riwayat"].iter_rows(min_row=2, values_only=True):
            assert row[2] == jname

    def test_branch_admin_other_store_403(self, tok):
        r = requests.get(f"{API}/history/price-stock/export", headers=H(tok["jombang"]), params={"store_id": "pgs-official"})
        assert r.status_code == 403

    def test_customer_403(self, tok):
        r = requests.get(f"{API}/history/price-stock/export", headers=H(tok["demo"]))
        assert r.status_code == 403

    def test_bad_date_400(self, tok):
        r = requests.get(f"{API}/history/price-stock/export", headers=H(tok["admin"]), params={"date_from": "2026-02-01", "date_to": "2026-01-01"})
        assert r.status_code == 400


# ---------- product by code ----------
@pytest.fixture(scope="module")
def barcode_product(tok):
    code = f"899{uuid.uuid4().int % 10**10:010d}"
    data = {"name": f"TEST_Scan {code[-4:]}", "category": "dapur", "subcategory": "peralatan-masak", "brand": "TEST", "sku": f"TS-{code[-6:]}",
            "barcode": code, "condition": "new", "status": "active", "description": DESC, "images": [IMG], "price": 20000,
            "discount_price": 0, "stock": 10, "min_order": 1, "max_order": 0, "weight_grams": 500}
    r = requests.post(f"{API}/product-editor/publish", headers=H(tok["seller"]), json={"data": data})
    assert r.status_code == 200, r.text
    pid = r.json()["product_id"]
    yield pid, code, data["sku"]
    DB.products.delete_one({"product_id": pid, "name": {"$regex": "^TEST_"}})
    DB.price_history.delete_many({"product_id": pid})


class TestByCode:
    @pytest.mark.parametrize("code", ["DBLP32HC", "dblp32hc", "pgs-9849", " DBLP32HC "])
    def test_sku_and_id(self, code):
        r = requests.get(f"{API}/products/by-code/{code}")
        assert r.status_code == 200, r.text
        assert r.json()["product_id"] == "pgs-9849" and r.json()["name"]

    def test_url(self):
        r = requests.get(f"{API}/products/by-code/" + requests.utils.quote("https://x.id/product/pgs-9849?ref=qr", safe=""))
        assert r.status_code == 200, r.text
        assert r.json()["product_id"] == "pgs-9849"

    def test_barcode(self, barcode_product):
        pid, code, sku = barcode_product
        r = requests.get(f"{API}/products/by-code/{code}")
        assert r.status_code == 200 and r.json()["product_id"] == pid
        assert requests.get(f"{API}/products/by-code/{sku.lower()}").json()["product_id"] == pid
        g = requests.get(f"{API}/products/{pid}")
        assert g.status_code == 200

    def test_editor_get_returns_barcode(self, tok, barcode_product):
        pid, code, _ = barcode_product
        r = requests.get(f"{API}/product-editor/products/{pid}", headers=H(tok["seller"]))
        assert r.status_code == 200, r.text
        assert r.json().get("data", r.json()).get("barcode") == code

    def test_unknown_404(self):
        r = requests.get(f"{API}/products/by-code/NOPE-{uuid.uuid4().hex[:6]}")
        assert r.status_code == 404 and r.json()["detail"]


# ---------- cashier pickup ----------
@pytest.fixture(scope="module")
def pickup(tok):
    before = DB.products.find_one({"product_id": PID}, {"_id": 0, "stock": 1, "sold": 1})
    t = tok["demo"]
    saved_cart = requests.get(f"{API}/cart", headers=H(t, STORE)).json()
    requests.delete(f"{API}/cart", headers=H(t))
    r = requests.post(f"{API}/cart/items", headers=H(t, STORE), json={"product_id": PID, "quantity": 1})
    assert r.status_code == 200, r.text
    r = requests.post(f"{API}/checkout", headers=H(t), json={"full_name": "TEST Scan", "phone": "081234567890", "payment_method": "cod",
                                                              "store_id": STORE, "courier": "pickup"})
    assert r.status_code == 200, r.text
    o = r.json()
    yield o
    DB.orders.delete_one({"order_id": o["order_id"]})
    DB.products.update_one({"product_id": PID}, {"$set": before})
    for it in saved_cart.get("items", []):
        requests.post(f"{API}/cart/items", headers=H(t, it.get("store_id") or STORE), json={"product_id": it["product_id"], "quantity": it["quantity"],
                                                                                           **({"variant_id": it["variant_id"]} if it.get("variant_id") else {})})


class TestPickup:
    def test_lookup_store_admin(self, tok, pickup):
        r = requests.post(f"{API}/seller/pickup/lookup", headers=H(tok["sidoarjo"]), json={"code": pickup["pickup_code"]})
        assert r.status_code == 200, r.text
        assert r.json()["order_id"] == pickup["order_id"] and r.json()["status"] == "cod"

    def test_lookup_super_admin(self, tok, pickup):
        r = requests.post(f"{API}/seller/pickup/lookup", headers=H(tok["admin"]), json={"code": pickup["pickup_code"]})
        assert r.status_code == 200 and r.json()["order_id"] == pickup["order_id"]

    def test_lookup_other_branch_404(self, tok, pickup):
        r = requests.post(f"{API}/seller/pickup/lookup", headers=H(tok["jombang"]), json={"code": pickup["pickup_code"]})
        assert r.status_code == 404

    def test_customer_403(self, tok, pickup):
        r = requests.post(f"{API}/seller/pickup/lookup", headers=H(tok["demo"]), json={"code": pickup["pickup_code"]})
        assert r.status_code == 403

    def test_bad_code(self, tok):
        assert requests.post(f"{API}/seller/pickup/lookup", headers=H(tok["admin"]), json={"code": "00"}).status_code == 422
        assert requests.post(f"{API}/seller/pickup/lookup", headers=H(tok["admin"]), json={"code": "abcdef"}).status_code == 404

    def test_complete_then_again_400(self, tok, pickup):
        r = requests.post(f"{API}/seller/pickup/complete", headers=H(tok["sidoarjo"]), json={"code": pickup["pickup_code"]})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "completed"
        g = requests.get(f"{API}/orders/{pickup['order_id']}", headers=H(tok["demo"]))
        assert g.json()["status"] == "completed"
        r2 = requests.post(f"{API}/seller/pickup/complete", headers=H(tok["admin"]), json={"code": pickup["pickup_code"]})
        assert r2.status_code == 400
