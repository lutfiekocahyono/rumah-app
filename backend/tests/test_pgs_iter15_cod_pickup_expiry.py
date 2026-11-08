# PGS iteration 15: COD only for pickup, COD pickup auto-expiry (2x24h) + manual extend, "Siap diambil" ready flow.
import os
import subprocess
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
PID = "pgs-9955"
STORE = "pgs-official"
DEST = 69243  # GUBENG Surabaya


def _env(k):
    for line in open("/app/backend/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip('"')


DB = MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]
CRED = {"sidoarjo": ("sidoarjo@pgs.id", "Sidoarjo123!"), "jombang": ("jombang@pgs.id", "Jombang123!")}
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


@pytest.fixture(scope="module", autouse=True)
def tok():
    t = {k: _login(k) for k in CRED}
    yield t
    # cleanup: cancel any test order still open (restocks)
    for oid in CREATED:
        o = DB.orders.find_one({"order_id": oid}, {"status": 1})
        if o and o["status"] in ("cod", "paid", "processing", "pending"):
            requests.put(f"{API}/seller/orders/{oid}/status", headers=H(t["sidoarjo"]), json={"status": "cancelled"})


@pytest.fixture()
def buyer():
    email = f"test_cod15_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "TestPass123!", "name": "TEST COD15"})
    assert r.status_code == 200, r.text
    t = r.json()["token"]
    yield t
    requests.delete(f"{API}/cart", headers=H(t))


def _stock():
    r = requests.get(f"{API}/products/{PID}/availability")
    return {s["store_id"]: s["stock"][PID] for s in r.json()["stores"]}[STORE]


def _add(t, qty=1):
    r = requests.post(f"{API}/cart/items", headers=H(t, STORE), json={"product_id": PID, "quantity": qty})
    assert r.status_code == 200, r.text


def _checkout(t, courier="pickup", pm="cod", **kw):
    body = {"full_name": "TEST Buyer", "phone": "081234567890", "address": "Jl. Test No. 1", "city": "Surabaya",
            "payment_method": pm, "store_id": STORE, "courier": courier, **kw}
    if courier != "pickup":
        body["destination_id"] = DEST
    r = requests.post(f"{API}/checkout", headers=H(t), json=body)
    if r.status_code == 200:
        CREATED.append(r.json()["order_id"])
    return r


def _cod_order(t, qty=1):
    _add(t, qty)
    r = _checkout(t)
    assert r.status_code == 200, r.text
    return r.json()


def _parse(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=timezone.utc) if "+" not in s[10:] and not s.endswith("Z") else datetime.fromisoformat(s.replace("Z", "+00:00"))


def _notifs(t):
    r = requests.get(f"{API}/notifications", headers=H(t))
    assert r.status_code == 200
    return r.json()


# ---------- checkout rules ----------
class TestCheckoutRules:
    def test_cod_courier_rejected(self, buyer):
        _add(buyer)
        r = _checkout(buyer, courier="jne")
        assert r.status_code == 400, r.text
        assert "COD hanya untuk Ambil di toko" in r.json()["detail"]

    def test_midtrans_not_ready_rejected(self, buyer):
        _add(buyer)
        r = _checkout(buyer, courier="jne", pm="midtrans")
        assert r.status_code == 400, r.text
        assert "online" in r.json()["detail"].lower()

    def test_cod_pickup_expires_48h(self, buyer):
        before = _stock()
        o = _cod_order(buyer)
        assert o["status"] == "cod" and o["payment_method"] == "cod" and o["courier"]["code"] == "pickup"
        exp = _parse(o["expires_at"])
        delta = (exp - datetime.now(timezone.utc)).total_seconds() / 3600
        assert 47.8 < delta <= 48.05, delta
        assert _stock() == before - 1

    def test_full_saldo_delivery_allowed(self, buyer):
        _add(buyer)
        uid = DB.users.find_one({"email": requests.get(f"{API}/auth/me", headers=H(buyer)).json()["email"]})["user_id"]
        DB.wallets.update_one({"user_id": uid}, {"$inc": {"balance": 5_000_000}}, upsert=True)
        try:
            r = _checkout(buyer, courier="jne", pm="saldo")
            assert r.status_code == 200, r.text
            o = r.json()
            assert o["status"] == "paid" and o["payment_method"] == "saldo" and o["courier"]["code"] == "jne"
            assert o.get("expires_at") is None
        finally:
            DB.wallets.delete_one({"user_id": uid})


