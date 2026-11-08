# PGS iteration 23: Seller Center product editor (context/upload/drafts/publish/validation) + purchasable variants in cart/checkout.
import io
import os
import uuid

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
IMG = "https://pusatgrosirsidoarjo.com/wp-content/uploads/2023/07/Cetakan-7-Lubang-Cekung-Suggo-300x300.webp"
STORE = "pgs-official"
DESC = "Deskripsi **tebal** produk uji coba yang cukup panjang untuk validasi.\n- poin satu\n- poin dua"


def _env(k):
    for line in open("/app/backend/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip('"')


DB = MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]
CRED = {"sidoarjo": ("sidoarjo@pgs.id", "Sidoarjo123!"), "admin": ("admin@pgs.id", "Admin1234!"),
        "jombang": ("jombang@pgs.id", "Jombang123!")}
PRODUCTS: list = []
ORDERS: list = []
DRAFTS: list = []


def H(t, store=None):
    h = {"Authorization": f"Bearer {t}"}
    if store:
        h["X-Store-Id"] = store
    return h


def form(**kw):
    base = {"name": f"TEST_Produk {uuid.uuid4().hex[:5]}", "category": "dapur", "subcategory": "peralatan-masak",
            "brand": "TEST", "sku": "TSKU", "condition": "new", "status": "active", "description": DESC,
            "images": [IMG], "price": 20000, "discount_price": 15000, "stock": 10, "min_order": 1, "max_order": 0}
    base.update(kw)
    return base


def variant_form(**kw):
    opts = [{"name": "Warna", "values": ["Merah", "Biru"]}, {"name": "Ukuran", "values": ["M"]}]
    rows = [{"values": ["Merah", "M"], "price": 12000, "stock": 5, "sku": "R-M", "active": True},
            {"values": ["Biru", "M"], "price": 14000, "stock": 3, "sku": "B-M", "active": True}]
    return form(variants_enabled=True, variant_options=opts, variants=rows, **kw)


@pytest.fixture(scope="module")
def tok():
    t = {}
    for k, (e, p) in CRED.items():
        r = requests.post(f"{API}/auth/login", json={"email": e, "password": p})
        assert r.status_code == 200, r.text
        t[k] = r.json()["token"]
    yield t
    for oid in ORDERS:
        o = DB.orders.find_one({"order_id": oid}, {"status": 1})
        if o and o["status"] != "cancelled":
            requests.put(f"{API}/admin/orders/{oid}/status", headers=H(t["admin"]), json={"status": "cancelled"})
    for pid in PRODUCTS:
        DB.products.delete_one({"product_id": pid, "name": {"$regex": "^TEST_"}})
    for did in DRAFTS:
        DB.product_drafts.delete_one({"draft_id": did})


@pytest.fixture(scope="module")
def buyer():
    r = requests.post(f"{API}/auth/register", json={"email": f"test_pe23_{uuid.uuid4().hex[:8]}@example.com",
                                                    "password": "TestPass123!", "name": "TEST PE23"})
    assert r.status_code == 200, r.text
    t = r.json()["token"]
    yield t
    requests.delete(f"{API}/cart", headers=H(t))


def publish(t, data, **kw):
    r = requests.post(f"{API}/product-editor/publish", headers=H(t), json={"data": data, **kw})
    if r.status_code == 200:
        PRODUCTS.append(r.json()["product_id"])
    return r


# ---------- context / upload ----------
class TestContextUpload:
    def test_context_seller_own_store(self, tok):
        d = requests.get(f"{API}/product-editor/context", headers=H(tok["sidoarjo"])).json()
        assert d["admin"] is False and [s["store_id"] for s in d["stores"]] == [STORE]
        assert d["limits"]["video_mb"] == 50

    def test_context_admin_all_stores(self, tok):
        d = requests.get(f"{API}/product-editor/context", headers=H(tok["admin"])).json()
        assert d["admin"] is True and len(d["stores"]) >= 3 and d["stores"][0]["store_id"] in ("pgs-official", "pgs-jombang", "pgs-jember")

    def test_context_customer_forbidden(self, buyer):
        assert requests.get(f"{API}/product-editor/context", headers=H(buyer)).status_code == 403

    def test_upload_rejects_bad_type_and_size(self, tok):
        r = requests.post(f"{API}/product-editor/upload", headers=H(tok["sidoarjo"]), files={"file": ("a.gif", b"GIF89a", "image/gif")})
        assert r.status_code == 400
        big = io.BytesIO(b"0" * (8 * 1024 * 1024 + 10))
        r = requests.post(f"{API}/product-editor/upload", headers=H(tok["sidoarjo"]), files={"file": ("a.jpg", big, "image/jpeg")})
        assert r.status_code == 400 and "8 MB" in r.json()["detail"]

    def test_upload_png_ok(self, tok):
        png = bytes.fromhex("89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C4890000000D49444154789C6360000002000154A24F5D0000000049454E44AE426082")
        r = requests.post(f"{API}/product-editor/upload", headers=H(tok["sidoarjo"]), files={"file": ("t.png", png, "image/png")})
        assert r.status_code == 200, r.text
        assert r.json()["url"].startswith("/api/files/") and r.json()["kind"] == "image"
        assert requests.get(f"{BASE_URL}{r.json()['url']}").status_code == 200

    def test_upload_mp4_ok(self, tok):
        r = requests.post(f"{API}/product-editor/upload", headers=H(tok["sidoarjo"]), files={"file": ("v.mp4", b"\x00" * 2048, "video/mp4")})
        assert r.status_code == 200, r.text
        assert r.json()["kind"] == "video"


