# PGS iteration 43: carton size (P×L×T cm) estimate preview/apply, bulk dims, list filters, Excel dims, weight regression.
# Teardown restores every product doc touched by this module from a snapshot and deletes only our previews/events.
import io
import os
import re
from datetime import datetime, timezone

import pytest
import requests
from openpyxl import Workbook
from pymongo import MongoClient

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
STORE = "pgs-official"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _env(k):
    for line in open("/app/backend/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip('"')


DB = MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]
T0 = datetime.now(timezone.utc)
SNAP = {p["product_id"]: p for p in DB.products.find({"store_id": STORE})}  # full snapshot for restore
S = {}  # shared state between ordered tests


@pytest.fixture(scope="module", autouse=True)
def tok():
    r = requests.post(f"{API}/auth/login", json={"email": "admin@pgs.id", "password": "Admin1234!"})
    if r.status_code != 200:
        pytest.skip("admin login failed")
    yield {"Authorization": f"Bearer {r.json()['token']}"}
    restored = 0
    for pid, doc in SNAP.items():
        cur = DB.products.find_one({"_id": doc["_id"]})
        if cur != doc:
            DB.products.replace_one({"_id": doc["_id"]}, doc)
            restored += 1
    print("restored products:", restored)
    print("previews deleted:", DB.weight_previews.delete_many({"preview_id": {"$in": S.get("previews", [])}}).deleted_count)
    print("events deleted:", DB.product_events.delete_many({"at": {"$gte": T0}}).deleted_count)
    print("price_history deleted:", DB.price_history.delete_many({"at": {"$gte": T0}}).deleted_count)


def _prev(tok, kind):
    r = requests.post(f"{API}/product-editor/{kind}/preview", params={"store_id": STORE}, headers=tok, timeout=120)
    assert r.status_code == 200, r.text
    S.setdefault("previews", []).append(r.json()["preview_id"])
    return r.json()


# ---- dims summary / preview ----
def test_dims_summary(tok):
    r = requests.get(f"{API}/product-editor/dims/summary", params={"store_id": STORE}, headers=tok)
    assert r.status_code == 200, r.text
    d = r.json()
    print(d)
    assert d["missing"] == 6618 and d["estimated"] == 0


def test_unknown_kind_404(tok):
    r = requests.get(f"{API}/product-editor/foo/summary", params={"store_id": STORE}, headers=tok)
    assert r.status_code == 404


def test_dims_preview_sensible(tok):
    d = _prev(tok, "dims")
    S["dims_preview"] = d
    assert d["total"] == 6618 == len(d["items"])
    for i in d["items"]:
        assert isinstance(i["dims"], list) and len(i["dims"]) == 3 and all(isinstance(x, int) and 1 <= x <= 500 for x in i["dims"]), i
    by = {i["product_id"]: i for i in d["items"]}
    print("groups", d["groups"][:12])
    print("AC", by["pgs-44248"]["dims"], by["pgs-44248"]["rule"], "| speaker trolley", by["pgs-10611"]["dims"], by["pgs-10611"]["rule"])
    assert by["pgs-44248"]["rule"].startswith("AC split") and by["pgs-44248"]["dims"] == [95, 35, 40]
    S["trolley_rule"] = by["pgs-10611"]["rule"]
    # spot-check big items: TV/kulkas have large volume
    vol = lambda x: x["dims"][0] * x["dims"][1] * x["dims"][2]
    for kw, rule in (("tv", "TV"), ("kulkas", "Kulkas")):
        hits = [i for i in d["items"] if re.search(rf"^{kw}\b", i["name"], re.I)][:5]
        print(kw, [(i["name"][:40], i["dims"], i["rule"]) for i in hits])
        assert all(i["rule"].startswith(rule) for i in hits)
        assert all(vol(i) >= 20000 for i in hits)


def test_trolley_speaker_is_big(tok):
    # 'Speaker Wooden Trolley ...' should be a big active speaker, not a small 'Speaker' (35x30x45 / 4kg)
    assert S.get("trolley_rule", "").startswith("Speaker aktif"), S.get("trolley_rule")


