# PGS iteration 32: QR product link lookup fix (query + path form) and Accurate Online phase-1 admin settings.
import os

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
PID = "pgs-9849"
SKU = "DBLP32HC"
TOKEN = "TEST_fake_api_token_ABCD1234"
SECRET = "TEST_fake_signature_secret_WXYZ"


def _env(k):
    for line in open("/app/backend/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip('"')


DB = MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]


def _login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=20)
    if r.status_code != 200:
        pytest.skip(f"login failed for {email}: {r.status_code}")
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def admin():
    return _login("admin@pgs.id", "Admin1234!")


@pytest.fixture(scope="module")
def demo():
    return _login("demo@pgs.id", "Demo1234!")


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    DB.settings.delete_one({"key": "accurate"})  # start clean (only fake-key test data)
    yield
    DB.settings.delete_one({"key": "accurate"})


# --- Product lookup by code (QR link 404 retest) ---
class TestByCode:
    def test_query_full_link(self):
        r = requests.get(f"{API}/products/by-code", params={"code": f"https://pusatgrosirsidoarjo.com/product/{PID}"}, timeout=20)
        assert r.status_code == 200, r.text
        assert r.json()["product_id"] == PID

    def test_query_raw_encoded_url(self):
        r = requests.get(f"{API}/products/by-code?code=https%3A%2F%2Fpusatgrosirsidoarjo.com%2Fproduct%2F{PID}", timeout=20)
        assert r.status_code == 200, r.text
        assert r.json()["product_id"] == PID

    def test_path_encoded_link(self):
        r = requests.get(f"{API}/products/by-code/https%3A%2F%2Fx.id%2Fproduct%2F{PID}", timeout=20)
        assert r.status_code == 200, r.text
        assert r.json()["product_id"] == PID

    def test_query_sku_case_insensitive(self):
        for c in (SKU, SKU.lower()):
            r = requests.get(f"{API}/products/by-code", params={"code": c}, timeout=20)
            assert r.status_code == 200, r.text
            assert r.json()["product_id"] == PID

    def test_unknown_404(self):
        r = requests.get(f"{API}/products/by-code", params={"code": "TEST_NOPE_999"}, timeout=20)
        assert r.status_code == 404
        assert "tidak ditemukan" in r.json()["detail"]

    def test_empty_404(self):
        r = requests.get(f"{API}/products/by-code", params={"code": " "}, timeout=20)
        assert r.status_code == 404


# --- Accurate Online settings (admin only) ---
class TestAccurate:
    def test_customer_forbidden(self, demo):
        for m, p in (("get", "settings"), ("put", "settings"), ("post", "test"), ("get", "warehouses"), ("get", "items"), ("delete", "settings")):
            r = requests.request(m, f"{API}/admin/accurate/{p}", headers=demo, json={}, timeout=20)
            assert r.status_code == 403, (m, p, r.status_code)

    def test_unauth_401(self):
        r = requests.get(f"{API}/admin/accurate/settings", timeout=20)
        assert r.status_code in (401, 403)

    def test_initial_not_configured(self, admin):
        r = requests.get(f"{API}/admin/accurate/settings", headers=admin, timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d["configured"] is False and d["phase"] == 1 and d["write_enabled"] is False

    def test_test_without_keys_400(self, admin):
        r = requests.post(f"{API}/admin/accurate/test", headers=admin, timeout=20)
        assert r.status_code == 400
        assert "API Token" in r.json()["detail"]

    def test_first_put_without_keys_400(self, admin):
        r = requests.put(f"{API}/admin/accurate/settings", headers=admin, json={"api_token": "", "signature_secret": ""}, timeout=20)
        assert r.status_code == 400
        r = requests.put(f"{API}/admin/accurate/settings", headers=admin, json={"api_token": TOKEN, "signature_secret": ""}, timeout=20)
        assert r.status_code == 400

    def test_put_keys_masked_and_encrypted(self, admin):
        r = requests.put(f"{API}/admin/accurate/settings", headers=admin, json={"api_token": TOKEN, "signature_secret": SECRET, "database_id": "TEST_1"}, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["configured"] is True
        assert d["token_hint"] == "••••1234" and d["secret_hint"] == "••••WXYZ"
        assert TOKEN not in r.text and SECRET not in r.text
        assert "api_token" not in d and "signature_secret" not in d
        doc = DB.settings.find_one({"key": "accurate"})
        assert doc["api_token"] != TOKEN and doc["api_token"].startswith("gAAAA")
        assert doc["signature_secret"] != SECRET and SECRET not in str(doc)
        g = requests.get(f"{API}/admin/accurate/settings", headers=admin, timeout=20)
        assert g.json()["configured"] is True and TOKEN not in g.text and g.json()["database_id"] == "TEST_1"

    def test_blank_put_keeps_keys(self, admin):
        before = DB.settings.find_one({"key": "accurate"})
        r = requests.put(f"{API}/admin/accurate/settings", headers=admin, json={"api_token": "", "signature_secret": "", "database_id": ""}, timeout=20)
        assert r.status_code == 200
        assert r.json()["configured"] is True and r.json()["token_hint"] == "••••1234"
        after = DB.settings.find_one({"key": "accurate"})
        assert after["api_token"] == before["api_token"] and after["signature_secret"] == before["signature_secret"]

    def test_connection_fake_keys_fails_gracefully(self, admin):
        r = requests.post(f"{API}/admin/accurate/test", headers=admin, timeout=40)
        print("accurate test ->", r.status_code, r.text[:300])
        assert 400 <= r.status_code < 600 and r.status_code != 500
        detail = r.json()["detail"]
        assert isinstance(detail, str) and any(w in detail for w in ("Accurate", "Kunci", "Tidak bisa", "Respon"))
        g = requests.get(f"{API}/admin/accurate/settings", headers=admin, timeout=20).json()
        assert g["last_test_ok"] is False and g["last_test_at"] and g["last_test_message"] == detail

    def test_warehouses_items_without_success(self, admin):
        for p in ("warehouses", "items"):
            r = requests.get(f"{API}/admin/accurate/{p}", headers=admin, timeout=40)
            print(p, r.status_code, r.text[:200])
            assert r.status_code in (400, 502), r.text
            assert "Jalankan Uji Koneksi dulu" in r.json()["detail"] or "Accurate" in r.json()["detail"]

    def test_warehouse_map_ignores_unknown(self, admin):
        body = {"warehouse_map": {"pgs-official": " Gudang Utama ", "TEST_unknown_store": "X", "pgs-jombang": "   "}}
        r = requests.put(f"{API}/admin/accurate/warehouse-map", headers=admin, json=body, timeout=20)
        assert r.status_code == 200, r.text
        assert r.json()["warehouse_map"] == {"pgs-official": "Gudang Utama"}

    def test_delete_clears(self, admin):
        r = requests.delete(f"{API}/admin/accurate/settings", headers=admin, timeout=20)
        assert r.status_code == 200 and r.json()["configured"] is False
        assert DB.settings.find_one({"key": "accurate"}) is None
        g = requests.get(f"{API}/admin/accurate/settings", headers=admin, timeout=20).json()
        assert g["configured"] is False and g["token_hint"] == "" and g["warehouse_map"] == {}
