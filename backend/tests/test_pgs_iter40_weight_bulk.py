# PGS iteration 39/40: product weight — summary, auto-estimate preview/apply, bulk "Isi Berat", filters, Excel/editor clearing estimate flag.
# Cleanup (per main agent): $unset weight_grams & weight_estimated on ALL products (none had weight before), delete weight_previews & product_events.
import io
import os

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
S: dict = {}


def _ev(step):
    evs = list(DB.product_events.find({}, {"_id": 0, "product_id": 1, "kind": 1}))
    print(f"[events after {step}] {len(evs)} {evs}")
    return evs


@pytest.fixture(scope="module")
def tok():
    r = requests.post(f"{API}/auth/login", json={"email": "admin@pgs.id", "password": "Admin1234!"})
    if r.status_code != 200:
        pytest.skip("admin login failed")
    yield {"Authorization": f"Bearer {r.json()['token']}"}
    print("TEARDOWN events:", list(DB.product_events.find({}, {"_id": 0})))
    # teardown: restore the "no weight anywhere" baseline
    DB.products.update_many({}, {"$unset": {"weight_grams": "", "weight_estimated": ""}})
    DB.weight_previews.delete_many({})
    DB.product_events.delete_many({})


# ---------- summary ----------
def test_summary_initial(tok):
    r = requests.get(f"{API}/product-editor/weight/summary", params={"store_id": STORE}, headers=tok)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["store_id"] == STORE
    assert d["missing"] == DB.products.count_documents({"store_id": STORE})
    assert d["missing"] >= 6000 and d["estimated"] == 0
    S["missing0"] = d["missing"]


def test_summary_requires_auth():
    r = requests.get(f"{API}/product-editor/weight/summary", params={"store_id": STORE})
    assert r.status_code in (401, 403)


# ---------- preview ----------
def test_preview_rules(tok):
    r = requests.post(f"{API}/product-editor/weight/preview", params={"store_id": STORE}, headers=tok)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["preview_id"].startswith("wp_") and d["total"] == S["missing0"] == len(d["items"])
    assert sum(g["count"] for g in d["groups"]) == d["total"]
    assert DB.weight_previews.count_documents({"preview_id": d["preview_id"], "status": "preview"}) == 1
    items = d["items"]
    assert all(1 <= i["grams"] <= 500000 and i["rule"] for i in items)
    S["preview"] = d
    pick = {}
    for kind, pred in [("tv", lambda n: " tv " in f" {n} " or "televisi" in n), ("ac", lambda n: "ac split" in n or ("ac " in n and "pk" in n)),
                       ("dispenser", lambda n: "dispenser" in n and not any(x in n for x in ("sabun", "tisu", "tissue", "odol", "pasta"))),
                       ("speaker", lambda n: "speaker" in n)]:
        match = [i for i in items if pred(i["name"].lower())]
        print(kind, len(match), [(m["name"][:50], m["grams"], m["rule"]) for m in match[:4]])
        if match:
            pick[kind] = match[0]
    S["pick"] = pick
    if "tv" in pick:
        assert pick["tv"]["rule"].startswith("TV") and pick["tv"]["grams"] >= 6000
    if "ac" in pick:
        assert pick["ac"]["rule"].startswith("AC") and pick["ac"]["grams"] >= 20000
    if "dispenser" in pick:
        assert pick["dispenser"]["rule"].startswith("Dispenser")
    if "speaker" in pick:
        assert "Speaker" in pick["speaker"]["rule"]


