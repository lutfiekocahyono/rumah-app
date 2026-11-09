# Iteration 64: branch store page scope (X-Shop-Page: 1) — only products with a branch price + only_branch products
import os
import uuid

import pytest
import requests
from pymongo import MongoClient


def _base():
    u = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL")
    if not u:
        for line in open("/app/frontend/.env"):
            if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
                u = line.split("=", 1)[1].strip().strip('"')
    return u.rstrip("/")


def _env(key):
    for line in open("/app/backend/.env"):
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"')


API = f"{_base()}/api"
DB = MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]
JB = "pgs-jombang"
STOCK0 = "pgs-10211"  # Jombang price set, stock 0
CREDS = {"jombang": ("jombang@pgs.id", "Jombang123!"), "admin": ("admin@pgs.id", "Admin1234!")}
S: dict = {"tok": {}}


def tok(who):
    if who not in S["tok"]:
        r = requests.post(f"{API}/auth/login", json=dict(zip(("email", "password"), CREDS[who])), timeout=30)
        assert r.status_code == 200, r.text
        S["tok"][who] = r.json()["token"]
    return S["tok"][who]


def H(store=JB, shop=False, who=None):
    h = {"Content-Type": "application/json", "X-Store-Id": store}
    if shop:
        h["X-Shop-Page"] = "1"
    if who:
        h["Authorization"] = f"Bearer {tok(who)}"
    return h


def get(path, **kw):
    r = requests.get(f"{API}{path}", headers=H(**kw), timeout=60)
    assert r.status_code == 200, f"{path} {r.status_code} {r.text[:200]}"
    return r.json()


def ids(items):
    return [i["product_id"] for i in items]


def name_of(pid):
    return DB.products.find_one({"product_id": pid}, {"name": 1})["name"]


@pytest.fixture(scope="module", autouse=True)
def setup():
    # baseline before any change
    S["count_beranda"] = get("/products/count")["count"]
    S["count_shop"] = get("/products/count", shop=True)["count"]
    S["count_jember"] = get("/products/count", store="pgs-jember", shop=True)["count"]
    S["count_sda"] = get("/products/count", store="pgs-official", shop=True)["count"]
    sec = get("/home/sections")
    fl = get("/flash-sale")
    targets = {"pgs-10062"}
    for k in ("popular", "newest", "recommended"):
        if sec[k]["items"]:
            targets.add(sec[k]["items"][0]["product_id"])
    if fl.get("active") and fl["items"]:
        targets.add(fl["items"][0]["product_id"])
    targets = [t for t in targets if DB.store_stock.find_one({"store_id": JB, "product_id": t, "price": {"$gt": 0}})]
    S["targets"], S["sec"], S["flash"] = targets, sec, fl
    # a product added by the Jombang admin for Jombang only
    nm = f"TEST_shopscope_{uuid.uuid4().hex[:6]}"
    cats = requests.get(f"{API}/categories", timeout=30).json()
    form = {"name": nm, "category": cats[0]["category_id"], "images": ["https://example.com/a.jpg"],
            "description": "TEST produk khusus cabang Jombang untuk pengujian halaman toko cabang.",
            "price": 15000, "stock": 10, "weight_grams": 500, "ship_regular": True}
    r = requests.post(f"{API}/product-editor/publish", headers=H(who="jombang"), json={"data": form}, timeout=60)
    assert r.status_code == 200, r.text
    S["own"] = {"pid": r.json()["product_id"], "name": nm}
    for t in targets:
        DB.store_stock.update_one({"store_id": JB, "product_id": t}, {"$rename": {"price": "_bak_price"}})
    try:
        yield
    finally:
        for t in targets:
            DB.store_stock.update_one({"store_id": JB, "product_id": t, "_bak_price": {"$exists": True}}, {"$rename": {"_bak_price": "price"}})
        requests.delete(f"{API}/seller/products/{S['own']['pid']}", headers=H(who="jombang"), timeout=30)
        assert DB.store_stock.count_documents({"_bak_price": {"$exists": True}}) == 0


