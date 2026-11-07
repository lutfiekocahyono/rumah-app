# Pusat Grosir Sidoarjo API regression tests: catalog, auth, cart, wishlist, checkout, orders
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
DEMO = {"email": "demo@pgs.id", "password": "Demo1234!"}


@pytest.fixture(scope="module")
def s():
    x = requests.Session()
    x.headers.update({"Content-Type": "application/json"})
    return x


@pytest.fixture(scope="module")
def products(s):
    r = s.get(f"{BASE_URL}/api/products")
    assert r.status_code == 200
    return r.json()


@pytest.fixture(scope="module")
def guest():
    return {"X-Guest-Id": f"TEST_guest_{uuid.uuid4().hex[:8]}"}


@pytest.fixture(scope="module")
def new_user(s):
    email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    r = s.post(f"{BASE_URL}/api/auth/register", json={"email": email, "password": "Test1234!", "name": "TEST_User"})
    assert r.status_code == 200, r.text
    d = r.json()
    return {"email": email, "token": d["token"], "user": d["user"], "h": {"Authorization": f"Bearer {d['token']}"}}


# Catalog
class TestCatalog:
    def test_categories(self, s):
        r = s.get(f"{BASE_URL}/api/categories")
        assert r.status_code == 200
        d = r.json()
        assert len(d) == 8
        assert all({"category_id", "name", "icon", "image"} <= set(c) for c in d)

    def test_products_list(self, products):
        assert len(products) > 0
        assert "_id" not in products[0]

    def test_products_by_category(self, s, products):
        cat = products[0]["category"]
        r = s.get(f"{BASE_URL}/api/products", params={"category": cat})
        assert r.status_code == 200
        assert len(r.json()) > 0 and all(p["category"] == cat for p in r.json())

    def test_products_search(self, s, products):
        word = products[0]["name"].split()[0]
        r = s.get(f"{BASE_URL}/api/products", params={"q": word.lower()})
        assert r.status_code == 200
        assert any(p["product_id"] == products[0]["product_id"] for p in r.json())

    @pytest.mark.parametrize("sort,key,rev", [("price_asc", "price", False), ("price_desc", "price", True), ("rating", "rating", True), ("popular", "sold", True)])
    def test_products_sort(self, s, sort, key, rev):
        r = s.get(f"{BASE_URL}/api/products", params={"sort": sort})
        assert r.status_code == 200
        vals = [p[key] for p in r.json()]
        assert vals == sorted(vals, reverse=rev)

    def test_invalid_sort_422(self, s):
        assert s.get(f"{BASE_URL}/api/products", params={"sort": "bad"}).status_code == 422

    def test_search_special_chars_no_500(self, s):
        r = s.get(f"{BASE_URL}/api/products", params={"q": "("})
        assert r.status_code != 500, "Unescaped regex in q causes 500"

    def test_product_detail_and_404(self, s, products):
        pid = products[0]["product_id"]
        r = s.get(f"{BASE_URL}/api/products/{pid}")
        assert r.status_code == 200 and r.json()["product_id"] == pid
        assert s.get(f"{BASE_URL}/api/products/nope_xyz").status_code == 404


# Auth
class TestAuth:
    def test_login_demo(self, s):
        r = s.post(f"{BASE_URL}/api/auth/login", json=DEMO)
        assert r.status_code == 200
        d = r.json()
        assert d["user"]["email"] == DEMO["email"] and d["token"]
        me = s.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {d['token']}"})
        assert me.status_code == 200 and me.json()["email"] == DEMO["email"]

    def test_login_wrong_password(self, s):
        assert s.post(f"{BASE_URL}/api/auth/login", json={"email": DEMO["email"], "password": "wrong"}).status_code == 401

    def test_register_and_me(self, s, new_user):
        me = s.get(f"{BASE_URL}/api/auth/me", headers=new_user["h"])
        assert me.status_code == 200 and me.json()["email"] == new_user["email"]

    def test_register_duplicate(self, s, new_user):
        r = s.post(f"{BASE_URL}/api/auth/register", json={"email": new_user["email"], "password": "Test1234!", "name": "x"})
        assert r.status_code == 400

    def test_me_no_token(self, s):
        assert s.get(f"{BASE_URL}/api/auth/me").status_code == 401


