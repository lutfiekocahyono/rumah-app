# Iteration 55: legacy POST /seller/products -> only_branch; price-down warning (branch-copy + branch bulk edit) with 409 confirm gate
import os
import uuid
from datetime import datetime, timezone

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient


def _base():
    u = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL")
    if not u:
        for line in open("/app/frontend/.env"):
            if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
                u = line.split("=", 1)[1].strip().strip('"')
    return u.rstrip("/")


API = f"{_base()}/api"
CREDS = {"admin": ("admin@pgs.id", "Admin1234!"), "sidoarjo": ("sidoarjo@pgs.id", "Sidoarjo123!"),
         "jombang": ("jombang@pgs.id", "Jombang123!"), "jember": ("jember@pgs.id", "Jember123!")}
STORE = {"sidoarjo": "pgs-official", "jombang": "pgs-jombang", "jember": "pgs-jember"}
TOK: dict = {}
NARROW_Q = "SG-CS32"  # exactly one PGS product (pgs-9955) — used for bulk edit, restored afterwards
NARROW_PID = "pgs-9955"

load_dotenv("/app/backend/.env")
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def H(who=None, store=None):
    h = {"Content-Type": "application/json"}
    if who:
        if who not in TOK:
            e, p = CREDS[who]
            r = requests.post(f"{API}/auth/login", json={"email": e, "password": p}, timeout=30)
            assert r.status_code == 200, r.text
            TOK[who] = r.json()["token"]
        h["Authorization"] = f"Bearer {TOK[who]}"
    if store:
        h["X-Store-Id"] = store
    return h


def names(r):
    d = r.json()
    items = d if isinstance(d, list) else d.get("items", d.get("products", []))
    return [i.get("name") for i in items]


# ---------- Legacy route: POST /api/seller/products sets only_branch ----------
@pytest.mark.parametrize("who", ["sidoarjo", "jombang", "jember"])
def test_legacy_create_only_branch(who):
    cat = requests.get(f"{API}/categories", timeout=30).json()[0]["category_id"]
    name = f"TEST_legacy_{who}_{uuid.uuid4().hex[:6]}"
    body = {"name": name, "category": cat, "images": ["https://example.com/a.jpg"], "price": 15000, "stock": 10,
            "description": "TEST produk lama rute seller untuk pengujian visibilitas cabang otomatis.", "weight_grams": 500}
    r = requests.post(f"{API}/seller/products", json=body, headers=H(who), timeout=30)
    assert r.status_code == 200, r.text
    pid = r.json()["product_id"]
    try:
        doc = DB.products.find_one({"product_id": pid}, {"_id": 0, "only_branch": 1, "store_id": 1})
        assert doc["only_branch"] == STORE[who] and doc["store_id"] == STORE[who]
        for other, sid in STORE.items():
            lst = requests.get(f"{API}/products", params={"q": name}, headers=H(store=sid), timeout=30)
            assert lst.status_code == 200
            assert (name in names(lst)) == (other == who), f"{who} product visibility wrong in {sid}"
    finally:
        d = requests.delete(f"{API}/seller/products/{pid}", headers=H(who), timeout=30)
        assert d.status_code == 200, d.text
        assert DB.products.count_documents({"product_id": pid}) == 0


# ---------- Branch copy preview: price_down + down_sample, apply gated by 409 ----------
def test_branch_copy_preview_price_down_and_409():
    rule = {"store_id": "pgs-jember", "mode": "rp", "price_add": -500, "copy_price": True, "copy_stock": False}
    r = requests.post(f"{API}/admin/branch-copy/preview", json={"rules": [rule]}, headers=H("admin"), timeout=120)
    assert r.status_code == 200, r.text
    b = r.json()["branches"][0]
    assert isinstance(b["price_down"], int) and b["price_down"] > 0
    assert 0 < len(b["down_sample"]) <= 10
    s = b["down_sample"][0]
    assert set(s) >= {"product_id", "name", "old_price", "new_price"} and s["new_price"] < s["old_price"]
    pid = r.json()["preview_id"]
    for body in (None, {"confirm_down": False}):
        a = requests.post(f"{API}/admin/branch-copy/{pid}/apply", json=body, headers=H("admin"), timeout=120)
        assert a.status_code == 409, a.text
        assert "TURUN" in a.json()["detail"]
    st = DB.branch_copy.find_one({"preview_id": pid}, {"status": 1})
    assert st["status"] == "preview"  # not consumed by the blocked apply


