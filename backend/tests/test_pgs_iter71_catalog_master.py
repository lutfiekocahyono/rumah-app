# PGS iteration 71: category delete keeps unrelated categories, Excel import brand rules, /categories includes Lainnya.
import io
import os
import uuid

import pytest
import requests
from openpyxl import Workbook
from pymongo import MongoClient

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
IMG = "https://pusatgrosirsidoarjo.com/wp-content/uploads/2023/07/Cetakan-7-Lubang-Cekung-Suggo-300x300.webp"
DESC = "Deskripsi produk uji coba yang cukup panjang untuk validasi import excel."


def _env(k):
    for line in open("/app/backend/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip('"')


DB = MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]
SUF = uuid.uuid4().hex[:5]
S = {"cats": [], "pids": [], "brands": [], "lainnya_inc": 0, "draft_names": []}


def H(t):
    return {"Authorization": f"Bearer {t}"}


def login(e, p):
    r = requests.post(f"{API}/auth/login", json={"email": e, "password": p})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def tok():
    yield {"admin": login("admin@pgs.id", "Admin1234!"), "jombang": login("jombang@pgs.id", "Jombang123!")}
    for pid in S["pids"]:
        DB.products.delete_one({"product_id": pid, "name": {"$regex": "^TEST_"}})
    for name in S["draft_names"]:
        DB.product_drafts.delete_many({"data.name": name})
    for bid in S["brands"]:
        DB.brands.delete_one({"brand_id": bid, "name": {"$regex": "^TEST_"}})
    for cid in S["cats"]:
        DB.categories.delete_one({"category_id": cid, "source": "admin"})
    if S["lainnya_inc"]:
        DB.categories.update_one({"category_id": "lainnya"}, {"$inc": {"count": -S["lainnya_inc"]}})


def cat(t, name, parent=None):
    r = requests.post(f"{API}/admin/categories", headers=H(t), json={"name": name, "parent": parent})
    assert r.status_code == 200, r.text
    S["cats"].append(r.json()["category_id"])
    return r.json()["category_id"]


def mkprod(key, category, sub, cats):
    pid = f"TEST_p71_{SUF}_{key}"
    DB.products.insert_one({"product_id": pid, "name": f"TEST_P71 {key} {SUF}", "store_id": "pgs-official", "status": "inactive",
                            "category": category, "subcategory": sub, "categories": cats, "brand": "", "price": 1000, "stock": 0})
    S["pids"].append(pid)
    return pid


def prod(pid):
    return DB.products.find_one({"product_id": pid}, {"_id": 0, "category": 1, "subcategory": 1, "categories": 1})


# ---- /categories includes Lainnya ----
def test_categories_include_lainnya():
    top = requests.get(f"{API}/categories").json()
    assert "lainnya" in [c["category_id"] for c in top]
    allc = requests.get(f"{API}/categories", params={"all": True}).json()
    assert "lainnya" in [c["category_id"] for c in allc] and len(allc) >= 81


# ---- category delete keeps unrelated categories ----
def test_category_delete_multi(tok):
    t = tok["admin"]
    A = cat(t, f"TEST_A71 {SUF}")
    A1 = cat(t, f"TEST_A71s {SUF}", A)
    B = cat(t, f"TEST_B71 {SUF}")
    B1 = cat(t, f"TEST_B71s {SUF}", B)
    p1 = mkprod("1", A, A1, [A, A1, B])
    p2 = mkprod("2", A, A1, [A, A1])
    p3 = mkprod("3", B, "", [B, A])
    p4 = mkprod("4", A, "", [A])
    p5 = mkprod("5", B, B1, [B, B1, A])
    p6 = mkprod("6", A, "", [])
    imp = requests.get(f"{API}/admin/categories/{A1}/impact", headers=H(t)).json()
    assert imp == {"products": 2, "subcategories": 0}, imp
    r = requests.delete(f"{API}/admin/categories/{A1}", headers=H(t))
    assert r.status_code == 200, r.text
    assert r.json()["products_moved"] == 1  # iter72: only products that really land in Lainnya (p2)
    S["lainnya_inc"] += 1
    assert prod(p1) == {"category": B, "subcategory": "", "categories": [B]}, prod(p1)
    assert prod(p2) == {"category": "lainnya", "subcategory": "", "categories": ["lainnya"]}, prod(p2)
    assert prod(p3)["categories"] == [B, A] and prod(p4)["categories"] == [A]  # untouched
    r = requests.delete(f"{API}/admin/categories/{A}", headers=H(t))
    assert r.status_code == 200, r.text
    S["lainnya_inc"] += r.json()["products_moved"]
    assert prod(p3) == {"category": B, "subcategory": "", "categories": [B]}, prod(p3)
    assert prod(p4) == {"category": "lainnya", "subcategory": "", "categories": ["lainnya"]}, prod(p4)
    assert prod(p5) == {"category": B, "subcategory": B1, "categories": [B, B1]}, prod(p5)
    assert prod(p6) == {"category": "lainnya", "subcategory": "", "categories": ["lainnya"]}, prod(p6)
    assert prod(p1)["categories"] == [B]


