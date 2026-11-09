# Iteration 66: branch store page Kategori row (GET /api/stores/{id}/categories) + Sidoarjo store page scoping
import copy
import os
import uuid

import pytest
import requests
from pymongo import MongoClient


def _read(path, key):
    for line in open(path):
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"')


BASE = (os.environ.get("EXPO_BACKEND_URL") or _read("/app/frontend/.env", "EXPO_BACKEND_URL") or _read("/app/frontend/.env", "EXPO_PUBLIC_BACKEND_URL")).rstrip("/")
API = f"{BASE}/api"
DB = MongoClient(_read("/app/backend/.env", "MONGO_URL"))[_read("/app/backend/.env", "DB_NAME")]
BRANCHES = ["pgs-jombang", "pgs-jember", "pgs-official"]
SMALL = "perlengkapan-bayi"
MP_STORE = "st_c789b1a7c3"  # active marketplace seller


def H(store, shop=False):
    h = {"X-Store-Id": store}
    if shop:
        h["X-Shop-Page"] = "1"
    return h


def get(path, store="pgs-jombang", shop=False, code=200):
    r = requests.get(f"{API}{path}", headers=H(store, shop), timeout=60)
    assert r.status_code == code, f"{path} {r.status_code} {r.text[:200]}"
    return r.json()


def tree(cid):
    parent = {c["category_id"]: c.get("parent") for c in DB.categories.find({}, {"category_id": 1, "parent": 1})}
    out, fr = {cid}, {cid}
    while fr:
        fr = {k for k, p in parent.items() if p in fr and k not in out}
        out |= fr
    return list(out)


def all_products(cat, store, shop):
    out, skip = [], 0
    while True:
        page = get(f"/products?category={cat}&branch={store}&limit=40&skip={skip}", store=store, shop=shop)
        out += page
        if len(page) < 40:
            return out
        skip += 40


# ---- Category endpoint: shape, sort, only mains, 404 ----
@pytest.mark.parametrize("sid", BRANCHES)
def test_store_categories_mains_sorted(sid):
    cats = get(f"/stores/{sid}/categories")
    assert isinstance(cats, list) and cats
    counts = [c["count"] for c in cats]
    assert all(c > 0 for c in counts)
    assert counts == sorted(counts, reverse=True)
    assert all(not c.get("parent") for c in cats)
    assert all({"category_id", "name", "icon"} <= set(c) for c in cats)
    assert "_id" not in cats[0]


def test_store_categories_404_non_official():
    get(f"/stores/{MP_STORE}/categories", code=404)
    get("/stores/does-not-exist/categories", code=404)


def test_category_count_matches_filtered_list():
    cats = get("/stores/pgs-jombang/categories")
    c = next(x for x in cats if x["category_id"] == SMALL) if any(x["category_id"] == SMALL for x in cats) else cats[-1]
    prods = all_products(c["category_id"], "pgs-jombang", shop=True)
    assert len(prods) == c["count"], (c, len(prods))
    assert all(p.get("store_name") != "PGS · semua cabang" for p in prods)


def test_hide_small_category_for_jombang_only():
    pids = [p["product_id"] for p in DB.products.find({"categories": {"$in": tree(SMALL)}}, {"product_id": 1})]
    assert pids and not DB.products.find_one({"product_id": {"$in": pids}, "only_branch": "pgs-jombang"})
    before = {s: {c["category_id"]: c["count"] for c in get(f"/stores/{s}/categories")} for s in BRANCHES}
    assert SMALL in before["pgs-jombang"]
    q = {"store_id": "pgs-jombang", "product_id": {"$in": pids}, "price": {"$exists": True}}
    bak_ids = [d["_id"] for d in DB.store_stock.find(q, {"_id": 1})]
    try:
        DB.store_stock.update_many({"_id": {"$in": bak_ids}}, {"$rename": {"price": "_bak_price"}})
        after = {s: {c["category_id"]: c["count"] for c in get(f"/stores/{s}/categories")} for s in BRANCHES}
        assert SMALL not in after["pgs-jombang"]
        assert after["pgs-jember"].get(SMALL) == before["pgs-jember"].get(SMALL)
        assert after["pgs-official"].get(SMALL) == before["pgs-official"].get(SMALL)
        assert get(f"/products?category={SMALL}&branch=pgs-jombang&limit=40", shop=True) == []
        # Beranda/normal category is unaffected
        assert len(get(f"/products?category={SMALL}&branch=pgs-jombang&limit=40")) > 0
    finally:
        DB.store_stock.update_many({"_id": {"$in": bak_ids}}, {"$rename": {"_bak_price": "price"}})
    assert DB.store_stock.count_documents({"_bak_price": {"$exists": True}}) == 0
    assert {c["category_id"]: c["count"] for c in get("/stores/pgs-jombang/categories")} == before["pgs-jombang"]


