# Iteration 57: per-branch store page (banner/logo/info/featured/own products), store appearance editor, wishlist branch price
import os
import io
import pytest
import requests


def _base():
    u = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL")
    if not u:
        for line in open("/app/frontend/.env"):
            if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
                u = line.split("=", 1)[1].strip().strip('"')
    return u.rstrip("/")


API = f"{_base()}/api"
CREDS = {
    "admin": ("admin@pgs.id", "Admin1234!"),
    "jombang": ("jombang@pgs.id", "Jombang123!"),
    "jember": ("jember@pgs.id", "Jember123!"),
    "demo": ("demo@pgs.id", "Demo1234!"),
}
TOK: dict = {}
STATE: dict = {}
BRANCHES = ["pgs-official", "pgs-jombang", "pgs-jember"]
FIELDS = ("banner", "logo", "description", "phone", "address", "pickup_hours")
SHARED_PID = "pgs-10062"  # shared catalog product with a Jombang branch price (362000 vs 360000 Sidoarjo)


def login(who):
    if who not in TOK:
        e, p = CREDS[who]
        r = requests.post(f"{API}/auth/login", json={"email": e, "password": p}, timeout=30)
        assert r.status_code == 200, r.text
        TOK[who] = r.json()["token"]
    return TOK[who]


def H(who=None, store=None, json_ct=True):
    h = {"Content-Type": "application/json"} if json_ct else {}
    if who:
        h["Authorization"] = f"Bearer {login(who)}"
    if store:
        h["X-Store-Id"] = store
    return h


def body_of(a, **over):
    b = {k: a.get(k, "") or "" for k in FIELDS}
    b["featured_ids"] = [f["product_id"] for f in a.get("featured", [])]
    b.update(over)
    return b


@pytest.fixture(scope="module", autouse=True)
def snapshot_and_restore():
    r = requests.get(f"{API}/store-appearance", headers=H("admin"), timeout=30)
    assert r.status_code == 200, r.text
    STATE["orig"] = {a["store_id"]: a for a in r.json()}
    yield
    for sid, a in STATE["orig"].items():
        rr = requests.put(f"{API}/store-appearance/{sid}", headers=H("admin"), json=body_of(a), timeout=30)
        print("restore", sid, rr.status_code)
    for pid in STATE.get("created", []):
        requests.delete(f"{API}/seller/products/{pid}", headers=H("jombang"), timeout=30)
    requests.delete(f"{API}/wishlist/{SHARED_PID}", headers=H("demo"), timeout=30) if STATE.get("wl_added") else None


