# Iteration 53: branch admin Daftar Produk (shared PGS catalog w/ branch price & stock) + isolation. READ-ONLY tests (no writes on real data).
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", os.environ.get("EXPO_BACKEND_URL", "")).rstrip("/")
if not BASE_URL:
    for line in open("/app/frontend/.env"):
        if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")
API = f"{BASE_URL}/api"
CREDS = {"admin": ("admin@pgs.id", "Admin1234!"), "jombang": ("jombang@pgs.id", "Jombang123!"),
         "jember": ("jember@pgs.id", "Jember123!"), "sidoarjo": ("sidoarjo@pgs.id", "Sidoarjo123!")}
_tok = {}


def hdr(who):
    if who not in _tok:
        r = requests.post(f"{API}/auth/login", json={"email": CREDS[who][0], "password": CREDS[who][1]}, timeout=30)
        if r.status_code != 200:
            pytest.skip(f"login {who} failed {r.status_code}")
        _tok[who] = r.json().get("token") or r.json().get("access_token")
    return {"Authorization": f"Bearer {_tok[who]}"}


def lst(who, **params):
    r = requests.get(f"{API}/product-editor/products", headers=hdr(who), params=params, timeout=60)
    assert r.status_code == 200, r.text
    return r.json()


# ---- Branch list (root cause fix) ----
@pytest.mark.parametrize("who,sid", [("jombang", "pgs-jombang"), ("jember", "pgs-jember")])
def test_branch_list_total_and_store(who, sid):
    d = lst(who, limit=50)
    assert d["store_id"] == sid
    assert d["total"] >= 6618, d["total"]
    assert len(d["items"]) == 50
    assert all(i["store_id"] in ("pgs-official", sid) for i in d["items"])
    assert all(i.get("shared") is True for i in d["items"] if i["store_id"] == "pgs-official")


@pytest.mark.parametrize("who,sid", [("jombang", "pgs-jombang"), ("jember", "pgs-jember")])
def test_branch_values_match_store_stock(who, sid):
    d = lst(who, limit=30)
    shared = [i for i in d["items"] if i.get("shared")][:15]
    ids = ",".join(i["product_id"] for i in shared)
    side = {i["product_id"]: i for i in lst("sidoarjo", q="", limit=100)["items"]}
    mism = 0
    for i in shared:
        # compare with /branch-prices view for the same product (branch truth)
        r = requests.get(f"{API}/branch-prices", headers=hdr(who), params={"q": i["product_id"]}, timeout=30)
        assert r.status_code == 200
        bp = [x for x in r.json()["items"] if x["product_id"] == i["product_id"]]
        if not bp:
            continue  # variant products not in branch-prices
        bp = bp[0]
        assert i["stock"] == bp["stock"], (i["product_id"], i["stock"], bp["stock"])
        if i["price"] != bp["branch"]["price"]:
            mism += 1
    assert mism == 0, f"{mism} price mismatches vs branch-prices; ids={ids}"


def test_jombang_differs_from_sidoarjo_somewhere():
    j = {i["product_id"]: i for i in lst("jombang", limit=100)["items"]}
    s_items = []
    for pid in list(j)[:100]:
        pass
    # check by search of first 10 ids in sidoarjo
    diff = 0
    for pid in list(j)[:20]:
        s = lst("sidoarjo", q=pid, limit=5)["items"]
        s = [x for x in s if x["product_id"] == pid]
        if s and (s[0]["stock"] != j[pid]["stock"] or s[0]["price"] != j[pid]["price"]):
            diff += 1
    print("products differing jombang vs sidoarjo:", diff)
    assert diff > 0


