# Iteration 33: QR product-link lookup (website permalink slug, /product/<slug>, uppercase) + Accurate fake-key error
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
PID = "pgs-9849"


def _login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=20)
    if r.status_code != 200:
        pytest.skip(f"login failed {email}")
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def admin():
    return _login("admin@pgs.id", "Admin1234!")


# Product lookup by scanned code (query form)
@pytest.mark.parametrize("code", [
    "https://pusatgrosirsidoarjo.com/distributor/happy-call-double-pan-32-cm/",
    "https://pusatgrosirsidoarjo.com/distributor/happy-call-double-pan-32-cm",
    "https://x.id/product/happy-call-double-pan-32-cm/",
    "https://x.id/product/pgs-9849",
    "https://x.id/product/pgs-9849?ref=qr",
    "PGS-9849",
    "pgs-9849",
    "HTTPS://X.ID/PRODUCT/PGS-9849",
    "dblp32hc",
    "DBLP32HC",
    "  pgs-9849  ",
])
def test_by_code_query_matches(code):
    r = requests.get(f"{API}/products/by-code", params={"code": code}, timeout=20)
    assert r.status_code == 200, f"{code}: {r.status_code} {r.text}"
    assert r.json()["product_id"] == PID
    assert "_id" not in r.json()


@pytest.mark.parametrize("code", ["TEST_UNKNOWN_123", "https://x.id/product/TEST_nope-zz", "https://pusatgrosirsidoarjo.com/distributor/TEST-no-such-slug/"])
def test_by_code_unknown_404(code):
    r = requests.get(f"{API}/products/by-code", params={"code": code}, timeout=20)
    assert r.status_code == 404
    assert "tidak ditemukan" in r.json()["detail"]


def test_by_code_path_form():
    r = requests.get(f"{API}/products/by-code/{PID}", timeout=20)
    assert r.status_code == 200 and r.json()["product_id"] == PID
    r = requests.get(f"{API}/products/by-code/https%3A%2F%2Fx.id%2Fproduct%2FPGS-9849", timeout=20)
    assert r.status_code == 200 and r.json()["product_id"] == PID
    r = requests.get(f"{API}/products/by-code/dblp32hc", timeout=20)
    assert r.status_code == 200 and r.json()["product_id"] == PID


def test_product_detail_reachable():
    r = requests.get(f"{API}/products/{PID}", timeout=20)
    assert r.status_code == 200 and r.json()["product_id"] == PID


# Accurate: fake keys -> 400 Indonesian message; cleanup
def test_accurate_fake_keys_400(admin):
    try:
        r = requests.put(f"{API}/admin/accurate/settings", headers=admin,
                         json={"api_token": "TEST_fake_token_abc", "signature_secret": "TEST_fake_secret"}, timeout=30)
        assert r.status_code in (200, 201), r.text
        t = requests.post(f"{API}/admin/accurate/test", headers=admin, json={}, timeout=40)
        assert t.status_code == 400, t.text
        assert "Kunci API ditolak Accurate" in t.json()["detail"]
    finally:
        requests.delete(f"{API}/admin/accurate/settings", headers=admin, timeout=20)
    g = requests.get(f"{API}/admin/accurate/settings", headers=admin, timeout=20)
    assert g.status_code == 200
