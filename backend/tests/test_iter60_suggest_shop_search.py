# Iteration 60: search suggestions (/products/suggest) + in-store search/category filter (/stores/{id}/page categories, /own-products?q=&category=)
import os
import pytest
import requests


def _base():
    u = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL")
    if not u:
        for line in open("/app/frontend/.env"):
            if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
                u = line.split("=", 1)[1].strip().strip('"')
    return u.rstrip("/")


API = f"{_base()}/api"
TOK: dict = {}
ST: dict = {"created": []}
TAG = "Zqxtest"  # unique prefix so suggestions are deterministic


def login(email, pw):
    if email not in TOK:
        r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=30)
        assert r.status_code == 200, r.text
        TOK[email] = r.json()["token"]
    return {"Authorization": f"Bearer {TOK[email]}", "Content-Type": "application/json"}


def J():
    return login("jombang@pgs.id", "Jombang123!")


def sugg(q, store=None):
    h = {"X-Store-Id": store} if store else {}
    r = requests.get(f"{API}/products/suggest", params={"q": q}, headers=h, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module", autouse=True)
def products():
    base = {"description": "TEST produk khusus Jombang", "price": 15000, "images": ["https://example.com/a.jpg"]}
    for name, cat, stock in ((f"{TAG} Kesehatan Habis", "kesehatan", 0), (f"{TAG} Kesehatan Ada", "kesehatan", 7),
                             (f"TEST_Dapur {TAG} Panci", "dapur", 3)):
        r = requests.post(f"{API}/seller/products", headers=J(), json={**base, "name": name, "category": cat, "stock": stock}, timeout=30)
        assert r.status_code == 200, r.text
        ST["created"].append(r.json()["product_id"])
    yield
    for pid in ST["created"]:
        d = requests.delete(f"{API}/seller/products/{pid}", headers=J(), timeout=30)
        print("cleanup", pid, d.status_code)


# ---- suggest ----
def test_suggest_short_query_empty():
    for q in ("", "k", " k "):
        assert sugg(q, "pgs-jombang") == {"products": [], "brands": [], "categories": []}


def test_suggest_shape_and_limits():
    d = sugg("kes", "pgs-jombang")
    assert set(d) == {"products", "brands", "categories"}
    assert len(d["products"]) <= 6 and len(d["brands"]) <= 4 and len(d["categories"]) <= 3
    for p in d["products"]:
        assert set(p) <= {"product_id", "name", "image"} and "product_id" in p and "name" in p
        assert "kes" in p["name"].lower()
    assert all(isinstance(b, str) for b in d["brands"])
    assert any(c["category_id"] == "kesehatan" for c in d["categories"])


def test_suggest_prefix_first():
    d = sugg(TAG.lower(), "pgs-jombang")
    names = [p["name"] for p in d["products"]]
    ids = [p["product_id"] for p in d["products"]]
    assert ST["created"][0] in ids and ST["created"][1] in ids and ST["created"][2] in ids, names
    # prefix matches (Zqxtest ...) before contains match (TEST_Dapur Zqxtest ...)
    assert ids.index(ST["created"][2]) > max(ids.index(ST["created"][0]), ids.index(ST["created"][1])), names


def test_suggest_branch_isolation():
    for store in ("pgs-jember", "pgs-official", None):
        ids = [p["product_id"] for p in sugg(TAG, store)["products"]]
        assert not set(ids) & set(ST["created"]), f"jombang-only product leaked to {store}: {ids}"


def test_suggest_brand():
    d = sugg("kes", "pgs-jombang")
    if not d["brands"]:
        pytest.skip("no brand containing 'kes'")
    b = d["brands"][0]
    assert "kes" in b.lower()


def test_suggest_regex_safe():
    d = sugg("(.*", "pgs-jombang")
    assert isinstance(d["products"], list)


# ---- store page categories / own-products filters ----
def test_page_categories():
    page = requests.get(f"{API}/stores/pgs-jombang/page", timeout=30).json()
    cats = {c["category_id"]: c for c in page["categories"]}
    assert cats["kesehatan"]["count"] >= 2 and cats["dapur"]["count"] >= 1
    assert cats["kesehatan"]["name"] == "Kesehatan"
    assert page["product_count"] >= 3
    jem = requests.get(f"{API}/stores/pgs-jember/page", timeout=30).json()
    assert "categories" in jem and all(c["count"] > 0 for c in jem["categories"])


def test_own_products_q_filter():
    r = requests.get(f"{API}/stores/pgs-jombang/own-products", params={"q": "panci"}, timeout=30)
    ids = [p["product_id"] for p in r.json()]
    assert ids == [ST["created"][2]], ids


def test_own_products_category_filter_and_stock_order():
    r = requests.get(f"{API}/stores/pgs-jombang/own-products", params={"category": "kesehatan"}, timeout=30)
    ids = [p["product_id"] for p in r.json()]
    assert ST["created"][2] not in ids
    assert ids.index(ST["created"][1]) < ids.index(ST["created"][0]), "in-stock first"


def test_own_products_q_and_category_combined_and_nomatch():
    r = requests.get(f"{API}/stores/pgs-jombang/own-products", params={"q": TAG, "category": "dapur"}, timeout=30)
    assert [p["product_id"] for p in r.json()] == [ST["created"][2]]
    r = requests.get(f"{API}/stores/pgs-jombang/own-products", params={"q": "nomatchxyz123"}, timeout=30)
    assert r.status_code == 200 and r.json() == []


def test_own_products_other_branch_not_listed():
    r = requests.get(f"{API}/stores/pgs-jember/own-products", params={"q": TAG}, timeout=30)
    assert r.status_code == 200 and r.json() == []
