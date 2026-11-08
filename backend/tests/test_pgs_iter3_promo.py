# PGS iteration 3: homepage promos — banners, home settings, flash sale, vouchers, checkout w/ voucher, recommendations, uploads
import os
import uuid
import io
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN = {"email": "admin@pgs.id", "password": "Admin1234!"}
DEMO = {"email": "demo@pgs.id", "password": "Demo1234!"}
SHIP = {"full_name": "TEST_Buyer", "phone": "081234567890", "address": "Jl. Test No 1", "city": "Sidoarjo"}


def _login(c):
    r = requests.post(f"{API}/auth/login", json=c)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _guest():
    return {"X-Guest-Id": f"TEST_guest_{uuid.uuid4().hex[:8]}"}


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def demo():
    return _login(DEMO)


@pytest.fixture(scope="module")
def flash_orig(admin):
    """Snapshot flash sale + home settings and restore after module."""
    f = requests.get(f"{API}/admin/flash-sale", headers=admin).json()
    h = requests.get(f"{API}/home-settings").json()
    yield f
    requests.put(f"{API}/admin/flash-sale", headers=admin, json={
        "title": f["title"], "active": f["active"], "ends_at": f["ends_at"],
        "items": [{"product_id": i["product_id"], "flash_price": i["flash_price"]} for i in f["items"]]})
    requests.put(f"{API}/admin/home-settings", headers=admin,
                 json={"free_shipping": h["free_shipping"], "recommend_mode": h["recommend_mode"]})


# --- public homepage endpoints ---
class TestPublicHome:
    def test_banners(self):
        r = requests.get(f"{API}/banners")
        assert r.status_code == 200
        bs = r.json()
        assert len(bs) >= 3 and all(b["active"] and b["image"] and "banner_id" in b for b in bs)
        assert any(b["link_type"] == "search" for b in bs)

    def test_home_settings(self):
        d = requests.get(f"{API}/home-settings").json()
        assert d["recommend_mode"] in ("personal", "random")
        assert {"enabled", "title", "subtitle", "min_purchase"} <= set(d["free_shipping"])
        assert "_id" not in d

    def test_flash_sale(self):
        d = requests.get(f"{API}/flash-sale").json()
        assert d["active"] is True and d["ends_at"] and len(d["items"]) >= 1
        for p in d["items"]:
            assert p["flash_price"] and p["my_price"] <= p["flash_price"]
            assert p["flash_ends_at"]

    def test_vouchers_and_claim(self):
        g = _guest()
        vs = requests.get(f"{API}/vouchers", headers=g).json()
        codes = {v["code"]: v for v in vs}
        assert "PGSHEMAT" in codes and "PGS10RB" in codes
        assert codes["PGSHEMAT"]["claimed"] is False
        r = requests.post(f"{API}/vouchers/pgshemat/claim", headers=g)
        assert r.status_code == 200 and r.json()["claimed"] is True
        vs2 = {v["code"]: v for v in requests.get(f"{API}/vouchers", headers=g).json()}
        assert vs2["PGSHEMAT"]["claimed"] is True and vs2["PGS10RB"]["claimed"] is False
        mine = requests.get(f"{API}/vouchers/mine", headers=g).json()
        assert [v["code"] for v in mine] == ["PGSHEMAT"]
        assert requests.post(f"{API}/vouchers/NOPE999/claim", headers=g).status_code == 404

    def test_claim_with_token(self, demo):
        r = requests.post(f"{API}/vouchers/PGS10RB/claim", headers=demo)
        assert r.status_code == 200
        vs = {v["code"]: v for v in requests.get(f"{API}/vouchers", headers=demo).json()}
        assert vs["PGS10RB"]["claimed"] is True


# --- flash price applies in product & cart ---
class TestFlashPricing:
    def test_flash_price_product_and_cart_then_deactivate(self, admin, flash_orig):
        items = requests.get(f"{API}/flash-sale").json()["items"]
        p = items[0]
        d = requests.get(f"{API}/products/{p['product_id']}").json()
        assert d["flash_price"] == p["flash_price"]
        assert d["my_price"] == min(d["price_tiers"][0]["price"], d["flash_price"])
        g = _guest()
        c = requests.post(f"{API}/cart/items", headers=g, json={"product_id": p["product_id"], "quantity": 1}).json()
        it = c["items"][0]
        assert it["price"] == min(d["price_tiers"][0]["price"], d["flash_price"])
        # deactivate -> normal price
        r = requests.put(f"{API}/admin/flash-sale", headers=admin, json={
            "title": flash_orig["title"], "active": False, "ends_at": flash_orig["ends_at"],
            "items": [{"product_id": i["product_id"], "flash_price": i["flash_price"]} for i in flash_orig["items"]]})
        assert r.status_code == 200 and r.json()["active"] is False
        assert requests.get(f"{API}/flash-sale").json()["active"] is False
        d2 = requests.get(f"{API}/products/{p['product_id']}").json()
        assert d2["flash_price"] is None and d2["my_price"] == d2["price_tiers"][0]["price"]
        c2 = requests.get(f"{API}/cart", headers=g).json()
        assert c2["items"][0]["price"] == d2["price_tiers"][0]["price"]
        # restore
        r = requests.put(f"{API}/admin/flash-sale", headers=admin, json={
            "title": flash_orig["title"], "active": True, "ends_at": flash_orig["ends_at"],
            "items": [{"product_id": i["product_id"], "flash_price": i["flash_price"]} for i in flash_orig["items"]]})
        assert r.json()["active"] is True
        assert requests.get(f"{API}/flash-sale").json()["active"] is True
        requests.delete(f"{API}/cart", headers=g)


