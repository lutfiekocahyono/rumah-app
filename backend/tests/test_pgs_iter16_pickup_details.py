# PGS iteration 16: pickup checkout without address (pickup_code), courier requires address, optional store phone/address/hours.
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
PID = "pgs-9955"
STORE = "pgs-official"
DEST = 69243
CRED = {"sidoarjo": ("sidoarjo@pgs.id", "Sidoarjo123!"), "jombang": ("jombang@pgs.id", "Jombang123!"),
        "jember": ("jember@pgs.id", "Jember123!")}
CREATED: list = []


def H(t, store=None):
    h = {"Authorization": f"Bearer {t}"}
    if store:
        h["X-Store-Id"] = store
    return h


def _login(k):
    r = requests.post(f"{API}/auth/login", json={"email": CRED[k][0], "password": CRED[k][1]})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def tok():
    t = {k: _login(k) for k in CRED}
    yield t
    for oid in CREATED:
        requests.put(f"{API}/seller/orders/{oid}/status", headers=H(t["sidoarjo"]), json={"status": "cancelled"})


@pytest.fixture()
def buyer():
    email = f"test_pick16_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "TestPass123!", "name": "TEST Pick16"})
    assert r.status_code == 200, r.text
    t = r.json()["token"]
    yield t
    requests.delete(f"{API}/cart", headers=H(t))


def _add(t):
    r = requests.post(f"{API}/cart/items", headers=H(t, STORE), json={"product_id": PID, "quantity": 1})
    assert r.status_code == 200, r.text


# Checkout: pickup needs no address; courier delivery does
class TestCheckoutAddress:
    def test_pickup_cod_without_address(self, tok, buyer):
        _add(buyer)
        r = requests.post(f"{API}/checkout", headers=H(buyer), json={
            "full_name": "TEST Pick", "phone": "081234567890", "payment_method": "cod",
            "store_id": STORE, "courier": "pickup"})
        assert r.status_code == 200, r.text
        o = r.json()
        CREATED.append(o["order_id"])
        assert o["courier"]["code"] == "pickup" and o["status"] == "cod"
        assert len(o["pickup_code"]) == 6 and o["pickup_code"].isdigit()
        assert o["shipping"]["address"] == "" and o["shipping"]["city"] == ""
        g = requests.get(f"{API}/orders/{o['order_id']}", headers=H(buyer))
        assert g.status_code == 200 and g.json()["pickup_code"] == o["pickup_code"]
        s = requests.get(f"{API}/seller/orders/{o['order_id']}", headers=H(tok["sidoarjo"]))
        if s.status_code == 200:
            assert s.json()["pickup_code"] == o["pickup_code"]

    def test_courier_without_address_rejected(self, tok, buyer):
        _add(buyer)
        r = requests.post(f"{API}/checkout", headers=H(buyer), json={
            "full_name": "TEST Pick", "phone": "081234567890", "payment_method": "midtrans",
            "store_id": STORE, "courier": "jne", "destination_id": DEST})
        if r.status_code == 200:
            CREATED.append(r.json()["order_id"])
        assert r.status_code == 400, r.text
        # online payment may be off -> different 400 first; check address rule explicitly with saldo too
        print("detail:", r.json()["detail"])

    def test_courier_saldo_without_address_rejected(self, tok, buyer):
        _add(buyer)
        r = requests.post(f"{API}/checkout", headers=H(buyer), json={
            "full_name": "TEST Pick", "phone": "081234567890", "payment_method": "cod",
            "store_id": STORE, "courier": "jne", "destination_id": DEST})
        if r.status_code == 200:
            CREATED.append(r.json()["order_id"])
        assert r.status_code == 400, r.text
        assert r.json()["detail"] == "Lengkapi alamat dan kota pengiriman", r.json()["detail"]


# Store edit: phone/address/hours optional
class TestStoreOptional:
    @pytest.mark.parametrize("who,sid", [("jombang", "pgs-jombang"), ("jember", "pgs-jember")])
    def test_empty_then_filled_then_restore(self, tok, who, sid):
        h = H(tok[who])
        cur = requests.get(f"{API}/me/store", headers=h).json()
        assert cur["store_id"] == sid
        base = {"name": cur["name"], "description": cur.get("description") or "", "city": cur["city"],
                "logo": cur.get("logo") or ""}
        orig = {"phone": cur.get("phone") or "", "address": cur.get("address") or "", "pickup_hours": cur.get("pickup_hours") or ""}
        try:
            r = requests.put(f"{API}/me/store", headers=h, json={**base, "phone": "", "address": "", "pickup_hours": ""})
            assert r.status_code == 200, r.text
            assert r.json()["phone"] == "" and r.json()["status"] == "active"
            r = requests.put(f"{API}/me/store", headers=h, json={**base, "phone": "", "address": "TEST_Jl. Raya 1",
                                                                "pickup_hours": "TEST_08.00-16.00"})
            assert r.status_code == 200, r.text
            off = {s["store_id"]: s for s in requests.get(f"{API}/official-stores").json()}
            assert off[sid]["address"] == "TEST_Jl. Raya 1"
            assert off[sid]["pickup_hours"] == "TEST_08.00-16.00"
        finally:
            r = requests.put(f"{API}/me/store", headers=h, json={**base, **orig})
            assert r.status_code == 200, r.text
        off = {s["store_id"]: s for s in requests.get(f"{API}/official-stores").json()}
        assert (off[sid]["address"] or "") == orig["address"] and (off[sid]["pickup_hours"] or "") == orig["pickup_hours"]
