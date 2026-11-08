# PGS iteration 4: account features (auth hardening, email/phone verification, password flows, profile, addresses,
# activity, settings, notifications) + seller/store basics (open store, admin verification, seller products)
import io
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN = {"email": "admin@pgs.id", "password": "Admin1234!"}
SELLER = {"email": "acct1@pgs.id", "password": "Test1234!"}
SHIP = {"full_name": "TEST_Buyer", "phone": "081234567890", "address": "Jl. Test No 1", "city": "Sidoarjo"}
PW = "TestPass123!"


def H(t):
    return {"Authorization": f"Bearer {t}"}


def _login(c):
    r = requests.post(f"{API}/auth/login", json=c)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _register(prefix="TEST_u"):
    email = f"{prefix.lower()}_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": PW, "name": f"TEST {prefix}"})
    assert r.status_code == 200, r.text
    return {"email": email, "token": r.json()["token"], "user": r.json()["user"]}


@pytest.fixture(scope="module")
def admin():
    return H(_login(ADMIN))


@pytest.fixture(scope="module")
def u1():
    return _register("TEST_u1")


# ---------- auth basics ----------
class TestAuth:
    def test_register_short_password(self):
        r = requests.post(f"{API}/auth/register", json={"email": f"test_{uuid.uuid4().hex[:6]}@example.com", "password": "short1", "name": "x"})
        assert r.status_code == 422

    def test_me_fields(self, u1):
        r = requests.get(f"{API}/auth/me", headers=H(u1["token"]))
        assert r.status_code == 200
        d = r.json()
        for k in ("email_verified", "phone", "phone_verified", "has_password"):
            assert k in d, k
        assert d["email_verified"] is False and d["has_password"] is True and d["phone_verified"] is False

    def test_login_rate_limit_429(self):
        t = _register("TEST_rl")
        codes = [requests.post(f"{API}/auth/login", json={"email": t["email"], "password": "wrongpass1"}).status_code for _ in range(10)]
        assert all(c == 401 for c in codes), codes
        r = requests.post(f"{API}/auth/login", json={"email": t["email"], "password": PW})
        assert r.status_code == 429, r.text


# ---------- email verification & forgot password ----------
class TestEmailCodes:
    def test_verify_email_fake_domain_400(self, u1):
        r = requests.post(f"{API}/auth/verify-email/request", headers=H(u1["token"]))
        assert r.status_code == 400, r.text
        assert "tidak bisa menerima" in r.json()["detail"]

    def test_verify_email_real_domain_200(self):
        r = requests.post(f"{API}/auth/register", json={"email": "delivered@resend.dev", "password": PW, "name": "TEST Delivered"})
        if r.status_code == 400:
            r = requests.post(f"{API}/auth/login", json={"email": "delivered@resend.dev", "password": PW})
            if r.status_code != 200:
                pytest.skip("delivered@resend.dev already exists with unknown password")
        tok = r.json()["token"]
        r = requests.post(f"{API}/auth/verify-email/request", headers=H(tok))
        assert r.status_code in (200, 429), r.text
        print("verify-email send:", r.status_code, r.text)
        # wrong codes -> 400; after MAX_ATTEMPTS the code is invalidated
        codes = [requests.post(f"{API}/auth/verify-email/confirm", headers=H(tok), json={"code": "000000"}).status_code for _ in range(6)]
        assert all(c == 400 for c in codes), codes
        bad = requests.post(f"{API}/auth/verify-email/confirm", headers=H(tok), json={"code": "12ab"})
        assert bad.status_code == 422

    def test_reset_request_generic(self, u1):
        a = requests.post(f"{API}/auth/password-reset/request", json={"email": f"nobody_{uuid.uuid4().hex[:6]}@nowhere.io"})
        assert a.status_code == 200 and "Jika email terdaftar" in a.json()["message"]
        b = requests.post(f"{API}/auth/password-reset/request", json={"email": u1["email"]})
        print("reset existing (fake domain):", b.status_code, b.text)
        assert b.status_code == 200, f"existing fake-domain email reset leaks/fails: {b.status_code} {b.text}"
        assert b.json() == a.json()

    def test_reset_confirm_wrong_code(self, u1):
        r = requests.post(f"{API}/auth/password-reset/confirm", json={"email": u1["email"], "code": "000000", "new_password": "NewPass123!"})
        assert r.status_code == 400


