# PGS iteration 25: product editor Tahap 2 "SEO & Tombol" - seo_title / meta_description / keywords on publish + draft.
import os
import uuid

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
IMG = "https://pusatgrosirsidoarjo.com/wp-content/uploads/2023/07/Cetakan-7-Lubang-Cekung-Suggo-300x300.webp"
DESC = "Deskripsi **tebal** produk uji coba yang cukup panjang untuk validasi.\n- poin satu\n- poin dua"


def _env(k):
    for line in open("/app/backend/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip('"')


DB = MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]
PRODUCTS: list = []
DRAFTS: list = []


def H(t):
    return {"Authorization": f"Bearer {t}"}


def form(**kw):
    base = {"name": f"TEST_SEO {uuid.uuid4().hex[:5]}", "category": "dapur", "subcategory": "peralatan-masak",
            "brand": "TEST", "status": "active", "description": DESC, "images": [IMG],
            "price": 20000, "stock": 20, "weight_grams": 700}
    base.update(kw)
    return base


@pytest.fixture(scope="module")
def tok():
    r = requests.post(f"{API}/auth/login", json={"email": "sidoarjo@pgs.id", "password": "Sidoarjo123!"})
    assert r.status_code == 200, r.text
    t = r.json()["token"]
    yield t
    for pid in PRODUCTS:
        DB.products.delete_one({"product_id": pid, "name": {"$regex": "^TEST_"}})
    for did in DRAFTS:
        requests.delete(f"{API}/product-editor/drafts/{did}", headers=H(t))


def publish(t, data, product_id=None):
    r = requests.post(f"{API}/product-editor/publish", headers=H(t), json={"product_id": product_id, "data": data})
    if r.status_code == 200:
        PRODUCTS.append(r.json()["product_id"])
    return r


# SEO fields persist on publish and come back in the editor API + public product API
class TestSeoPublish:
    def test_seo_persist(self, tok):
        title = "TEST Judul SEO Cetakan Kue " + "x" * 10
        meta = "Meta deskripsi uji coba untuk hasil pencarian Google."
        r = publish(tok, form(seo_title=f"  {title}  ", meta_description=meta,
                              keywords=["cetakan", " cetakan kue ", "cetakan", "  ", "kue"]))
        assert r.status_code == 200, r.text
        pid = r.json()["product_id"]
        d = requests.get(f"{API}/product-editor/products/{pid}", headers=H(tok)).json()["data"]
        assert d["seo_title"] == title
        assert d["meta_description"] == meta
        assert d["keywords"] == ["cetakan", "cetakan kue", "kue"], d["keywords"]
        doc = DB.products.find_one({"product_id": pid}, {"_id": 0, "seo_title": 1, "keywords": 1})
        assert doc["seo_title"] == title

    def test_keywords_dedupe_after_trim(self, tok):
        # "sepatu" and " sepatu " are the same keyword once trimmed
        r = publish(tok, form(keywords=["sepatu", " sepatu ", "Sepatu"]))
        assert r.status_code == 200, r.text
        d = requests.get(f"{API}/product-editor/products/{r.json()['product_id']}", headers=H(tok)).json()["data"]
        assert d["keywords"].count("sepatu") == 1, d["keywords"]

    def test_keywords_dedupe_case_trim_exact(self, tok):
        # iter26: [' Sepatu ','sepatu','SEPATU'] -> ['sepatu'] (strip + lower before dedupe)
        r = publish(tok, form(keywords=[" Sepatu ", "sepatu", "SEPATU", " Sepatu Kets ", "sepatu kets"]))
        assert r.status_code == 200, r.text
        d = requests.get(f"{API}/product-editor/products/{r.json()['product_id']}", headers=H(tok)).json()["data"]
        assert d["keywords"] == ["sepatu", "sepatu kets"], d["keywords"]

    def test_edit_updates_seo(self, tok):
        r = publish(tok, form(seo_title="Awal"))
        pid = r.json()["product_id"]
        r2 = publish(tok, form(seo_title="Diubah", meta_description="Baru", keywords=["a1b"]), product_id=pid)
        assert r2.status_code == 200, r2.text
        d = requests.get(f"{API}/product-editor/products/{pid}", headers=H(tok)).json()["data"]
        assert (d["seo_title"], d["meta_description"], d["keywords"]) == ("Diubah", "Baru", ["a1b"])

    def test_empty_seo_defaults(self, tok):
        r = publish(tok, form())
        d = requests.get(f"{API}/product-editor/products/{r.json()['product_id']}", headers=H(tok)).json()["data"]
        assert d["seo_title"] == "" and d["meta_description"] == "" and d["keywords"] == []

    def test_exact_limits_ok(self, tok):
        r = publish(tok, form(seo_title="a" * 70, meta_description="b" * 160, keywords=[f"k{i}" for i in range(10)]))
        assert r.status_code == 200, r.text

    @pytest.mark.parametrize("kw", [{"seo_title": "a" * 71}, {"meta_description": "b" * 161},
                                    {"keywords": [f"k{i}" for i in range(11)]}])
    def test_over_limit_422(self, tok, kw):
        r = publish(tok, form(**kw))
        assert r.status_code == 422, r.text


# Drafts keep SEO fields
class TestSeoDraft:
    def test_draft_roundtrip(self, tok):
        r = requests.post(f"{API}/product-editor/drafts", headers=H(tok),
                          json={"data": form(seo_title="Draft SEO", meta_description="Meta draft", keywords=["x1", "x2"])})
        assert r.status_code == 200, r.text
        did = r.json()["draft_id"]
        DRAFTS.append(did)
        d = requests.get(f"{API}/product-editor/drafts/{did}", headers=H(tok)).json()["data"]
        assert (d["seo_title"], d["meta_description"], d["keywords"]) == ("Draft SEO", "Meta draft", ["x1", "x2"])

    def test_draft_over_limit_422(self, tok):
        r = requests.post(f"{API}/product-editor/drafts", headers=H(tok), json={"data": form(seo_title="a" * 71)})
        assert r.status_code == 422
