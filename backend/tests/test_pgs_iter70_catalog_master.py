# PGS iteration 70: Master Merek & Kategori (Super Admin), brand picker validation in product editor, brand logos.
import os
import uuid

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
IMG = "https://pusatgrosirsidoarjo.com/wp-content/uploads/2023/07/Cetakan-7-Lubang-Cekung-Suggo-300x300.webp"
DESC = "Deskripsi **tebal** produk uji coba yang cukup panjang untuk validasi.\n- poin satu\n- poin dua"
LOGO = IMG


def _env(k):
    for line in open("/app/backend/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip('"')


DB = MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]
CRED = {"admin": ("admin@pgs.id", "Admin1234!"), "jombang": ("jombang@pgs.id", "Jombang123!")}
SUF = uuid.uuid4().hex[:5]
S = {"brands": [], "cats": [], "products": [], "lainnya_inc": 0}


def H(t):
    return {"Authorization": f"Bearer {t}"}


def form(**kw):
    base = {"name": f"TEST_CM {SUF}", "category": "dapur", "subcategory": "", "brand": "", "sku": "TSKU", "condition": "new",
            "status": "active", "description": DESC, "images": [IMG], "price": 10000, "discount_price": 0, "stock": 50,
            "min_order": 1, "max_order": 0, "weight_grams": 500}
    base.update(kw)
    return base


@pytest.fixture(scope="module")
def tok():
    t = {}
    for k, (e, p) in CRED.items():
        r = requests.post(f"{API}/auth/login", json={"email": e, "password": p})
        assert r.status_code == 200, r.text
        t[k] = r.json()["token"]
    yield t
    # cleanup only what we created, by id
    for pid in S["products"]:
        DB.products.delete_one({"product_id": pid, "name": {"$regex": "^TEST_"}})
        for c in ("price_history", "product_events", "product_history"):
            DB[c].delete_many({"product_id": pid})
    for bid in S["brands"]:
        DB.brands.delete_one({"brand_id": bid, "name": {"$regex": "^TEST_"}})
    for cid in S["cats"]:
        DB.categories.delete_one({"category_id": cid, "source": "admin"})
    if S["lainnya_inc"]:
        DB.categories.update_one({"category_id": "lainnya"}, {"$inc": {"count": -S["lainnya_inc"]}})


def publish(t, data):
    r = requests.post(f"{API}/product-editor/publish", headers=H(t), json={"data": data})
    if r.status_code == 200:
        S["products"].append(r.json()["product_id"])
    return r


def prod(pid):
    return DB.products.find_one({"product_id": pid}, {"_id": 0})


# ---- brands list (public) ----
def test_public_brands_list():
    r = requests.get(f"{API}/brands")
    assert r.status_code == 200
    d = r.json()
    assert len(d) >= 115 and all({"brand_id", "name", "logo", "count"} <= set(b) for b in d)
    assert sum(b["count"] for b in d) >= 4600
    assert [b["name"].lower() for b in d] == sorted(b["name"].lower() for b in d)


# ---- brand CRUD + permissions ----
def test_brand_create_dup_perm(tok):
    r = requests.post(f"{API}/admin/brands", headers=H(tok["admin"]), json={"name": f"TEST_Brand{SUF}", "logo": LOGO})
    assert r.status_code == 200, r.text
    b = r.json()
    S["brands"].append(b["brand_id"])
    S["brand"] = b
    assert b["name"] == f"TEST_Brand{SUF}" and b["logo"] == LOGO and b["count"] == 0
    assert requests.post(f"{API}/admin/brands", headers=H(tok["admin"]), json={"name": f"test_brand{SUF}".upper()}).status_code == 409
    assert requests.post(f"{API}/admin/brands", headers=H(tok["admin"]), json={"name": "advance"}).status_code == 409
    assert requests.post(f"{API}/admin/brands", headers=H(tok["jombang"]), json={"name": f"TEST_J{SUF}"}).status_code == 403
    assert requests.post(f"{API}/admin/brands", json={"name": f"TEST_N{SUF}"}).status_code in (401, 403)
    assert requests.get(f"{API}/admin/brands/{b['brand_id']}/impact", headers=H(tok["jombang"])).status_code == 403
    assert requests.delete(f"{API}/admin/brands/{b['brand_id']}", headers=H(tok["jombang"])).status_code == 403
    assert requests.post(f"{API}/admin/brands", headers=H(tok["admin"]), json={"name": ""}).status_code == 422
    names = [x["name"] for x in requests.get(f"{API}/brands").json()]
    assert b["name"] in names