# ---------- extend ----------
class TestExtend:
    def test_extend_24_from_current(self, tok, buyer):
        o = _cod_order(buyer)
        cur = _parse(o["expires_at"])
        r = requests.post(f"{API}/seller/orders/{o['order_id']}/extend", headers=H(tok["sidoarjo"]), json={"hours": 24})
        assert r.status_code == 200, r.text
        new = _parse(r.json()["expires_at"])
        assert abs((new - cur).total_seconds() - 24 * 3600) < 5
        assert "diperpanjang 24 jam" in r.json()["status_history"][-1]["note"]
        g = requests.get(f"{API}/seller/orders/{o['order_id']}", headers=H(tok["sidoarjo"])).json()
        assert _parse(g["expires_at"]) == new
        assert any(n["title"] == "Batas waktu pesanan diperpanjang" for n in _notifs(buyer))

    def test_extend_48_from_now_when_past(self, tok, buyer):
        o = _cod_order(buyer)
        DB.orders.update_one({"order_id": o["order_id"]}, {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(hours=5)}})
        r = requests.post(f"{API}/seller/orders/{o['order_id']}/extend", headers=H(tok["sidoarjo"]), json={"hours": 48})
        assert r.status_code == 200, r.text
        d = (_parse(r.json()["expires_at"]) - datetime.now(timezone.utc)).total_seconds() / 3600
        assert 47.9 < d <= 48.05, d

    def test_extend_other_store_404_and_validation(self, tok, buyer):
        o = _cod_order(buyer)
        r = requests.post(f"{API}/seller/orders/{o['order_id']}/extend", headers=H(tok["jombang"]), json={"hours": 24})
        assert r.status_code == 404
        r = requests.post(f"{API}/seller/orders/{o['order_id']}/extend", headers=H(tok["sidoarjo"]), json={"hours": 0})
        assert r.status_code == 422
        r = requests.post(f"{API}/seller/orders/{o['order_id']}/extend", json={"hours": 24})
        assert r.status_code in (401, 403)

    def test_extend_non_cod_400(self, tok, buyer):
        o = _cod_order(buyer)
        assert requests.put(f"{API}/seller/orders/{o['order_id']}/status", headers=H(tok["sidoarjo"]), json={"status": "processing"}).status_code == 200
        r = requests.post(f"{API}/seller/orders/{o['order_id']}/extend", headers=H(tok["sidoarjo"]), json={"hours": 24})
        assert r.status_code == 400, r.text


# ---------- ready ----------
class TestReady:
    def test_ready_flow(self, tok, buyer):
        o = _cod_order(buyer)
        oid, h = o["order_id"], H(tok["sidoarjo"])
        r = requests.post(f"{API}/seller/orders/{oid}/ready", headers=h)
        assert r.status_code == 400, r.text  # status cod, not processing
        assert requests.put(f"{API}/seller/orders/{oid}/status", headers=h, json={"status": "processing"}).status_code == 200
        r = requests.post(f"{API}/seller/orders/{oid}/ready", headers=h)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ready_at"] and d["status"] == "processing"
        assert d["status_history"][-1]["note"] == "Siap diambil di toko"
        r2 = requests.post(f"{API}/seller/orders/{oid}/ready", headers=h)  # idempotent
        assert r2.status_code == 200 and r2.json()["ready_at"] == d["ready_at"]
        assert sum(1 for x in r2.json()["status_history"] if x.get("note") == "Siap diambil di toko") == 1
        ns = [n for n in _notifs(buyer) if n["title"] == "Pesanan siap diambil"]
        assert len(ns) == 1 and oid in ns[0]["body" if "body" in ns[0] else "message"]
        b = requests.get(f"{API}/orders/{oid}", headers=H(buyer)).json()
        assert b["ready_at"] == d["ready_at"]
        assert requests.post(f"{API}/seller/orders/{oid}/ready", headers=H(tok["jombang"])).status_code == 404

    def test_ready_delivery_order_400(self, tok, buyer):
        _add(buyer)
        uid = DB.users.find_one({"email": requests.get(f"{API}/auth/me", headers=H(buyer)).json()["email"]})["user_id"]
        DB.wallets.update_one({"user_id": uid}, {"$inc": {"balance": 5_000_000}}, upsert=True)
        try:
            r = _checkout(buyer, courier="jne", pm="saldo")
            assert r.status_code == 200, r.text
            oid = r.json()["order_id"]
            h = H(tok["sidoarjo"])
            assert requests.put(f"{API}/seller/orders/{oid}/status", headers=h, json={"status": "processing"}).status_code == 200
            assert requests.post(f"{API}/seller/orders/{oid}/ready", headers=h).status_code == 400
        finally:
            DB.wallets.delete_one({"user_id": uid})


# ---------- auto-cancel ----------
class TestAutoCancel:
    def test_expired_cod_auto_cancel_on_restart(self, buyer):
        before = _stock()
        o = _cod_order(buyer, qty=2)
        assert _stock() == before - 2
        DB.orders.update_one({"order_id": o["order_id"]}, {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(minutes=1)}})
        subprocess.run(["sudo", "supervisorctl", "restart", "backend"], check=True, capture_output=True)
        for _ in range(30):
            time.sleep(2)
            try:
                if requests.get(f"{API}/orders/{o['order_id']}", headers=H(buyer), timeout=5).json().get("status") == "cancelled":
                    break
            except Exception:
                pass
        d = requests.get(f"{API}/orders/{o['order_id']}", headers=H(buyer)).json()
        assert d["status"] == "cancelled", d
        assert d["status_history"][-1]["note"].startswith("Batal otomatis")
        assert _stock() == before
        assert any(n["title"] == "Pesanan dibatalkan otomatis" for n in _notifs(buyer))
