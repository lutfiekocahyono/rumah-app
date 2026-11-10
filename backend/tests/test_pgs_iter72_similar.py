# PGS iteration 72: Produk Serupa (auto + manual Super Admin / branch override) and Excel import unknown brand -> Tanpa merek.
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
TARGET = "pgs-10062"  # Suggo Panci Set (peralatan-masak), has Jombang branch price


def _env(k):
    for line in open("/app/backend/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip('"')


DB = MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]
SUF = uuid.uuid4().hex[:5]
S = {"pids": [], "names": []}


def H(t, store=None):
    h = {"Authorization": f"Bearer {t}"} if t else {}
    if store:
        h["X-Store-Id"] = store
    return h


def login(e, p):
    r = requests.post(f"{API}/auth/login", json={"email": e, "password": p})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def tok():
    t = {"admin": login("admin@pgs.id", "Admin1234!"), "jombang": login("jombang@pgs.id", "Jombang123!"),
         "jember": login("jember@pgs.id", "Jember123!")}
    yield t
    for k in ("admin", "jombang", "jember"):  # clean manual lists
        requests.put(f"{API}/product-editor/similar/{TARGET}", headers=H(t[k]), json={"items": []})
    for pid in S["pids"]:
        DB.products.delete_one({"product_id": pid, "name": {"$regex": "^TEST_"}})
        for c in ("price_history", "product_events", "product_history"):
            DB[c].delete_many({"product_id": pid})
    for n in S["names"]:
        DB.product_drafts.delete_many({"data.name": n})


def sim(store):
    r = requests.get(f"{API}/products/{TARGET}/similar", headers=H(None, store))
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def pool():
    ids = [p["product_id"] for p in sim("pgs-official")["items"]]
    assert len(ids) >= 6
    return ids


# ---- public similar endpoint: auto mode ----
class TestAuto:
    def test_auto_official(self, pool):
        d = sim("pgs-official")
        assert d["mode"] == "auto"
        assert 0 < len(d["items"]) <= 12
        assert TARGET not in [p["product_id"] for p in d["items"]]
        cats = [DB.products.find_one({"product_id": p["product_id"]}, {"categories": 1}).get("categories") for p in d["items"]]
        assert all("peralatan-masak" in (c or []) for c in cats), cats

    def test_auto_jombang_branch_price(self):
        d = sim("pgs-jombang")
        assert d["mode"] == "auto" and len(d["items"]) <= 12
        checked = 0
        for p in d["items"]:
            ss = DB.store_stock.find_one({"store_id": "pgs-jombang", "product_id": p["product_id"], "price": {"$gt": 0}})
            if ss and not DB.products.find_one({"product_id": p["product_id"]}, {"variants": 1}).get("variants"):
                assert p["price"] == ss["price"], (p["product_id"], p["price"], ss["price"])
                checked += 1
        assert checked > 0

    def test_404(self):
        r = requests.get(f"{API}/products/nope_{SUF}/similar")
        assert r.status_code == 404