# --- admin vouchers CRUD + apply + checkout ---
class TestVouchers:
    code = f"TESTV{uuid.uuid4().hex[:6].upper()}"

    def test_non_admin_forbidden(self, demo):
        for path in ("admin/vouchers", "admin/banners", "admin/flash-sale"):
            assert requests.get(f"{API}/{path}", headers=demo).status_code == 403
        assert requests.put(f"{API}/admin/home-settings", headers=demo, json={
            "free_shipping": {"enabled": True}, "recommend_mode": "random"}).status_code == 403

    def test_create_validation(self, admin):
        bad = {"code": "TESTPCT1", "title": "x", "mode": "percent", "value": 150}
        assert requests.post(f"{API}/admin/vouchers", headers=admin, json=bad).status_code == 400
        r = requests.post(f"{API}/admin/vouchers", headers=admin, json={
            "code": self.code.lower(), "title": "TEST_Voucher", "mode": "rupiah", "value": 5000,
            "min_purchase": 1000, "quota": 1, "show_on_home": False})
        assert r.status_code == 200, r.text
        assert r.json()["code"] == self.code and r.json()["used"] == 0
        dup = requests.post(f"{API}/admin/vouchers", headers=admin, json={"code": self.code, "title": "dup", "value": 1})
        assert dup.status_code == 400
        assert any(v["code"] == self.code for v in requests.get(f"{API}/admin/vouchers", headers=admin).json())

    def test_apply_and_checkout(self, admin):
        g = _guest()
        prods = [p for p in requests.get(f"{API}/products", params={"limit": 50}).json()
                 if p.get("in_stock") and p["stock"] >= 5 and p["price"] > 2000]
        requests.post(f"{API}/cart/items", headers=g, json={"product_id": prods[0]["product_id"], "quantity": 1})
        sub = requests.get(f"{API}/cart", headers=g).json()["subtotal"]
        # min purchase check
        r = requests.post(f"{API}/vouchers/apply", headers=g, json={"code": "PGSHEMAT"})
        if sub < 200000:
            assert r.status_code == 400 and "Minimal" in r.json()["detail"]
        r = requests.post(f"{API}/vouchers/apply", headers=g, json={"code": self.code.lower()})
        assert r.status_code == 200 and r.json()["discount"] == min(5000, sub)
        assert requests.post(f"{API}/vouchers/apply", headers=g, json={"code": "INVALIDX"}).status_code == 400
        # invalid at checkout
        assert requests.post(f"{API}/checkout", headers=g, json={**SHIP, "payment_method": "cod", "voucher_code": "INVALIDX"}).status_code == 400
        r = requests.post(f"{API}/checkout", headers=g, json={**SHIP, "payment_method": "cod", "voucher_code": self.code})
        assert r.status_code == 200, r.text
        o = r.json()
        assert o["discount"] == min(5000, sub) and o["voucher_code"] == self.code
        assert o["total"] == o["subtotal"] - o["discount"] + o["shipping_cost"]  # default courier is pickup now
        v = [v for v in requests.get(f"{API}/admin/vouchers", headers=admin).json() if v["code"] == self.code][0]
        assert v["used"] == 1
        # quota exhausted
        requests.post(f"{API}/cart/items", headers=g, json={"product_id": prods[0]["product_id"], "quantity": 1})
        r = requests.post(f"{API}/vouchers/apply", headers=g, json={"code": self.code})
        assert r.status_code == 400 and "Kuota" in r.json()["detail"]
        requests.delete(f"{API}/cart", headers=g)

    def test_inactive_and_expired(self, admin):
        g = _guest()
        body = {"code": self.code, "title": "TEST_Voucher", "mode": "rupiah", "value": 5000, "quota": 0, "active": False}
        r = requests.put(f"{API}/admin/vouchers/{self.code}", headers=admin, json=body)
        assert r.status_code == 200 and r.json()["active"] is False and r.json()["used"] == 1
        prods = requests.get(f"{API}/products", params={"limit": 5}).json()
        requests.post(f"{API}/cart/items", headers=g, json={"product_id": prods[0]["product_id"], "quantity": 1})
        assert requests.post(f"{API}/vouchers/apply", headers=g, json={"code": self.code}).status_code == 400
        r = requests.put(f"{API}/admin/vouchers/{self.code}", headers=admin,
                         json={**body, "active": True, "ends_at": "2020-01-01T00:00:00Z"})
        assert r.status_code == 200
        r = requests.post(f"{API}/vouchers/apply", headers=g, json={"code": self.code})
        assert r.status_code == 400 and "berakhir" in r.json()["detail"]
        assert requests.put(f"{API}/admin/vouchers/{self.code}", headers=admin, json={**body, "code": "OTHERCODE"}).status_code == 400
        requests.delete(f"{API}/cart", headers=g)

    def test_delete(self, admin):
        assert requests.delete(f"{API}/admin/vouchers/{self.code}", headers=admin).status_code == 200
        assert not any(v["code"] == self.code for v in requests.get(f"{API}/admin/vouchers", headers=admin).json())


