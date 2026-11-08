# Iteration 20: Homepage sections (Populer / Terbaru / Rekomendasi) per-branch rules, pins, newest window, sold & views counters
import copy
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
OFFICIAL = ["pgs-official", "pgs-jombang", "pgs-jember"]


def _env(k):
    for line in open("/app/backend/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip('"')


DB = MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]
CRED = {"admin": ("admin@pgs.id", "Admin1234!"), "sidoarjo": ("sidoarjo@pgs.id", "Sidoarjo123!"),
        "jombang": ("jombang@pgs.id", "Jombang123!"), "jember": ("jember@pgs.id", "Jember123!"),
        "acct1": ("acct1@pgs.id", "Test1234!")}
TPID = f"TEST_hs_{uuid.uuid4().hex[:8]}"
TCAT = f"TEST_hscat_{uuid.uuid4().hex[:6]}"
ORDERS: list = []


def H(t=None, store=None):
    h = {}
    if t:
        h["Authorization"] = f"Bearer {t}"
    if store:
        h["X-Store-Id"] = store
    return h


def DEF():
    return {
        "popular": {"enabled": True, "title": "Produk Populer", "limit": 10, "sort": "best_selling", "pinned": [], "categories": [], "days": 7},
        "newest": {"enabled": True, "title": "Produk Terbaru", "limit": 10, "sort": "newest", "pinned": [], "categories": [], "days": 7},
        "recommended": {"enabled": True, "title": "Rekomendasi untukmu", "limit": 20, "sort": "personal", "pinned": [], "categories": [], "days": 7},
    }


@pytest.fixture(scope="module", autouse=True)
def tok():
    snap = {d["store_id"]: d for d in DB.home_sections.find({"store_id": {"$in": OFFICIAL}})}
    t = {}
    for k, (e, p) in CRED.items():
        r = requests.post(f"{API}/auth/login", json={"email": e, "password": p})
        assert r.status_code == 200, r.text
        t[k] = r.json()["token"]
    # TEST product: copy of a real catalog product, old created_at, unique category
    base = DB.products.find_one({"product_id": "pgs-9955"}, {"_id": 0})
    doc = copy.deepcopy(base)
    doc.update({"product_id": TPID, "name": "TEST_ HS Produk", "category": TCAT, "categories": [TCAT], "stock": 50,
                "in_stock": True, "sold": 5, "views": 0, "store_id": "pgs-official",
                "created_at": datetime.now(timezone.utc) - timedelta(days=30)})
    doc.pop("restocked_at", None)
    DB.products.insert_one(doc)
    yield t
    for oid in ORDERS:
        o = DB.orders.find_one({"order_id": oid}, {"status": 1})
        if o and o["status"] not in ("cancelled",):
            requests.put(f"{API}/admin/orders/{oid}/status", headers=H(t["admin"]), json={"status": "cancelled"})
    DB.products.delete_one({"product_id": TPID})
    DB.store_stock.delete_many({"product_id": TPID})
    for sid in OFFICIAL:  # restore exact snapshot
        if sid in snap:
            DB.home_sections.replace_one({"store_id": sid}, snap[sid], upsert=True)
        else:
            DB.home_sections.delete_one({"store_id": sid})


def put_admin(t, sid, cfg):
    return requests.put(f"{API}/admin/home-sections/{sid}", headers=H(t["admin"]), json=cfg)


def sections(store=None, t=None):
    r = requests.get(f"{API}/home/sections", headers=H(t, store))
    assert r.status_code == 200, r.text
    return r.json()


def ids(sec):
    return [i["product_id"] for i in sec["items"]]


# ---------- public endpoint shape ----------
class TestPublic:
    def test_shape_each_branch(self, tok):
        for sid in OFFICIAL + [None, "bogus"]:
            d = sections(sid)
            for k in ("popular", "newest", "recommended"):
                assert {"enabled", "title", "limit", "items"} <= set(d[k]), (sid, k)
                assert isinstance(d[k]["items"], list)
                assert len(d[k]["items"]) <= d[k]["limit"]
                assert all(i.get("stock", 0) > 0 for i in d[k]["items"])

    def test_recommended_paging(self, tok):
        a = requests.get(f"{API}/home/sections/recommended?skip=0&limit=10").json()
        b = requests.get(f"{API}/home/sections/recommended?skip=10&limit=10").json()
        assert len(a) == 10 and len(b) == 10
        assert not (set(x["product_id"] for x in a) & set(x["product_id"] for x in b))
        assert requests.get(f"{API}/home/sections/recommended?limit=31").status_code == 422


