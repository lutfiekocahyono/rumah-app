# PGS iteration 13: Admin "Pengaturan Pembayaran" (Midtrans key, sandbox), payments/methods, checkout guard.
# Run: pytest tests/test_pgs_iter13_midtrans_settings.py -n 0   (FAKE keys only; always removed at the end)
import asyncio
import os
import uuid
import pytest
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")

API = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/") + "/api"
PID, STORE, GUBENG = "pgs-9955", "pgs-official", 69243
FAKE = "SB-Mid-server-FAKE" + uuid.uuid4().hex[:12].upper()
SHIP = {"full_name": "TEST_Iter13 Buyer", "phone": "081234567890", "address": "Jl. Test No 13", "city": "Surabaya",
        "payment_method": "midtrans", "store_id": STORE, "destination_id": GUBENG,
        "destination_label": "GUBENG, GUBENG, SURABAYA, JAWA TIMUR, 60281"}
PUBLIC_KEYS = {"configured", "key_hint", "client_key", "enabled", "production", "key_status", "ready"}


def _db_run(coro_fn):
    async def run():
        db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        return await coro_fn(db)
    return asyncio.run(run())


def _login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _no_secret(resp):
    assert FAKE not in resp.text
    assert "server_key_enc" not in resp.text and "server_key" not in resp.json()


@pytest.fixture(scope="module")
def admin():
    h = _login("admin@pgs.id", "Admin1234!")
    yield h
    # always remove test key and restore defaults
    r = requests.put(f"{API}/admin/payment-settings", headers=h, timeout=30,
                     json={"enabled": True, "production": False, "server_key": "", "client_key": ""})
    assert r.status_code == 200 and r.json()["configured"] is False


@pytest.fixture(scope="module")
def demo():
    return _login("demo@pgs.id", "Demo1234!")


# --- auth guard
class TestAuthGuard:
    def test_get_unauth(self):
        assert requests.get(f"{API}/admin/payment-settings").status_code == 401

    def test_get_customer_403(self, demo):
        assert requests.get(f"{API}/admin/payment-settings", headers=demo).status_code == 403

    def test_put_customer_403(self, demo):
        r = requests.put(f"{API}/admin/payment-settings", headers=demo, json={"server_key": FAKE})
        assert r.status_code == 403

    def test_verify_customer_403(self, demo):
        assert requests.post(f"{API}/admin/payment/verify-midtrans", headers=demo).status_code == 403