# ---------- apply (narrow: only 5 products) ----------
def test_apply_with_skip_and_override(tok):
    S.setdefault('ev', []).append('test_apply_with_skip_and_override')
    d = S["preview"]
    chosen = [p["product_id"] for p in S["pick"].values()]
    for i in d["items"]:
        if len(chosen) >= 5:
            break
        if i["product_id"] not in chosen:
            chosen.append(i["product_id"])
    S["chosen"] = chosen
    skip = [i["product_id"] for i in d["items"] if i["product_id"] not in chosen]
    over = {chosen[-1]: 1234}
    r = requests.post(f"{API}/product-editor/weight/{d['preview_id']}/apply", json={"skip": skip, "overrides": over}, headers=tok, timeout=120)
    assert r.status_code == 200, r.text
    assert r.json()["saved"] == 5
    by = {i["product_id"]: i["grams"] for i in d["items"]}
    for pid in chosen:
        p = DB.products.find_one({"product_id": pid})
        assert p["weight_estimated"] is True
        assert p["weight_grams"] == (1234 if pid == chosen[-1] else by[pid])
    assert DB.products.count_documents({"store_id": STORE, "weight_grams": {"$gt": 0}}) == 5


def test_apply_twice_400(tok):
    r = requests.post(f"{API}/product-editor/weight/{S['preview']['preview_id']}/apply", json={"skip": [], "overrides": {}}, headers=tok)
    assert r.status_code == 400
    assert DB.products.count_documents({"store_id": STORE, "weight_grams": {"$gt": 0}}) == 5


def test_summary_after_apply(tok):
    d = requests.get(f"{API}/product-editor/weight/summary", params={"store_id": STORE}, headers=tok).json()
    assert d["estimated"] == 5 and d["missing"] == S["missing0"] - 5


def test_list_estimated_filter(tok):
    r = requests.get(f"{API}/product-editor/products", params={"store_id": STORE, "status": "estimated_weight", "limit": 100}, headers=tok)
    d = r.json()
    assert d["total"] == 5 and {i["product_id"] for i in d["items"]} == set(S["chosen"])
    assert all(i["weight_estimated"] and i["weight_grams"] > 0 for i in d["items"])


def test_list_no_weight_filter_and_q(tok):
    d = requests.get(f"{API}/product-editor/products", params={"store_id": STORE, "status": "no_weight"}, headers=tok).json()
    assert d["total"] == S["missing0"] - 5 and all(i["weight_grams"] == 0 for i in d["items"])
    assert not set(S["chosen"]) & {i["product_id"] for i in d["items"]}
    allq = requests.get(f"{API}/product-editor/products", params={"store_id": STORE, "q": "tv"}, headers=tok).json()["total"]
    nq = requests.get(f"{API}/product-editor/products", params={"store_id": STORE, "q": "tv", "status": "no_weight"}, headers=tok).json()
    assert 0 < nq["total"] <= allq and all("tv" in (i["name"] + i["sku"]).lower() for i in nq["items"])
    est_tv = sum(1 for pid in S["chosen"] if "tv" in (DB.products.find_one({"product_id": pid})["name"] + DB.products.find_one({"product_id": pid}).get("sku", "")).lower())
    assert nq["total"] == allq - est_tv


# ---------- bulk Isi Berat ----------
def test_bulk_weight_only_missing(tok):
    S.setdefault('ev', []).append('test_bulk_weight_only_missing')
    est = S["chosen"][0]
    missing = [i["product_id"] for i in S["preview"]["items"] if i["product_id"] not in S["chosen"]][:2]
    S["bulk_missing"] = missing
    before = {pid: DB.products.find_one({"product_id": pid}, {"_id": 0, "price": 1, "stock": 1, "original_price": 1}) for pid in missing}
    r = requests.post(f"{API}/product-editor/bulk", json={"store_id": STORE, "product_ids": [est] + missing, "weight_grams": 1500, "weight_only_missing": True}, headers=tok)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["updated"] == 2
    assert len(d["skipped"]) == 1 and d["skipped"][0]["product_id"] == est and d["skipped"][0]["reason"] == "Sudah punya berat"
    for pid in missing:
        p = DB.products.find_one({"product_id": pid})
        assert p["weight_grams"] == 1500 and p["weight_estimated"] is False
        assert {k: p.get(k) for k in before[pid]} == before[pid], "price/stock must not change on weight-only bulk"
    assert DB.products.find_one({"product_id": est})["weight_estimated"] is True