# ---------- change password ----------
class TestChangePassword:
    def test_change_password_flow(self):
        t = _register("TEST_pw")
        r = requests.post(f"{API}/auth/password/change", headers=H(t["token"]), json={"current_password": "wrongwrong", "new_password": "NewPass123!"})
        assert r.status_code == 400
        r = requests.post(f"{API}/auth/password/change", headers=H(t["token"]), json={"current_password": PW, "new_password": "NewPass123!"})
        assert r.status_code == 200, r.text
        new = r.json()["token"]
        assert requests.get(f"{API}/auth/me", headers=H(t["token"])).status_code == 401
        assert requests.get(f"{API}/auth/me", headers=H(new)).status_code == 200
        assert requests.post(f"{API}/auth/login", json={"email": t["email"], "password": "NewPass123!"}).status_code == 200
        n = requests.get(f"{API}/notifications", headers=H(new)).json()
        assert any(x["kind"] == "security" and "Password" in x["title"] for x in n)


# ---------- phone OTP ----------
class TestPhone:
    def test_phone_otp_and_duplicate(self, u1):
        phone = "0812" + str(uuid.uuid4().int)[:8]
        r = requests.post(f"{API}/auth/phone/request", headers=H(u1["token"]), json={"phone": phone})
        assert r.status_code == 200, r.text
        code = r.json()["dev_code"]
        assert r.json()["phone"] == "62" + phone[1:]
        assert requests.post(f"{API}/auth/phone/confirm", headers=H(u1["token"]), json={"code": "999999" if code != "999999" else "111111"}).status_code == 400
        # wrong attempt consumed one try but code is still valid
        r = requests.post(f"{API}/auth/phone/confirm", headers=H(u1["token"]), json={"code": code})
        assert r.status_code == 200, r.text
        assert r.json()["phone_verified"] is True
        me = requests.get(f"{API}/auth/me", headers=H(u1["token"])).json()
        assert me["phone_verified"] is True and me["phone"] == "62" + phone[1:]
        other = _register("TEST_ph2")
        r = requests.post(f"{API}/auth/phone/request", headers=H(other["token"]), json={"phone": "+62" + phone[1:]})
        assert r.status_code == 400 and "dipakai" in r.json()["detail"]

    def test_phone_invalid(self, u1):
        r = requests.post(f"{API}/auth/phone/request", headers=H(u1["token"]), json={"phone": "12345678"})
        assert r.status_code == 400


# ---------- profile & avatar ----------
class TestProfile:
    def test_update_profile(self, u1):
        r = requests.put(f"{API}/me/profile", headers=H(u1["token"]), json={"name": "TEST Edited", "gender": "female", "birthdate": "1995-05-17"})
        assert r.status_code == 200, r.text
        me = requests.get(f"{API}/auth/me", headers=H(u1["token"])).json()
        assert me["name"] == "TEST Edited" and me.get("gender") == "female" and me.get("birthdate") == "1995-05-17"
        assert requests.put(f"{API}/me/profile", headers=H(u1["token"]), json={"name": "x", "gender": "other"}).status_code == 422
        assert requests.put(f"{API}/me/profile", headers=H(u1["token"]), json={"name": "x", "birthdate": "17-05-1995"}).status_code == 422

    def test_avatar(self, u1):
        png = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")
        r = requests.post(f"{API}/me/avatar", headers=H(u1["token"]), files={"file": ("a.png", io.BytesIO(png), "image/png")})
        assert r.status_code == 200, r.text
        pic = r.json()["picture"]
        assert pic.startswith("/api/files/")
        assert requests.get(f"{BASE_URL}{pic}").status_code == 200
        bad = requests.post(f"{API}/me/avatar", headers=H(u1["token"]), files={"file": ("a.txt", io.BytesIO(b"hi"), "text/plain")})
        assert bad.status_code == 400


# ---------- addresses ----------
class TestAddresses:
    def test_address_crud_default_logic(self, u1):
        h = H(u1["token"])
        base = {"recipient": "TEST R", "phone": "08123456789", "address": "Jl. Test 123", "city": "Sidoarjo", "postal_code": "61211"}
        a = requests.post(f"{API}/me/addresses", headers=h, json={**base, "label": "Rumah"}).json()
        assert len(a) == 1 and a[0]["is_default"] is True
        b = requests.post(f"{API}/me/addresses", headers=h, json={**base, "label": "Kantor"}).json()
        assert len(b) == 2 and sum(x["is_default"] for x in b) == 1
        kantor = next(x for x in b if x["label"] == "Kantor")
        rumah = next(x for x in b if x["label"] == "Rumah")
        assert kantor["is_default"] is False
        c = requests.put(f"{API}/me/addresses/{kantor['address_id']}", headers=h, json={**base, "label": "Kantor2", "is_default": True}).json()
        assert sum(x["is_default"] for x in c) == 1 and next(x for x in c if x["address_id"] == kantor["address_id"])["is_default"]
        # edit non-default without is_default keeps state
        c = requests.put(f"{API}/me/addresses/{rumah['address_id']}", headers=h, json={**base, "label": "Rumah2"}).json()
        assert next(x for x in c if x["address_id"] == rumah["address_id"])["label"] == "Rumah2"
        assert requests.put(f"{API}/me/addresses/nope", headers=h, json={**base, "label": "x"}).status_code == 404
        d = requests.delete(f"{API}/me/addresses/{kantor['address_id']}", headers=h).json()
        assert len(d) == 1 and d[0]["is_default"] is True and d[0]["address_id"] == rumah["address_id"]
        assert requests.get(f"{API}/me/addresses", headers=h).json() == d
        assert "_id" not in d[0]