# ---------- auth / permissions ----------
class TestPermissions:
    def test_seller_get_own_branch(self, tok):
        for k, sid in (("sidoarjo", "pgs-official"), ("jombang", "pgs-jombang"), ("jember", "pgs-jember")):
            r = requests.get(f"{API}/seller/home-sections", headers=H(tok[k]))
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["store_id"] == sid and set(d["sections"]) == {"popular", "newest", "recommended"}
            assert "pinned_products" in d["sections"]["popular"]

    def test_non_official_seller_403(self, tok):
        assert requests.get(f"{API}/seller/home-sections", headers=H(tok["acct1"])).status_code == 403
        assert requests.put(f"{API}/seller/home-sections", headers=H(tok["acct1"]), json=DEF()).status_code == 403

    def test_unauth_401(self, tok):
        assert requests.get(f"{API}/seller/home-sections").status_code in (401, 403)
        assert requests.get(f"{API}/admin/home-sections/pgs-official").status_code in (401, 403)

    def test_admin_endpoints(self, tok):
        assert requests.get(f"{API}/admin/home-sections/pgs-jember", headers=H(tok["admin"])).json()["store_id"] == "pgs-jember"
        assert requests.get(f"{API}/admin/home-sections/toko-x", headers=H(tok["admin"])).status_code == 404
        assert requests.get(f"{API}/admin/home-sections/pgs-official", headers=H(tok["sidoarjo"])).status_code == 403

    def test_validation(self, tok):
        c = DEF(); c["popular"]["sort"] = "personal"
        assert put_admin(tok, "pgs-official", c).status_code == 400
        c = DEF(); c["newest"]["sort"] = "personal"
        assert put_admin(tok, "pgs-official", c).status_code == 400
        c = DEF(); c["popular"]["limit"] = 31
        assert put_admin(tok, "pgs-official", c).status_code == 422
        c = DEF(); c["popular"]["title"] = ""
        assert put_admin(tok, "pgs-official", c).status_code == 422
        c = DEF(); c["newest"]["days"] = 0
        assert put_admin(tok, "pgs-official", c).status_code == 422


# ---------- rules ----------
class TestRules:
    def test_title_limit_disabled(self, tok):
        c = DEF(); c["popular"].update(title="TEST_ Laris", limit=3); c["newest"]["enabled"] = False
        r = requests.put(f"{API}/seller/home-sections", headers=H(tok["jember"]), json=c)
        assert r.status_code == 200, r.text
        d = sections("pgs-jember")
        assert d["popular"]["title"] == "TEST_ Laris" and len(d["popular"]["items"]) == 3
        assert d["newest"]["enabled"] is False and d["newest"]["items"] == []
        # other branch unaffected
        assert sections("pgs-official")["newest"]["enabled"] is True
        put_admin(tok, "pgs-jember", DEF())

    def test_pins_merge_order_and_remove(self, tok):
        pool = [i["product_id"] for i in requests.get(f"{API}/home/sections/recommended?skip=0&limit=30").json()][-6:]
        A, B, C = pool[0], pool[1], pool[2]
        cj = DEF(); cj["popular"]["pinned"] = [A, B, "nonexistent-xyz"]
        r = put_admin(tok, "pgs-jombang", cj)
        assert r.status_code == 200 and r.json()["sections"]["popular"]["pinned"] == [A, B]
        assert [p["product_id"] for p in r.json()["sections"]["popular"]["pinned_products"]] == [A, B]
        cs = DEF(); cs["popular"]["pinned"] = [C, A]
        assert put_admin(tok, "pgs-official", cs).status_code == 200
        assert ids(sections("pgs-jombang")["popular"])[:3] == [A, B, C]
        assert ids(sections("pgs-official")["popular"])[:3] == [C, A, B]
        assert ids(sections("pgs-jember")["popular"])[:3] == [C, A, B]
        assert len(set(ids(sections("pgs-jombang")["popular"]))) == len(ids(sections("pgs-jombang")["popular"]))
        # pins only affect their section
        assert ids(sections("pgs-jombang")["newest"])[:3] != [A, B, C]
        # remove pins
        cj["popular"]["pinned"] = [B]
        put_admin(tok, "pgs-jombang", cj)
        put_admin(tok, "pgs-official", DEF())
        d = ids(sections("pgs-jombang")["popular"])
        assert d[0] == B and A not in d[:1] and C not in d[:1]
        put_admin(tok, "pgs-jombang", DEF())

    def test_category_filter(self, tok):
        children = [c["category_id"] for c in DB.categories.find({"parent": "dapur"}, {"category_id": 1})]
        c = DEF(); c["popular"]["categories"] = ["dapur"]
        put_admin(tok, "pgs-official", c)
        items = sections("pgs-official")["popular"]["items"]
        assert items, "no items for category dapur"
        allowed = {"dapur", *children}
        assert all(set(i.get("categories") or []) & allowed for i in items)
        put_admin(tok, "pgs-official", DEF())

    def test_sort_rating_and_random(self, tok):
        c = DEF(); c["popular"]["sort"] = "rating"; c["newest"]["sort"] = "random"
        put_admin(tok, "pgs-official", c)
        d = sections("pgs-official")
        r = [i["rating"] for i in d["popular"]["items"]]
        assert r == sorted(r, reverse=True)
        assert len(d["newest"]["items"]) == 10
        put_admin(tok, "pgs-official", DEF())

    def test_views_and_most_viewed(self, tok):
        for _ in range(2):
            assert requests.post(f"{API}/activity/view/{TPID}").status_code == 200
        assert DB.products.find_one({"product_id": TPID})["views"] == 2
        c = DEF(); c["popular"]["sort"] = "most_viewed"
        put_admin(tok, "pgs-official", c)
        assert ids(sections("pgs-official")["popular"])[0] == TPID
        put_admin(tok, "pgs-official", DEF())

    def test_newest_window_and_restock(self, tok):
        c = DEF(); c["newest"]["categories"] = [TCAT]; c["newest"]["days"] = 7
        put_admin(tok, "pgs-official", c)
        assert ids(sections("pgs-official")["newest"]) == []  # created 30 days ago
        c["newest"]["days"] = 31
        put_admin(tok, "pgs-official", c)
        assert ids(sections("pgs-official")["newest"]) == [TPID]
        c["newest"]["days"] = 7
        put_admin(tok, "pgs-official", c)
        # lowering stock is not a restock
        r = requests.put(f"{API}/seller/inventory/{TPID}", headers=H(tok["sidoarjo"]), json={"stock": 40})
        assert r.status_code == 200, r.text
        assert "restocked_at" not in DB.products.find_one({"product_id": TPID})
        r = requests.put(f"{API}/seller/inventory/{TPID}", headers=H(tok["sidoarjo"]), json={"stock": 60})
        assert r.status_code == 200
        assert DB.products.find_one({"product_id": TPID}).get("restocked_at")
        assert ids(sections("pgs-official")["newest"]) == [TPID]
        # popular is unaffected by days
        c2 = DEF(); c2["popular"]["categories"] = [TCAT]
        put_admin(tok, "pgs-official", c2)
        assert ids(sections("pgs-official")["popular"]) == [TPID]
        put_admin(tok, "pgs-official", DEF())