# --- settings flow: initial -> verify 400 -> fake key invalid -> methods false -> verify -> remove
class TestSettingsFlow:
    def test_initial_get(self, admin):
        r = requests.get(f"{API}/admin/payment-settings", headers=admin)
        assert r.status_code == 200
        d = r.json()
        assert set(d) == PUBLIC_KEYS
        assert d["configured"] is False and d["production"] is False and d["ready"] is False
        assert d["key_hint"] == "" and d["key_status"] is None

    def test_verify_without_key_400(self, admin):
        r = requests.post(f"{API}/admin/payment/verify-midtrans", headers=admin, timeout=30)
        assert r.status_code == 400
        assert r.json()["detail"] == "Isi Server Key Midtrans dulu"

    def test_methods_initial(self):
        d = requests.get(f"{API}/payments/methods").json()
        assert d["midtrans"] is False and d["cod"] is True and d["midtrans_sandbox"] is True

    def test_put_fake_key_invalid(self, admin):
        r = requests.put(f"{API}/admin/payment-settings", headers=admin, timeout=40,
                         json={"enabled": True, "production": False, "server_key": FAKE, "client_key": "SB-Mid-client-TEST"})
        assert r.status_code == 200, r.text
        _no_secret(r)
        d = r.json()
        print("key_status", d["key_status"])
        assert d["configured"] is True
        assert d["key_hint"] == "••••" + FAKE[-4:]
        assert d["client_key"] == "SB-Mid-client-TEST"
        assert d["key_status"]["state"] == "invalid"
        assert "ditolak Midtrans" in d["key_status"]["message"]
        assert d["ready"] is False

    def test_db_encrypted(self, admin):
        doc = _db_run(lambda db: db.settings.find_one({"key": "payment_midtrans"}))
        assert doc["server_key_enc"] and FAKE not in doc["server_key_enc"]
        assert doc["key_status"]["state"] == "invalid"

    def test_get_after_put(self, admin):
        r = requests.get(f"{API}/admin/payment-settings", headers=admin)
        _no_secret(r)
        d = r.json()
        assert d["configured"] is True and d["key_status"]["state"] == "invalid" and d["ready"] is False

    def test_methods_false_with_invalid(self):
        assert requests.get(f"{API}/payments/methods").json()["midtrans"] is False

    def test_verify_with_key(self, admin):
        r = requests.post(f"{API}/admin/payment/verify-midtrans", headers=admin, timeout=40)
        assert r.status_code == 200
        _no_secret(r)
        assert r.json()["key_status"]["state"] == "invalid"

    def test_put_keep_key_none(self, admin):
        # server_key None keeps key; enabled toggle saved
        r = requests.put(f"{API}/admin/payment-settings", headers=admin, timeout=40,
                         json={"enabled": False, "production": False, "server_key": None, "client_key": "SB-Mid-client-TEST"})
        d = r.json()
        assert d["configured"] is True and d["enabled"] is False and d["key_hint"].endswith(FAKE[-4:])
        assert d["ready"] is False

    def test_mode_switch_reverifies(self, admin):
        r = requests.put(f"{API}/admin/payment-settings", headers=admin, timeout=40,
                         json={"enabled": True, "production": True, "server_key": None, "client_key": "SB-Mid-client-TEST"})
        d = r.json()
        print("prod key_status", d["key_status"])
        assert d["production"] is True and d["key_status"]["state"] == "invalid"
        assert "bukan key Sandbox" in d["key_status"]["message"]
        assert requests.get(f"{API}/payments/methods").json()["midtrans_sandbox"] is False
        r = requests.put(f"{API}/admin/payment-settings", headers=admin, timeout=40,
                         json={"enabled": True, "production": False, "server_key": None, "client_key": "SB-Mid-client-TEST"})
        assert r.json()["production"] is False

    def test_validation_too_long(self, admin):
        r = requests.put(f"{API}/admin/payment-settings", headers=admin, json={"server_key": "x" * 201})
        assert r.status_code == 422


# --- checkout guard: midtrans when not ready -> 400, no order/stock change
class TestCheckoutGuard:
    def test_midtrans_checkout_400(self, admin):
        reg = requests.post(f"{API}/auth/register", json={"email": f"test_iter13_{uuid.uuid4().hex[:6]}@example.com", "password": "Test1234!", "name": "TEST_Iter13"})
        assert reg.status_code == 200, reg.text
        uid = reg.json()["user"]["user_id"]
        h = {"Authorization": f"Bearer {reg.json()['token']}", "X-Store-Id": STORE}
        try:
            assert requests.post(f"{API}/cart/items", headers=h, json={"product_id": PID, "quantity": 1}).status_code == 200
            stock0 = requests.get(f"{API}/products/{PID}", headers=h).json()["stock"]
            r = requests.post(f"{API}/checkout", headers=h, json={**SHIP, "courier": "sicepat"}, timeout=40)
            assert r.status_code == 400, r.text
            assert r.json()["detail"] == "Pembayaran online belum aktif, pilih COD"
            assert requests.get(f"{API}/products/{PID}", headers=h).json()["stock"] == stock0
            assert _db_run(lambda db: db.orders.count_documents({"user_id": uid})) == 0
            cart = requests.get(f"{API}/cart", headers=h).json()
            assert cart["item_count"] == 1
        finally:
            async def clean(db):
                await db.carts.delete_many({"owner": f"user:{uid}"})
                await db.users.delete_many({"user_id": uid})
            _db_run(clean)


# --- remove key -> configured false, key_status removed
class TestRemove:
    def test_remove_key(self, admin):
        r = requests.put(f"{API}/admin/payment-settings", headers=admin, timeout=30,
                         json={"enabled": True, "production": False, "server_key": "", "client_key": ""})
        d = r.json()
        assert d["configured"] is False and d["key_hint"] == "" and d["key_status"] is None and d["ready"] is False
        doc = _db_run(lambda db: db.settings.find_one({"key": "payment_midtrans"}))
        assert not doc.get("server_key_enc") and "key_status" not in doc
        assert requests.get(f"{API}/payments/methods").json()["midtrans"] is False
        assert requests.post(f"{API}/admin/payment/verify-midtrans", headers=admin).status_code == 400