def test_bulk_weight_overwrite(tok):
    S.setdefault('ev', []).append('test_bulk_weight_overwrite')
    est = S["chosen"][0]
    r = requests.post(f"{API}/product-editor/bulk", json={"store_id": STORE, "product_ids": [est], "weight_grams": 2222, "weight_only_missing": False}, headers=tok)
    assert r.status_code == 200 and r.json()["updated"] == 1, r.text
    p = DB.products.find_one({"product_id": est})
    assert p["weight_grams"] == 2222 and p["weight_estimated"] is False


def test_bulk_weight_validation(tok):
    r = requests.post(f"{API}/product-editor/bulk", json={"store_id": STORE, "product_ids": [S["chosen"][0]], "weight_grams": 600000}, headers=tok)
    assert r.status_code == 422
    r = requests.post(f"{API}/product-editor/bulk", json={"store_id": STORE, "product_ids": [S["chosen"][0]], "weight_grams": 0}, headers=tok)
    assert r.status_code == 400


# ---------- Excel import clears estimate flag ----------
def _xlsx(rows):
    wb = Workbook()
    ws = wb.active
    ws.append(["ID Produk (jangan diubah)", "Berat (gram)*"])
    for r in rows:
        ws.append(r)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def test_import_berat_clears_estimate(tok):
    S.setdefault('ev', []).append('test_import_berat_clears_estimate')
    pid = S["chosen"][1]
    assert DB.products.find_one({"product_id": pid})["weight_estimated"] is True
    files = {"file": ("w.xlsx", _xlsx([[pid, 3333]]), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    r = requests.post(f"{API}/product-editor/import", params={"store_id": STORE, "commit": "true"}, files=files, headers=tok, timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    print(d["counts"], d["rows"][:2])
    assert d["counts"]["update"] == 1
    p = DB.products.find_one({"product_id": pid})
    assert p["weight_grams"] == 3333 and p["weight_estimated"] is False


def test_import_same_berat_keeps_estimate(tok):
    S.setdefault('ev', []).append('test_import_same_berat_keeps_estimate')
    pid = S["chosen"][2]
    g = DB.products.find_one({"product_id": pid})["weight_grams"]
    files = {"file": ("w.xlsx", _xlsx([[pid, g]]), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    r = requests.post(f"{API}/product-editor/import", params={"store_id": STORE, "commit": "true"}, files=files, headers=tok, timeout=60)
    assert r.status_code == 200, r.text
    assert r.json()["counts"].get("update", 0) == 0
    assert DB.products.find_one({"product_id": pid})["weight_estimated"] is True


# ---------- editor publish ----------
def test_editor_form_and_publish_clears_estimate(tok):
    S.setdefault('ev', []).append('test_editor_form_and_publish_clears_estimate')
    pid = S["chosen"][3]
    r = requests.get(f"{API}/product-editor/products/{pid}", headers=tok)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["weight_estimated"] is True and data["weight_grams"] > 0
    data.update(weight_grams=data["weight_grams"] + 100, weight_estimated=False)
    r = requests.post(f"{API}/product-editor/publish", json={"product_id": pid, "data": data}, headers=tok)
    print(r.status_code, r.text[:400])
    if r.status_code == 422:
        pytest.skip(f"imported product incomplete for publish: {r.text[:200]}")
    assert r.status_code == 200
    p = DB.products.find_one({"product_id": pid})
    assert p["weight_estimated"] is False and p["weight_grams"] == data["weight_grams"]


@pytest.fixture(autouse=True)
def _trace(request):
    yield
    _ev(request.node.name)


# ---------- no buyer notifications ----------
def test_no_product_events(tok):
    n = DB.product_events.count_documents({})
    print("product_events:", list(DB.product_events.find({}, {"_id": 0}).limit(5)))
    assert n == 0
