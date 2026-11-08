# Iteration 11: Alamat Tersimpan Pintar — destination_id/destination_label on saved addresses + checkout integration
import os, uuid, pytest, requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
API = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"
GUBENG = 69243


def login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def user():
    email = f"test_iter11_{uuid.uuid4().hex[:6]}@example.com"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "Test1234!", "name": "TEST_Iter11"})
    assert r.status_code == 200, r.text
    d = r.json()
    u = {"h": {"Authorization": f"Bearer {d['token']}", "X-Store-Id": "pgs-official"}, "uid": d["user"]["user_id"], "orders": []}
    yield u
    # cleanup: delete TEST addresses by id, then TEST user
    for a in requests.get(f"{API}/me/addresses", headers=u["h"]).json():
        requests.delete(f"{API}/me/addresses/{a['address_id']}", headers=u["h"])
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient
    load_dotenv("/app/backend/.env")

    async def run():
        db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        await db.users.delete_one({"user_id": u["uid"]})
        await db.activity.delete_many({"user_id": u["uid"]})
    asyncio.run(run())


def base_addr(**kw):
    b = {"label": "TEST_Rumah", "recipient": "TEST Penerima", "phone": "081234567890", "address": "Jl. TEST No. 1", "city": "Surabaya", "postal_code": "", "is_default": False}
    b.update(kw)
    return b


class TestAddressDestination:
    # Old-style address (no destination fields) still works
    def test_add_without_destination(self, user):
        r = requests.post(f"{API}/me/addresses", headers=user["h"], json=base_addr(label="TEST_Lama"))
        assert r.status_code == 200, r.text
        a = [x for x in r.json() if x["label"] == "TEST_Lama"][0]
        assert a.get("destination_id") is None
        assert a.get("destination_label", "") == ""
        assert a["is_default"] is True  # first address becomes default
        assert "_id" not in a
        user["old"] = a["address_id"]

    # New address with destination persists id (int) + label
    def test_add_with_destination(self, user):
        r = requests.post(f"{API}/me/addresses", headers=user["h"], json=base_addr(label="TEST_Area", destination_id=GUBENG, destination_label="GUBENG, GUBENG, SURABAYA, JAWA TIMUR, 60281", postal_code="60281"))
        assert r.status_code == 200, r.text
        a = [x for x in r.json() if x["label"] == "TEST_Area"][0]
        assert a["destination_id"] == GUBENG and isinstance(a["destination_id"], int)
        assert a["destination_label"].startswith("GUBENG")
        user["area"] = a["address_id"]
        g = requests.get(f"{API}/me/addresses", headers=user["h"]).json()
        assert [x for x in g if x["address_id"] == a["address_id"]][0]["destination_id"] == GUBENG

    # PUT adds area to old address, then GET verifies
    def test_put_sets_destination(self, user):
        r = requests.put(f"{API}/me/addresses/{user['old']}", headers=user["h"], json=base_addr(label="TEST_Lama", destination_id=GUBENG, destination_label="GUBENG, GUBENG, SURABAYA, JAWA TIMUR, 60281"))
        assert r.status_code == 200, r.text
        g = requests.get(f"{API}/me/addresses", headers=user["h"]).json()
        a = [x for x in g if x["address_id"] == user["old"]][0]
        assert a["destination_id"] == GUBENG
        assert a["is_default"] is True  # default kept when is_default false in PUT

    # PUT clearing destination
    def test_put_clears_destination(self, user):
        r = requests.put(f"{API}/me/addresses/{user['old']}", headers=user["h"], json=base_addr(label="TEST_Lama", destination_id=None, destination_label=""))
        assert r.status_code == 200
        a = [x for x in r.json() if x["address_id"] == user["old"]][0]
        assert a.get("destination_id") is None

    # Validation: non-int destination_id rejected; overlong label rejected
    def test_invalid_destination(self, user):
        r = requests.post(f"{API}/me/addresses", headers=user["h"], json=base_addr(destination_id="abc"))
        assert r.status_code == 422
        r = requests.post(f"{API}/me/addresses", headers=user["h"], json=base_addr(destination_label="x" * 201))
        assert r.status_code == 422

    # Rates with saved destination return auto couriers
    def test_rates_for_saved_destination(self, user):
        r = requests.post(f"{API}/shipping/rates", headers=user["h"], json={"store_id": "pgs-official", "destination_id": GUBENG})
        assert r.status_code == 200, r.text
        data = r.json()
        lst = data if isinstance(data, list) else data.get("data", data.get("couriers", []))
        codes = [c["code"] for c in lst]
        print("rates", [(c["code"], c.get("cost"), c.get("source")) for c in lst])
        assert any(c.get("source") == "auto" for c in lst), "no auto rates"
        assert len(codes) >= 2


class TestDemoUntouched:
    # Demo's existing addresses (no destination) are still served fine
    def test_demo_addresses_list(self):
        t = login("demo@pgs.id", "Demo1234!")
        r = requests.get(f"{API}/me/addresses", headers={"Authorization": f"Bearer {t}"})
        assert r.status_code == 200
        for a in r.json():
            assert "_id" not in a and "address_id" in a
        print("demo addresses", [(a["label"], a.get("destination_id")) for a in r.json()])


def teardown_module(module):
    pass
