# Search filters: GET /api/products (brand/price/sort/category/in_stock) and /api/products/facets
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"


def get(path, headers=None, **params):
    r = requests.get(f"{API}{path}", params=params, headers=headers or {}, timeout=60)
    return r


def all_products(**params):
    out, skip = [], 0
    while True:
        r = get("/products", limit=200, skip=skip, **params)
        assert r.status_code == 200, r.text
        page = r.json()
        out += page
        if len(page) < 200:
            return out
        skip += 200


# --- brand filter
class TestBrand:
    def test_single_brand(self):
        r = get("/products", brand="Advance", limit=200)
        assert r.status_code == 200
        d = r.json()
        assert d and all(p.get("brand") == "Advance" for p in d)

    def test_multi_brand(self):
        d = all_products(brand="Advance|Miyako")
        brands = {p.get("brand") for p in d}
        assert brands == {"Advance", "Miyako"}, brands

    def test_unknown_brand_empty(self):
        r = get("/products", brand="TEST_NoSuchBrand")
        assert r.status_code == 200 and r.json() == []


# --- price range & sort
class TestPriceSort:
    def test_range(self):
        d = all_products(min_price=100000, max_price=200000)
        assert d and all(100000 <= p["price"] <= 200000 for p in d)

    def test_min_gt_max_empty(self):
        r = get("/products", min_price=500000, max_price=100)
        assert r.status_code == 200 and r.json() == []
        f = get("/products/facets", min_price=500000, max_price=100)
        assert f.status_code == 200 and f.json()["total"] == 0

    def test_negative_price_422(self):
        assert get("/products", min_price=-1).status_code == 422

    def test_price_asc(self):
        d = get("/products", sort="price_asc", limit=200, q="rice cooker").json()
        prices = [p["price"] for p in d]
        assert len(prices) > 1 and prices == sorted(prices)

    def test_price_desc(self):
        d = get("/products", sort="price_desc", limit=200, q="rice cooker").json()
        prices = [p["price"] for p in d]
        assert len(prices) > 1 and prices == sorted(prices, reverse=True)

    def test_price_asc_paging_consistent(self):
        a = get("/products", sort="price_asc", limit=40, skip=0).json()
        b = get("/products", sort="price_asc", limit=40, skip=40).json()
        assert a[-1]["price"] <= b[0]["price"]
        assert not ({p["product_id"] for p in a} & {p["product_id"] for p in b})


# --- category (includes subcategories) & combined
class TestCategoryCombined:
    def test_category_dapur_includes_sub(self):
        d = all_products(category="dapur")
        assert d
        cats = {c for p in d for c in p.get("categories", [])}
        assert any(c != "dapur" for c in cats), "no subcategory products included"

    def test_combined_q_brand_price_sort(self):
        d = get("/products", q="rice cooker", brand="Niko", min_price=100000, sort="price_asc", limit=200).json()
        assert d
        for p in d:
            assert "rice cooker" in p["name"].lower() and p["brand"] == "Niko" and p["price"] >= 100000
        assert [p["price"] for p in d] == sorted(p["price"] for p in d)

    def test_in_stock_branch(self):
        h = {"X-Store-Id": "pgs-jombang"}
        r = requests.get(f"{API}/products", params={"in_stock": "true", "q": "rice cooker", "limit": 200}, headers=h, timeout=60)
        assert r.status_code == 200
        allr = get("/products", q="rice cooker", limit=200).json()
        d = r.json()
        assert len(d) <= len(allr)
        # every returned product should really have stock at Jombang (store page context shows branch stock)
        ids = {p["product_id"] for p in d}
        sr = requests.get(f"{API}/products", params={"store": "pgs-official", "q": "rice cooker", "limit": 200}, headers=h, timeout=60).json()
        jomb = {p["product_id"]: p["stock"] for p in sr}
        bad = [i for i in ids if i in jomb and jomb[i] <= 0]
        assert not bad, f"in_stock=true returned products without Jombang stock: {bad[:5]}"


# --- facets
class TestFacets:
    def test_total_matches_list(self):
        for params in ({"q": "rice cooker"}, {"brand": "Advance"}, {"category": "dapur", "min_price": 50000}):
            f = get("/products/facets", **params).json()
            n = len(all_products(**params))
            assert f["total"] == n, (params, f["total"], n)

    def test_facets_shape(self):
        f = get("/products/facets", q="rice cooker").json()
        assert f["brands"] and all(isinstance(b["count"], int) and b["name"] for b in f["brands"])
        assert f["price_min"] <= f["price_max"]
        d = all_products(q="rice cooker")
        assert f["price_min"] == min(p["price"] for p in d) and f["price_max"] == max(p["price"] for p in d)
        b0 = f["brands"][0]
        assert b0["count"] == len(all_products(q="rice cooker", brand=b0["name"]))

    def test_categories_top_level(self):
        cats = get("/categories", all="true").json()
        top = {c["category_id"] for c in cats if not c.get("parent")}
        f = get("/products/facets").json()
        ids = [c["category_id"] for c in f["categories"]]
        assert ids and set(ids) <= top | {"lainnya"}, set(ids) - top  # "lainnya" = products without a category

    def test_category_count_matches_filter(self):
        f = get("/products/facets").json()
        mism = []
        for c in f["categories"][:6]:
            n = get("/products/facets", category=c["category_id"]).json()["total"]
            if n != c["count"]:
                mism.append((c["category_id"], c["count"], n))
        assert not mism, f"facet category count != filtered total: {mism}"