# ---------- sold counter ----------
def _buyer():
    r = requests.post(f"{API}/auth/register", json={"email": f"test_hs20_{uuid.uuid4().hex[:8]}@example.com",
                                                    "password": "TestPass123!", "name": "TEST HS20"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _order(qty=2):
    b = _buyer()
    r = requests.post(f"{API}/cart/items", headers=H(b, "pgs-official"), json={"product_id": TPID, "quantity": qty})
    assert r.status_code == 200, r.text
    r = requests.post(f"{API}/checkout", headers=H(b), json={"full_name": "TEST Buyer", "phone": "081234567890",
                      "address": "Jl. Test 1", "city": "Surabaya", "payment_method": "cod", "store_id": "pgs-official", "courier": "pickup"})
    assert r.status_code == 200, r.text
    ORDERS.append(r.json()["order_id"])
    return b, r.json()["order_id"]


def sold():
    return DB.products.find_one({"product_id": TPID})["sold"]


class TestSold:
    def test_seller_complete_then_admin_cancel(self, tok):
        s0 = sold()
        _, oid = _order(2)
        h = H(tok["sidoarjo"])
        assert requests.put(f"{API}/seller/orders/{oid}/status", headers=h, json={"status": "processing"}).status_code == 200
        assert sold() == s0
        r = requests.put(f"{API}/seller/orders/{oid}/status", headers=h, json={"status": "completed"})
        assert r.status_code == 200, r.text
        assert sold() == s0 + 2
        requests.put(f"{API}/admin/orders/{oid}/status", headers=H(tok["admin"]), json={"status": "completed"})
        assert sold() == s0 + 2  # counted once
        c = DEF(); c["popular"]["categories"] = [TCAT]
        assert requests.put(f"{API}/admin/orders/{oid}/status", headers=H(tok["admin"]), json={"status": "cancelled"}).status_code == 200
        assert sold() == s0
        requests.put(f"{API}/admin/orders/{oid}/status", headers=H(tok["admin"]), json={"status": "cancelled"})
        assert sold() == s0  # decremented once

    def test_buyer_confirm(self, tok):
        s0 = sold()
        b, oid = _order(1)
        h = H(tok["sidoarjo"])
        assert requests.put(f"{API}/seller/orders/{oid}/status", headers=h, json={"status": "processing"}).status_code == 200
        r = requests.put(f"{API}/seller/orders/{oid}/status", headers=h, json={"status": "shipped", "tracking_number": "TESTRESI1"})
        assert r.status_code == 200, r.text
        r = requests.post(f"{API}/orders/{oid}/confirm", headers=H(b))
        assert r.status_code == 200, r.text
        assert sold() == s0 + 1
        assert requests.post(f"{API}/orders/{oid}/confirm", headers=H(b)).status_code == 400
        assert sold() == s0 + 1

    def test_admin_complete_and_popular_top(self, tok):
        s0 = sold()
        _, oid = _order(3)
        assert requests.put(f"{API}/admin/orders/{oid}/status", headers=H(tok["admin"]), json={"status": "completed"}).status_code == 200
        assert sold() == s0 + 3
        # best_selling: our product has the most sold (real products all 0) -> first in popular
        assert ids(sections("pgs-jombang")["popular"])[0] == TPID
        item = sections("pgs-jombang")["popular"]["items"][0]
        assert item["sold"] == s0 + 3
        requests.put(f"{API}/admin/orders/{oid}/status", headers=H(tok["admin"]), json={"status": "cancelled"})
        assert sold() == s0
