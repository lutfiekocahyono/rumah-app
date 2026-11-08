# PGS iteration 2: imported catalog, store info, tiered pricing, admin panel, checkout payments, auth 401
import os
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
    d = r.json()
    return {"Authorization": f"Bearer {d['token']}"}, d["user"]


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN)[0]


@pytest.fixture(scope="module")
def demo():
    return _login(DEMO)


@pytest.fixture(scope="module")
def prods():
    r = requests.get(f"{API}/products", params={"limit": 50})
    assert r.status_code == 200
    ps = [p for p in r.json() if p.get("in_stock") and p["stock"] >= 20 and p["price"] > 1000]
    assert len(ps) >= 2
    return ps


@pytest.fixture(scope="module", autouse=True)
def reset_after(admin, demo, prods):
    # snapshot the shop's real pricing and restore it afterwards (never wipe it to zero)
    saved_tiers = {p["product_id"]: requests.get(f"{API}/admin/products/{p['product_id']}/tiers", headers=admin).json().get("tier_prices") for p in prods[:2]}
    yield
    h, u = demo
    requests.put(f"{API}/admin/customers/{u['user_id']}", headers=admin, json={"customer_type": "langsung"})
    for p in prods[:2]:
        requests.put(f"{API}/admin/products/{p['product_id']}/tiers", headers=admin,
                     json={"tier_prices": saved_tiers.get(p["product_id"]) or {"langsung": [], "pengecer": [], "reseller": []}})
    requests.delete(f"{API}/cart", headers=h)


# Catalog (imported data)
class TestCatalog:
    def test_top_categories(self):
        r = requests.get(f"{API}/categories")
        assert r.status_code == 200
        cats = r.json()
        print("top cats", len(cats), [c["category_id"] for c in cats])
        assert len(cats) == 14

    def test_sub_categories_dapur(self):
        r = requests.get(f"{API}/categories", params={"parent": "dapur"})
        assert r.status_code == 200 and len(r.json()) > 0
        assert all(c["parent"] == "dapur" for c in r.json())

    def test_pagination_dapur(self):
        a = requests.get(f"{API}/products", params={"category": "dapur"}).json()
        b = requests.get(f"{API}/products", params={"category": "dapur", "skip": 40}).json()
        assert len(a) == 40 and len(b) > 0
        assert not set(p["product_id"] for p in a) & set(p["product_id"] for p in b)

    def test_search_and_sort(self):
        r = requests.get(f"{API}/products", params={"q": "panci", "sort": "price_asc"})
        assert r.status_code == 200
        d = r.json()
        assert len(d) > 0 and all("panci" in p["name"].lower() for p in d)
        prices = [p["price"] for p in d]
        assert prices == sorted(prices)

    def test_total_imported_products(self, admin):
        r = requests.get(f"{API}/admin/stats", headers=admin)
        assert r.status_code == 200
        print("stats", r.json())
        assert r.json()["products"] >= 6000

    def test_store(self):
        r = requests.get(f"{API}/store")
        assert r.status_code == 200
        d = r.json()
        print("store", d)
        assert d.get("name") and d.get("phone") and d.get("hours")
        assert len(d.get("branches", [])) == 3


# Auth / admin guard
class TestAuthGuards:
    def test_invalid_token_cart_401(self):
        r = requests.get(f"{API}/cart", headers={"Authorization": "Bearer invalid.token.x"})
        assert r.status_code == 401

    @pytest.mark.parametrize("path", ["/admin/stats", "/admin/orders", "/admin/customers"])
    def test_non_admin_403(self, demo, path):
        r = requests.get(f"{API}{path}", headers=demo[0])
        assert r.status_code == 403

    def test_no_token_admin_401(self):
        assert requests.get(f"{API}/admin/stats").status_code in (401, 403)