# --- admin banners + upload ---
class TestBannersUpload:
    def test_upload_and_banner_crud(self, admin, demo):
        png = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
               b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7V\xbd\xfa\x00\x00\x00\x00IEND\xaeB`\x82")
        assert requests.post(f"{API}/admin/upload", headers=demo, files={"file": ("a.png", io.BytesIO(png), "image/png")}).status_code == 403
        assert requests.post(f"{API}/admin/upload", headers=admin, files={"file": ("a.txt", io.BytesIO(b"hi"), "text/plain")}).status_code == 400
        r = requests.post(f"{API}/admin/upload", headers=admin, files={"file": ("TEST_a.png", io.BytesIO(png), "image/png")})
        assert r.status_code == 200, r.text
        url = r.json()["url"]
        assert url.startswith("/api/files/")
        f = requests.get(f"{BASE_URL}{url}")
        assert f.status_code == 200 and f.content == png and f.headers["content-type"].startswith("image/png")
        assert requests.get(f"{API}/files/nope/x.png").status_code == 404
        b = requests.post(f"{API}/admin/banners", headers=admin, json={
            "title": "TEST_Banner", "image": url, "link_type": "search", "link_value": "rak", "order": 99})
        assert b.status_code == 200
        bid = b.json()["banner_id"]
        assert any(x["banner_id"] == bid for x in requests.get(f"{API}/banners").json())
        u = requests.put(f"{API}/admin/banners/{bid}", headers=admin, json={
            "title": "TEST_Banner2", "image": url, "link_type": "category", "link_value": "x", "active": False})
        assert u.status_code == 200 and u.json()["title"] == "TEST_Banner2"
        assert not any(x["banner_id"] == bid for x in requests.get(f"{API}/banners").json())
        assert requests.put(f"{API}/admin/banners/{bid}", headers=admin, json={
            "title": "T", "image": url, "link_type": "bad"}).status_code == 422
        assert requests.delete(f"{API}/admin/banners/{bid}", headers=admin).status_code == 200
        assert not any(x["banner_id"] == bid for x in requests.get(f"{API}/admin/banners", headers=admin).json())


# --- home settings + recommendations ---
class TestRecommendations:
    def test_home_settings_update(self, admin, flash_orig):
        r = requests.put(f"{API}/admin/home-settings", headers=admin, json={
            "free_shipping": {"enabled": True, "title": "TEST_Ongkir", "subtitle": "TEST sub", "min_purchase": 123000},
            "recommend_mode": "random"})
        assert r.status_code == 200
        d = requests.get(f"{API}/home-settings").json()
        assert d["free_shipping"]["title"] == "TEST_Ongkir" and d["recommend_mode"] == "random"
        assert requests.put(f"{API}/admin/home-settings", headers=admin, json={
            "free_shipping": {}, "recommend_mode": "bogus"}).status_code == 422
        rec = requests.get(f"{API}/recommendations", params={"limit": 10}).json()
        assert len(rec) == 10

    def test_personal_mode(self, admin, flash_orig):
        requests.put(f"{API}/admin/home-settings", headers=admin, json={
            "free_shipping": {"enabled": True}, "recommend_mode": "personal"})
        g = _guest()
        prods = requests.get(f"{API}/products", params={"limit": 40}).json()
        target = prods[-1]
        cat = target["category"] if "category" in target else None
        for _ in range(3):
            assert requests.post(f"{API}/activity/view/{target['product_id']}", headers=g).status_code == 200
        rec = requests.get(f"{API}/recommendations", headers=g, params={"limit": 10}).json()
        assert len(rec) == 10
        print("target cat", cat, "rec cats", [p.get("category") for p in rec])
        if cat:
            assert any(p.get("category") == cat for p in rec), "personal recs don't include viewed category"

    def test_personal_pagination_no_dupes(self, admin, flash_orig):
        g = _guest()
        prods = requests.get(f"{API}/products", params={"limit": 40}).json()
        requests.post(f"{API}/activity/view/{prods[-1]['product_id']}", headers=g)
        p1 = requests.get(f"{API}/recommendations", headers=g, params={"limit": 20, "skip": 0}).json()
        p2 = requests.get(f"{API}/recommendations", headers=g, params={"limit": 20, "skip": 20}).json()
        ids1, ids2 = {p["product_id"] for p in p1}, {p["product_id"] for p in p2}
        dup = ids1 & ids2
        print("page dupes", len(dup))
        assert not dup, f"{len(dup)} duplicate products between page 1 and 2"