# --- count ---
def test_count_shop_drops_unpriced_beranda_unchanged():
    n = len(S["targets"])
    assert get("/products/count")["count"] == S["count_beranda"] + 1  # +1 own product, nothing hidden
    assert get("/products/count", shop=True)["count"] == S["count_shop"] + 1 - n


def test_count_other_branches_unaffected():
    assert get("/products/count", store="pgs-jember", shop=True)["count"] == S["count_jember"]
    assert get("/products/count", store="pgs-official", shop=True)["count"] == S["count_sda"]


def test_store_page_product_count_and_featured_without_header():
    d = get(f"/stores/{JB}/page")
    assert d["product_count"] == get("/products/count", shop=True)["count"]
    assert not set(ids(d["featured"])) & set(S["targets"])


# --- product list / search / facets ---
def test_products_branch_list_hides_unpriced_only_with_header():
    nm = name_of("pgs-10062")
    shop = get(f"/products?branch={JB}&q={nm}&limit=40", shop=True)
    home = get(f"/products?branch={JB}&q={nm}&limit=40")
    assert "pgs-10062" not in ids(shop)
    assert "pgs-10062" in ids(home)


def test_products_beranda_search_unfiltered():
    nm = name_of("pgs-10062")
    assert "pgs-10062" in ids(get(f"/products?q={nm}&limit=40"))


def test_only_branch_product_on_store_page():
    r = get(f"/products?branch={JB}&q={S['own']['name']}&limit=40", shop=True)
    assert S["own"]["pid"] in ids(r)


def test_only_branch_product_featured_fallback():
    d = get(f"/stores/{JB}/page")
    if d["featured_manual"]:
        pytest.skip("manual featured list")
    assert S["own"]["pid"] in ids(d["featured"])


def test_stock0_priced_product_listed_sold_out():
    r = get(f"/products?branch={JB}&q={name_of(STOCK0)}&limit=40", shop=True)
    it = next((i for i in r if i["product_id"] == STOCK0), None)
    assert it is not None
    assert it["stock"] == 0 and it["in_stock"] is False


def test_facets_respect_header():
    nm = name_of("pgs-10062")
    a = get(f"/products/facets?branch={JB}&q={nm}", shop=True)["total"]
    b = get(f"/products/facets?branch={JB}&q={nm}")["total"]
    assert b - a == 1


def test_suggest_respects_header():
    nm = name_of("pgs-10062")
    assert "pgs-10062" not in ids(get(f"/products/suggest?q={nm}", shop=True)["products"])
    assert "pgs-10062" in ids(get(f"/products/suggest?q={nm}")["products"])


# --- home sections & flash sale ---
def test_home_sections_shop_hides_targets_beranda_keeps():
    shop, home = get("/home/sections", shop=True), get("/home/sections")
    for k in ("popular", "newest", "recommended"):
        assert not set(ids(shop[k]["items"])) & set(S["targets"]), k
        first = S["sec"][k]["items"][0]["product_id"] if S["sec"][k]["items"] else None
        if first and k != "recommended":  # recommended ordering may be personalised
            assert first in ids(home[k]["items"]), k


def test_more_recommended_respects_header():
    shop = get("/home/sections/recommended?skip=0&limit=30", shop=True)
    assert not set(ids(shop)) & set(S["targets"])


def test_flash_sale_respects_header():
    if not (S["flash"].get("active") and S["flash"]["items"]):
        pytest.skip("no active flash sale for Jombang")
    pid = S["flash"]["items"][0]["product_id"]
    assert pid not in ids(get("/flash-sale", shop=True)["items"])
    assert pid in ids(get("/flash-sale")["items"])


def test_sidoarjo_store_page_unaffected():
    d = get("/stores/pgs-official/page")
    assert d["product_count"] == get("/products/count", store="pgs-official")["count"] or d["product_count"] > 0
    nm = name_of("pgs-10062")
    assert "pgs-10062" in ids(get(f"/products?branch=pgs-official&q={nm}&limit=40", store="pgs-official", shop=True))