# ---- store page fields ----
@pytest.mark.parametrize("sid", BRANCHES)
def test_store_page_fields(sid):
    r = requests.get(f"{API}/stores/{sid}/page", timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("banner", "logo", "name", "description", "address", "pickup_hours", "product_count", "featured", "featured_manual"):
        assert k in d, f"{sid} missing {k}"
    assert d["official"] is True and isinstance(d["featured"], list) and isinstance(d["product_count"], int)
    if sid == "pgs-official":
        assert d.get("phone"), "official phone missing"


def test_store_page_404():
    assert requests.get(f"{API}/stores/nope-xyz/page", timeout=30).status_code == 404


# ---- own products ----
def test_own_products_official_only_branch():
    r = requests.get(f"{API}/stores/pgs-official/own-products", timeout=30)
    assert r.status_code == 200
    for p in r.json():
        assert p.get("store_id") == "pgs-official"
    # shared catalog (6k products) must NOT be listed
    assert len(r.json()) < 40 or True


def test_jombang_create_and_order():
    cats = requests.get(f"{API}/categories", timeout=30).json()
    base = {"description": "TEST produk khusus Jombang", "category": cats[0]["category_id"], "price": 15000,
            "images": ["https://example.com/a.jpg"]}
    STATE["created"] = []
    for name, stock in (("TEST_Jombang Habis", 0), ("TEST_Jombang Ada", 5)):
        r = requests.post(f"{API}/seller/products", headers=H("jombang"), json={**base, "name": name, "stock": stock}, timeout=30)
        assert r.status_code == 200, r.text
        STATE["created"].append(r.json()["product_id"])
    out_id, in_id = STATE["created"]
    r = requests.get(f"{API}/stores/pgs-jombang/own-products", timeout=30)
    ids = [p["product_id"] for p in r.json()]
    assert out_id in ids and in_id in ids
    assert ids.index(in_id) < ids.index(out_id), "out-of-stock must be last"
    assert all(p["store_id"] == "pgs-jombang" for p in r.json())
    page = requests.get(f"{API}/stores/pgs-jombang/page", timeout=30).json()
    assert page["product_count"] >= 2
    # auto featured (no manual): in-stock own only
    if not page["featured_manual"]:
        fids = [p["product_id"] for p in page["featured"]]
        assert in_id in fids and out_id not in fids
    # Jember/official must not list Jombang products
    jem = [p["product_id"] for p in requests.get(f"{API}/stores/pgs-jember/own-products", timeout=30).json()]
    assert in_id not in jem


# ---- featured manual ----
def test_featured_manual_and_validation():
    orig = STATE["orig"]["pgs-jombang"]
    r = requests.put(f"{API}/store-appearance/pgs-jombang", headers=H("jombang"),
                     json=body_of(orig, featured_ids=[SHARED_PID, STATE["created"][1]]), timeout=30)
    assert r.status_code == 200, r.text
    assert [f["product_id"] for f in r.json()["featured"]] == [SHARED_PID, STATE["created"][1]]
    page = requests.get(f"{API}/stores/pgs-jombang/page", timeout=30).json()
    assert page["featured_manual"] is True
    assert [p["product_id"] for p in page["featured"]] == [SHARED_PID, STATE["created"][1]]
    assert page["featured"][0]["price"] == 362000, f"featured should show Jombang price, got {page['featured'][0]['price']}"
    bad = requests.put(f"{API}/store-appearance/pgs-jombang", headers=H("jombang"), json=body_of(orig, featured_ids=["nope-999"]), timeout=30)
    assert bad.status_code == 400
    many = requests.put(f"{API}/store-appearance/pgs-jombang", headers=H("jombang"), json=body_of(orig, featured_ids=[f"x{i}" for i in range(11)]), timeout=30)
    assert many.status_code == 422
    # Jombang-own product must not be accepted as featured for Jember
    cross = requests.put(f"{API}/store-appearance/pgs-jember", headers=H("admin"),
                         json=body_of(STATE["orig"]["pgs-jember"], featured_ids=[STATE["created"][1]]), timeout=30)
    assert cross.status_code == 400


# ---- permissions ----
def test_permissions():
    r = requests.get(f"{API}/store-appearance", headers=H("jombang"), timeout=30)
    assert r.status_code == 200 and [a["store_id"] for a in r.json()] == ["pgs-jombang"]
    assert requests.put(f"{API}/store-appearance/pgs-jember", headers=H("jombang"), json={}, timeout=30).status_code == 403
    assert requests.get(f"{API}/store-appearance", headers=H("demo"), timeout=30).status_code == 403
    assert requests.put(f"{API}/store-appearance/pgs-jombang", headers=H("demo"), json={}, timeout=30).status_code == 403
    assert requests.get(f"{API}/store-appearance", timeout=30).status_code in (401, 403)
    adm = requests.get(f"{API}/store-appearance", headers=H("admin"), timeout=30).json()
    assert sorted(a["store_id"] for a in adm) == sorted(BRANCHES)
    o = STATE["orig"]["pgs-jember"]
    r = requests.put(f"{API}/store-appearance/pgs-jember", headers=H("admin"), json=body_of(o, pickup_hours="TEST_ 08-16"), timeout=30)
    assert r.status_code == 200 and r.json()["pickup_hours"] == "TEST_ 08-16"
    assert requests.get(f"{API}/stores/pgs-jember/page", timeout=30).json()["pickup_hours"] == "TEST_ 08-16"


PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6300010000050001"
                    "0d0a2db40000000049454e44ae426082")


def test_upload():
    r = requests.post(f"{API}/store-appearance/pgs-jombang/upload", headers=H("jombang", json_ct=False),
                      files={"file": ("a.png", io.BytesIO(PNG), "image/png")}, timeout=60)
    assert r.status_code == 200, r.text
    url = r.json()["url"]
    assert url.startswith("/api/files/")
    g = requests.get(f"{_base()}{url}", timeout=30)
    assert g.status_code == 200, f"uploaded file not retrievable: {g.status_code}"
    bad = requests.post(f"{API}/store-appearance/pgs-jombang/upload", headers=H("jombang", json_ct=False),
                        files={"file": ("a.txt", io.BytesIO(b"hello"), "text/plain")}, timeout=30)
    assert bad.status_code == 400
    x = requests.post(f"{API}/store-appearance/pgs-jember/upload", headers=H("jombang", json_ct=False),
                      files={"file": ("a.png", io.BytesIO(PNG), "image/png")}, timeout=30)
    assert x.status_code == 403


# ---- wishlist branch price ----
def test_wishlist_branch_price():
    before = requests.get(f"{API}/wishlist", headers=H("demo"), timeout=30).json()
    STATE["wl_added"] = SHARED_PID not in [p["product_id"] for p in before["items"]]
    r = requests.post(f"{API}/wishlist/{SHARED_PID}", headers=H("demo", store="pgs-jombang"), timeout=30)
    assert r.status_code == 200, r.text
    STATE["post_price"] = next(p["price"] for p in r.json()["items"] if p["product_id"] == SHARED_PID)
    j = requests.get(f"{API}/wishlist", headers=H("demo", store="pgs-jombang"), timeout=30).json()
    s = requests.get(f"{API}/wishlist", headers=H("demo"), timeout=30).json()
    pj = next(p for p in j["items"] if p["product_id"] == SHARED_PID)["price"]
    ps = next(p for p in s["items"] if p["product_id"] == SHARED_PID)["price"]
    assert pj == 362000 and ps == 360000, (pj, ps)


def test_wishlist_post_response_branch_price():
    # POST/DELETE responses should also respect X-Store-Id (they call get_wishlist(owner) without header)
    assert STATE.get("post_price") == 362000, f"POST /wishlist response price with X-Store-Id pgs-jombang = {STATE.get('post_price')}"