# Tiered pricing - OBSOLETE since iter30: global /admin/pricing removed (per-product tiers, see test_pgs_iter30_product_wholesale.py)
@pytest.mark.skip(reason="global /admin/pricing removed in iter30")
class TestPricing:
    def test_global_pricing_reseller(self, admin, demo, prods):
        h, u = demo
        r = requests.put(f"{API}/admin/pricing", headers=admin, json={
            "type_discounts": {"langsung": 0, "pengecer": 3, "reseller": 5},
            "qty_tiers": [{"min_qty": 6, "mode": "percent", "value": 2}, {"min_qty": 12, "mode": "percent", "value": 4}]})
        assert r.status_code == 200, r.text
        assert requests.get(f"{API}/admin/pricing", headers=admin).json()["type_discounts"]["reseller"] == 5
        r = requests.put(f"{API}/admin/customers/{u['user_id']}", headers=admin, json={"customer_type": "reseller"})
        assert r.status_code == 200 and r.json()["customer_type"] == "reseller"
        p = prods[0]
        d = requests.get(f"{API}/products/{p['product_id']}", headers=h).json()
        base = round(p["price"] * 0.95)
        assert abs(d["my_price"] - base) <= 1
        assert [t["min_qty"] for t in d["price_tiers"]] == [1, 6, 12]
        assert abs(d["price_tiers"][2]["price"] - round(base * 0.96)) <= 1
        # guest sees langsung price
        g = requests.get(f"{API}/products/{p['product_id']}").json()
        assert g["my_price"] == p["price"]
        # cart qty 12
        requests.delete(f"{API}/cart", headers=h)
        c = requests.post(f"{API}/cart/items", headers=h, json={"product_id": p["product_id"], "quantity": 12}).json()
        it = c["items"][0]
        assert c["customer_type"] == "reseller"
        assert abs(it["price"] - round(base * 0.96)) <= 1
        assert it["base_price"] == p["price"]
        assert c["subtotal"] == it["price"] * 12
        assert c["savings"] == (p["price"] - it["price"]) * 12
        assert it["next_tier"] is None
        c = requests.put(f"{API}/cart/items/{p['product_id']}", headers=h, json={"quantity": 7}).json()
        assert c["items"][0]["next_tier"]["min_qty"] == 12

    def test_manual_tiers_override_reseller_only(self, admin, demo, prods):
        h, u = demo
        p = prods[1]
        X, Y = max(1, p["price"] - 500), max(1, p["price"] - 900)
        r = requests.put(f"{API}/admin/products/{p['product_id']}/tiers", headers=admin,
                         json={"tier_prices": {"reseller": [{"min_qty": 1, "price": X}, {"min_qty": 10, "price": Y}]}})
        assert r.status_code == 200, r.text
        g = requests.get(f"{API}/admin/products/{p['product_id']}/tiers", headers=admin).json()
        assert len(g["tier_prices"]["reseller"]) == 2 and g["tier_prices"]["langsung"] == []
        d = requests.get(f"{API}/products/{p['product_id']}", headers=h).json()
        assert d["my_price"] == X
        assert d["price_tiers"] == [{"min_qty": 1, "price": X}, {"min_qty": 10, "price": Y}]
        # guest (langsung) still uses global (no qty tiers 6/12 discount for langsung base 0%)
        gd = requests.get(f"{API}/products/{p['product_id']}").json()
        assert gd["my_price"] == p["price"] and [t["min_qty"] for t in gd["price_tiers"]] == [1, 6, 12]

    def test_admin_customers_list(self, admin):
        r = requests.get(f"{API}/admin/customers", params={"q": "demo"}, headers=admin)
        assert r.status_code == 200 and any(c["email"] == "demo@pgs.id" for c in r.json())
        assert all("password_hash" not in c for c in r.json())

    def test_invalid_customer_type_422(self, admin, demo):
        r = requests.put(f"{API}/admin/customers/{demo[1]['user_id']}", headers=admin, json={"customer_type": "vip"})
        assert r.status_code == 422


# Checkout & admin orders
class TestCheckoutOrders:
    def _add(self, h, pid):
        requests.delete(f"{API}/cart", headers=h)
        assert requests.post(f"{API}/cart/items", headers=h, json={"product_id": pid, "quantity": 1}).status_code == 200

    def test_validation(self, demo, prods):
        self._add(demo[0], prods[0]["product_id"])
        r = requests.post(f"{API}/checkout", headers=demo[0], json={**SHIP, "full_name": "", "payment_method": "cod"})
        assert r.status_code == 422

    @pytest.mark.parametrize("m", ["midtrans", "xendit"])
    def test_gateway_503(self, demo, prods, m):
        self._add(demo[0], prods[0]["product_id"])
        r = requests.post(f"{API}/checkout", headers=demo[0], json={**SHIP, "payment_method": m})
        print(m, r.status_code, r.text)
        assert r.status_code == 503 and "belum dikonfigurasi" in r.text
        # cart must not be cleared on failure
        assert requests.get(f"{API}/cart", headers=demo[0]).json()["item_count"] == 1

    def test_cod_and_admin_flow(self, admin, demo, prods):
        h = demo[0]
        self._add(h, prods[0]["product_id"])
        r = requests.post(f"{API}/checkout", headers=h, json={**SHIP, "payment_method": "cod"})
        assert r.status_code == 200, r.text
        o = r.json()
        assert o["status"] == "cod" and o["total"] == o["subtotal"] + 25000
        oid = o["order_id"]
        assert requests.get(f"{API}/cart", headers=h).json()["item_count"] == 0
        assert requests.get(f"{API}/orders/{oid}", headers=h).json()["order_id"] == oid
        rf = requests.post(f"{API}/orders/{oid}/refresh", headers=h)
        assert rf.status_code == 200 and rf.json()["status"] == "cod"
        lst = requests.get(f"{API}/admin/orders", params={"status": "cod"}, headers=admin).json()
        assert any(x["order_id"] == oid for x in lst) and all(x["status"] == "cod" for x in lst)
        st = requests.get(f"{API}/admin/stats", headers=admin).json()
        assert st["orders_today"] >= 1 and st["need_action"] >= 1
        u = requests.put(f"{API}/admin/orders/{oid}/status", headers=admin, json={"status": "shipped"})
        assert u.status_code == 200 and u.json()["status"] == "shipped"
        assert requests.get(f"{API}/orders/{oid}", headers=h).json()["status"] == "shipped"
        bad = requests.put(f"{API}/admin/orders/{oid}/status", headers=admin, json={"status": "paid"})
        assert bad.status_code == 422
        # other user can't see order
        assert requests.get(f"{API}/orders/{oid}", headers={"X-Guest-Id": "TEST_other"}).status_code == 404
        requests.put(f"{API}/admin/orders/{oid}/status", headers=admin, json={"status": "cancelled"})