# ---- categories CRUD + permissions ----
def test_category_create(tok):
    r = requests.post(f"{API}/admin/categories", headers=H(tok["admin"]), json={"name": f"TEST_Kat {SUF}"})
    assert r.status_code == 200, r.text
    c = r.json()
    S["cats"].append(c["category_id"])
    S["cat"] = c
    assert c["parent"] is None and c["category_id"] == f"test-kat-{SUF}"
    r = requests.post(f"{API}/admin/categories", headers=H(tok["admin"]), json={"name": f"TEST_Sub {SUF}", "parent": c["category_id"]})
    assert r.status_code == 200, r.text
    S["cats"].append(r.json()["category_id"])
    S["sub"] = r.json()
    assert S["sub"]["parent"] == c["category_id"]
    assert requests.post(f"{API}/admin/categories", headers=H(tok["admin"]), json={"name": f"test_kat {SUF}"}).status_code == 409
    assert requests.post(f"{API}/admin/categories", headers=H(tok["admin"]), json={"name": "x", "parent": "nope-xyz"}).status_code == 404
    assert requests.post(f"{API}/admin/categories", headers=H(tok["jombang"]), json={"name": f"TEST_J {SUF}"}).status_code == 403
    allc = requests.get(f"{API}/categories", params={"all": True}).json()
    assert c["category_id"] in [x["category_id"] for x in allc]
    subs = requests.get(f"{API}/categories", params={"parent": c["category_id"]}).json()
    assert [x["category_id"] for x in subs] == [S["sub"]["category_id"]]


def test_lainnya_undeletable(tok):
    r = requests.delete(f"{API}/admin/categories/lainnya", headers=H(tok["admin"]))
    assert r.status_code == 400
    assert DB.categories.find_one({"category_id": "lainnya"})


# ---- product editor brand validation ----
def test_editor_unknown_brand_422(tok):
    r = publish(tok["admin"], form(brand=f"TEST_Unknown{SUF}"))
    assert r.status_code == 422, r.text
    assert "brand" in r.json()["detail"]["errors"]


def test_editor_publish_canonical_brand(tok):
    r = publish(tok["admin"], form(brand=f"test_brand{SUF}", category=S["cat"]["category_id"], subcategory=S["sub"]["category_id"]))
    assert r.status_code == 200, r.text
    pid = r.json()["product_id"]
    S["pid"] = pid
    p = prod(pid)
    assert p["brand"] == f"TEST_Brand{SUF}"
    assert p["category"] == S["cat"]["category_id"] and p["subcategory"] == S["sub"]["category_id"]


def test_jombang_publish_listed_brand(tok):
    r = publish(tok["jombang"], form(name=f"TEST_CMJ {SUF}", brand="ADVANCE"))
    assert r.status_code == 200, r.text
    assert prod(r.json()["product_id"])["brand"] == "Advance"
    r = publish(tok["jombang"], form(name=f"TEST_CMJ2 {SUF}", brand=f"TEST_Free{SUF}"))
    assert r.status_code == 422 and "brand" in r.json()["detail"]["errors"]


def test_brand_logo_in_product_and_facets(tok):
    r = requests.get(f"{API}/products/{S['pid']}", headers=H(tok["admin"]))
    assert r.status_code == 200, r.text
    assert r.json().get("brand_logo") == LOGO
    f = requests.get(f"{API}/products/facets", params={"q": f"TEST_CM {SUF}"}, headers=H(tok["admin"])).json()
    hit = [b for b in f["brands"] if b["name"] == f"TEST_Brand{SUF}"]
    assert hit and hit[0]["logo"] == LOGO, f["brands"]
    lst = requests.get(f"{API}/products", params={"q": f"TEST_CM {SUF}"}, headers=H(tok["admin"])).json()
    items = lst if isinstance(lst, list) else lst.get("products", lst.get("items", []))
    assert any(i.get("brand_logo") == LOGO for i in items)