def test_branch_copy_preview_up_only_has_zero_down():
    rule = {"store_id": "pgs-jember", "mode": "rp", "price_add": 1_000_000, "copy_price": True, "copy_stock": False}
    r = requests.post(f"{API}/admin/branch-copy/preview", json={"rules": [rule]}, headers=H("admin"), timeout=120)
    assert r.status_code == 200, r.text
    b = r.json()["branches"][0]
    assert b["price_down"] == 0 and b["down_sample"] == []


def test_branch_copy_apply_forbidden_for_branch_admin():
    r = requests.post(f"{API}/admin/branch-copy/preview", json={"rules": [{"store_id": "pgs-jember", "price_add": -500}]},
                      headers=H("jember"), timeout=60)
    assert r.status_code in (401, 403)


# ---------- Branch bulk edit (Harga Cabang): down warning + confirm_down ----------
@pytest.fixture
def restore_narrow():
    start = datetime.now(timezone.utc)
    snap = DB.store_stock.find_one({"store_id": "pgs-jember", "product_id": NARROW_PID})
    yield snap
    if snap:
        DB.store_stock.replace_one({"_id": snap["_id"]}, snap)
    else:
        DB.store_stock.delete_one({"store_id": "pgs-jember", "product_id": NARROW_PID})
    DB.price_history.delete_many({"store_id": "pgs-jember", "product_id": NARROW_PID, "at": {"$gte": start}})
    DB.product_events.delete_many({"store_id": "pgs-jember", "product_id": NARROW_PID, "at": {"$gte": start}, "digest_id": None})


def test_branch_bulk_down_confirm_then_up(restore_narrow):
    old = restore_narrow["price"]
    r = requests.post(f"{API}/branch-prices/bulk/preview", json={"mode": "pct", "value": -5, "q": NARROW_Q}, headers=H("jember"), timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["changed"] == 1 and d["down"] == 1 and d["up"] == 0
    assert d["down_sample"][0]["product_id"] == NARROW_PID and d["down_sample"][0]["old_price"] == old
    assert d["down_sample"][0]["new_price"] < old
    pid = d["preview_id"]
    a = requests.post(f"{API}/branch-prices/bulk/{pid}/apply", headers=H("jember"), timeout=60)
    assert a.status_code == 409 and "TURUN" in a.json()["detail"], a.text
    a = requests.post(f"{API}/branch-prices/bulk/{pid}/apply", json={"confirm_down": False}, headers=H("jember"), timeout=60)
    assert a.status_code == 409
    a = requests.post(f"{API}/branch-prices/bulk/{pid}/apply", json={"confirm_down": True}, headers=H("jember"), timeout=60)
    assert a.status_code == 200 and a.json()["saved"] == 1, a.text
    cur = DB.store_stock.find_one({"store_id": "pgs-jember", "product_id": NARROW_PID})
    assert cur["price"] == d["down_sample"][0]["new_price"]
    # price-up: apply without confirmation is NOT blocked
    r = requests.post(f"{API}/branch-prices/bulk/preview", json={"mode": "rp", "value": 100, "q": NARROW_Q}, headers=H("jember"), timeout=60)
    assert r.status_code == 200 and r.json()["down"] == 0 and r.json()["up"] == 1 and r.json()["down_sample"] == []
    a = requests.post(f"{API}/branch-prices/bulk/{r.json()['preview_id']}/apply", headers=H("jember"), timeout=60)
    assert a.status_code == 200 and a.json()["saved"] == 1, a.text


def test_branch_bulk_other_branch_cannot_apply():
    r = requests.post(f"{API}/branch-prices/bulk/preview", json={"mode": "pct", "value": -5, "q": NARROW_Q}, headers=H("jember"), timeout=60)
    assert r.status_code == 200
    a = requests.post(f"{API}/branch-prices/bulk/{r.json()['preview_id']}/apply", json={"confirm_down": True}, headers=H("jombang"), timeout=60)
    assert a.status_code in (403, 400), a.text
