# Iteration 58 retest: wishlist POST/DELETE branch price, ?branch= catalog search, featured_manual fallback
import os
import pytest
import requests
from pymongo import MongoClient


def _base():
    u = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL")
    if not u:
        for line in open("/app/frontend/.env"):
            if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
                u = line.split("=", 1)[1].strip().strip('"')
    return u.rstrip("/")


def _env(k):
    for line in open("/app/backend/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip('"')


API = f"{_base()}/api"
CREDS = {"admin": ("admin@pgs.id", "Admin1234!"), "jombang": ("jombang@pgs.id", "Jombang123!"), "demo": ("demo@pgs.id", "Demo1234!")}
TOK: dict = {}
STATE: dict = {"created": [], "wl_added": []}
SHARED_PID = "pgs-10062"  # Jombang 362000 vs Sidoarjo 360000
FIELDS = ("banner", "logo", "description", "phone", "address", "pickup_hours")
DB = MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]  # read-only checks


def login(who):
    if who not in TOK:
        e, p = CREDS[who]
        r = requests.post(f"{API}/auth/login", json={"email": e, "password": p}, timeout=30)
        assert r.status_code == 200, r.text
        TOK[who] = r.json()["token"]
    return TOK[who]


def H(who=None, store=None):
    h = {"Content-Type": "application/json"}
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
def cleanup():
    r = requests.get(f"{API}/store-appearance", headers=H("admin"), timeout=30)
    STATE["orig"] = {a["store_id"]: a for a in r.json()}
    yield
    a = STATE["orig"]["pgs-jombang"]
    print("restore jombang", requests.put(f"{API}/store-appearance/pgs-jombang", headers=H("admin"), json=body_of(a), timeout=30).status_code)
    for pid in STATE["created"]:
        requests.delete(f"{API}/seller/products/{pid}", headers=H("jombang"), timeout=30)
    for pid in STATE["wl_added"]:
        requests.delete(f"{API}/wishlist/{pid}", headers=H("demo"), timeout=30)


def _price(resp, pid):
    return next(p["price"] for p in resp.json()["items"] if p["product_id"] == pid)


# ---- wishlist POST/DELETE respect X-Store-Id ----
def test_wishlist_post_delete_branch_price():
    before = [p["product_id"] for p in requests.get(f"{API}/wishlist", headers=H("demo"), timeout=30).json()["items"]]
    other = next(p["product_id"] for p in requests.get(f"{API}/products?q=keset&limit=5", timeout=30).json() if p["product_id"] != SHARED_PID)
    for pid in (SHARED_PID, other):
        if pid not in before:
            STATE["wl_added"].append(pid)
    r = requests.post(f"{API}/wishlist/{SHARED_PID}", headers=H("demo", store="pgs-jombang"), timeout=30)
    assert r.status_code == 200, r.text
    assert _price(r, SHARED_PID) == 362000
    r2 = requests.post(f"{API}/wishlist/{other}", headers=H("demo"), timeout=30)
    assert _price(r2, SHARED_PID) == 360000  # no header -> Sidoarjo
    if other in STATE["wl_added"]:
        d = requests.delete(f"{API}/wishlist/{other}", headers=H("demo", store="pgs-jombang"), timeout=30)
        assert d.status_code == 200
        assert other not in [p["product_id"] for p in d.json()["items"]]
        assert _price(d, SHARED_PID) == 362000
        STATE["wl_added"].remove(other)


# ---- ?branch= search returns shared catalog with branch prices ----
def test_products_branch_keset():
    r = requests.get(f"{API}/products", params={"branch": "pgs-jombang", "q": "keset", "limit": 40}, timeout=30)
    assert r.status_code == 200
    items = r.json()
    assert len(items) > 0
    assert any(p.get("store_id") == "pgs-official" for p in items), "shared catalog expected"
    ids = [p["product_id"] for p in items]
    bp = {d["product_id"]: d["price"] for d in DB.store_stock.find({"store_id": "pgs-jombang", "product_id": {"$in": ids}, "price": {"$gt": 0}}, {"_id": 0})}
    STATE["keset_bp"] = len(bp)
    print("keset results", len(items), "with jombang price", len(bp))
    for p in items:
        if p["product_id"] in bp and not p.get("flash_price"):
            assert p["price"] == bp[p["product_id"]], (p["product_id"], p["price"], bp[p["product_id"]])
    # old store= behaviour still only own products
    own = requests.get(f"{API}/products", params={"store": "pgs-jombang", "q": "keset"}, timeout=30).json()
    assert all(p["store_id"] == "pgs-jombang" for p in own)


def test_products_branch_shared_price():
    r = requests.get(f"{API}/products", params={"branch": "pgs-jombang", "q": requests.get(f"{API}/products/{SHARED_PID}", timeout=30).json()["name"][:20]}, timeout=30)
    hit = [p for p in r.json() if p["product_id"] == SHARED_PID]
    assert hit and hit[0]["price"] == 362000, hit[:1]


# ---- featured_manual false when manual ids all unavailable ----
def test_featured_manual_false_when_unavailable():
    cats = requests.get(f"{API}/categories", timeout=30).json()
    r = requests.post(f"{API}/seller/products", headers=H("jombang"), json={"name": "TEST_Iter58 Featured", "description": "TEST", "category": cats[0]["category_id"],
                                                                             "price": 15000, "stock": 3, "images": ["https://example.com/a.jpg"]}, timeout=30)
    assert r.status_code == 200, r.text
    pid = r.json()["product_id"]
    STATE["created"].append(pid)
    s = requests.put(f"{API}/store-appearance/pgs-jombang", headers=H("jombang"), json=body_of(STATE["orig"]["pgs-jombang"], featured_ids=[pid]), timeout=30)
    assert s.status_code == 200, s.text
    page = requests.get(f"{API}/stores/pgs-jombang/page", timeout=30).json()
    assert page["featured_manual"] is True and [p["product_id"] for p in page["featured"]] == [pid]
    d = requests.delete(f"{API}/seller/products/{pid}", headers=H("jombang"), timeout=30)
    assert d.status_code in (200, 204), d.text
    page = requests.get(f"{API}/stores/pgs-jombang/page", timeout=30).json()
    assert page["featured_manual"] is False, page["featured_manual"]
    assert pid not in [p["product_id"] for p in page["featured"]]
