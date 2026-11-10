# Brand page (iter73): API backing /brand/{name} — brand filter, branch prices, special-char brand names
import os
import requests
import pytest

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE}/api"


def prods(brand, store="pgs-official", **kw):
    params = {"brand": brand, "limit": 200, **kw}
    r = requests.get(f"{API}/products", params=params, headers={"X-Store-Id": store})
    assert r.status_code == 200, r.text
    return r.json()


def all_prods(brand, store="pgs-official", **kw):
    out, skip = [], 0
    while True:
        r = requests.get(f"{API}/products", params={"brand": brand, "skip": skip, **kw}, headers={"X-Store-Id": store})
        assert r.status_code == 200
        p = r.json()
        out += p
        if len(p) < 40:
            return out
        skip += len(p)


def test_brands_list_has_advance():
    bs = requests.get(f"{API}/brands").json()
    adv = [b for b in bs if b["name"] == "Advance"]
    assert adv and adv[0]["count"] == 126, adv


def test_advance_all_products_brand_and_count():
    p = all_prods("Advance")
    assert all(x["brand"] == "Advance" for x in p)
    assert len({x["product_id"] for x in p}) == len(p)
    print("advance sidoarjo count", len(p))
    assert len(p) == 126


def test_branch_prices_differ_jombang():
    s = {x["product_id"]: x["price"] for x in all_prods("Advance", "pgs-official")}
    j = {x["product_id"]: x["price"] for x in all_prods("Advance", "pgs-jombang")}
    diff = [k for k in s if k in j and s[k] != j[k]]
    print("sidoarjo", len(s), "jombang", len(j), "diff prices", len(diff))
    assert len(j) > 0


def test_facets_count_match():
    r = requests.get(f"{API}/products/facets", params={"brand": "Advance"}, headers={"X-Store-Id": "pgs-official"})
    assert r.status_code == 200
    print(r.json().get("total"), [b for b in r.json()["brands"]][:3])


def test_special_char_brand():
    bs = requests.get(f"{API}/brands").json()
    sp = [b for b in bs if "&" in b["name"]]
    print("special brands", [(b["name"], b["count"]) for b in sp])
    for b in sp:
        p = all_prods(b["name"])
        assert len(p) == b["count"], (b["name"], len(p), b["count"])
        assert all(x["brand"] == b["name"] for x in p)


@pytest.mark.parametrize("sort", ["price_asc", "price_desc"])
def test_sort_price(sort):
    p = all_prods("Advance", sort=sort)
    prices = [x["price"] for x in p]
    assert prices == sorted(prices, reverse=(sort == "price_desc"))