# ---- Excel import brand rules ----
def xlsx(name, brand):
    wb = Workbook()
    ws = wb.active
    ws.title = "Produk"
    ws.append(["ID Produk (jangan diubah)", "SKU", "Nama Produk*", "Kategori*", "Merek", "Status (aktif/nonaktif)", "Harga Normal*",
               "Stok", "Berat (gram)*", "URL Foto* (pisahkan dengan baris baru)", "Deskripsi* (min. 30 karakter)"])
    ws.append(["", f"T71{SUF}", name, "dapur", brand, "nonaktif", 10000, 5, 500, IMG, DESC])
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def imp(t, data, commit):
    return requests.post(f"{API}/product-editor/import", headers=H(t), params={"commit": str(commit).lower()},
                         files={"file": ("f.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})


def brand_names():
    return [b["name"].lower() for b in requests.get(f"{API}/brands").json()]


def test_import_branch_admin_unknown_brand(tok):  # iter72: saved as Tanpa merek (create), brand not added
    brand, name = f"TEST_JBrand{SUF}", f"TEST_P71J {SUF}"
    S["draft_names"].append(name)
    for commit in (False, True):
        r = imp(tok["jombang"], xlsx(name, brand), commit)
        assert r.status_code == 200, r.text
        rows = r.json()["rows"]
        assert f"Merek “{brand}” belum ada di daftar, disimpan sebagai Tanpa merek" in rows[0]["message"], rows
        assert rows[0]["action"] == "create", rows
        assert brand.lower() not in brand_names()
    assert not DB.brands.find_one({"name": brand})
    p = DB.products.find_one({"name": name}, {"_id": 0, "product_id": 1, "brand": 1})
    if p:
        S["pids"].append(p["product_id"])
    assert p and p["brand"] == ""


def test_import_super_admin_brand(tok):
    brand, name = f"TEST_SBrand{SUF}", f"TEST_P71S {SUF}"
    r = imp(tok["admin"], xlsx(name, brand), False)
    assert r.status_code == 200, r.text
    assert brand.lower() not in brand_names()  # preview never adds brands
    r = imp(tok["admin"], xlsx(name, brand), True)
    assert r.status_code == 200, r.text
    p = DB.products.find_one({"name": name}, {"_id": 0, "product_id": 1, "brand": 1})
    b = DB.brands.find_one({"name": brand}, {"_id": 0})
    if p:
        S["pids"].append(p["product_id"])
    if b:
        S["brands"].append(b["brand_id"])
    assert r.json()["rows"][0]["action"] == "create", r.json()["rows"]
    assert b and p and p["brand"] == brand
    assert brand.lower() in brand_names()


def test_real_data_intact():
    assert DB.brands.count_documents({"name": {"$not": {"$regex": "^TEST_"}}}) == 115
    assert DB.products.count_documents({"brand": {"$nin": [None, ""]}, "name": {"$not": {"$regex": "^TEST_"}}}) == 4607
    assert DB.products.count_documents({"$or": [{"category": "lainnya"}, {"categories": "lainnya"}], "name": {"$not": {"$regex": "^TEST_"}}}) == 215
