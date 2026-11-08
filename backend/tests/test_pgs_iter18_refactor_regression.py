# PGS iteration 18: regression after server.py split (marketing.py + order_tasks.py). Behaviour must be unchanged.
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
PID = "pgs-9955"
STORE = "pgs-official"


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


def _login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin():
    return _login("admin@pgs.id", "Admin1234!")


@pytest.fixture(scope="module")
def store_admin():
    return _login("sidoarjo@pgs.id", "Sidoarjo123!")


@pytest.fixture()
def buyer():
    email = f"test_iter18_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "TestPass123!", "name": "TEST Iter18"})
    assert r.status_code == 200, r.text
    d = r.json()
    yield d["token"], d["user"]["user_id"]
    requests.delete(f"{API}/cart", headers=H(d["token"]))


@pytest.fixture()
def voucher(admin):
    code = f"TST{uuid.uuid4().hex[:6].upper()}"
    r = requests.post(f"{API}/admin/vouchers", headers=H(admin), json={
        "code": code, "title": "TEST iter18", "mode": "rupiah", "value": 1000, "quota": 5, "show_on_home": False})
    assert r.status_code == 200, r.text
    yield code
    requests.delete(f"{API}/admin/vouchers/{code}", headers=H(admin))


def _stock():
    r = requests.get(f"{API}/products/{PID}/availability")
    return {s["store_id"]: s["stock"][PID] for s in r.json()["stores"]}[STORE]


def _used(code):
    return DB.vouchers.find_one({"code": code})["used"]


def _balance(uid):
    return int((DB.wallets.find_one({"user_id": uid}) or {}).get("balance", 0))


# ---------- marketing (public) ----------
class TestMarketingPublic:
    def test_banners(self):
        r = requests.get(f"{API}/banners")
        assert r.status_code == 200 and isinstance(r.json(), list)
        for b in r.json():
            assert b["active"] is True and "banner_id" in b and "image" in b

    def test_home_settings(self):
        r = requests.get(f"{API}/home-settings")
        assert r.status_code == 200
        d = r.json()
        assert "free_shipping" in d and d["recommend_mode"] in ("personal", "random")

    def test_flash_sale(self):
        r = requests.get(f"{API}/flash-sale")
        assert r.status_code == 200
        d = r.json()
        assert "active" in d and isinstance(d["items"], list)

    def test_vouchers_mine_requires_owner_and_claim(self, buyer, voucher, admin):
        t, _ = buyer
        # hidden voucher not in public list
        assert voucher not in [v["code"] for v in requests.get(f"{API}/vouchers").json()]
        r = requests.post(f"{API}/vouchers/{voucher.lower()}/claim", headers=H(t))
        assert r.status_code == 200 and r.json()["claimed"] is True and r.json()["code"] == voucher
        mine = requests.get(f"{API}/vouchers/mine", headers=H(t)).json()
        assert voucher in [v["code"] for v in mine]
        assert requests.post(f"{API}/vouchers/NOPE999/claim", headers=H(t)).status_code == 404

    def test_apply_voucher(self, buyer, voucher):
        t, _ = buyer
        requests.post(f"{API}/cart/items", headers=H(t, STORE), json={"product_id": PID, "quantity": 1})
        r = requests.post(f"{API}/vouchers/apply", headers=H(t), json={"code": f" {voucher.lower()} "})
        assert r.status_code == 200, r.text
        assert r.json() == {"code": voucher, "title": "TEST iter18", "discount": 1000}
        bad = requests.post(f"{API}/vouchers/apply", headers=H(t), json={"code": "NOPE999"})
        assert bad.status_code == 400


