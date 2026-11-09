# Branch price (Filter Harga Cabang): cards, sort, price range & facets use the buyer's branch price (iteration 47)
# DATA SAFETY: temp prices are written directly to db.store_stock for 5 pgs-jombang rows and removed at teardown.
import os
import time
import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
BASE_URL = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/")
J, OFF, JEM = "pgs-jombang", "pgs-official", "pgs-jember"
BIG = 99999999


def H(sid):
    return {"X-Store-Id": sid}


def get(path, sid, **params):
    r = requests.get(f"{BASE_URL}/api{path}", headers=H(sid), params=params, timeout=60)
    assert r.status_code == 200, f"{path} {params} -> {r.status_code} {r.text[:200]}"
    return r.json()


@pytest.fixture(scope="module")
def temp():
    """Pick 5 shared-catalog products from the Jombang home feed, set branch prices, always clean up."""
    db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    secs = get("/home/sections", J)
    pop = [i for i in secs["popular"]["items"] if not i.get("variants") and not i.get("tier_prices")]
    new = [i for i in secs["newest"]["items"] if not i.get("variants") and not i.get("tier_prices")]
    picks, seen = [], set()
    for i in [pop[0], new[0], new[1], new[2], new[3]]:
        if i["product_id"] not in seen:
            picks.append(i["product_id"]); seen.add(i["product_id"])
    assert len(picks) == 5
    prods = {p["product_id"]: p for p in db.products.find({"product_id": {"$in": picks}}, {"_id": 0})}
    A, B, C, D, E = picks
    plan = {A: prods[A]["price"] + 2000, B: prods[B]["price"] + 2000, C: prods[C]["price"] + 2000, D: BIG, E: 1}
    for pid in picks:  # never overwrite real branch prices
        row = db.store_stock.find_one({"store_id": J, "product_id": pid})
        assert row and "price" not in row, f"{pid} already has a branch price, abort"
    for pid, pr in plan.items():
        db.store_stock.update_one({"store_id": J, "product_id": pid}, {"$set": {"price": pr}})
    yield {"A": A, "B": B, "C": C, "D": D, "E": E, "plan": plan, "base": {k: prods[k]["price"] for k in picks}, "prod": prods}
    db.store_stock.update_many({"store_id": J, "product_id": {"$in": picks}}, {"$unset": {"price": "", "original_price": "", "tier_prices": ""}})
    assert db.store_stock.count_documents({"price": {"$exists": True}}) == 0


def find(items, pid):
    return next((i for i in items if i["product_id"] == pid), None)


class TestCards:
    def test_newest_list_branch_price(self, temp):
        B = temp["B"]
        it = find(get("/products", J, limit=40), B)
        assert it and it["price"] == temp["plan"][B] and it["my_price"] == temp["plan"][B]
        it2 = find(get("/products", OFF, limit=40), B)
        assert it2 and it2["price"] == temp["base"][B]

    def test_search_branch_price(self, temp):
        A = temp["A"]
        name = temp["prod"][A]["name"]
        it = find(get("/products", J, q=name, limit=50), A)
        assert it and it["my_price"] == temp["plan"][A]
        assert find(get("/products", OFF, q=name, limit=50), A)["my_price"] == temp["base"][A]
        assert find(get("/products", JEM, q=name, limit=50), A)["my_price"] == temp["base"][A]

    def test_category_branch_price(self, temp):
        C = temp["C"]
        p = temp["prod"][C]
        cat = (p.get("categories") or [p.get("category")])[0]
        it = find(get("/products", J, category=cat, q=p["name"], limit=50), C)
        assert it and it["my_price"] == temp["plan"][C]

    def test_detail_matches_card(self, temp):
        for k in "ABCDE":
            pid = temp[k]
            d = get(f"/products/{pid}", J)
            assert d["my_price"] == temp["plan"][pid], (k, d["my_price"])


class TestSort:
    def test_price_asc_jombang(self, temp):
        items = get("/products", J, sort="price_asc", limit=40)
        assert items[0]["product_id"] == temp["E"] and items[0]["price"] == 1
        prices = [i["price"] for i in items]
        assert prices == sorted(prices)

    def test_price_desc_jombang(self, temp):
        items = get("/products", J, sort="price_desc", limit=40)
        assert items[0]["product_id"] == temp["D"] and items[0]["price"] == BIG
        prices = [i["price"] for i in items]
        assert prices == sorted(prices, reverse=True)

    def test_official_order_unchanged(self, temp):
        for sid in (OFF, JEM):
            a = get("/products", sid, sort="price_asc", limit=40)
            assert a[0]["product_id"] != temp["E"] or a[0]["price"] == temp["base"][temp["E"]]
            assert [i["price"] for i in a] == sorted(i["price"] for i in a)
            d = get("/products", sid, sort="price_desc", limit=40)
            assert all(i["price"] != BIG for i in d)

    def test_pagination_consistent(self, temp):
        p1 = get("/products", J, sort="price_asc", limit=20, skip=0)
        p2 = get("/products", J, sort="price_asc", limit=20, skip=20)
        assert not ({i["product_id"] for i in p1} & {i["product_id"] for i in p2})
        assert p1[-1]["price"] <= p2[0]["price"]

    def test_performance(self, temp):
        for sid, s in ((J, "price_asc"), (J, "price_desc"), (OFF, "price_asc")):
            t = time.time(); get("/products", sid, sort=s, limit=40); dt = time.time() - t
            print(sid, s, round(dt, 3))
            assert dt < 1.5


