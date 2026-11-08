# PGS iteration 37: Balasan Cepat Toko (seller quick replies) CRUD, seeding once, store isolation, buyer 403.
import os

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"


def _env(k):
    for line in open("/app/backend/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip('"')


DB = MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]
CREATED_JOMBANG = []
JEMBER_WAS_SEEDED = bool(DB.quick_replies_seeded.find_one({"_id": "pgs-jember"})) or DB.quick_replies.count_documents({"store_id": "pgs-jember"}) > 0


def _login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=20)
    if r.status_code != 200:
        pytest.skip(f"login failed for {email}: {r.status_code}")
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def jombang():
    return _login("jombang@pgs.id", "Jombang123!")


@pytest.fixture(scope="module")
def jember():
    return _login("jember@pgs.id", "Jember123!")


@pytest.fixture(scope="module")
def demo():
    return _login("demo@pgs.id", "Demo1234!")


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    if CREATED_JOMBANG:
        DB.quick_replies.delete_many({"reply_id": {"$in": CREATED_JOMBANG}, "store_id": "pgs-jombang"})
    if not JEMBER_WAS_SEEDED:  # jember was untouched before this run -> restore pristine state
        DB.quick_replies.delete_many({"store_id": "pgs-jember"})
        DB.quick_replies_seeded.delete_one({"_id": "pgs-jember"})


# ---- auth / role
class TestAccess:
    def test_buyer_forbidden(self, demo):
        assert requests.get(f"{API}/seller/quick-replies", headers=demo, timeout=20).status_code == 403
        assert requests.post(f"{API}/seller/quick-replies", json={"title": "x", "text": "y"}, headers=demo, timeout=20).status_code == 403

    def test_anon_unauthorized(self):
        assert requests.get(f"{API}/seller/quick-replies", timeout=20).status_code in (401, 403)


# ---- seeding once (jember, fresh store)
class TestSeedOnce:
    def test_seed_defaults(self, jember):
        if JEMBER_WAS_SEEDED:
            pytest.skip("jember already seeded before run")
        r = requests.get(f"{API}/seller/quick-replies", headers=jember, timeout=20)
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert [i["title"] for i in items] == ["Stok tersedia", "Stok habis", "Harga grosir", "Jam ambil di toko", "Ongkir"]
        assert all("_id" not in i and "store_id" not in i and i["reply_id"].startswith("qr_") for i in items)
        assert "{produk}" in items[0]["text"] and "{toko}" in items[0]["text"]
        # second GET -> same 5, no duplicates
        r2 = requests.get(f"{API}/seller/quick-replies", headers=jember, timeout=20).json()["items"]
        assert [i["reply_id"] for i in r2] == [i["reply_id"] for i in items]
        assert DB.quick_replies.count_documents({"store_id": "pgs-jember"}) == 5

    def test_delete_all_no_reseed(self, jember):
        if JEMBER_WAS_SEEDED:
            pytest.skip("jember already seeded before run")
        items = requests.get(f"{API}/seller/quick-replies", headers=jember, timeout=20).json()["items"]
        for i in items:
            assert requests.delete(f"{API}/seller/quick-replies/{i['reply_id']}", headers=jember, timeout=20).status_code == 200
        r = requests.get(f"{API}/seller/quick-replies", headers=jember, timeout=20)
        assert r.status_code == 200 and r.json()["items"] == []


# ---- CRUD (jombang) + isolation
class TestCrud:
    def test_validation(self, jombang):
        for body in ({"title": "", "text": "x"}, {"title": "x", "text": ""}, {"title": "a" * 41, "text": "x"}, {"title": "x", "text": "a" * 1001}, {"title": "x"}):
            r = requests.post(f"{API}/seller/quick-replies", json=body, headers=jombang, timeout=20)
            assert r.status_code == 422, (body, r.status_code)

    def test_whitespace_only(self, jombang):
        r = requests.post(f"{API}/seller/quick-replies", json={"title": "   ", "text": "   "}, headers=jombang, timeout=20)
        if r.status_code == 200:
            CREATED_JOMBANG.append(r.json()["reply_id"])
        print("whitespace-only POST ->", r.status_code, r.text[:200])
        assert r.status_code in (400, 422), "whitespace-only title/text accepted (stored empty after strip)"

    def test_add_edit_delete(self, jombang, jember):
        before = requests.get(f"{API}/seller/quick-replies", headers=jombang, timeout=20).json()["items"]
        r = requests.post(f"{API}/seller/quick-replies", json={"title": "  TEST_Grosir40  ", "text": " TEST_ halo {produk} di {toko} "}, headers=jombang, timeout=20)
        assert r.status_code == 200, r.text
        q = r.json()
        CREATED_JOMBANG.append(q["reply_id"])
        assert q["title"] == "TEST_Grosir40" and q["text"] == "TEST_ halo {produk} di {toko}" and "store_id" not in q and "_id" not in q
        assert q["order"] > max([i["order"] for i in before], default=-1)
        lst = requests.get(f"{API}/seller/quick-replies", headers=jombang, timeout=20).json()["items"]
        assert lst[-1]["reply_id"] == q["reply_id"]
        # max lengths accepted
        r = requests.post(f"{API}/seller/quick-replies", json={"title": "a" * 40, "text": "b" * 1000}, headers=jombang, timeout=20)
        assert r.status_code == 200
        CREATED_JOMBANG.append(r.json()["reply_id"])
        # edit
        r = requests.put(f"{API}/seller/quick-replies/{q['reply_id']}", json={"title": "TEST_Edited", "text": "TEST_ edited"}, headers=jombang, timeout=20)
        assert r.status_code == 200 and r.json()["title"] == "TEST_Edited"
        got = next(i for i in requests.get(f"{API}/seller/quick-replies", headers=jombang, timeout=20).json()["items"] if i["reply_id"] == q["reply_id"])
        assert got["text"] == "TEST_ edited"
        assert requests.put(f"{API}/seller/quick-replies/{q['reply_id']}", json={"title": "", "text": "x"}, headers=jombang, timeout=20).status_code == 422
        # other store cannot touch
        assert requests.put(f"{API}/seller/quick-replies/{q['reply_id']}", json={"title": "hack", "text": "hack"}, headers=jember, timeout=20).status_code == 404
        assert requests.delete(f"{API}/seller/quick-replies/{q['reply_id']}", headers=jember, timeout=20).status_code == 404
        assert all(i["reply_id"] != q["reply_id"] for i in requests.get(f"{API}/seller/quick-replies", headers=jember, timeout=20).json()["items"])
        assert DB.quick_replies.find_one({"reply_id": q["reply_id"]})["title"] == "TEST_Edited"
        # delete
        assert requests.delete(f"{API}/seller/quick-replies/{q['reply_id']}", headers=jombang, timeout=20).status_code == 200
        assert requests.delete(f"{API}/seller/quick-replies/{q['reply_id']}", headers=jombang, timeout=20).status_code == 404
        assert all(i["reply_id"] != q["reply_id"] for i in requests.get(f"{API}/seller/quick-replies", headers=jombang, timeout=20).json()["items"])

    def test_unknown_id_404(self, jombang):
        assert requests.put(f"{API}/seller/quick-replies/qr_nope", json={"title": "a", "text": "b"}, headers=jombang, timeout=20).status_code == 404
        assert requests.delete(f"{API}/seller/quick-replies/qr_nope", headers=jombang, timeout=20).status_code == 404