def test_weight_preview_cannot_apply_as_dims(tok):
    w = _prev(tok, "weight")
    assert "grams" in w["items"][0]
    r = requests.post(f"{API}/product-editor/dims/{w['preview_id']}/apply", json={"skip": [], "overrides": {}}, headers=tok)
    print(r.status_code, r.text)
    assert r.status_code == 400
    assert DB.products.count_documents({"store_id": STORE, "dims_estimated": True}) == 0


def test_dims_apply_skip_and_override(tok):
    items = S["dims_preview"]["items"]
    keep = [i["product_id"] for i in items if i["product_id"] not in ("pgs-44248", "pgs-10611")][:4] + ["pgs-44248"]
    S["keep"] = keep
    skip = [i["product_id"] for i in items if i["product_id"] not in keep]
    r = requests.post(f"{API}/product-editor/dims/{S['dims_preview']['preview_id']}/apply",
                      json={"skip": skip, "overrides": {keep[0]: [40, 30, 20]}}, headers=tok, timeout=60)
    assert r.status_code == 200, r.text
    assert r.json()["saved"] == 5
    p = DB.products.find_one({"product_id": keep[0]})
    assert [p["length_cm"], p["width_cm"], p["height_cm"]] == [40, 30, 20] and p["dims_estimated"] is True
    ac = DB.products.find_one({"product_id": "pgs-44248"})
    assert [ac["length_cm"], ac["width_cm"], ac["height_cm"]] == [95, 35, 40] and ac["dims_estimated"] is True
    assert DB.products.count_documents({"store_id": STORE, "dims_estimated": True}) == 5
    assert "weight_grams" not in p  # dims apply does not touch weight


def test_dims_second_apply_400(tok):
    r = requests.post(f"{API}/product-editor/dims/{S['dims_preview']['preview_id']}/apply", json={"skip": [], "overrides": {}}, headers=tok)
    assert r.status_code == 400, r.text
    assert DB.products.count_documents({"store_id": STORE, "dims_estimated": True}) == 5


def test_dims_summary_after(tok):
    d = requests.get(f"{API}/product-editor/dims/summary", params={"store_id": STORE}, headers=tok).json()
    assert d == {"store_id": STORE, "missing": 6613, "estimated": 5}


# ---- list filters ----
def test_list_filters(tok):
    g = lambda **p: requests.get(f"{API}/product-editor/products", params={"store_id": STORE, **p}, headers=tok).json()
    est = g(status="estimated_dims", limit=100)
    assert est["total"] == 5 and all(i["dims_estimated"] and all(x > 0 for x in i["dims"]) for i in est["items"])
    nd = g(status="no_dims")
    assert nd["total"] == 6613
    name = DB.products.find_one({"product_id": "pgs-44248"})["name"]
    assert g(status="estimated_dims", q=name)["total"] == 1
    assert g(status="no_dims", q=name)["total"] == 0
    assert g(status="no_dims", q="pgs-10611")["total"] == 1


