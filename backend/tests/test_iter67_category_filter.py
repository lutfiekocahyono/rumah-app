# Iter 67: branch store category page filters (brand / price / stock / grosir) for /category/dapur?toko=pgs-jombang
import os
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("EXPO_BACKEND_URL").rstrip("/")
SHOP = {"X-Shop-Page": "1"}
BR = "pgs-jombang"
CAT = "dapur"


def _env(k):
    for line in open("/app/backend/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip('"')


@pytest.fixture(scope="module")
def db():
    return MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]


def _all(params):
    out, skip = [], 0
    while True:
        r = requests.get(f"{BASE_URL}/api/products", params={**params, "skip": skip, "limit": 200}, headers=SHOP)
        assert r.status_code == 200, r.text
        page = r.json()
        out += page
        if len(page) < 200:
            return out
        skip += 200


def _facets(params):
    r = requests.get(f"{BASE_URL}/api/products/facets", params=params, headers=SHOP)
    assert r.status_code == 200, r.text
    return r.json()


# facets total == list count for category in branch
def test_facets_total_matches_list():
    f = _facets({"category": CAT, "branch": BR})
    lst = _all({"category": CAT, "branch": BR, "sort": "popular"})
    print("total", f["total"], "list", len(lst), "brands", f["brands"][:5], "range", f["price_min"], f["price_max"])
    assert f["total"] == len(lst)
    assert f["total"] > 0


# brand filter returns only that brand and count matches
def test_brand_filter():
    f = _facets({"category": CAT, "branch": BR})
    b = f["brands"][0]
    lst = _all({"category": CAT, "branch": BR, "brand": b["name"], "sort": "popular"})
    assert len(lst) == b["count"]
    assert all(p.get("brand") == b["name"] for p in lst)


# sub categories from shop categories endpoint consistent with facets
def test_sub_category_counts():
    subs = requests.get(f"{BASE_URL}/api/stores/{BR}/categories", params={"parent": CAT}).json()
    print("subs", [(s["category_id"], s.get("count")) for s in subs])
    for s in subs[:4]:
        f = _facets({"category": s["category_id"], "branch": BR})
        lst = _all({"category": s["category_id"], "branch": BR, "sort": "popular"})
        assert f["total"] == len(lst), s
        if s.get("count") is not None:
            assert s["count"] == f["total"], (s, f["total"])


# price range uses the Jombang branch price
def test_price_range_branch_price(db):
    lst = _all({"category": CAT, "branch": BR, "sort": "popular"})
    ids = [p["product_id"] for p in lst]
    bp = {d["product_id"]: d["price"] for d in db.store_stock.find({"store_id": BR, "product_id": {"$in": ids}, "price": {"$gt": 0}})}
    diff = [p for p in lst if p["product_id"] in bp and p["price"] != bp[p["product_id"]]]
    print("branch priced", len(bp), "of", len(lst), "card price != branch price:", [(p["product_id"], p["price"], bp[p["product_id"]]) for p in diff[:5]])
    prices = sorted(bp.get(p["product_id"], p["price"]) for p in lst)
    lo, hi = prices[len(prices) // 4], prices[len(prices) * 3 // 4]
    got = _all({"category": CAT, "branch": BR, "min_price": lo, "max_price": hi, "sort": "popular"})
    exp = {p["product_id"] for p in lst if lo <= bp.get(p["product_id"], p["price"]) <= hi}
    assert {p["product_id"] for p in got} == exp
    assert all(lo <= p["price"] <= hi for p in got), [(p["product_id"], p["price"]) for p in got if not lo <= p["price"] <= hi][:5]
    f = _facets({"category": CAT, "branch": BR, "min_price": lo, "max_price": hi})
    assert f["total"] == len(got)
    f0 = _facets({"category": CAT, "branch": BR})
    assert f0["price_min"] == prices[0] and f0["price_max"] == prices[-1]


# in_stock uses Jombang stock
def test_in_stock_branch(db):
    lst = _all({"category": CAT, "branch": BR, "sort": "popular"})
    got = _all({"category": CAT, "branch": BR, "in_stock": "true", "sort": "popular"})
    print("all", len(lst), "in stock", len(got))
    assert all(p["in_stock"] for p in got)
    exp = {p["product_id"] for p in lst if p["in_stock"]}
    assert {p["product_id"] for p in got} == exp
    f = _facets({"category": CAT, "branch": BR, "in_stock": "true"})
    assert f["total"] == len(got)


# wholesale filter
def test_wholesale():
    got = _all({"category": CAT, "branch": BR, "wholesale": "true", "sort": "popular"})
    f = _facets({"category": CAT, "branch": BR, "wholesale": "true"})
    print("wholesale", len(got))
    assert f["total"] == len(got)


# without X-Shop-Page, the non-branch category shows more products (not scoped)
def test_without_shop_header_not_scoped():
    r = requests.get(f"{BASE_URL}/api/products/facets", params={"category": CAT})
    f_all = r.json()
    f_br = _facets({"category": CAT, "branch": BR})
    print("all", f_all["total"], "branch", f_br["total"])
    assert f_all["total"] >= f_br["total"]