# ---------- drafts ----------
class TestDrafts:
    def test_draft_crud(self, tok):
        h = H(tok["sidoarjo"])
        r = requests.post(f"{API}/product-editor/drafts", headers=h, json={"data": {"name": "TEST_draft"}})
        assert r.status_code == 200, r.text
        did = r.json()["draft_id"]
        DRAFTS.append(did)
        r = requests.post(f"{API}/product-editor/drafts", headers=h, json={"draft_id": did, "data": {"name": "TEST_draft2", "price": 5000}})
        assert r.json()["draft_id"] == did
        assert any(d["draft_id"] == did for d in requests.get(f"{API}/product-editor/drafts", headers=h).json())
        g = requests.get(f"{API}/product-editor/drafts/{did}", headers=h).json()
        assert g["data"]["name"] == "TEST_draft2" and g["data"]["price"] == 5000
        # other seller cannot see it
        assert requests.get(f"{API}/product-editor/drafts/{did}", headers=H(tok["jombang"])).status_code == 404
        assert requests.delete(f"{API}/product-editor/drafts/{did}", headers=h).status_code == 200
        assert requests.get(f"{API}/product-editor/drafts/{did}", headers=h).status_code == 404


# ---------- publish / validation ----------
class TestPublish:
    def test_publish_empty_returns_errors(self, tok):
        r = publish(tok["sidoarjo"], {"name": "abc", "price": 50, "discount_price": 60, "min_order": 5, "max_order": 2, "description": "short"})
        assert r.status_code == 422
        e = r.json()["detail"]["errors"]
        for k in ("name", "category", "images", "description", "price", "max_order"):
            assert k in e, e

    def test_discount_ge_price(self, tok):
        r = publish(tok["sidoarjo"], form(price=10000, discount_price=10000))
        assert r.status_code == 422 and "discount_price" in r.json()["detail"]["errors"]

    def test_variant_price_low(self, tok):
        f = variant_form()
        f["variants"][0]["price"] = 50
        r = publish(tok["sidoarjo"], f)
        assert r.status_code == 422 and "variant.Merah/M.price" in r.json()["detail"]["errors"]

    def test_publish_edit_and_inactive(self, tok):
        r = publish(tok["sidoarjo"], form())
        assert r.status_code == 200, r.text
        pid = r.json()["product_id"]
        p = requests.get(f"{API}/products/{pid}").json()
        assert p["price"] == 15000 and p["original_price"] == 20000 and p["store_id"] == STORE
        e = requests.get(f"{API}/product-editor/products/{pid}", headers=H(tok["sidoarjo"])).json()
        assert e["data"]["price"] == 20000 and e["data"]["discount_price"] == 15000
        assert requests.get(f"{API}/product-editor/products/{pid}", headers=H(tok["jombang"])).status_code == 404
        f = e["data"]
        f["status"] = "inactive"
        f["name"] = f["name"] + " edit"
        r = publish(tok["sidoarjo"], f, product_id=pid)
        assert r.status_code == 200 and r.json()["product_id"] == pid
        assert requests.get(f"{API}/products/{pid}").status_code == 404
        lst = requests.get(f"{API}/products", params={"q": "TEST_Produk"}).json()
        assert pid not in [x["product_id"] for x in lst]

    def test_admin_publish_to_store(self, tok):
        r = publish(tok["admin"], form(), store_id="pgs-jombang")
        assert r.status_code == 200, r.text
        assert r.json()["store_id"] == "pgs-jombang"

    def test_seller_existing_product_not_editable(self, tok):
        assert requests.get(f"{API}/product-editor/products/pgs-9957", headers=H(tok["jombang"])).status_code == 404