def test_impacts(tok):
    r = requests.get(f"{API}/admin/brands/{S['brand']['brand_id']}/impact", headers=H(tok["admin"]))
    assert r.status_code == 200 and r.json()["products"] == 1
    r = requests.get(f"{API}/admin/categories/{S['cat']['category_id']}/impact", headers=H(tok["admin"]))
    assert r.status_code == 200 and r.json() == {"products": 1, "subcategories": 1}
    cnt = {b["name"]: b["count"] for b in requests.get(f"{API}/brands").json()}
    assert cnt[f"TEST_Brand{SUF}"] == 1


def test_rename_brand_moves_products(tok):
    bid = S["brand"]["brand_id"]
    new = f"TEST_BrandRen{SUF}"
    assert requests.put(f"{API}/admin/brands/{bid}", headers=H(tok["admin"]), json={"name": "Advance", "logo": ""}).status_code == 409
    r = requests.put(f"{API}/admin/brands/{bid}", headers=H(tok["admin"]), json={"name": new, "logo": LOGO})
    assert r.status_code == 200, r.text
    assert r.json()["products_updated"] == 1
    assert prod(S["pid"])["brand"] == new
    assert requests.get(f"{API}/products/{S['pid']}", headers=H(tok["admin"])).json().get("brand_logo") == LOGO


def test_rename_category_keeps_id(tok):
    cid = S["cat"]["category_id"]
    r = requests.put(f"{API}/admin/categories/{cid}", headers=H(tok["admin"]), json={"name": f"TEST_KatRen {SUF}"})
    assert r.status_code == 200, r.text
    assert r.json()["category_id"] == cid and r.json()["name"] == f"TEST_KatRen {SUF}"
    assert prod(S["pid"])["category"] == cid
    assert requests.put(f"{API}/admin/categories/{cid}", headers=H(tok["jombang"]), json={"name": "x"}).status_code == 403


def test_delete_category_moves_to_lainnya(tok):
    cid, sid = S["cat"]["category_id"], S["sub"]["category_id"]
    before_real = DB.products.count_documents({"categories": "lainnya"})
    r = requests.delete(f"{API}/admin/categories/{cid}", headers=H(tok["admin"]))
    assert r.status_code == 200, r.text
    assert r.json() == {"deleted": 2, "products_moved": 1}
    S["lainnya_inc"] += 1
    p = prod(S["pid"])
    assert p["category"] == "lainnya" and p["categories"] == ["lainnya"] and p["subcategory"] == ""
    assert not DB.categories.find_one({"category_id": {"$in": [cid, sid]}})
    assert DB.products.count_documents({"categories": "lainnya"}) == before_real + 1  # no real product moved
    assert requests.delete(f"{API}/admin/categories/{cid}", headers=H(tok["admin"])).status_code == 404


def test_delete_brand_empties_products(tok):
    bid = S["brand"]["brand_id"]
    r = requests.delete(f"{API}/admin/brands/{bid}", headers=H(tok["admin"]))
    assert r.status_code == 200, r.text
    assert r.json() == {"deleted": True, "products_updated": 1}
    assert prod(S["pid"])["brand"] == ""
    assert requests.get(f"{API}/admin/brands/{bid}/impact", headers=H(tok["admin"])).status_code == 404
    assert requests.get(f"{API}/products/{S['pid']}", headers=H(tok["admin"])).json().get("brand_logo", "") == ""


def test_real_data_intact():
    assert DB.brands.count_documents({"name": {"$not": {"$regex": "^TEST_"}}}) >= 115
    assert DB.products.count_documents({"brand": {"$nin": [None, ""]}, "name": {"$not": {"$regex": "^TEST_"}}}) == 4607
