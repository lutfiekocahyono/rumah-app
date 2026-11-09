# Iteration 56: per-branch Flash Sale schedules (GET/PUT /api/flash-sale/schedules) + effect on flash/product/cart
import os
import subprocess
from datetime import datetime, timedelta, timezone
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
    "sidoarjo": ("sidoarjo@pgs.id", "Sidoarjo123!"),
    "jombang": ("jombang@pgs.id", "Jombang123!"),
    "jember": ("jember@pgs.id", "Jember123!"),
    "demo": ("demo@pgs.id", "Demo1234!"),
}
TOK: dict = {}
ST: dict = {}


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


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc) if s else None


def now():
    return datetime.now(timezone.utc)


def put(who, sid, body):
    return requests.put(f"{API}/flash-sale/schedules/{sid}", headers=H(who), json=body, timeout=30)


@pytest.fixture(scope="module", autouse=True)
def restore():
    ST["sido_ends"] = parse(requests.get(f"{API}/flash-sale", headers=H(store="pgs-official"), timeout=30).json().get("ends_at"))
    yield
    for sid in ("pgs-jombang", "pgs-jember"):
        put("admin", sid, {"follow": True})
    # never leave an own schedule for Sidoarjo
    subprocess.run(["mongosh", "--quiet", "test_database", "--eval",
                    'db.settings.updateOne({key:"flash_sale"},{$unset:{"schedules.pgs-official":""}})'], check=False)