# ---------- activity, settings, notifications ----------
class TestActivityNotif:
    def test_activity(self, u1):
        r = requests.get(f"{API}/me/activity", headers=H(u1["token"]))
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d["logs"], list) and isinstance(d["recently_viewed"], list) and len(d["logs"]) > 0

    def test_settings_and_promo_optout(self, admin):
        on, off = _register("TEST_on"), _register("TEST_off")
        assert requests.get(f"{API}/me/settings", headers=H(off["token"])).json() == {"notif_order": True, "notif_promo": True, "notif_security": True}
        r = requests.put(f"{API}/me/settings", headers=H(off["token"]), json={"notif_order": True, "notif_promo": False, "notif_security": True})
        assert r.status_code == 200 and r.json()["notif_promo"] is False
        assert requests.get(f"{API}/me/settings", headers=H(off["token"])).json()["notif_promo"] is False
        code = f"TEST{uuid.uuid4().hex[:6].upper()}"
        r = requests.post(f"{API}/admin/vouchers", headers=admin, json={"code": code, "title": "TEST voucher", "mode": "percent", "value": 5})
        assert r.status_code == 200, r.text
        try:
            n_on = requests.get(f"{API}/notifications", headers=H(on["token"])).json()
            n_off = requests.get(f"{API}/notifications", headers=H(off["token"])).json()
            assert any(x["kind"] == "promo" and code in x["title"] for x in n_on)
            assert not any(x["kind"] == "promo" for x in n_off)
        finally:
            requests.delete(f"{API}/admin/vouchers/{code}", headers=admin)

    def test_notifications_read(self):
        t = _register("TEST_nt")
        h = H(t["token"])
        n = requests.get(f"{API}/notifications", headers=h).json()
        assert len(n) >= 1 and n[0]["kind"] == "security" and "_id" not in n[0]  # welcome notif
        cnt = requests.get(f"{API}/notifications/unread-count", headers=h).json()["count"]
        assert cnt == sum(1 for x in n if not x["read"]) and cnt >= 1
        requests.post(f"{API}/notifications/{n[0]['notif_id']}/read", headers=h)
        assert requests.get(f"{API}/notifications/unread-count", headers=h).json()["count"] == cnt - 1
        requests.post(f"{API}/notifications/read-all", headers=h)
        assert requests.get(f"{API}/notifications/unread-count", headers=h).json()["count"] == 0

    def test_order_notifications(self, admin):
        t = _register("TEST_ord")
        h = H(t["token"])
        p = requests.get(f"{API}/products", params={"limit": 20, "sort": "popular"}).json()
        pid = next(x["product_id"] for x in p if x.get("in_stock", True) and x.get("stock", 1) > 0)
        assert requests.post(f"{API}/cart/items", headers=h, json={"product_id": pid, "quantity": 1}).status_code == 200
        r = requests.post(f"{API}/checkout", headers=h, json={**SHIP, "payment_method": "cod"})
        assert r.status_code == 200, r.text
        oid = r.json()["order_id"]
        n = requests.get(f"{API}/notifications", headers=h).json()
        assert any(x["kind"] == "order" and oid in x["body"] for x in n)
        r = requests.put(f"{API}/admin/orders/{oid}/status", headers=admin, json={"status": "cancelled"})
        assert r.status_code == 200, r.text
        n = requests.get(f"{API}/notifications", headers=h).json()
        assert sum(1 for x in n if x["kind"] == "order" and oid in x["body"]) >= 2