class TestRange:
    def test_big_price_only_jombang(self, temp):
        j = get("/products", J, min_price=BIG - 9, limit=40)
        assert [i["product_id"] for i in j] == [temp["D"]]
        assert get("/products", OFF, min_price=BIG - 9, limit=40) == []
        assert get("/products", JEM, min_price=BIG - 9, limit=40) == []

    def test_range_around_branch_price(self, temp):
        A = temp["A"]; b = temp["base"][A]; name = temp["prod"][A]["name"]
        j_in = get("/products", J, q=name, min_price=b + 1000, max_price=b + 3000, limit=50)
        assert find(j_in, A)
        j_out = get("/products", J, q=name, min_price=b, max_price=b + 1000, limit=50)
        assert not find(j_out, A)
        assert find(get("/products", OFF, q=name, min_price=b, max_price=b + 1000, limit=50), A)
        assert not find(get("/products", OFF, q=name, min_price=b + 1000, max_price=b + 3000, limit=50), A)

    def test_cheap_branch_price_range(self, temp):
        E = temp["E"]
        j = get("/products", J, max_price=1, limit=40)
        assert find(j, E)
        assert not find(get("/products", OFF, max_price=1, limit=40), E)

    def test_combined_filters(self, temp):
        C = temp["C"]; p = temp["prod"][C]
        cat = (p.get("categories") or [p.get("category")])[0]
        b = temp["base"][C]
        kw = dict(category=cat, min_price=b + 1000, max_price=b + 3000, in_stock="true", limit=200, sort="price_asc")
        if p.get("brand"):
            kw["brand"] = p["brand"]
        j = get("/products", J, **kw)
        assert find(j, C), "combined category/brand/in_stock/range must keep C in Jombang"
        assert all(b + 1000 <= i["price"] <= b + 3000 for i in j)
        assert not find(get("/products", OFF, **kw), C)
        w = get("/products", J, wholesale="true", min_price=0, max_price=BIG, sort="price_asc", limit=20)
        assert isinstance(w, list)


class TestFacets:
    def test_facets_range_jombang(self, temp):
        f = get("/products/facets", J)
        assert f["price_max"] == BIG and f["price_min"] == 1
        o = get("/products/facets", OFF)
        assert o["price_max"] != BIG and o["price_min"] != 1 or temp["base"][temp["E"]] == 1

    def test_facets_total_counts_respect_range(self, temp):
        f = get("/products/facets", J, min_price=BIG - 9)
        assert f["total"] == 1 and f["price_min"] == BIG and f["price_max"] == BIG
        assert sum(c["count"] for c in f["categories"]) >= 1
        assert sum(b["count"] for b in f["brands"]) <= 1
        o = get("/products/facets", OFF, min_price=BIG - 9)
        assert o["total"] == 0 and o["categories"] == [] and o["brands"] == []


class TestHome:
    def test_home_sections(self, temp):
        j = get("/home/sections", J)
        o = get("/home/sections", OFF)
        A, B = temp["A"], temp["B"]
        all_j = [i for s in j.values() for i in s["items"]]
        all_o = [i for s in o.values() for i in s["items"]]
        for it in all_j:
            if it["product_id"] in temp["plan"]:
                assert it["my_price"] == temp["plan"][it["product_id"]], it["product_id"]
        for it in all_o:
            if it["product_id"] in temp["plan"]:
                assert it["my_price"] == temp["base"][it["product_id"]]
        assert find(all_j, A) or find(all_j, B), "temp products should still be on Jombang home"

    def test_recommendations(self, temp):
        for path in ("/home/sections/recommended", "/recommendations"):
            items = get(path, J, limit=30)
            items = items if isinstance(items, list) else items.get("items", [])
            for it in items:
                if it["product_id"] in temp["plan"]:
                    assert it["my_price"] == temp["plan"][it["product_id"]], (path, it["product_id"])
