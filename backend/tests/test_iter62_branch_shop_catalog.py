# Iteration 62: branch store page lists the whole branch catalog (?branch=) with branch price/stock, sold-out last, facets, product_count
import pytest
import requests
from test_iter60_suggest_shop_search import API, login

BR = ["pgs-official", "pgs-jombang", "pgs-jember"]
LIMIT = 200


def J():
    return login("jombang@pgs.id", "Jombang123!")


def fetch_all(branch, sort="popular", **params):
    out, skip = [], 0
    while True:
        r = requests.get(f"{API}/products", params={"branch": branch, "sort": sort, "skip": skip, "limit": LIMIT, **params}, timeout=60)
        assert r.status_code == 200, r.text
        page = r.json()
        out += page
        if len(page) < LIMIT:
            return out
        skip += LIMIT


def assert_stock_order(items):
    seen_out = False
    for i, p in enumerate(items):
        if not p["in_stock"]:
            seen_out = True
        else:
            assert not seen_out, f"in-stock item {p['name']} at {i} after an out-of-stock item"


# ---- list ordering / stock-last across pages ----
@pytest.mark.parametrize("branch", BR)
@pytest.mark.parametrize("sort", ["popular", "newest", "price_asc", "price_desc"])
def test_sold_out_last_all_pages(branch, sort):
    items = fetch_all(branch, sort)
    assert items, "empty branch catalog"
    assert_stock_order(items)
    ids = [p["product_id"] for p in items]
    assert len(ids) == len(set(ids)), "duplicates across pages"
    if sort.startswith("price"):
        ins = [p["price"] for p in items if p["in_stock"]]
        assert ins == sorted(ins, reverse=sort == "price_desc"), "in-stock group not sorted by branch price"


def test_small_pages_match_big_page():
    big = fetch_all("pgs-jombang", "popular")
    small, skip = [], 0
    while skip < min(len(big), 200):
        r = requests.get(f"{API}/products", params={"branch": "pgs-jombang", "sort": "popular", "skip": skip, "limit": 40}, timeout=60)
        small += r.json()
        skip += 40
    assert [p["product_id"] for p in small] == [p["product_id"] for p in big[:len(small)]]


@pytest.mark.parametrize("branch", ["pgs-jombang", "pgs-jember"])
def test_branch_has_out_of_stock(branch):
    items = fetch_all(branch)
    n_out = sum(1 for p in items if not p["in_stock"])
    print(branch, "total", len(items), "out", n_out)
    assert n_out > 0


# ---- count consistency ----
@pytest.mark.parametrize("branch", BR)
def test_product_count_matches(branch):
    page = requests.get(f"{API}/stores/{branch}/page", timeout=30).json()
    items = fetch_all(branch)
    fac = requests.get(f"{API}/products/facets", params={"branch": branch}, timeout=60).json()
    print(branch, page["product_count"], len(items), fac["total"])
    assert page["product_count"] == len(items) == fac["total"]


# ---- branch price differs ----
def test_jombang_price_differs_somewhere():
    sda = {p["product_id"]: p for p in fetch_all("pgs-official")}
    jom = fetch_all("pgs-jombang")
    diff = [(p["name"], sda[p["product_id"]]["price"], p["price"]) for p in jom if p["product_id"] in sda and sda[p["product_id"]]["price"] != p["price"]]
    print("diff sample", diff[:3], len(diff))
    assert diff


def test_detail_matches_branch_list_price():
    jom = fetch_all("pgs-jombang")[:5]
    for p in jom:
        d = requests.get(f"{API}/products/{p['product_id']}", headers={"X-Store-Id": "pgs-jombang"}, timeout=30).json()
        assert d["price"] == p["price"], (p["name"], d["price"], p["price"])


# ---- filters with branch ----
def test_in_stock_filter():
    items = fetch_all("pgs-jombang", in_stock="true")
    assert items and all(p["in_stock"] for p in items)
    all_items = fetch_all("pgs-jombang")
    assert len(items) == sum(1 for p in all_items if p["in_stock"])


def test_price_range_filter_uses_branch_price():
    items = fetch_all("pgs-jombang", min_price=10000, max_price=50000)
    assert items
    bad = [(p["name"], p["price"]) for p in items if not (10000 <= p["price"] <= 50000)]
    assert not bad, bad[:5]


def test_facets_brand_category_filter():
    fac = requests.get(f"{API}/products/facets", params={"branch": "pgs-jombang"}, timeout=60).json()
    assert fac["brands"] and fac["categories"] and fac["price_max"] >= fac["price_min"]
    b = fac["brands"][0]
    items = fetch_all("pgs-jombang", brand=b["name"])
    assert len(items) == b["count"] and all(p.get("brand") == b["name"] for p in items)
    c = fac["categories"][0]
    items = fetch_all("pgs-jombang", category=c["category_id"])
    assert len(items) == c["count"]
    assert_stock_order(items)


def test_q_search():
    first = fetch_all("pgs-jombang")[0]
    word = first["name"].split()[0]
    items = fetch_all("pgs-jombang", q=word)
    assert items and all(word.lower() in p["name"].lower() for p in items)
    assert_stock_order(items)


# ---- own product isolation ----
@pytest.fixture(scope="module")
def own_product():
    r = requests.post(f"{API}/seller/products", headers=J(), json={"name": "TEST_Iter62 Jombang Only", "description": "TEST", "price": 12345,
                                                                   "category": "dapur", "stock": 4, "images": ["https://example.com/a.jpg"]}, timeout=30)
    assert r.status_code in (200, 201), r.text
    pid = r.json()["product_id"]
    yield pid
    print("delete", requests.delete(f"{API}/seller/products/{pid}", headers=J(), timeout=30).status_code)


def test_own_product_visible_only_in_jombang(own_product):
    jom = fetch_all("pgs-jombang", q="TEST_Iter62")
    assert [p["product_id"] for p in jom] == [own_product]
    assert jom[0]["in_stock"] and jom[0]["price"] == 12345
    for b in ("pgs-jember", "pgs-official"):
        assert not fetch_all(b, q="TEST_Iter62"), f"leaked into {b}"
    fj = requests.get(f"{API}/products/facets", params={"branch": "pgs-jember", "q": "TEST_Iter62"}, timeout=30).json()
    assert fj["total"] == 0
    cnt = requests.get(f"{API}/stores/pgs-jombang/page", timeout=30).json()["product_count"]
    assert cnt == len(fetch_all("pgs-jombang"))


def test_own_products_endpoint_removed():
    r = requests.get(f"{API}/stores/pgs-jombang/own-products", timeout=30)
    assert r.status_code in (404, 405)