# ---- Sidoarjo store page scoping ----
@pytest.fixture(scope="module")
def temp_products():
    base = DB.products.find_one({"store_id": "pgs-official", "categories": SMALL, "variants": {"$in": [None, []]}}, {"_id": 0}) \
        or DB.products.find_one({"store_id": "pgs-official", "categories": SMALL}, {"_id": 0})
    tag = uuid.uuid4().hex[:6]
    mp = {**copy.deepcopy(base), "product_id": f"TEST_mp_{tag}", "name": f"TEST_MP Produk {tag}", "store_id": MP_STORE, "stock": 5}
    zero = {**copy.deepcopy(base), "product_id": f"TEST_zero_{tag}", "name": f"TEST_ZERO Produk {tag}", "price": 0, "stock": 5}
    for d in (mp, zero):
        d.pop("only_branch", None)
        d.pop("sku", None)
        d.pop("barcode", None)
    DB.products.insert_many([copy.deepcopy(mp), copy.deepcopy(zero)])
    yield {"mp": mp["product_id"], "zero": zero["product_id"], "tag": tag}
    DB.products.delete_many({"product_id": {"$in": [mp["product_id"], zero["product_id"]]}})


def test_sidoarjo_shop_excludes_marketplace_and_price0(temp_products):
    tag = temp_products["tag"]
    shop = [p["product_id"] for p in get(f"/products?branch=pgs-official&q={tag}&limit=40", store="pgs-official", shop=True)]
    beranda = [p["product_id"] for p in get(f"/products?branch=pgs-official&q={tag}&limit=40", store="pgs-official")]
    assert temp_products["mp"] in beranda, beranda  # marketplace product visible on Beranda
    assert temp_products["mp"] not in shop and temp_products["zero"] not in shop, shop
    sda_cnt = get("/products/count", store="pgs-official", shop=True)["count"]
    ber_cnt = get("/products/count", store="pgs-official")["count"]
    assert ber_cnt == sda_cnt + 2 or ber_cnt >= sda_cnt + 1, (ber_cnt, sda_cnt)
    cats = {c["category_id"]: c["count"] for c in get("/stores/pgs-official/categories")}
    exp = DB.products.count_documents({"store_id": "pgs-official", "price": {"$gt": 0}, "categories": {"$in": tree(SMALL)}, "status": {"$ne": "inactive"}})
    assert cats.get(SMALL) == exp


def test_sidoarjo_rails_label_and_own_stock():
    sec = get("/home/sections", store="pgs-official", shop=True)
    items = [i for k in ("popular", "newest", "recommended") for i in sec[k]["items"]]
    assert items
    assert all(i.get("store_name") == "PGS Sidoarjo" for i in items), {i.get("store_name") for i in items}
    for i in items[:10]:
        d = DB.products.find_one({"product_id": i["product_id"]}, {"stock": 1, "in_stock": 1, "variants": 1})
        if not d.get("variants"):
            own = d.get("stock", 0) if d.get("in_stock", True) else 0
            assert i["stock"] == own, (i["product_id"], i["stock"], own)
    ber = get("/home/sections", store="pgs-official")
    labels = {i.get("store_name") for k in ("popular", "newest", "recommended") for i in ber[k]["items"]}
    assert "PGS · semua cabang" in labels, labels


def test_sidoarjo_store_page_count():
    d = get("/stores/pgs-official/page", store="pgs-official")
    assert d["product_count"] == get("/products/count", store="pgs-official", shop=True)["count"]
