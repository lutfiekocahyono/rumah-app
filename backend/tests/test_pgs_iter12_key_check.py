# PGS iteration 12: "Cek Kunci Ongkir" — admin verify-key, key_status, shipping/status auto flag.
# Run: pytest tests/test_pgs_iter12_key_check.py -n 0   (NEVER reads/prints api_key_enc or key_hint)
import os
import uuid
import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")

API = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/") + "/api"
STORE, GUBENG = "pgs-official", 69243
coll = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]].settings


def _login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def admin():
    h = _login("admin@pgs.id", "Admin1234!")
    yield h
    # always restore key_status to valid via the real check
    r = requests.post(f"{API}/admin/shipping/verify-key", headers=h, timeout=30)
    assert r.json()["key_status"]["state"] == "valid"


@pytest.fixture(scope="module")
def demo():
    return _login("demo@pgs.id", "Demo1234!")


# --- auth guard on verify-key / settings
class TestAuthGuard:
    def test_verify_unauth_401(self):
        assert requests.post(f"{API}/admin/shipping/verify-key").status_code == 401

    def test_verify_customer_403(self, demo):
        r = requests.post(f"{API}/admin/shipping/verify-key", headers=demo)
        assert r.status_code == 403

    def test_settings_customer_403(self, demo):
        assert requests.get(f"{API}/admin/shipping-settings", headers=demo).status_code == 403


# --- real verify with stored key
class TestVerify:
    def test_verify_valid(self, admin):
        before = coll.find_one({"key": "shipping_api"}, {"key_status": 1})["key_status"]["checked_at"]
        r = requests.post(f"{API}/admin/shipping/verify-key", headers=admin, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["configured"] is True
        ks = d["key_status"]
        assert ks["state"] == "valid"
        assert ks["message"]
        assert ks["checked_at"]
        after = coll.find_one({"key": "shipping_api"}, {"key_status": 1})["key_status"]["checked_at"]
        assert after > before
        assert "api_key_enc" not in d and "api_key" not in d

    def test_settings_has_status_no_raw_key(self, admin):
        r = requests.get(f"{API}/admin/shipping-settings", headers=admin)
        assert r.status_code == 200
        d = r.json()
        assert d["key_status"]["state"] == "valid"
        assert set(d.keys()) == {"configured", "key_hint", "enabled", "default_weight_grams", "origins", "key_status"}
        assert "_id" not in r.text and "api_key_enc" not in r.text

    def test_status_auto_true(self):
        assert requests.get(f"{API}/shipping/status").json() == {"auto": True}


# --- forced invalid state in DB (key untouched)
class TestForcedInvalid:
    def test_invalid_state_flips_auto(self, admin):
        coll.update_one({"key": "shipping_api"}, {"$set": {"key_status.state": "invalid"}})
        try:
            assert requests.get(f"{API}/shipping/status").json() == {"auto": False}
            g = requests.get(f"{API}/admin/shipping-settings", headers=admin).json()
            assert g["key_status"]["state"] == "invalid"
            # observation: rates endpoint with destination still quotes live?
            reg = requests.post(f"{API}/auth/register", json={"email": f"test_iter12_{uuid.uuid4().hex[:6]}@example.com", "password": "Test1234!", "name": "TEST_Iter12"})
            h = {"Authorization": f"Bearer {reg.json()['token']}", "X-Store-Id": STORE}
            rates = requests.post(f"{API}/shipping/rates", headers=h, json={"store_id": STORE, "destination_id": GUBENG}).json()
            print("RATES_WHEN_INVALID", [(c["code"], c["cost"], c.get("source")) for c in rates])
            dests = requests.get(f"{API}/shipping/destinations", params={"q": "gubeng"}, headers=h).json()
            print("DEST_AUTO_WHEN_INVALID", dests.get("auto"))
            uid = reg.json()["user"]["user_id"]
            udb = coll.database
            udb.users.delete_one({"user_id": uid}); udb.notifications.delete_many({"user_id": uid}); udb.carts.delete_many({"owner": f"user:{uid}"})
        finally:
            r = requests.post(f"{API}/admin/shipping/verify-key", headers=admin, timeout=30)
        assert r.json()["key_status"]["state"] == "valid"
        assert requests.get(f"{API}/shipping/status").json() == {"auto": True}


# --- classification evidence: RajaOngkir response for a fake key (direct call, not via app)
class TestFakeKeyDirect:
    def test_fake_key_400_invalid_text(self):
        r = requests.get("https://rajaongkir.komerce.id/api/v1/destination/domestic-destination",
                         params={"search": "sidoarjo", "limit": 1, "offset": 0}, headers={"key": "TEST_fake_key_123456"}, timeout=15)
        print("FAKE_KEY", r.status_code, r.text[:200])
        assert r.status_code in (400, 401, 403)
        t = r.text.lower()
        assert "api key" in t or "apikey" in t or r.status_code in (401, 403)
