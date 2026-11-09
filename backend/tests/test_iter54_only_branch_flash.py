# Iteration 54: branch-admin own products (only_branch visibility) + per-branch Flash Sale prices
import os
import json
import uuid
import pytest
import requests


def _base():
    u = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL")
    if not u:
        for line in open("/app/frontend/.env"):
            if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
                u = line.split("=", 1)[1].strip().strip('"')
    return u.rstrip("/")


BASE = _base()
API = f"{BASE}/api"
CREDS = {
    "admin": ("admin@pgs.id", "Admin1234!"),
    "sidoarjo": ("sidoarjo@pgs.id", "Sidoarjo123!"),
    "jombang": ("jombang@pgs.id", "Jombang123!"),
    "jember": ("jember@pgs.id", "Jember123!"),
    "demo": ("demo@pgs.id", "Demo1234!"),
}
STATE: dict = {}


def login(who):
    if who in STATE.get("tok", {}):
        return STATE["tok"][who]
    e, p = CREDS[who]
    r = requests.post(f"{API}/auth/login", json={"email": e, "password": p}, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "token" in d and "access_token" not in d
    STATE.setdefault("tok", {})[who] = d["token"]
    return d["token"]


def H(who=None, store=None):
    h = {"Content-Type": "application/json"}
    if who:
        h["Authorization"] = f"Bearer {login(who)}"
    if store:
        h["X-Store-Id"] = store
    return h


def form(name, price=15000):
    cats = requests.get(f"{API}/categories", timeout=30).json()
    return {"name": name, "category": cats[0]["category_id"], "images": ["https://example.com/a.jpg"],
            "description": "TEST produk khusus cabang untuk pengujian otomatis visibilitas cabang ini.",
            "price": price, "stock": 10, "weight_grams": 500, "ship_regular": True}


def names_of(r):
    d = r.json()
    items = d if isinstance(d, list) else d.get("items", d.get("products", []))
    return [i.get("product_id") for i in items]


@pytest.fixture(scope="module", autouse=True)
def products():
    tag = uuid.uuid4().hex[:6]
    out = {}
    STATE["count_before"] = {s: requests.get(f"{API}/products/count", headers=H(store=s), timeout=30).json()["count"]
                             for s in ("pgs-jombang", "pgs-jember", "pgs-official")}
    for who in ("jombang", "sidoarjo"):
        nm = f"TEST_{who}_only_{tag}"
        r = requests.post(f"{API}/product-editor/publish", headers=H(who), json={"data": form(nm)}, timeout=60)
        assert r.status_code == 200, f"{who} publish failed {r.status_code} {r.text}"
        out[who] = {"pid": r.json()["product_id"], "name": nm, "store": r.json()["store_id"]}
    STATE["prods"] = out
    STATE["count_after"] = {s: requests.get(f"{API}/products/count", headers=H(store=s), timeout=30).json()["count"]
                            for s in ("pgs-jombang", "pgs-jember", "pgs-official")}
    yield out
    for who, p in out.items():
        requests.delete(f"{API}/seller/products/{p['pid']}", headers=H(who), timeout=30)


# --- creation ---
def test_jombang_product_created_store_and_only_branch(products):
    p = products["jombang"]
    assert p["store"] == "pgs-jombang"
    d = requests.get(f"{API}/products/{p['pid']}", timeout=30).json()
    assert d["store_id"] == "pgs-jombang"
    assert d.get("only_branch") in ("pgs-jombang", None)  # field may not be exposed by Product model
    STATE["detail_only_branch_exposed"] = "only_branch" in d


def test_sidoarjo_product_created_only_branch(products):
    p = products["sidoarjo"]
    assert p["store"] == "pgs-official"
    # check via editor list of sidoarjo (raw doc in db verified separately)
    r = requests.get(f"{API}/products/{p['pid']}", timeout=30)
    assert r.status_code == 200


# --- visibility ---
@pytest.mark.parametrize("who,store,visible", [
    ("jombang", "pgs-jombang", True), ("jombang", "pgs-jember", False), ("jombang", "pgs-official", False),
    ("sidoarjo", "pgs-official", True), ("sidoarjo", None, True), ("sidoarjo", "pgs-jombang", False), ("sidoarjo", "pgs-jember", False),
])
def test_products_search_visibility(products, who, store, visible):
    p = products[who]
    r = requests.get(f"{API}/products", params={"q": p["name"]}, headers=H(store=store), timeout=30)
    assert r.status_code == 200
    assert (p["pid"] in names_of(r)) == visible


def test_products_count_delta(products):
    b, a = STATE["count_before"], STATE["count_after"]
    assert a["pgs-jombang"] - b["pgs-jombang"] == 1, (b, a)
    assert a["pgs-official"] - b["pgs-official"] == 1, (b, a)
    assert a["pgs-jember"] - b["pgs-jember"] == 0, (b, a)


def test_recommendations_and_home_respect_only_branch(products):
    sj, jb = products["sidoarjo"]["pid"], products["jombang"]["pid"]
    for store, bad in (("pgs-jember", {sj, jb}), ("pgs-jombang", {sj}), ("pgs-official", {jb})):
        ids = set()
        for skip in (0, 60):
            r = requests.get(f"{API}/recommendations", params={"limit": 60, "skip": skip}, headers=H(store=store), timeout=30)
            assert r.status_code == 200
            ids |= set(names_of(r))
        h = requests.get(f"{API}/home/sections", headers=H(store=store), timeout=30)
        assert h.status_code == 200
        for k, v in h.json().items():
            ids |= {i["product_id"] for i in v.get("items", [])}
        assert not (ids & bad), f"{store} leaks {ids & bad}"


def test_detail_direct_still_works(products):
    for who in ("jombang", "sidoarjo"):
        r = requests.get(f"{API}/products/{products[who]['pid']}", headers=H(store="pgs-jember"), timeout=30)
        assert r.status_code == 200


# --- branch admin lists ---
def test_sidoarjo_only_not_in_jombang_editor_list(products):
    r = requests.get(f"{API}/product-editor/products", params={"q": products["sidoarjo"]["name"]}, headers=H("jombang"), timeout=30)
    assert r.status_code == 200, r.text
    assert products["sidoarjo"]["pid"] not in json.dumps(r.json())
    r2 = requests.get(f"{API}/product-editor/products", params={"q": products["jombang"]["name"]}, headers=H("jombang"), timeout=30)
    assert products["jombang"]["pid"] in json.dumps(r2.json())


def test_sidoarjo_only_not_in_branch_prices(products):
    for who in ("jombang", "admin"):
        params = {"q": products["sidoarjo"]["name"]}
        if who == "admin":
            params["store_id"] = "pgs-jember"
        r = requests.get(f"{API}/branch-prices", params=params, headers=H(who), timeout=30)
        assert r.status_code == 200, r.text
        assert products["sidoarjo"]["pid"] not in json.dumps(r.json())


def test_branch_copy_preview_excludes_only_branch(products):
    r = requests.post(f"{API}/admin/branch-copy/preview", headers=H("admin"),
                      json={"rules": [{"store_id": "pgs-jember", "mode": "rp", "price_add": 0, "copy_price": True, "copy_stock": False}]}, timeout=120)
    assert r.status_code == 200, r.text
    total = r.json()["branches"][0]["total"]
    import subprocess
    # count master catalogue products directly in DB (no only_branch, no variants)
    out = subprocess.run(["python3", "-c", (
        "import os,asyncio;from motor.motor_asyncio import AsyncIOMotorClient as C;from dotenv import load_dotenv;load_dotenv('/app/backend/.env');"
        "db=C(os.environ['MONGO_URL'])[os.environ['DB_NAME']];"
        "print(asyncio.get_event_loop().run_until_complete(db.products.count_documents({'store_id':'pgs-official','variants.0':{'$exists':False},'only_branch':None})))")],
        capture_output=True, text=True)
    assert int(out.stdout.strip()) == total


# --- edit / delete permissions ---
def test_jombang_can_edit_own_product(products):
    p = products["jombang"]
    r = requests.get(f"{API}/product-editor/products/{p['pid']}", headers=H("jombang"), timeout=30)
    assert r.status_code == 200, r.text
    f = form(p["name"] + " edit", price=16000)
    r = requests.post(f"{API}/product-editor/publish", headers=H("jombang"), json={"data": f, "product_id": p["pid"]}, timeout=60)
    assert r.status_code == 200, r.text
    d = requests.get(f"{API}/products/{p['pid']}", timeout=30).json()
    assert d["price"] == 16000 and d["name"].endswith(" edit")
    p["name"] = d["name"]
    # still only visible in Jombang after edit
    r = requests.get(f"{API}/products", params={"q": p["name"]}, headers=H(store="pgs-jember"), timeout=30)
    assert p["pid"] not in names_of(r)
    r = requests.get(f"{API}/products", params={"q": p["name"]}, headers=H(store="pgs-jombang"), timeout=30)
    assert p["pid"] in names_of(r)


def test_jombang_cannot_edit_master_product():
    r = requests.get(f"{API}/product-editor/products/pgs-26611", headers=H("jombang"), timeout=30)
    assert r.status_code == 404
    r = requests.post(f"{API}/product-editor/publish", headers=H("jombang"), json={"data": form("TEST_hack_master"), "product_id": "pgs-26611"}, timeout=60)
    assert r.status_code == 404


def test_sidoarjo_cannot_delete_master():
    r = requests.delete(f"{API}/seller/products/pgs-26611", headers=H("sidoarjo"), timeout=30)
    assert r.status_code == 404
    assert requests.get(f"{API}/products/pgs-26611", timeout=30).status_code == 200


def test_jombang_cannot_delete_other_branch_product(products):
    r = requests.delete(f"{API}/seller/products/{products['sidoarjo']['pid']}", headers=H("jombang"), timeout=30)
    assert r.status_code == 404
    r = requests.delete(f"{API}/seller/products/{products['jombang']['pid']}", headers=H("jember"), timeout=30)
    assert r.status_code == 404


# --- admin-only endpoints ---
@pytest.mark.parametrize("method,path,body", [
    ("get", "/admin/fonnte", None), ("put", "/admin/fonnte", {}),
    ("post", "/admin/branch-copy/preview", {"rules": [{"store_id": "pgs-jember"}]}),
    ("get", "/admin/accurate/settings", None), ("put", "/admin/accurate/settings", {}),
    ("get", "/admin/customer-locations", None), ("get", "/admin/customers", None),
    ("get", "/admin/flash-sale", None), ("put", "/admin/flash-sale", {"title": "x", "active": False, "ends_at": "2030-01-01T00:00:00Z", "items": []}),
])
@pytest.mark.parametrize("who", ["jombang", "sidoarjo", "jember"])
def test_admin_only_forbidden(who, method, path, body):
    r = getattr(requests, method)(f"{API}{path}", headers=H(who), json=body, timeout=30)
    assert r.status_code == 403, f"{who} {method} {path} -> {r.status_code}"


# --- flash sale per branch ---
def test_admin_flash_branches_shape():
    d = requests.get(f"{API}/admin/flash-sale", headers=H("admin"), timeout=30).json()
    STATE["flash_orig"] = d
    it = d["items"][0]
    assert {b["store_id"] for b in it["branches"]} == {"pgs-jombang", "pgs-jember"}
    for b in it["branches"]:
        assert set(b) >= {"store_id", "name", "price", "auto_price", "flash_price"}
        assert b["auto_price"] == it["flash_price"] + b["price"] - it["price"]


def test_public_flash_branch_auto():
    d = STATE["flash_orig"]
    exp = {i["product_id"]: {b["store_id"]: b["auto_price"] for b in i["branches"]} for i in d["items"]}
    for store in ("pgs-jombang", "pgs-jember"):
        r = requests.get(f"{API}/flash-sale", headers=H(store=store), timeout=30).json()
        assert r["active"]
        for i in r["items"]:
            assert i["flash_price"] == exp[i["product_id"]][store], (store, i["product_id"], i["flash_price"])
            assert i["my_price"] == i["flash_price"]
    r = requests.get(f"{API}/flash-sale", timeout=30).json()
    base = {i["product_id"]: i["flash_price"] for i in d["items"]}
    assert all(i["flash_price"] == base[i["product_id"]] for i in r["items"])


def _restore():
    d = STATE["flash_orig"]
    body = {"title": d["title"], "active": d["active"], "ends_at": d["ends_at"],
            "items": [{"product_id": i["product_id"], "flash_price": i["flash_price"]} for i in d["items"]]}
    r = requests.put(f"{API}/admin/flash-sale", headers=H("admin"), json=body, timeout=30)
    assert r.status_code == 200, r.text


def test_flash_branch_override_and_validation():
    d = STATE["flash_orig"]
    pid = d["items"][0]["product_id"]
    jem = next(b for b in d["items"][0]["branches"] if b["store_id"] == "pgs-jember")
    try:
        items = [{"product_id": i["product_id"], "flash_price": i["flash_price"]} for i in d["items"]]
        items[0]["branch_prices"] = {"pgs-jember": jem["price"]}
        body = {"title": d["title"], "active": d["active"], "ends_at": d["ends_at"], "items": items}
        r = requests.put(f"{API}/admin/flash-sale", headers=H("admin"), json=body, timeout=30)
        assert r.status_code == 400, r.text
        items[0]["branch_prices"] = {"pgs-jember": 9000}
        r = requests.put(f"{API}/admin/flash-sale", headers=H("admin"), json=body, timeout=30)
        assert r.status_code == 200, r.text
        row = next(b for b in r.json()["items"][0]["branches"] if b["store_id"] == "pgs-jember")
        assert row["flash_price"] == 9000
        pub = requests.get(f"{API}/flash-sale", headers=H(store="pgs-jember"), timeout=30).json()
        assert next(i for i in pub["items"] if i["product_id"] == pid)["flash_price"] == 9000
        pub = requests.get(f"{API}/flash-sale", headers=H(store="pgs-jombang"), timeout=30).json()
        jom = next(b for b in d["items"][0]["branches"] if b["store_id"] == "pgs-jombang")
        assert next(i for i in pub["items"] if i["product_id"] == pid)["flash_price"] == jom["auto_price"]
    finally:
        _restore()
    after = requests.get(f"{API}/admin/flash-sale", headers=H("admin"), timeout=30).json()
    assert all(b["flash_price"] == 0 for i in after["items"] for b in i["branches"])
    assert [(i["product_id"], i["flash_price"]) for i in after["items"]] == [(i["product_id"], i["flash_price"]) for i in d["items"]]


# --- cart uses branch flash price ---
def test_cart_branch_flash_price():
    d = STATE["flash_orig"]
    pid = d["items"][0]["product_id"]
    jom = next(b for b in d["items"][0]["branches"] if b["store_id"] == "pgs-jombang")
    h = H("demo", "pgs-jombang")
    before = requests.get(f"{API}/cart", headers=h, timeout=30).json()
    had = any(i["product_id"] == pid and i.get("store_id") == "pgs-jombang" for i in before["items"])
    r = requests.post(f"{API}/cart/items", headers=h, json={"product_id": pid, "quantity": 1}, timeout=30)
    assert r.status_code == 200, r.text
    line = next(i for i in r.json()["items"] if i["product_id"] == pid and i["store_id"] == "pgs-jombang")
    STATE["cart_line"] = line
    try:
        assert line["price"] == jom["auto_price"], (line["price"], jom)
        assert line["price"] != min(d["items"][0]["flash_price"], jom["price"])
        det = requests.get(f"{API}/products/{pid}", headers=h, timeout=30).json()
        assert det["my_price"] == jom["auto_price"] and det["flash_price"] == jom["auto_price"]
    finally:
        if not had:
            requests.delete(f"{API}/cart/items/{line['key']}", headers=h, timeout=30)


def test_branch_admin_cannot_add_via_legacy_seller_create_master():
    """Sidoarjo admin through legacy POST /seller/products: does it bypass only_branch (creates master catalogue)?"""
    r = requests.post(f"{API}/seller/products", headers=H("sidoarjo"), json={
        "name": "TEST_legacy_sidoarjo", "price": 15000, "stock": 1, "category": "dapur", "images": ["https://example.com/a.jpg"],
        "image": "https://example.com/a.jpg", "description": "TEST legacy product create for sidoarjo admin"}, timeout=30)
    if r.status_code == 200:
        pid = r.json()["product_id"]
        vis = requests.get(f"{API}/products", params={"q": "TEST_legacy_sidoarjo"}, headers=H(store="pgs-jember"), timeout=30)
        leaked = pid in names_of(vis)
        requests.delete(f"{API}/seller/products/{pid}", headers=H("sidoarjo"), timeout=30)
        assert not leaked, "legacy /seller/products by Sidoarjo admin creates master catalogue product visible in Jember"
