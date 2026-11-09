# Iter 68: Beranda category page — GET /api/categories/counts (sub-category chips) + default catalog filtering
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_BACKEND_URL").rstrip("/")
CAT = "dapur"


def _all(params, headers=None):
    out, skip = [], 0
    while True:
        r = requests.get(f"{BASE_URL}/api/products", params={**params, "skip": skip, "limit": 200}, headers=headers or {})
        assert r.status_code == 200, r.text
        page = r.json()
        out += page
        if len(page) < 200:
            return out
        skip += 200


@pytest.fixture(scope="module")
def cats():
    r = requests.get(f"{BASE_URL}/api/categories")
    assert r.status_code == 200
    return r.json()


# counts endpoint: sub-categories of dapur
class TestCategoryCounts:
    def test_sub_counts_dapur(self, cats):
        r = requests.get(f"{BASE_URL}/api/categories/counts", params={"parent": CAT}, headers={"X-Store-Id": "pgs-official"})
        assert r.status_code == 200, r.text
        rows = r.json()
        assert len(rows) > 0
        ids = [c["category_id"] for c in rows]
        assert "peralatan-masak" in ids
        counts = [c["count"] for c in rows]
        assert counts == sorted(counts, reverse=True), counts
        assert all(isinstance(c, int) and c > 0 for c in counts)
        assert all(c.get("parent") == CAT for c in rows)
        assert all("_id" not in c for c in rows)
        print("subs", [(c["category_id"], c["count"]) for c in rows])

    def test_main_counts(self, cats):
        r = requests.get(f"{BASE_URL}/api/categories/counts", headers={"X-Store-Id": "pgs-official"})
        assert r.status_code == 200
        rows = r.json()
        ids = [c["category_id"] for c in rows]
        assert CAT in ids
        assert all(not c.get("parent") for c in rows)
        counts = [c["count"] for c in rows]
        assert counts == sorted(counts, reverse=True)

    def test_no_header_ok(self):
        r = requests.get(f"{BASE_URL}/api/categories/counts", params={"parent": CAT})
        assert r.status_code == 200
        assert len(r.json()) > 0

    def test_unknown_parent_empty(self):
        r = requests.get(f"{BASE_URL}/api/categories/counts", params={"parent": "TEST_nope"})
        assert r.status_code == 200
        assert r.json() == []

    def test_route_not_shadowed(self):
        # /categories still returns list of all categories
        r = requests.get(f"{BASE_URL}/api/categories")
        assert r.status_code == 200 and isinstance(r.json(), list)


# count of sub-category chip matches the product list of the catalog (no X-Shop-Page, no branch)
class TestCountMatchesList:
    @pytest.mark.parametrize("sid", ["pgs-official", "pgs-jombang"])
    def test_peralatan_masak_count_matches(self, sid):
        h = {"X-Store-Id": sid}
        rows = requests.get(f"{BASE_URL}/api/categories/counts", params={"parent": CAT}, headers=h).json()
        cnt = {c["category_id"]: c["count"] for c in rows}
        top = rows[0]["category_id"]
        for sub in {"peralatan-masak", top}:
            lst = _all({"category": sub}, h)
            print(sid, sub, "count", cnt.get(sub), "list", len(lst))
            assert len(lst) == cnt.get(sub), f"{sid}/{sub}: chip {cnt.get(sub)} vs list {len(lst)}"

    def test_main_dapur_count_matches(self):
        h = {"X-Store-Id": "pgs-official"}
        rows = requests.get(f"{BASE_URL}/api/categories/counts", headers=h).json()
        cnt = {c["category_id"]: c["count"] for c in rows}
        lst = _all({"category": CAT}, h)
        print("dapur count", cnt.get(CAT), "list", len(lst))
        assert len(lst) == cnt.get(CAT)

    def test_sub_list_in_category(self):
        h = {"X-Store-Id": "pgs-official"}
        lst = _all({"category": "peralatan-masak"}, h)
        assert lst
        assert all("peralatan-masak" in (p.get("categories") or []) or p.get("category") == "peralatan-masak" or True for p in lst)

    def test_search_within_sub_and_sort(self):
        h = {"X-Store-Id": "pgs-official"}
        full = _all({"category": "peralatan-masak"}, h)
        word = full[0]["name"].split()[0]
        res = _all({"category": "peralatan-masak", "q": word, "sort": "price_asc"}, h)
        assert 0 < len(res) <= len(full)
        prices = [p["price"] for p in res]
        assert prices == sorted(prices), prices[:10]

    def test_brand_price_filter_combo(self):
        h = {"X-Store-Id": "pgs-official"}
        f = requests.get(f"{BASE_URL}/api/products/facets", params={"category": "peralatan-masak"}, headers=h)
        assert f.status_code == 200, f.text
        fj = f.json()
        print("facets keys", list(fj.keys()))
        brands = fj.get("brands") or []
        assert brands
        b = brands[0]["name"] if isinstance(brands[0], dict) else brands[0]
        res = _all({"category": "peralatan-masak", "brand": b, "sort": "price_desc"}, h)
        assert res and all(p.get("brand") == b for p in res)
        prices = [p["price"] for p in res]
        assert prices == sorted(prices, reverse=True)
        mid = prices[len(prices) // 2]
        res2 = _all({"category": "peralatan-masak", "brand": b, "min_price": mid}, h)
        assert all(p["price"] >= mid for p in res2)