# --- GET schedules: scope by role ---
def test_get_schedules_jombang_only_own():
    r = requests.get(f"{API}/flash-sale/schedules", headers=H("jombang"), timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert [x["store_id"] for x in d] == ["pgs-jombang"]


def test_get_schedules_sidoarjo_only_own():
    r = requests.get(f"{API}/flash-sale/schedules", headers=H("sidoarjo"), timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert [x["store_id"] for x in d] == ["pgs-official"]
    assert d[0]["follows_sidoarjo"] is False


def test_get_schedules_admin_all_fields():
    r = requests.get(f"{API}/flash-sale/schedules", headers=H("admin"), timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert sorted(x["store_id"] for x in d) == ["pgs-jember", "pgs-jombang", "pgs-official"]
    for x in d:
        assert set(["store_id", "name", "own", "starts_at", "ends_at", "status", "follows_sidoarjo"]) <= set(x)
        assert x["status"] in ("running", "upcoming", "ended", "off")
        assert isinstance(x["name"], str) and x["name"]


def test_get_schedules_customer_403():
    r = requests.get(f"{API}/flash-sale/schedules", headers=H("demo"), timeout=30)
    assert r.status_code == 403, r.text


def test_get_schedules_unauth_401():
    r = requests.get(f"{API}/flash-sale/schedules", timeout=30)
    assert r.status_code in (401, 403), r.text


# --- PUT permissions & validation ---
def test_put_jombang_other_branch_403():
    r = put("jombang", "pgs-jember", {"follow": False, "ends_at": iso(now() + timedelta(hours=2))})
    assert r.status_code == 403, r.text


def test_put_customer_403():
    r = put("demo", "pgs-jombang", {"follow": True})
    assert r.status_code == 403, r.text


def test_put_validation_ends_le_starts():
    t = now() + timedelta(hours=5)
    r = put("jombang", "pgs-jombang", {"follow": False, "starts_at": iso(t), "ends_at": iso(t - timedelta(hours=1))})
    assert r.status_code == 400, r.text
    r = put("jombang", "pgs-jombang", {"follow": False, "starts_at": iso(t), "ends_at": iso(t)})
    assert r.status_code == 400, r.text


def test_put_validation_ends_past():
    r = put("jombang", "pgs-jombang", {"follow": False, "ends_at": iso(now() - timedelta(hours=1))})
    assert r.status_code == 400, r.text


def test_put_validation_missing_ends():
    r = put("jombang", "pgs-jombang", {"follow": False, "starts_at": iso(now() + timedelta(hours=1))})
    assert r.status_code == 400, r.text


def test_put_follow_true_sidoarjo_400():
    r = put("admin", "pgs-official", {"follow": True})
    assert r.status_code == 400, r.text
    r = put("sidoarjo", "pgs-official", {"follow": True})
    assert r.status_code == 400, r.text


def test_put_jombang_own_200():
    end = now() + timedelta(hours=6)
    r = put("jombang", "pgs-jombang", {"follow": False, "ends_at": iso(end)})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["store_id"] == "pgs-jombang" and d["own"] is True and d["follows_sidoarjo"] is False
    assert d["status"] == "running"
    assert abs((parse(d["ends_at"]) - end).total_seconds()) < 2


# --- effect: Jombang upcoming -> no flash for Jombang buyers ---
def test_jombang_upcoming_disables_flash():
    start, end = now() + timedelta(hours=3), now() + timedelta(hours=8)
    r = put("jombang", "pgs-jombang", {"follow": False, "starts_at": iso(start), "ends_at": iso(end)})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "upcoming"
    fj = requests.get(f"{API}/flash-sale", headers=H(store="pgs-jombang"), timeout=30).json()
    assert fj["active"] is False and fj["items"] == []
    fs = requests.get(f"{API}/flash-sale", headers=H(store="pgs-official"), timeout=30).json()
    assert fs["active"] is True and fs["items"]
    ST["pid"] = fs["items"][0]["product_id"]
    assert parse(fs["ends_at"]) == ST["sido_ends"]
    fe = requests.get(f"{API}/flash-sale", headers=H(store="pgs-jember"), timeout=30).json()
    assert fe["active"] is True and parse(fe["ends_at"]) == ST["sido_ends"]


def test_jombang_upcoming_product_detail_no_flash():
    pid = ST["pid"]
    dj = requests.get(f"{API}/products/{pid}", headers=H(store="pgs-jombang"), timeout=30).json()
    assert dj["flash_price"] is None and dj.get("flash_ends_at") is None
    ds = requests.get(f"{API}/products/{pid}", headers=H(store="pgs-official"), timeout=30).json()
    assert ds["flash_price"] is not None


def test_jombang_upcoming_cart_normal_price():
    pid = ST["pid"]
    h = H("demo", "pgs-jombang")
    before = requests.get(f"{API}/cart", headers=h, timeout=30).json()
    had = any(i["product_id"] == pid and i.get("store_id") == "pgs-jombang" for i in before["items"])
    r = requests.post(f"{API}/cart/items", headers=h, json={"product_id": pid, "quantity": 1}, timeout=30)
    assert r.status_code == 200, r.text
    line = next(i for i in r.json()["items"] if i["product_id"] == pid and i["store_id"] == "pgs-jombang")
    try:
        det = requests.get(f"{API}/products/{pid}", headers=h, timeout=30).json()
        adm = requests.get(f"{API}/admin/flash-sale", headers=H("admin"), timeout=30).json()
        it = next(i for i in adm["items"] if i["product_id"] == pid)
        jom = next((b for b in it["branches"] if b["store_id"] == "pgs-jombang"), None)
        print("line", line["price"], line["base_price"], line["quantity"], "detail my_price", det["my_price"], "jombang", jom)
        assert line["base_price"] == (jom["price"] if jom else it["price"])
        assert line["price"] != (jom["auto_price"] if jom else it["flash_price"]), "flash price still applied in Jombang cart"
        if line["quantity"] == 1:
            assert line["price"] == det["my_price"], (line, det["my_price"])
    finally:
        if not had:
            requests.delete(f"{API}/cart/items/{line['key']}", headers=h, timeout=30)


# --- effect: Jember own end time ---
def test_jember_own_ends_at():
    end = (now() + timedelta(hours=1)).replace(microsecond=0)
    r = put("admin", "pgs-jember", {"follow": False, "ends_at": iso(end)})
    assert r.status_code == 200, r.text
    fe = requests.get(f"{API}/flash-sale", headers=H(store="pgs-jember"), timeout=30).json()
    assert fe["active"] is True and parse(fe["ends_at"]) == end, fe.get("ends_at")
    pid = fe["items"][0]["product_id"]
    de = requests.get(f"{API}/products/{pid}", headers=H(store="pgs-jember"), timeout=30).json()
    assert de["flash_price"] is not None and parse(de["flash_ends_at"]) == end
    fs = requests.get(f"{API}/flash-sale", headers=H(store="pgs-official"), timeout=30).json()
    assert parse(fs["ends_at"]) == ST["sido_ends"]


def test_jember_admin_cannot_touch_jombang():
    r = put("jember", "pgs-jombang", {"follow": True})
    assert r.status_code == 403, r.text


# --- follow true resets ---
def test_follow_true_resets():
    for who, sid in (("jombang", "pgs-jombang"), ("jember", "pgs-jember")):
        r = put(who, sid, {"follow": True})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["own"] is False and d["follows_sidoarjo"] is True and d["status"] == "running"
        assert parse(d["ends_at"]) == ST["sido_ends"]
        f = requests.get(f"{API}/flash-sale", headers=H(store=sid), timeout=30).json()
        assert f["active"] is True and parse(f["ends_at"]) == ST["sido_ends"]