# ---- editor endpoints + resolution ----
class TestManual:
    def test_unauth(self):
        assert requests.get(f"{API}/product-editor/similar/{TARGET}").status_code == 401
        assert requests.put(f"{API}/product-editor/similar/{TARGET}", json={"items": []}).status_code == 401

    def test_admin_save_and_resolution(self, tok, pool):
        a, b, c = pool[3], pool[1], pool[5]
        r = requests.put(f"{API}/product-editor/similar/{TARGET}", headers=H(tok["admin"]),
                         json={"items": [a, "invalid_xyz", b, TARGET, a, c]})
        assert r.status_code == 200, r.text
        assert r.json()["scope"] == "all"
        assert [i["product_id"] for i in r.json()["items"]] == [a, b, c]
        g = requests.get(f"{API}/product-editor/similar/{TARGET}", headers=H(tok["admin"])).json()
        assert g["scope"] == "all" and [i["product_id"] for i in g["items"]] == [a, b, c] and g["inherited"] is None
        for st in ("pgs-official", "pgs-jombang", "pgs-jember"):
            d = sim(st)
            assert d["mode"] == "manual" and [p["product_id"] for p in d["items"]] == [a, b, c], (st, d["mode"])

    def test_jombang_inherited_and_override(self, tok, pool):
        a, b, c = pool[3], pool[1], pool[5]
        g = requests.get(f"{API}/product-editor/similar/{TARGET}", headers=H(tok["jombang"])).json()
        assert g["scope"] == "pgs-jombang" and g["items"] == []
        assert [i["product_id"] for i in g["inherited"]] == [a, b, c]
        d, e = pool[0], pool[2]
        r = requests.put(f"{API}/product-editor/similar/{TARGET}", headers=H(tok["jombang"]), json={"items": [e, d]})
        assert r.status_code == 200 and r.json()["scope"] == "pgs-jombang"
        assert [p["product_id"] for p in sim("pgs-jombang")["items"]] == [e, d]
        assert [p["product_id"] for p in sim("pgs-jember")["items"]] == [a, b, c]
        assert [p["product_id"] for p in sim("pgs-official")["items"]] == [a, b, c]
        g = requests.get(f"{API}/product-editor/similar/{TARGET}", headers=H(tok["jombang"])).json()
        assert [i["product_id"] for i in g["items"]] == [e, d] and g["inherited"] is None
        j = requests.get(f"{API}/product-editor/similar/{TARGET}", headers=H(tok["jember"])).json()
        assert j["scope"] == "pgs-jember" and [i["product_id"] for i in j["inherited"]] == [a, b, c]

    def test_jombang_jombang_list_prices_branch(self, tok):
        for p in sim("pgs-jombang")["items"]:
            ss = DB.store_stock.find_one({"store_id": "pgs-jombang", "product_id": p["product_id"], "price": {"$gt": 0}})
            if ss and not DB.products.find_one({"product_id": p["product_id"]}, {"variants": 1}).get("variants"):
                assert p["price"] == ss["price"]

    def test_empty_falls_back(self, tok, pool):
        a, b, c = pool[3], pool[1], pool[5]
        r = requests.put(f"{API}/product-editor/similar/{TARGET}", headers=H(tok["jombang"]), json={"items": []})
        assert r.status_code == 200 and r.json()["items"] == []
        assert [p["product_id"] for p in sim("pgs-jombang")["items"]] == [a, b, c]
        r = requests.put(f"{API}/product-editor/similar/{TARGET}", headers=H(tok["admin"]), json={"items": []})
        assert r.status_code == 200
        for st in ("pgs-official", "pgs-jombang"):
            assert sim(st)["mode"] == "auto"
        assert DB.similar_products.count_documents({"product_id": TARGET}) == 0

    def test_put_too_many_and_404(self, tok, pool):
        r = requests.put(f"{API}/product-editor/similar/{TARGET}", headers=H(tok["admin"]), json={"items": [f"x{i}" for i in range(31)]})
        assert r.status_code == 422
        r = requests.put(f"{API}/product-editor/similar/nope_{SUF}", headers=H(tok["admin"]), json={"items": [pool[0]]})
        assert r.status_code == 404


# ---- Excel import: branch admin unknown brand -> Tanpa merek ----
def xlsx(name, brand, pid=""):
    wb = Workbook()
    ws = wb.active
    ws.title = "Produk"
    ws.append(["ID Produk (jangan diubah)", "SKU", "Nama Produk*", "Kategori*", "Merek", "Status (aktif/nonaktif)", "Harga Normal*",
               "Stok", "Berat (gram)*", "URL Foto* (pisahkan dengan baris baru)", "Deskripsi* (min. 30 karakter)"])
    ws.append([pid, f"T72{SUF}", name, "dapur", brand, "nonaktif", 10000, 5, 500, IMG, DESC])
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def imp(t, data, commit):
    return requests.post(f"{API}/product-editor/import", headers=H(t), params={"commit": str(commit).lower()},
                         files={"file": ("f.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})


def brand_names():
    return [b["name"].lower() for b in requests.get(f"{API}/brands").json()]


class TestImport:
    def test_create_unknown_brand_jombang(self, tok):
        brand, name = f"TEST_JB72{SUF}", f"TEST_P72J {SUF}"
        S["names"].append(name)
        note = f"Merek “{brand}” belum ada di daftar, disimpan sebagai Tanpa merek"
        for commit in (False, True):
            r = imp(tok["jombang"], xlsx(name, brand), commit)
            assert r.status_code == 200, r.text
            rows = r.json()["rows"]
            assert rows[0]["action"] == "create", rows
            assert note in rows[0]["message"], rows
            assert brand.lower() not in brand_names()
        p = DB.products.find_one({"name": name}, {"_id": 0})
        assert p, "product not created"
        S["pids"].append(p["product_id"])
        assert p["brand"] == "" and p["store_id"] == "pgs-jombang"
        assert not DB.product_drafts.find_one({"data.name": name})
        assert not DB.brands.find_one({"name": brand})

    def test_update_unknown_brand_jombang(self, tok):
        name = f"TEST_P72J {SUF}"
        p = DB.products.find_one({"name": name}, {"_id": 0, "product_id": 1})
        if not p:
            pytest.skip("create test failed")
        brand = f"TEST_JU72{SUF}"
        r = imp(tok["jombang"], xlsx(name + " v2", brand, p["product_id"]), True)
        assert r.status_code == 200, r.text
        rows = r.json()["rows"]
        assert rows[0]["action"] == "update", rows
        assert f"Merek “{brand}” belum ada di daftar, disimpan sebagai Tanpa merek" in rows[0]["message"]
        d = DB.products.find_one({"product_id": p["product_id"]}, {"_id": 0, "name": 1, "brand": 1})
        assert d["name"] == name + " v2" and d["brand"] == ""
        assert brand.lower() not in brand_names()
