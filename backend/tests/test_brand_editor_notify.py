# Product editor Merek (brand) persistence + hidden-product notification regression (no digest run)
import os
from datetime import datetime, timezone

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
PID = "pgs-9957"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture(scope="module")
def ctx():
    r = requests.post(f"{API}/auth/login", json={"email": "admin@pgs.id", "password": "Admin1234!"}, timeout=30)
    if r.status_code != 200:
        pytest.skip("admin login failed")
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    original = db.products.find_one({"product_id": PID})
    start = datetime.now(timezone.utc)
    ev_before = set(e["_id"] for e in db.product_events.find({}, {"_id": 1}))
    yield {"h": h, "original": original}
    # restore exactly + remove side-effect rows created by this test
    db.products.replace_one({"_id": original["_id"]}, original)
    new_ev = [e["_id"] for e in db.product_events.find({"product_id": PID}, {"_id": 1}) if e["_id"] not in ev_before]
    if new_ev:
        db.product_events.delete_many({"_id": {"$in": new_ev}})
    db.price_history.delete_many({"product_id": PID, "at": {"$gte": start}})


def form(ctx):
    r = requests.get(f"{API}/product-editor/products/{PID}", headers=ctx["h"], timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def publish(ctx, data):
    data["weight_grams"] = data.get("weight_grams") or 1000  # imported products have no weight yet (editor requires it)
    return requests.post(f"{API}/product-editor/publish", json={"product_id": PID, "data": data}, headers=ctx["h"], timeout=60)


def test_editor_returns_brand(ctx):
    assert form(ctx)["brand"] == "Suggo"


def test_save_brand_persists_and_filters(ctx):
    d = form(ctx)
    d["brand"] = "Advance"
    r = publish(ctx, d)
    assert r.status_code == 200, r.text
    p = requests.get(f"{API}/products/{PID}", timeout=30).json()
    assert p["brand"] == "Advance"
    assert form(ctx)["brand"] == "Advance"
    q = requests.get(f"{API}/products", params={"brand": "Advance", "q": "Cetakan 7 Lubang"}, timeout=30).json()
    assert PID in [x["product_id"] for x in q]
    # brand edit is an info change of an active product -> 'info' event expected
    assert db.product_events.count_documents({"product_id": PID, "kind": "info"}) >= 1


def test_hidden_with_price_change_no_events(ctx):
    n0 = db.product_events.count_documents({"product_id": PID})
    d = form(ctx)
    d["status"] = "inactive"
    d["price"] = int(d["price"]) + 1000
    r = publish(ctx, d)
    assert r.status_code == 200, r.text
    assert db.products.find_one({"product_id": PID})["status"] == "inactive"
    assert db.product_events.count_documents({"product_id": PID}) == n0, \
        list(db.product_events.find({"product_id": PID}, {"_id": 0, "kind": 1, "at": 1}))
    # hidden product not listed / not in facets
    q = requests.get(f"{API}/products", params={"q": "Cetakan 7 Lubang Cekung Suggo"}, timeout=30).json()
    assert PID not in [x["product_id"] for x in q]


def test_brand_trimmed_and_maxlen(ctx):
    d = form(ctx)
    d["status"] = "inactive"
    d["brand"] = "  Advance  "
    assert publish(ctx, d).status_code == 200
    assert db.products.find_one({"product_id": PID})["brand"] == "Advance"
    d["brand"] = "X" * 61
    assert publish(ctx, d).status_code == 422
