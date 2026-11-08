# PGS iteration 9: ETA translation (_eta_id) + shipping rates in Indonesian + COD checkout with cheapest courier.
# Run: pytest tests/test_pgs_iter9_checkout_eta.py -n 0   (NEVER reads/prints the RajaOngkir key)
import os
import sys
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
sys.path.insert(0, "/app/backend")
from shipping import _eta_id  # noqa: E402

API = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/") + "/api"
PID, STORE, GUBENG = "pgs-9955", "pgs-official", 69243
SHIP = {"full_name": "TEST_Iter9 Buyer", "phone": "081234567890", "address": "Jl. Test No 9", "city": "Surabaya"}


def _login(e, p):
    r = requests.post(f"{API}/auth/login", json={"email": e, "password": p})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


# ETA helper unit tests
@pytest.mark.parametrize("raw,exp", [("2 day", "2 hari"), ("3-5 day", "3-5 hari"), ("1-2 HARI", "1-2 hari"),
                                     ("2 days", "2 hari"), ("", ""), (None, ""), ("1", "1 hari"), ("2-3 Days.", "2-3 hari")])
def test_eta_id(raw, exp):
    assert _eta_id(raw) == exp


@pytest.fixture(scope="module")
def guest():
    return {"X-Guest-Id": "TEST_iter9_guest_rates", "X-Store-Id": STORE}


# Rates API returns Indonesian eta
def test_rates_eta_indonesian(guest):
    r = requests.post(f"{API}/shipping/rates", headers=guest, json={"store_id": STORE, "destination_id": GUBENG})
    assert r.status_code == 200, r.text
    rates = r.json()
    print([(c["code"], c["name"], c["cost"], c.get("eta"), c.get("source")) for c in rates])
    assert any(c.get("source") == "auto" for c in rates)
    for c in rates:
        assert "day" not in (c.get("eta") or "").lower(), c
        if c.get("source") == "auto":
            assert c["eta"].endswith(" hari"), c
    ship = [c for c in rates if c["code"] != "pickup" and c.get("active", True)]
    cheapest = min(ship, key=lambda c: c["cost"])
    print("cheapest", cheapest["code"], cheapest["cost"])
    assert cheapest["code"] == "sicepat"


def test_rates_no_destination_manual(guest):
    r = requests.post(f"{API}/shipping/rates", headers=guest, json={"store_id": STORE})
    assert r.status_code == 200
    assert all(c.get("source") == "manual" for c in r.json())
    for c in r.json():
        assert "day" not in (c.get("eta") or "").lower(), c


def test_rates_bad_store(guest):
    r = requests.post(f"{API}/shipping/rates", headers=guest, json={"store_id": "TEST_nope", "destination_id": GUBENG})
    assert r.status_code == 404


# COD checkout with cheapest auto courier then cancel as store admin to restock
def test_cod_checkout_sicepat_and_cancel():
    import uuid
    reg = requests.post(f"{API}/auth/register", json={"email": f"test_iter9_{uuid.uuid4().hex[:6]}@example.com", "password": "Test1234!", "name": "TEST_Iter9"})
    assert reg.status_code == 200, reg.text
    h = {"Authorization": f"Bearer {reg.json()['token']}", "X-Store-Id": STORE}
    stock0 = requests.get(f"{API}/products/{PID}", headers=h).json()["stock"]
    assert requests.post(f"{API}/cart/items", headers=h, json={"product_id": PID, "quantity": 1}).status_code == 200
    r = requests.post(f"{API}/checkout", headers=h, json={**SHIP, "payment_method": "cod", "courier": "sicepat", "store_id": STORE,
                                                         "destination_id": GUBENG, "destination_label": "GUBENG, GUBENG, SURABAYA, JAWA TIMUR, 60281"})
    assert r.status_code == 200, r.text
    o = r.json()
    print({k: o.get(k) for k in ("order_id", "shipping_cost", "courier", "courier_name", "payment_method", "total")})
    assert o["payment_method"] == "cod"
    assert o.get("shipping_cost") == 7500
    sh = _login("sidoarjo@pgs.id", "Sidoarjo123!")
    c = requests.put(f"{API}/seller/orders/{o['order_id']}/status", headers=sh, json={"status": "cancelled"})
    assert c.status_code == 200, c.text
    assert requests.get(f"{API}/products/{PID}", headers=h).json()["stock"] == stock0
    _cleanup(reg.json()["user"]["user_id"], [o["order_id"]])


def _cleanup(uid, oids):
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient

    async def run():
        db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        await db.notifications.delete_many({"link": {"$in": [f"/order/{x}" for x in oids]}})
        await db.orders.delete_many({"order_id": {"$in": oids}})
        await db.carts.delete_many({"owner": f"user:{uid}"})
        await db.users.delete_many({"user_id": uid})
    asyncio.run(run())