# ---- bulk dims ----
def test_bulk_dims_only_missing(tok):
    est, missing = S["keep"][1], "pgs-10611"
    before = DB.products.find_one({"product_id": est})
    r = requests.post(f"{API}/product-editor/bulk", json={"store_id": STORE, "product_ids": [est, missing], "dims": [50, 40, 30], "dims_only_missing": True}, headers=tok, timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    print(d)
    assert d["updated"] == 1 and [s["product_id"] for s in d["skipped"]] == [est]
    assert d["skipped"][0]["reason"] == "Sudah punya ukuran dus"
    after = DB.products.find_one({"product_id": est})
    assert [after["length_cm"], after["width_cm"], after["height_cm"]] == [before["length_cm"], before["width_cm"], before["height_cm"]] and after["dims_estimated"] is True
    m = DB.products.find_one({"product_id": missing})
    assert [m["length_cm"], m["width_cm"], m["height_cm"]] == [50, 40, 30] and m["dims_estimated"] is False


def test_bulk_dims_overwrite_clears_estimated(tok):
    est = S["keep"][1]
    r = requests.post(f"{API}/product-editor/bulk", json={"store_id": STORE, "product_ids": [est], "dims": [50, 40, 30]}, headers=tok, timeout=60)
    assert r.status_code == 200 and r.json()["updated"] == 1, r.text
    p = DB.products.find_one({"product_id": est})
    assert [p["length_cm"], p["width_cm"], p["height_cm"]] == [50, 40, 30] and p["dims_estimated"] is False


@pytest.mark.parametrize("dims", [[0, 10, 10], [10, 10], [501, 10, 10], [10, -1, 10]])
def test_bulk_dims_invalid(tok, dims):
    r = requests.post(f"{API}/product-editor/bulk", json={"store_id": STORE, "product_ids": [S["keep"][2]], "dims": dims}, headers=tok)
    assert r.status_code in (400, 422), r.text
    p = DB.products.find_one({"product_id": S["keep"][2]})
    assert p["dims_estimated"] is True


# ---- Excel ----
def test_excel_dims_clears_estimated(tok):
    pid = S["keep"][2]
    wb = Workbook()
    ws = wb.active
    ws.append(["ID Produk (jangan diubah)", "Panjang (cm)", "Lebar (cm)", "Tinggi (cm)"])
    p = DB.products.find_one({"product_id": pid})
    ws.append([pid, 77, p["width_cm"], p["height_cm"]])
    b = io.BytesIO()
    wb.save(b)
    r = requests.post(f"{API}/product-editor/import", params={"store_id": STORE, "commit": "true"},
                      files={"file": ("d.xlsx", b.getvalue(), XLSX)}, headers=tok, timeout=90)
    assert r.status_code == 200, r.text
    print(r.json()["counts"], r.json()["rows"][:1])
    assert r.json()["counts"]["update"] == 1
    p2 = DB.products.find_one({"product_id": pid})
    assert p2["length_cm"] == 77 and p2["dims_estimated"] is False
    # untouched estimated product keeps its flag
    assert DB.products.find_one({"product_id": S["keep"][3]})["dims_estimated"] is True


def test_no_product_events(tok):
    ev = list(DB.product_events.find({"at": {"$gte": T0}}, {"_id": 0}))
    print("events", ev)
    assert ev == []


# ---- weight regression ----
def test_weight_regression(tok):
    s = requests.get(f"{API}/product-editor/weight/summary", params={"store_id": STORE}, headers=tok).json()
    assert s["missing"] == 6618 and s["estimated"] == 0
    w = _prev(tok, "weight")
    keep = [w["items"][0]["product_id"], w["items"][1]["product_id"]]
    r = requests.post(f"{API}/product-editor/weight/{w['preview_id']}/apply",
                      json={"skip": [i["product_id"] for i in w["items"] if i["product_id"] not in keep], "overrides": {keep[0]: 1234}}, headers=tok, timeout=60)
    assert r.status_code == 200 and r.json()["saved"] == 2, r.text
    p = DB.products.find_one({"product_id": keep[0]})
    assert p["weight_grams"] == 1234 and p["weight_estimated"] is True and "dims_estimated" not in p or p.get("dims_estimated") in (True, False)
    assert requests.post(f"{API}/product-editor/weight/{w['preview_id']}/apply", json={}, headers=tok).status_code == 400
    s2 = requests.get(f"{API}/product-editor/weight/summary", params={"store_id": STORE}, headers=tok).json()
    assert s2["missing"] == 6616 and s2["estimated"] == 2
    lst = requests.get(f"{API}/product-editor/products", params={"store_id": STORE, "status": "estimated_weight"}, headers=tok).json()
    assert lst["total"] == 2
    # dims preview id cannot be applied as weight
    d = _prev(tok, "dims")
    assert requests.post(f"{API}/product-editor/weight/{d['preview_id']}/apply", json={}, headers=tok).status_code == 400