# ---------- seller / stores ----------
class TestSeller:
    def test_old_products_pgs_official(self):
        p = requests.get(f"{API}/products", params={"limit": 5, "store": "pgs-official"}).json()
        assert len(p) == 5 and all(x["store_name"] == "PGS Official" for x in p)
        s = requests.get(f"{API}/stores/pgs-official")
        assert s.status_code == 200 and s.json()["product_count"] >= 6618 and "phone" not in s.json()

    def test_pgs_official_locked(self, admin):
        r = requests.put(f"{API}/admin/stores/pgs-official/status", headers=admin, json={"status": "suspended"})
        assert r.status_code == 400

    def test_store_lifecycle(self, admin):
        t = _register("TEST_sel")
        h = H(t["token"])
        assert requests.get(f"{API}/me/store", headers=h).json() is None
        name = f"TEST Toko {uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/stores", headers=h, json={"name": name, "city": "Sidoarjo", "phone": "081234567890"})
        assert r.status_code == 200, r.text
        st = r.json()
        assert st["status"] == "pending"
        sid = st["store_id"]
        assert requests.post(f"{API}/stores", headers=h, json={"name": name + "x", "city": "Sidoarjo", "phone": "081234567890"}).status_code == 400
        t2 = _register("TEST_sel2")
        assert requests.post(f"{API}/stores", headers=H(t2["token"]), json={"name": name.upper(), "city": "Sby", "phone": "081234567890"}).status_code == 400
        assert requests.get(f"{API}/seller/products", headers=h).status_code == 403
        assert requests.get(f"{API}/stores/{sid}").status_code == 404
        pend = requests.get(f"{API}/admin/stores", headers=admin, params={"status": "pending"}).json()
        assert any(x["store_id"] == sid and x["owner_email"] == t["email"] for x in pend)
        assert requests.get(f"{API}/admin/stores", headers=h).status_code == 403
        r = requests.put(f"{API}/admin/stores/{sid}/status", headers=admin, json={"status": "active", "note": ""})
        assert r.status_code == 200 and r.json()["status"] == "active"
        assert any("disetujui" in x["title"] for x in requests.get(f"{API}/notifications", headers=h).json())
        cat = requests.get(f"{API}/categories").json()[0]["category_id"]
        body = {"name": "TEST Seller Produk", "category": cat, "price": 15000, "original_price": 20000, "stock": 5,
                "images": ["https://images.unsplash.com/photo-1523381210434-271e8be1f52b?w=400"]}
        assert requests.post(f"{API}/seller/products", headers=h, json={**body, "category": "nope"}).status_code == 400
        r = requests.post(f"{API}/seller/products", headers=h, json=body)
        assert r.status_code == 200, r.text
        pr = r.json()
        pid = pr["product_id"]
        try:
            assert pr["store_name"] == name and pr["store_id"] == sid
            assert pr["price_tiers"] == [{"min_qty": 1, "price": 15000}], pr["price_tiers"]
            assert pr["discount"] == 25
            lst = requests.get(f"{API}/products", params={"store": sid}).json()
            assert [x["product_id"] for x in lst] == [pid]
            pub = requests.get(f"{API}/stores/{sid}").json()
            assert pub["product_count"] == 1 and "phone" not in pub
            r = requests.put(f"{API}/seller/products/{pid}", headers=h, json={**body, "price": 12000, "stock": 0})
            assert r.status_code == 200 and r.json()["price"] == 12000
            g = requests.get(f"{API}/products/{pid}").json()
            assert g["price"] == 12000 and g["in_stock"] is False
            # other seller cannot touch
            s1 = H(_login(SELLER))
            assert requests.put(f"{API}/seller/products/{pid}", headers=s1, json=body).status_code == 404
            assert requests.delete(f"{API}/seller/products/{pid}", headers=s1).status_code == 404
            png = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")
            up = requests.post(f"{API}/seller/upload", headers=h, files={"file": ("p.png", io.BytesIO(png), "image/png")})
            assert up.status_code == 200 and up.json()["url"].startswith("/api/files/")
            # suspend -> seller endpoints blocked
            requests.put(f"{API}/admin/stores/{sid}/status", headers=admin, json={"status": "suspended", "note": "TEST"})
            assert requests.get(f"{API}/seller/products", headers=h).status_code == 403
            leak = requests.get(f"{API}/products/{pid}")
            print("product of suspended store still public:", leak.status_code)
        finally:
            requests.put(f"{API}/admin/stores/{sid}/status", headers=admin, json={"status": "active"})
            d = requests.delete(f"{API}/seller/products/{pid}", headers=h)
            assert d.status_code == 200
            assert requests.get(f"{API}/products/{pid}").status_code == 404
            requests.put(f"{API}/admin/stores/{sid}/status", headers=admin, json={"status": "rejected", "note": "TEST cleanup"})
