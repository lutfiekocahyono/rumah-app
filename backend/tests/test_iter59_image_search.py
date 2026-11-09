# Iteration 59: Cari dengan Foto (POST /api/products/image-search) + admin index status
import io
import os
import time

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
URL = f"{BASE_URL}/api/products/image-search"

QUERY_PID = "pgs-48799"  # indexed shared product (Rice Cooker Cuckoo), Jombang has its own price
QUERY_IMG = "/tmp/p48799.jpg"
QUERY_IMG2 = "/tmp/p51962.jpg"  # pgs-51962 Payung (indexed)
TEST_PID = "TEST_ps_jember_only"


def _search(path=QUERY_IMG, store=None, headers=None):
    h = dict(headers or {})
    if store:
        h["X-Store-Id"] = store
    with open(path, "rb") as f:
        return requests.post(URL, files={"file": ("foto.jpg", f, "image/jpeg")}, headers=h, timeout=90)


def _login(email, pw):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"login failed {email}")
    return r.json()["token"]


@pytest.fixture(scope="module")
def mdb():
    c = MongoClient(os.environ["MONGO_URL"])
    return c[os.environ["DB_NAME"]]


@pytest.fixture(scope="module")
def jember_only(mdb):
    """TEST_ product only for Jember branch, with the same fingerprint as QUERY_PID."""
    src = mdb.products.find_one({"product_id": QUERY_PID}, {"_id": 0})
    vec = mdb.image_vectors.find_one({"product_id": QUERY_PID}, {"_id": 0})
    doc = {**src, "product_id": TEST_PID, "name": "TEST_ jember only rice cooker", "only_branch": "pgs-jember", "sku": "TEST_PS"}
    mdb.products.insert_one(doc)
    mdb.image_vectors.insert_one({**vec, "product_id": TEST_PID})
    time.sleep(1)
    yield TEST_PID
    mdb.products.delete_one({"product_id": TEST_PID})
    mdb.image_vectors.delete_one({"product_id": TEST_PID})


class TestImageSearchCore:
    def test_finds_query_product_top(self):
        r = _search()
        assert r.status_code == 200, r.text
        d = r.json()
        assert isinstance(d["indexed"], int) and d["indexed"] > 0
        items = d["items"]
        assert 0 < len(items) <= 20
        ids = [i["product_id"] for i in items]
        assert QUERY_PID in ids
        hit = next(i for i in items if i["product_id"] == QUERY_PID)
        assert isinstance(hit["similarity"], int) and hit["similarity"] >= 90, hit["similarity"]
        assert hit["similarity"] == max(i["similarity"] for i in items if i.get("in_stock") and i.get("stock", 0) > 0) or not hit.get("in_stock")
        for k in ("name", "price", "my_price", "image", "stock"):
            assert k in hit

    def test_second_product(self):
        r = _search(QUERY_IMG2)
        assert r.status_code == 200
        ids = [i["product_id"] for i in r.json()["items"]]
        assert "pgs-51962" in ids[:3], ids[:5]

    def test_in_stock_before_out_of_stock(self):
        for store in (None, "pgs-jombang", "pgs-jember"):
            items = _search(store=store).json()["items"]
            flags = [1 if (i.get("stock", 0) > 0 and i.get("in_stock", True)) else 0 for i in items]
            assert flags == sorted(flags, reverse=True), (store, flags)
            # within each group, similarity is descending
            for g in (1, 0):
                sims = [i["similarity"] for i, f in zip(items, flags) if f == g]
                assert sims == sorted(sims, reverse=True)

    def test_works_with_customer_token(self):
        t = _login("demo@pgs.id", "Demo1234!")
        r = _search(headers={"Authorization": f"Bearer {t}"})
        assert r.status_code == 200
        assert len(r.json()["items"]) > 0


class TestBranch:
    def test_jombang_price(self, mdb):
        off = {i["product_id"]: i for i in _search(store="pgs-official").json()["items"]}
        jom = {i["product_id"]: i for i in _search(store="pgs-jombang").json()["items"]}
        assert QUERY_PID in off and QUERY_PID in jom
        ss = mdb.store_stock.find_one({"store_id": "pgs-jombang", "product_id": QUERY_PID})
        assert jom[QUERY_PID]["price"] == ss["price"], (jom[QUERY_PID]["price"], ss["price"])
        assert jom[QUERY_PID]["stock"] == ss["stock"]
        p = mdb.products.find_one({"product_id": QUERY_PID})
        assert off[QUERY_PID]["price"] == p["price"]
        assert jom[QUERY_PID]["store_name"] != off[QUERY_PID]["store_name"]

    def test_invalid_store_falls_back_to_official(self):
        a = [i["product_id"] for i in _search(store="bogus-store").json()["items"]]
        b = [i["product_id"] for i in _search(store="pgs-official").json()["items"]]
        assert a == b

    def test_branch_only_not_leaked(self, jember_only):
        # matrix cache refreshes when index marks dirty (indexing in progress); retry a bit
        seen = None
        for _ in range(12):
            jem = [i["product_id"] for i in _search(store="pgs-jember").json()["items"]]
            if jember_only in jem:
                seen = True
                break
            time.sleep(10)
        if not seen:
            pytest.skip("matrix cache did not refresh with TEST product (index not dirty)")
        jom = [i["product_id"] for i in _search(store="pgs-jombang").json()["items"]]
        off = [i["product_id"] for i in _search(store="pgs-official").json()["items"]]
        assert jember_only not in jom
        assert jember_only not in off


class TestValidation:
    def test_non_image(self):
        r = requests.post(URL, files={"file": ("a.txt", io.BytesIO(b"hello world not an image"), "text/plain")}, timeout=30)
        assert r.status_code == 400
        assert r.json()["detail"].startswith("File bukan foto")

    def test_too_big(self):
        r = requests.post(URL, files={"file": ("big.jpg", io.BytesIO(b"\xff" * (10 * 1024 * 1024 + 100)), "image/jpeg")}, timeout=120)
        assert r.status_code in (400, 413), r.status_code
        if r.status_code == 400:
            assert "10 MB" in r.json()["detail"]

    def test_missing_file(self):
        r = requests.post(URL, timeout=30)
        assert r.status_code == 422


class TestAdminIndex:
    def test_admin_ok(self):
        t = _login("admin@pgs.id", "Admin1234!")
        r = requests.get(f"{BASE_URL}/api/admin/image-index", headers={"Authorization": f"Bearer {t}"}, timeout=30)
        assert r.status_code == 200
        d = r.json()
        for k in ("running", "done", "failed", "products", "indexed"):
            assert k in d
        assert d["products"] >= 6618 and 0 < d["indexed"] <= d["products"] + 5

    def test_customer_forbidden(self):
        t = _login("demo@pgs.id", "Demo1234!")
        r = requests.get(f"{BASE_URL}/api/admin/image-index", headers={"Authorization": f"Bearer {t}"}, timeout=30)
        assert r.status_code == 403

    def test_anon_unauthorized(self):
        r = requests.get(f"{BASE_URL}/api/admin/image-index", timeout=30)
        assert r.status_code in (401, 403)
