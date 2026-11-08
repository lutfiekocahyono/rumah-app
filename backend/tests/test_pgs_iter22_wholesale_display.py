# Iter22: wholesale price display (price_min/max range + price_tiers) when admin pricing is configured.
# Since iter30 the former global settings (pengecer 3%, reseller 5%, 6->2%, 12->4%) live as per-product rupiah tiers (migrated).
import os
import pytest
import requests

API = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/") + "/api"


def _login(e, p):
    r = requests.post(f"{API}/auth/login", json={"email": e, "password": p})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}, r.json()["user"]


@pytest.fixture(scope="module")
def admin():
    return _login("admin@pgs.id", "Admin1234!")[0]


@pytest.fixture(scope="module")
def demo():
    return _login("demo@pgs.id", "Demo1234!")


@pytest.fixture(scope="module", autouse=True)
def require_pricing(admin):
    return None  # global /admin/pricing removed in iter30; values come from migrated per-product tier_prices


@pytest.fixture(scope="module")
def prod():
    ps = [p for p in requests.get(f"{API}/products", params={"limit": 20}).json() if p["store_id"] == "pgs-official" and p["price"] > 1000]
    assert ps
    return ps[0]


# Product list (guest): range + tiers
class TestListDisplay:
    def test_guest_list_has_range(self):
        ps = requests.get(f"{API}/products", params={"limit": 20}).json()
        off = [p for p in ps if p["store_id"] == "pgs-official"]
        assert off and all(p["price_max"] > p["price_min"] for p in off)
        p = off[0]
        assert p["price_max"] == p["price"]
        assert abs(p["price_min"] - round(p["price"] * 0.96)) <= 1  # guest = Pembeli Langsung range (12 pcs -4%)
        assert [t["min_qty"] for t in p["price_tiers"]] == [1, 6, 12]

    def test_home_feed_has_range(self):
        r = requests.get(f"{API}/home/sections")
        if r.status_code != 200:
            pytest.skip(f"/home returned {r.status_code}")
        txt = r.text
        assert "price_min" in txt and "price_max" in txt


# Product detail: guest vs demo (langsung -> reseller)
class TestDetail:
    def test_guest_detail_tiers(self, prod):
        d = requests.get(f"{API}/products/{prod['product_id']}").json()
        p = prod["price"]
        assert d["price_tiers"] == [{"min_qty": 1, "price": p}, {"min_qty": 6, "price": round(p * 0.98)}, {"min_qty": 12, "price": round(p * 0.96)}]
        assert len(d["price_matrix"]) == 3

    def test_demo_langsung_detail(self, demo, prod):
        d = requests.get(f"{API}/products/{prod['product_id']}", headers=demo[0]).json()
        assert d["my_price"] == prod["price"] and len(d["price_tiers"]) == 3

    def test_demo_reseller_detail(self, admin, demo, prod):
        h, u = demo
        try:
            assert requests.put(f"{API}/admin/customers/{u['user_id']}", headers=admin, json={"customer_type": "reseller"}).status_code == 200
            d = requests.get(f"{API}/products/{prod['product_id']}", headers=h).json()
            base = round(prod["price"] * 0.95)
            assert abs(d["my_price"] - base) <= 1
            assert abs(d["price_tiers"][2]["price"] - round(base * 0.96)) <= 1
        finally:
            requests.put(f"{API}/admin/customers/{u['user_id']}", headers=admin, json={"customer_type": "langsung"})
        assert requests.get(f"{API}/auth/me", headers=h).json()["customer_type"] == "langsung"


# Marketplace seller product: flat price (no wholesale tiers)
class TestMarketplaceFlat:
    def test_seller_product_flat(self):
        h, _ = _login("acct1@pgs.id", "Test1234!")
        cat = requests.get(f"{API}/categories").json()[0]["category_id"]
        r = requests.post(f"{API}/seller/products", headers=h, json={"name": "TEST_iter22 flat", "category": cat, "price": 50000,
                                                                    "stock": 10, "images": ["https://via.placeholder.com/300"]})
        assert r.status_code == 200, r.text
        pid = r.json()["product_id"]
        try:
            d = requests.get(f"{API}/products/{pid}").json()
            assert d["price_tiers"] == [{"min_qty": 1, "price": 50000}]
            assert d["price_min"] == d["price_max"] == 50000
        finally:
            assert requests.delete(f"{API}/seller/products/{pid}", headers=h).status_code == 200
        assert requests.get(f"{API}/products/{pid}").status_code == 404