# ---------- marketing (admin) ----------
class TestMarketingAdmin:
    def test_non_admin_forbidden(self, buyer):
        t, _ = buyer
        for p in ("/admin/banners", "/admin/vouchers", "/admin/flash-sale"):
            assert requests.get(f"{API}{p}", headers=H(t)).status_code == 403, p

    def test_banner_crud(self, admin):
        body = {"title": "TEST_iter18 banner", "image": "https://example.com/x.jpg", "order": 99, "active": False}
        r = requests.post(f"{API}/admin/banners", headers=H(admin), json=body)
        assert r.status_code == 200, r.text
        bid = r.json()["banner_id"]
        try:
            assert bid.startswith("bn_")
            assert bid in [b["banner_id"] for b in requests.get(f"{API}/admin/banners", headers=H(admin)).json()]
            assert bid not in [b["banner_id"] for b in requests.get(f"{API}/banners").json()]  # inactive
            u = requests.put(f"{API}/admin/banners/{bid}", headers=H(admin), json={**body, "title": "TEST_iter18 v2"})
            assert u.status_code == 200 and u.json()["title"] == "TEST_iter18 v2"
            assert requests.put(f"{API}/admin/banners/bn_nope", headers=H(admin), json=body).status_code == 404
            bad = requests.post(f"{API}/admin/banners", headers=H(admin), json={**body, "link_type": "bogus"})
            assert bad.status_code == 422
        finally:
            requests.delete(f"{API}/admin/banners/{bid}", headers=H(admin))
        assert bid not in [b["banner_id"] for b in requests.get(f"{API}/admin/banners", headers=H(admin)).json()]

    def test_voucher_crud(self, admin, voucher):
        lst = requests.get(f"{API}/admin/vouchers", headers=H(admin)).json()
        v = next(x for x in lst if x["code"] == voucher)
        assert v["used"] == 0 and v["value"] == 1000
        base = {"code": voucher, "title": "TEST iter18 upd", "mode": "rupiah", "value": 2000, "quota": 5, "show_on_home": False}
        u = requests.put(f"{API}/admin/vouchers/{voucher.lower()}", headers=H(admin), json=base)
        assert u.status_code == 200 and u.json()["value"] == 2000 and u.json()["title"] == "TEST iter18 upd"
        assert requests.put(f"{API}/admin/vouchers/{voucher}", headers=H(admin), json={**base, "code": "OTHERX"}).status_code == 400
        assert requests.post(f"{API}/admin/vouchers", headers=H(admin), json=base).status_code == 400  # duplicate
        pct = requests.post(f"{API}/admin/vouchers", headers=H(admin), json={**base, "code": "TSTPCT9", "mode": "percent", "value": 150})
        assert pct.status_code == 400

    def test_flash_sale_roundtrip(self, admin):
        orig = requests.get(f"{API}/admin/flash-sale", headers=H(admin)).json()
        assert set(orig) >= {"title", "active", "ends_at", "items"}
        body = {"title": orig["title"], "active": orig["active"], "ends_at": orig["ends_at"] or (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                "items": [{"product_id": i["product_id"], "flash_price": i["flash_price"]} for i in orig["items"]]}
        r = requests.put(f"{API}/admin/flash-sale", headers=H(admin), json=body)
        assert r.status_code == 200, r.text
        assert [i["product_id"] for i in r.json()["items"]] == [i["product_id"] for i in orig["items"]]

    def test_home_settings_roundtrip(self, admin):
        orig = requests.get(f"{API}/home-settings").json()
        body = {"free_shipping": {k: orig["free_shipping"][k] for k in ("enabled", "title", "subtitle", "min_purchase")},
                "recommend_mode": orig["recommend_mode"]}
        r = requests.put(f"{API}/admin/home-settings", headers=H(admin), json=body)
        assert r.status_code == 200, r.text
        assert r.json()["recommend_mode"] == orig["recommend_mode"]
        assert requests.put(f"{API}/admin/home-settings", headers=H(admin), json={**body, "recommend_mode": "x"}).status_code == 422


# ---------- order_tasks: checkout pickup COD + release on cancel ----------
class TestOrderRelease:
    def _order(self, t, uid, voucher):
        DB.wallets.update_one({"user_id": uid}, {"$inc": {"balance": 500}}, upsert=True)  # TEST user's own wallet
        r = requests.post(f"{API}/cart/items", headers=H(t, STORE), json={"product_id": PID, "quantity": 1})
        assert r.status_code == 200, r.text
        r = requests.post(f"{API}/checkout", headers=H(t), json={
            "full_name": "TEST Buyer", "phone": "081234567890", "address": "", "city": "", "payment_method": "cod",
            "store_id": STORE, "courier": "pickup", "voucher_code": voucher, "use_balance": True})
        assert r.status_code == 200, r.text
        return r.json()

    @pytest.mark.parametrize("who", ["seller", "admin"])
    def test_cancel_releases_voucher_stock_saldo(self, who, buyer, voucher, admin, store_admin):
        t, uid = buyer
        stock0 = _stock()
        o = self._order(t, uid, voucher)
        assert o["status"] == "cod" and o["courier"]["code"] == "pickup"
        assert o["pickup_code"] and len(o["pickup_code"]) == 6 and o["expires_at"]
        assert o["discount"] == 1000 and o["voucher_code"] == voucher and o["balance_used"] == 500
        assert o["total"] == o["subtotal"] - 1000 + o["shipping_cost"]
        assert _used(voucher) == 1 and _stock() == stock0 - 1 and _balance(uid) == 0
        if who == "seller":
            r = requests.put(f"{API}/seller/orders/{o['order_id']}/status", headers=H(store_admin), json={"status": "cancelled"})
        else:
            r = requests.put(f"{API}/admin/orders/{o['order_id']}/status", headers=H(admin), json={"status": "cancelled"})
        assert r.status_code == 200, r.text
        assert _used(voucher) == 0 and _stock() == stock0 and _balance(uid) == 500
        # idempotent: a second cancel must not double-release
        requests.put(f"{API}/admin/orders/{o['order_id']}/status", headers=H(admin), json={"status": "cancelled"})
        assert _used(voucher) == 0 and _stock() == stock0 and _balance(uid) == 500
        DB.wallets.delete_one({"user_id": uid})