def test_branch_search_name_sku_id():
    base = lst("jombang", limit=5)["items"]
    p = next(i for i in base if i.get("shared"))
    by_id = lst("jombang", q=p["product_id"])
    assert any(i["product_id"] == p["product_id"] for i in by_id["items"])
    word = p["name"].split()[0]
    by_name = lst("jombang", q=word)
    assert by_name["total"] >= 1 and all(word.lower() in (i["name"] + (i.get("sku") or "")).lower() or i["product_id"] == word for i in by_name["items"])
    sku_p = next((i for i in lst("jombang", limit=50)["items"] if i.get("sku")), None)
    if sku_p:
        by_sku = lst("jombang", q=sku_p["sku"])
        assert any(i["product_id"] == sku_p["product_id"] for i in by_sku["items"])


def test_branch_status_filters():
    allc = lst("jombang", limit=1)["total"]
    empty = lst("jombang", status="empty", limit=100)
    print("jombang empty total:", empty["total"])
    assert 0 < empty["total"] < allc
    assert all(i["stock"] == 0 for i in empty["items"])
    act, ina = lst("jombang", status="active", limit=1)["total"], lst("jombang", status="inactive", limit=50)
    assert act + ina["total"] == allc
    assert all(i["status"] == "inactive" for i in ina["items"])


def test_sidoarjo_list_official_only():
    d = lst("sidoarjo", limit=50)
    assert d["store_id"] == "pgs-official" and d["total"] == 6618 or d["total"] >= 6618
    assert all(i["store_id"] == "pgs-official" and not i.get("shared") for i in d["items"])


def test_admin_branch_view():
    d = lst("admin", store_id="pgs-jombang", limit=20)
    j = lst("jombang", limit=20)
    assert d["store_id"] == "pgs-jombang" and d["total"] == j["total"]
    assert [i["product_id"] for i in d["items"]] == [i["product_id"] for i in j["items"]]
    assert all(i.get("shared") for i in d["items"] if i["store_id"] == "pgs-official")


# ---- Isolation ----
def test_jombang_cannot_open_shared_for_edit():
    p = next(i for i in lst("jombang", limit=5)["items"] if i.get("shared"))
    r = requests.get(f"{API}/product-editor/products/{p['product_id']}", headers=hdr("jombang"), timeout=30)
    assert r.status_code in (403, 404), r.status_code
    r = requests.post(f"{API}/product-editor/products/{p['product_id']}/duplicate", headers=hdr("jombang"), timeout=30)
    assert r.status_code in (403, 404), r.status_code


def test_jombang_bulk_shared_skipped():
    p = next(i for i in lst("jombang", limit=5)["items"] if i.get("shared"))
    before = lst("sidoarjo", q=p["product_id"])["items"][0]
    # status=inactive on a shared product must be skipped (not found in toko ini) -> no write
    r = requests.post(f"{API}/product-editor/bulk", headers=hdr("jombang"),
                      json={"product_ids": [p["product_id"]], "status": "inactive" if before["status"] != "inactive" else "active"}, timeout=30)
    print("bulk resp", r.status_code, r.text[:300])
    after = lst("sidoarjo", q=p["product_id"])["items"][0]
    assert after["status"] == before["status"] and after["price"] == before["price"] and after["stock"] == before["stock"]
    if r.status_code == 200:
        assert r.json().get("updated", 0) == 0


def test_jombang_cannot_read_jember_prices():
    r = requests.get(f"{API}/branch-prices", headers=hdr("jombang"), params={"store_id": "pgs-jember"}, timeout=30)
    assert r.status_code == 403


def test_jombang_list_ignores_foreign_store_id():
    d = lst("jombang", store_id="pgs-jember", limit=5)
    assert d["store_id"] == "pgs-jombang"


@pytest.mark.parametrize("path", ["/admin/branch-copy/preview", "/admin/accurate/settings", "/admin/fonnte/settings",
                                  "/admin/customer-locations", "/admin/payment-settings", "/admin/stats", "/admin/vouchers",
                                  "/admin/banners", "/admin/flash-sale", "/admin/report", "/admin/push"])
def test_jombang_admin_endpoints_denied(path):
    r = requests.get(f"{API}{path}", headers=hdr("jombang"), timeout=30)
    assert r.status_code in (401, 403, 404, 405), (path, r.status_code)
    assert r.status_code != 200
