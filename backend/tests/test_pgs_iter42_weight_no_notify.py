# PGS iteration 42: weight-only edits (editor publish / Excel import) on raw imported products must NOT create buyer
# 'info' events; a description change must. Restores original docs and deletes only events/price_history we created.
import io
import os
from datetime import datetime, timezone

import pytest
import requests
from openpyxl import Workbook
from pymongo import MongoClient

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
STORE = "pgs-official"


def _env(k):
    for line in open("/app/backend/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip('"')


DB = MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]
T0 = datetime.now(timezone.utc)
RAW_Q = {"store_id": STORE, "specs": {"$exists": False}, "condition": {"$exists": False}, "variants": {"$exists": False},
         "weight_grams": {"$exists": False}}
# raw products: with brand / without brand, for editor and Excel
PICK = (list(DB.products.find({**RAW_Q, "brand": {"$exists": True, "$ne": ""}}).limit(3))
        + list(DB.products.find({**RAW_Q, "brand": {"$exists": False}}).limit(3)))
ORIG = {p["product_id"]: p for p in PICK}
PIDS = list(ORIG)


def _events(pid):
    return list(DB.product_events.find({"product_id": pid, "at": {"$gte": T0}}, {"_id": 0, "kind": 1, "product_id": 1}))


@pytest.fixture(scope="module", autouse=True)
def tok():
    r = requests.post(f"{API}/auth/login", json={"email": "admin@pgs.id", "password": "Admin1234!"})
    if r.status_code != 200:
        pytest.skip("admin login failed")
    yield {"Authorization": f"Bearer {r.json()['token']}"}
    # teardown: restore originals, remove only our events / price history
    for pid, doc in ORIG.items():
        DB.products.replace_one({"_id": doc["_id"]}, doc)
    print("events to delete:", list(DB.product_events.find({"product_id": {"$in": PIDS}, "at": {"$gte": T0}}, {"_id": 0})))
    DB.product_events.delete_many({"product_id": {"$in": PIDS}, "at": {"$gte": T0}})
    ph = DB.price_history.delete_many({"product_id": {"$in": PIDS}})
    print("price_history deleted:", ph.deleted_count)


def test_have_raw_products():
    print([(p["product_id"], p.get("brand"), p.get("category"), p.get("subcategory")) for p in PICK])
    assert len(PICK) == 6


def _xlsx(header, rows):
    wb = Workbook()
    ws = wb.active
    ws.append(header)
    for r in rows:
        ws.append(r)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def _publish(tok, pid, **changes):
    r = requests.get(f"{API}/product-editor/products/{pid}", headers=tok)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    data.update(changes)
    return requests.post(f"{API}/product-editor/publish", json={"product_id": pid, "data": data}, headers=tok, timeout=60)


# ---------- editor publish weight-only ----------
@pytest.mark.parametrize("i", [0, 3])
def test_editor_weight_only_no_event(tok, i):
    pid = PIDS[i]
    r = _publish(tok, pid, weight_grams=1234, weight_estimated=False)
    print(pid, r.status_code, r.text[:300])
    assert r.status_code == 200, r.text
    p = DB.products.find_one({"product_id": pid})
    assert p["weight_grams"] == 1234
    ev = _events(pid)
    print("events", ev)
    assert ev == [], f"weight-only editor publish created events: {ev}"


# ---------- Excel import weight-only ----------
def test_excel_weight_only_no_event(tok):
    pids = [PIDS[1], PIDS[4]]
    files = {"file": ("w.xlsx", _xlsx(["ID Produk (jangan diubah)", "Berat (gram)*"], [[pids[0], 777], [pids[1], 888]]),
                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    r = requests.post(f"{API}/product-editor/import", params={"store_id": STORE, "commit": "true"}, files=files, headers=tok, timeout=90)
    assert r.status_code == 200, r.text
    d = r.json()
    print(d["counts"], d["rows"][:2])
    assert d["counts"]["update"] == 2
    assert DB.products.find_one({"product_id": pids[0]})["weight_grams"] == 777
    assert DB.products.find_one({"product_id": pids[1]})["weight_grams"] == 888
    ev = _events(pids[0]) + _events(pids[1])
    print("events", ev)
    assert ev == [], f"weight-only Excel import created events: {ev}"


# ---------- second weight-only pass on now-normalized docs ----------
def test_editor_second_weight_change_no_event(tok):
    pid = PIDS[0]
    r = _publish(tok, pid, weight_grams=2345)
    assert r.status_code == 200, r.text
    assert _events(pid) == []


# ---------- description change DOES notify ----------
def test_editor_description_creates_info_event(tok):
    pid = PIDS[2]
    r = _publish(tok, pid, weight_grams=1500, description=(ORIG[pid].get("description") or "") + " TEST_desc perubahan keterangan produk")
    print(r.status_code, r.text[:300])
    assert r.status_code == 200, r.text
    ev = _events(pid)
    print("events", ev)
    assert [e["kind"] for e in ev] == ["info"]


def test_excel_description_creates_info_event(tok):
    pid = PIDS[5]
    files = {"file": ("d.xlsx", _xlsx(["ID Produk (jangan diubah)", "Berat (gram)*", "Deskripsi"],
                                      [[pid, 999, (ORIG[pid].get("description") or "") + " TEST_desc excel"]]),
                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    r = requests.post(f"{API}/product-editor/import", params={"store_id": STORE, "commit": "true"}, files=files, headers=tok, timeout=90)
    assert r.status_code == 200, r.text
    print(r.json()["counts"], r.json()["rows"][:1])
    ev = _events(pid)
    print("events", ev)
    assert [e["kind"] for e in ev] == ["info"]


# ---------- broad sample: weight-only editor publish on 15 random raw products ----------
def test_editor_weight_only_random_sample(tok):
    sample = list(DB.products.aggregate([{"$match": {**RAW_Q, "product_id": {"$nin": PIDS}}}, {"$sample": {"size": 15}}]))
    saved = {p["product_id"]: p for p in sample}
    bad, skipped = [], []
    try:
        for pid in saved:
            r = _publish(tok, pid, weight_grams=1111)
            if r.status_code == 422:
                skipped.append((pid, r.text[:150]))
                continue
            assert r.status_code == 200, r.text
            ev = list(DB.product_events.find({"product_id": pid, "at": {"$gte": T0}}, {"_id": 0, "kind": 1}))
            if ev:
                bad.append((pid, ev))
    finally:
        for pid, doc in saved.items():
            DB.products.replace_one({"_id": doc["_id"]}, doc)
        DB.product_events.delete_many({"product_id": {"$in": list(saved)}, "at": {"$gte": T0}})
        DB.price_history.delete_many({"product_id": {"$in": list(saved)}})
    print("skipped(422):", skipped, "bad:", bad)
    assert not bad, f"events created for weight-only publish: {bad}"
    assert len(skipped) < len(saved)