# ---------- variants purchase ----------
class TestVariants:
    @pytest.fixture(scope="class")
    def vp(self, tok):
        r = publish(tok["sidoarjo"], variant_form(min_order=2, max_order=3))
        assert r.status_code == 200, r.text
        pid = r.json()["product_id"]
        p = requests.get(f"{API}/products/{pid}").json()
        return p

    def test_product_has_variants(self, vp):
        assert len(vp["variants"]) == 2 and vp["price"] == 12000 and vp["stock"] == 8
        assert vp["variant_options"][0]["name"] == "Warna"

    def test_add_without_variant(self, buyer, vp):
        r = requests.post(f"{API}/cart/items", headers=H(buyer, STORE), json={"product_id": vp["product_id"], "quantity": 1})
        assert r.status_code == 400 and "Pilih variasi" in r.json()["detail"]

    def test_inventory_put_blocked(self, tok, vp):
        r = requests.put(f"{API}/seller/inventory/{vp['product_id']}", headers=H(tok["sidoarjo"]), json={"stock": 5})
        assert r.status_code == 400

    def test_variant_cart_checkout_restock(self, tok, buyer, vp):
        pid = vp["product_id"]
        blue = next(v for v in vp["variants"] if v["values"][0] == "Biru")
        key = f"{pid}::{blue['variant_id']}"
        requests.delete(f"{API}/cart", headers=H(buyer))
        r = requests.post(f"{API}/cart/items", headers=H(buyer, STORE), json={"product_id": pid, "variant_id": blue["variant_id"], "quantity": 1})
        assert r.status_code == 200, r.text
        line = next(i for i in r.json()["items"] if i["key"] == key)
        assert line["price"] == 14000 and line["stock"] == 3 and line["variant_name"] == "Biru / M"
        # max_order caps
        r = requests.put(f"{API}/cart/items/{key}", headers=H(buyer), json={"quantity": 10})
        line = next(i for i in r.json()["items"] if i["key"] == key)
        assert line["quantity"] == 3, line
        # min_order enforced
        requests.put(f"{API}/cart/items/{key}", headers=H(buyer), json={"quantity": 1})
        body = {"full_name": "TEST Buyer", "phone": "081234567890", "payment_method": "cod", "store_id": STORE, "courier": "pickup"}
        r = requests.post(f"{API}/checkout", headers=H(buyer), json=body)
        assert r.status_code == 400 and "Minimal" in r.json()["detail"], r.text
        requests.put(f"{API}/cart/items/{key}", headers=H(buyer), json={"quantity": 2})
        r = requests.post(f"{API}/checkout", headers=H(buyer), json=body)
        assert r.status_code == 200, r.text
        o = r.json()
        ORDERS.append(o["order_id"])
        assert o["items"][0]["variant_id"] == blue["variant_id"] and o["items"][0]["variant_name"] == "Biru / M"
        p = requests.get(f"{API}/products/{pid}").json()
        assert next(v for v in p["variants"] if v["variant_id"] == blue["variant_id"])["stock"] == 1 and p["stock"] == 6
        r = requests.put(f"{API}/admin/orders/{o['order_id']}/status", headers=H(tok["admin"]), json={"status": "cancelled"})
        assert r.status_code == 200
        p = requests.get(f"{API}/products/{pid}").json()
        assert next(v for v in p["variants"] if v["variant_id"] == blue["variant_id"])["stock"] == 3 and p["stock"] == 8

    def test_variant_delete_line(self, buyer, vp):
        red = next(v for v in vp["variants"] if v["values"][0] == "Merah")
        key = f"{vp['product_id']}::{red['variant_id']}"
        r = requests.post(f"{API}/cart/items", headers=H(buyer, STORE), json={"product_id": vp["product_id"], "variant_id": red["variant_id"], "quantity": 2})
        assert any(i["key"] == key for i in r.json()["items"])
        r = requests.delete(f"{API}/cart/items/{key}", headers=H(buyer))
        assert not any(i["key"] == key for i in r.json()["items"])

    def test_regular_product_cart_regression(self, buyer):
        r = requests.post(f"{API}/cart/items", headers=H(buyer, STORE), json={"product_id": "pgs-9955", "quantity": 1})
        assert r.status_code == 200, r.text
        line = next(i for i in r.json()["items"] if i["product_id"] == "pgs-9955")
        assert line["key"] == "pgs-9955" and line["variant_id"] is None
        r = requests.put(f"{API}/cart/items/pgs-9955", headers=H(buyer), json={"quantity": 2})
        assert next(i for i in r.json()["items"] if i["key"] == "pgs-9955")["quantity"] == 2
        r = requests.delete(f"{API}/cart/items/pgs-9955", headers=H(buyer))
        assert not any(i["key"] == "pgs-9955" for i in r.json()["items"])
