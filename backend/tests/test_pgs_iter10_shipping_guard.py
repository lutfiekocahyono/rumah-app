# PGS iteration 10: checkout refuses order when shipping cost changed (expected_shipping_cost guard).
# Run: pytest tests/test_pgs_iter10_shipping_guard.py -n 0   (NEVER reads/prints the RajaOngkir key)
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
SHIP = {"full_name": "TEST_Iter10 Buyer", "phone": "081234567890", "address": "Jl. Test No 10", "city": "Surabaya",
        "payment_method": "cod", "store_id": STORE, "destination_id": GUBENG,
        "destination_label": "GUBENG, GUBENG, SURABAYA, JAWA TIMUR, 60281"}


def _db_run(coro_fn):
    async def run():
        db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        return await coro_fn(db)
    return asyncio.run(run())


@pytest.fixture(scope="module")
def ctx():
    reg = requests.post(f"{API}/auth/register", json={"email": f"test_iter10_{uuid.uuid4().hex[:6]}@example.com", "password": "Test1234!", "name": "TEST_Iter10"})
    assert reg.status_code == 200, reg.text
    uid = reg.json()["user"]["user_id"]
    h = {"Authorization": f"Bearer {reg.json()['token']}", "X-Store-Id": STORE}
    rates = requests.post(f"{API}/shipping/rates", headers=h, json={"store_id": STORE, "destination_id": GUBENG}).json()
    sicepat = next(c for c in rates if c["code"] == "sicepat")
    print("sicepat real cost", sicepat["cost"])
    c = {"h": h, "uid": uid, "real": int(sicepat["cost"]), "name": sicepat["name"], "orders": []}
    yield c
    sh = requests.post(f"{API}/auth/login", json={"email": "sidoarjo@pgs.id", "password": "Sidoarjo123!"}).json()["token"]
    for oid in c["orders"]:
        r = requests.put(f"{API}/seller/orders/{oid}/status", headers={"Authorization": f"Bearer {sh}"}, json={"status": "cancelled"})
        print("cancel", oid, r.status_code)

    async def clean(db):
        await db.notifications.delete_many({"link": {"$in": [f"/order/{x}" for x in c["orders"]]}})
        await db.orders.delete_many({"order_id": {"$in": c["orders"]}})
        await db.carts.delete_many({"owner": f"user:{uid}"})
        await db.users.delete_many({"user_id": uid})
    _db_run(clean)


def _stock(h):
    return requests.get(f"{API}/products/{PID}", headers=h).json()["stock"]


def _add(h):
    r = requests.post(f"{API}/cart/items", headers=h, json={"product_id": PID, "quantity": 1})
    assert r.status_code == 200, r.text


# Mismatch -> 409 with exact Indonesian message, no order/stock/voucher/cart side effects
def test_mismatch_409_no_side_effects(ctx):
    h = ctx["h"]
    _add(h)
    stock0 = _stock(h)
    vdoc = _db_run(lambda db: db.vouchers.find_one({}, {"_id": 0, "code": 1, "used": 1}))
    body = {**SHIP, "courier": "sicepat", "expected_shipping_cost": ctx["real"] - 2500}
    if vdoc:
        body["voucher_code"] = vdoc["code"]
    r = requests.post(f"{API}/checkout", headers=h, json=body)
    assert r.status_code == 409, r.text
    rp = lambda n: f"Rp{n:,}".replace(",", ".")
    exp = f"Ongkir {ctx['name']} berubah dari {rp(ctx['real'] - 2500)} menjadi {rp(ctx['real'])}. Tarif sudah dimuat ulang, periksa lalu buat pesanan lagi."
    print(r.json()["detail"])
    assert r.json()["detail"] == exp
    assert requests.get(f"{API}/orders", headers=h).json() == []
    assert _stock(h) == stock0
    cart = requests.get(f"{API}/cart", headers=h).json()
    assert any(i["product_id"] == PID for i in cart["items"])
    if vdoc:
        v2 = _db_run(lambda db: db.vouchers.find_one({"code": vdoc["code"]}, {"_id": 0, "used": 1}))
        assert v2.get("used") == vdoc.get("used")


# Higher expected than real -> also 409
def test_mismatch_higher_409(ctx):
    r = requests.post(f"{API}/checkout", headers=ctx["h"], json={**SHIP, "courier": "sicepat", "expected_shipping_cost": ctx["real"] + 1000})
    assert r.status_code == 409
    assert "berubah dari" in r.json()["detail"]


# Unknown courier -> 409
def test_unknown_courier_409(ctx):
    r = requests.post(f"{API}/checkout", headers=ctx["h"], json={**SHIP, "courier": "TEST_nokurir", "expected_shipping_cost": 1000})
    assert r.status_code == 409, r.text
    assert r.json()["detail"].startswith("Kurir yang dipilih tidak tersedia lagi")
    assert requests.get(f"{API}/orders", headers=ctx["h"]).json() == []


# Matching expected -> 200, shipping_cost equals expected; stock decremented
def test_matching_200(ctx):
    h = ctx["h"]
    stock0 = _stock(h)
    r = requests.post(f"{API}/checkout", headers=h, json={**SHIP, "courier": "sicepat", "expected_shipping_cost": ctx["real"]})
    assert r.status_code == 200, r.text
    o = r.json()
    ctx["orders"].append(o["order_id"])
    assert o["shipping_cost"] == ctx["real"]
    assert o["payment_method"] == "cod"
    if stock0 != 9999:
        assert _stock(h) == stock0 - 1
    g = requests.get(f"{API}/orders/{o['order_id']}", headers=h)
    assert g.status_code == 200 and g.json()["shipping_cost"] == ctx["real"]


# Omitting expected_shipping_cost still works (backwards compatible)
def test_omit_expected_200(ctx):
    h = ctx["h"]
    _add(h)
    r = requests.post(f"{API}/checkout", headers=h, json={**SHIP, "courier": "sicepat"})
    assert r.status_code == 200, r.text
    ctx["orders"].append(r.json()["order_id"])
    assert r.json()["shipping_cost"] == ctx["real"]


# Pickup with expected 0 (no destination) still works
def test_pickup_expected_zero(ctx):
    h = ctx["h"]
    _add(h)
    rates = requests.post(f"{API}/shipping/rates", headers=h, json={"store_id": STORE}).json()
    pk = next((c for c in rates if c["code"] == "pickup"), None)
    if not pk:
        pytest.skip("no pickup courier")
    body = {**SHIP, "courier": "pickup", "expected_shipping_cost": int(pk["cost"]), "destination_id": None}
    r = requests.post(f"{API}/checkout", headers=h, json=body)
    assert r.status_code == 200, r.text
    ctx["orders"].append(r.json()["order_id"])
    assert r.json()["shipping_cost"] == int(pk["cost"])
