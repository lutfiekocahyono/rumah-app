# Iteration 61: /products/suggest brand prefix ordering + duplicate product name dedupe
import pytest
import requests
from test_iter60_suggest_shop_search import API, J, sugg

TAG = "Zqdupe"
ST: dict = {"ids": []}


@pytest.fixture(scope="module", autouse=True)
def dupes():
    base = {"description": "TEST dupe", "price": 12000, "images": ["https://example.com/a.jpg"], "category": "dapur", "stock": 4}
    for name in (f"{TAG} Panci Sama", f"{TAG} panci sama ", f"{TAG} Panci Beda"):
        r = requests.post(f"{API}/seller/products", headers=J(), json={**base, "name": name}, timeout=30)
        assert r.status_code == 200, r.text
        ST["ids"].append(r.json()["product_id"])
    yield
    for pid in ST["ids"]:
        print("cleanup", pid, requests.delete(f"{API}/seller/products/{pid}", headers=J(), timeout=30).status_code)


# brand names starting with q are listed before names merely containing q
def test_brand_prefix_first():
    for q in ("ma", "mas", "an"):
        b = sugg(q, "pgs-jombang")["brands"]
        flags = [x.lower().startswith(q) for x in b]
        assert flags == sorted(flags, reverse=True), f"{q}: {b}"
        assert all(q in x.lower() for x in b)


def test_brand_maspion_for_mas():
    assert "Maspion" in sugg("mas", "pgs-jombang")["brands"]


# duplicate product names (case/whitespace-insensitive) are returned once
def test_dedupe_names():
    d = sugg(TAG, "pgs-jombang")
    names = [p["name"].strip().lower() for p in d["products"]]
    assert len(names) == len(set(names)), names
    assert f"{TAG} panci sama".lower() in names and f"{TAG} panci beda".lower() in names, names


def test_dedupe_global():
    for q in ("mas", "kes", "pan", "ma"):
        names = [p["name"].strip().lower() for p in sugg(q, "pgs-jombang")["products"]]
        assert len(names) == len(set(names)), (q, names)