# Cart (guest + user)
class TestCart:
    def test_no_identity_400(self, s):
        assert s.get(f"{BASE_URL}/api/cart").status_code == 400

    @pytest.mark.parametrize("who", ["guest", "user"])
    def test_cart_crud(self, s, products, guest, new_user, who):
        h = guest if who == "guest" else new_user["h"]
        p1, p2 = products[0], products[1]
        r = s.post(f"{BASE_URL}/api/cart/items", json={"product_id": p1["product_id"], "quantity": 2}, headers=h)
        assert r.status_code == 200
        r = s.post(f"{BASE_URL}/api/cart/items", json={"product_id": p2["product_id"], "quantity": 1}, headers=h)
        d = r.json()
        assert d["item_count"] == 3 and d["subtotal"] == p1["price"] * 2 + p2["price"]
        r = s.put(f"{BASE_URL}/api/cart/items/{p1['product_id']}", json={"product_id": p1["product_id"], "quantity": 5}, headers=h)
        assert r.status_code == 200
        g = s.get(f"{BASE_URL}/api/cart", headers=h).json()
        assert next(i for i in g["items"] if i["product_id"] == p1["product_id"])["quantity"] == 5
        r = s.delete(f"{BASE_URL}/api/cart/items/{p2['product_id']}", headers=h)
        assert all(i["product_id"] != p2["product_id"] for i in r.json()["items"])
        assert s.get(f"{BASE_URL}/api/cart", headers=h).json()["item_count"] == 5

    def test_add_nonexistent_product_404(self, s, guest):
        assert s.post(f"{BASE_URL}/api/cart/items", json={"product_id": "nope", "quantity": 1}, headers=guest).status_code == 404

    def test_guest_and_user_isolated(self, s, guest, new_user):
        other = s.get(f"{BASE_URL}/api/cart", headers={"X-Guest-Id": f"TEST_other_{uuid.uuid4().hex[:6]}"}).json()
        assert other["item_count"] == 0


# Wishlist
class TestWishlist:
    def test_wishlist_flow(self, s, products, guest):
        pid = products[2]["product_id"]
        r = s.post(f"{BASE_URL}/api/wishlist/{pid}", headers=guest)
        assert r.status_code == 200 and any(p["product_id"] == pid for p in r.json()["items"])
        g = s.get(f"{BASE_URL}/api/wishlist", headers=guest).json()
        assert any(p["product_id"] == pid for p in g["items"])
        r = s.delete(f"{BASE_URL}/api/wishlist/{pid}", headers=guest)
        assert all(p["product_id"] != pid for p in r.json()["items"])


# Checkout + orders
class TestCheckout:
    def test_checkout_user(self, s, products, new_user):
        h = new_user["h"]
        s.post(f"{BASE_URL}/api/cart/items", json={"product_id": products[3]["product_id"], "quantity": 1}, headers=h)
        cart = s.get(f"{BASE_URL}/api/cart", headers=h).json()
        assert cart["item_count"] > 0
        r = s.post(f"{BASE_URL}/api/checkout", json={"full_name": "TEST_Name", "phone": "0812", "address": "Jl Test", "city": "Sidoarjo"}, headers=h)
        assert r.status_code == 200, r.text
        o = r.json()
        assert o["status"] == "paid" and o["total"] == cart["subtotal"] + 25000
        assert s.get(f"{BASE_URL}/api/cart", headers=h).json()["item_count"] == 0
        orders = s.get(f"{BASE_URL}/api/orders", headers=h).json()
        assert any(x["order_id"] == o["order_id"] for x in orders)

    def test_checkout_empty_cart_400(self, s, new_user):
        r = s.post(f"{BASE_URL}/api/checkout", json={"full_name": "a", "phone": "1", "address": "a", "city": "a"}, headers=new_user["h"])
        assert r.status_code == 400

    def test_checkout_guest(self, s, products, guest):
        s.post(f"{BASE_URL}/api/cart/items", json={"product_id": products[4]["product_id"], "quantity": 1}, headers=guest)
        r = s.post(f"{BASE_URL}/api/checkout", json={"full_name": "TEST_G", "phone": "0812", "address": "Jl", "city": "Sby"}, headers=guest)
        assert r.status_code == 200 and r.json()["user_id"] is None


# Regression: PUT quantity 0 must remove item (frontend minus at qty 1)
def test_put_qty_zero_removes_item():
    h = {"X-Guest-Id": f"TEST_q0_{uuid.uuid4().hex[:6]}"}
    requests.post(f"{BASE_URL}/api/cart/items", json={"product_id": "p-sembako-01", "quantity": 1}, headers=h)
    r = requests.put(f"{BASE_URL}/api/cart/items/p-sembako-01", json={"product_id": "p-sembako-01", "quantity": 0}, headers=h)
    assert r.status_code == 200 and r.json()["item_count"] == 0
