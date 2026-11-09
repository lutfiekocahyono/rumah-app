# Edit Harga Cabang (iteration 49): GET/PUT /api/branch-prices, history 'branch_price', buyer price/cart/inventory effects.
# DATA SAFETY: original store_stock rows (both branches) + product doc of the edited product are backed up and restored exactly;
# price_history (source branch_price) / product_events rows created during the run are deleted by id/time window.
import os
import json
import uuid
import datetime as dt
import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
BASE_URL = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"
J, JEM, OFF = "pgs-jombang", "pgs-jember", "pgs-official"
P = "pgs-9955"  # Casserole 32 Cm Suggo (no variants, has tiers)
P2 = "pgs-9952"  # used for the admin -> Jember edit
VAR = "TEST_bp_variant_" + uuid.uuid4().hex[:6]
CREDS = {"admin": ("admin@pgs.id", "Admin1234!"), "jombang": ("jombang@pgs.id", "Jombang123!"),
         "jember": ("jember@pgs.id", "Jember123!"), "sidoarjo": ("sidoarjo@pgs.id", "Sidoarjo123!"), "demo": ("demo@pgs.id", "Demo1234!")}
NEW_TIERS = {"langsung": [{"min_qty": 12, "price": 210000}, {"min_qty": 6, "price": 215000}], "pengecer": [{"min_qty": 1, "price": 218000}], "reseller": []}

db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def tok(who):
    e, p = CREDS[who]
    r = requests.post(f"{API}/auth/login", json={"email": e, "password": p}, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module", autouse=True)
def backup():
    start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=5)
    rows = {(r["store_id"], r["product_id"]): r for r in db.store_stock.find({"product_id": {"$in": [P, P2]}})}
    prods = {p["product_id"]: p for p in db.products.find({"product_id": {"$in": [P, P2]}})}
    with open("/tmp/bp_backup.json", "w") as f:
        json.dump({"rows": [{k: (v.isoformat() if isinstance(v, dt.datetime) else str(v) if k == "_id" else v) for k, v in r.items()} for r in rows.values()]}, f)
    yield
    for r in rows.values():
        db.store_stock.replace_one({"_id": r["_id"]}, r)
    for p in prods.values():
        db.products.replace_one({"_id": p["_id"]}, p)
    db.products.delete_one({"product_id": VAR})
    ph = db.price_history.delete_many({"source": "branch_price", "product_id": {"$in": [P, P2]}, "at": {"$gte": start}})
    ev = db.product_events.delete_many({"product_id": {"$in": [P, P2]}, "at": {"$gte": start}, "digest_id": None})
    db.carts.delete_many({"owner": {"$regex": "^guest:TEST_bp_"}})
    print(f"\nRESTORED rows={len(rows)} deleted price_history={ph.deleted_count} product_events={ev.deleted_count}")
    for k, r in rows.items():
        assert db.store_stock.find_one({"_id": r["_id"]}) == r, f"restore mismatch {k}"


@pytest.fixture(scope="module")
def T():
    return {k: tok(k) for k in CREDS}


def strip(r):
    return {k: r.get(k) for k in ("price", "original_price", "tier_prices", "stock", "price_set_at")}


# ---- GET /branch-prices permissions + shape
class TestList:
    def test_jombang_own(self, T):
        r = requests.get(f"{API}/branch-prices", headers=T["jombang"], params={"q": "Casserole 32"}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["store_id"] == J and "Jombang" in d["store_name"]
        it = next(i for i in d["items"] if i["product_id"] == P)
        assert it["own_price"] is True
        assert it["branch"]["price"] == it["sidoarjo"]["price"] + 2000
        assert it["branch"]["tier_prices"]["langsung"][0]["price"] == it["sidoarjo"]["tier_prices"]["langsung"][0]["price"] + 2000
        assert isinstance(it["stock"], int)

    def test_pagination(self, T):
        a = requests.get(f"{API}/branch-prices", headers=T["jombang"], params={"limit": 5}, timeout=30).json()["items"]
        b = requests.get(f"{API}/branch-prices", headers=T["jombang"], params={"limit": 5, "skip": 5}, timeout=30).json()["items"]
        assert len(a) == 5 and len(b) == 5 and not {i["product_id"] for i in a} & {i["product_id"] for i in b}

    @pytest.mark.parametrize("who,sid,code", [("jombang", JEM, 403), ("jember", J, 403), ("sidoarjo", None, 403), ("demo", None, 403),
                                              ("admin", OFF, 400), ("admin", "foo", 400)])
    def test_denied(self, T, who, sid, code):
        r = requests.get(f"{API}/branch-prices", headers=T[who], params={"store_id": sid} if sid else {}, timeout=30)
        assert r.status_code == code, r.text

    def test_unauth(self):
        assert requests.get(f"{API}/branch-prices", timeout=30).status_code == 401

    def test_admin_jember(self, T):
        d = requests.get(f"{API}/branch-prices", headers=T["admin"], params={"store_id": JEM, "q": "Casserole 32"}, timeout=30).json()
        assert d["store_id"] == JEM
        it = next(i for i in d["items"] if i["product_id"] == P)
        assert it["branch"]["price"] == it["sidoarjo"]["price"] + 1000


# ---- PUT validation (none of these may write)
class TestValidation:
    @pytest.mark.parametrize("body,code", [
        ({"price": 0}, 422), ({"price": -5}, 422),
        ({"price": 220000, "tier_prices": {"grosir": [{"min_qty": 6, "price": 1}]}}, 400),
        ({"price": 220000, "tier_prices": {"langsung": [{"min_qty": 6, "price": 1}, {"min_qty": 6, "price": 2}]}}, 400),
        ({"price": 220000, "tier_prices": {"langsung": [{"min_qty": i, "price": 1000} for i in range(1, 12)]}}, 400),
        ({"price": 220000, "tier_prices": {"langsung": [{"min_qty": 0, "price": 1}]}}, 422),
        ({"price": 220000, "store_id": JEM}, 403),
    ])
    def test_bad(self, T, body, code):
        before = strip(db.store_stock.find_one({"store_id": J, "product_id": P}))
        r = requests.put(f"{API}/branch-prices/{P}", headers=T["jombang"], json=body, timeout=30)
        assert r.status_code == code, r.text
        assert strip(db.store_stock.find_one({"store_id": J, "product_id": P})) == before

    def test_not_found(self, T):
        assert requests.put(f"{API}/branch-prices/nope-xyz", headers=T["jombang"], json={"price": 1000}, timeout=30).status_code == 404

    def test_variant(self, T):
        db.products.insert_one({"product_id": VAR, "store_id": OFF, "name": "TEST_bp variant", "price": 1000, "status": "draft",
                                "variants": [{"variant_id": "v1", "name": "A", "price": 1000, "stock": 1}]})
        r = requests.put(f"{API}/branch-prices/{VAR}", headers=T["jombang"], json={"price": 1000}, timeout=30)
        db.products.delete_one({"product_id": VAR})
        assert r.status_code == 400, r.text
        assert db.store_stock.find_one({"product_id": VAR}) is None

    @pytest.mark.parametrize("who", ["sidoarjo", "demo"])
    def test_put_denied(self, T, who):
        assert requests.put(f"{API}/branch-prices/{P}", headers=T[who], json={"price": 1000}, timeout=30).status_code == 403


# ---- Happy path: Jombang edits own branch; effects on buyers, cart, inventory, history
class TestEdit:
    def test_flow(self, T):
        jem0 = strip(db.store_stock.find_one({"store_id": JEM, "product_id": P}))
        prod0 = db.products.find_one({"product_id": P}, {"_id": 0, "price": 1, "original_price": 1, "tier_prices": 1, "stock": 1})
        stock0 = db.store_stock.find_one({"store_id": J, "product_id": P})["stock"]
        r = requests.put(f"{API}/branch-prices/{P}", headers=T["jombang"],
                         json={"price": 220000, "original_price": 230000, "tier_prices": NEW_TIERS}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["branch"]["price"] == 220000 and d["branch"]["original_price"] == 230000
        assert d["branch"]["tier_prices"] == {"langsung": [{"min_qty": 6, "price": 215000}, {"min_qty": 12, "price": 210000}],
                                              "pengecer": [{"min_qty": 1, "price": 218000}]}
        assert d["sidoarjo"]["price"] == prod0["price"] and d["stock"] == stock0
        row = db.store_stock.find_one({"store_id": J, "product_id": P})
        assert row["price"] == 220000 and row["stock"] == stock0 and row["tier_prices"] == d["branch"]["tier_prices"]
        assert strip(db.store_stock.find_one({"store_id": JEM, "product_id": P})) == jem0
        assert db.products.find_one({"product_id": P}, {"_id": 0, "price": 1, "original_price": 1, "tier_prices": 1, "stock": 1}) == prod0

        # history
        h = requests.get(f"{API}/history/price-stock", headers=T["jombang"], params={"product_id": P}, timeout=30)
        assert h.status_code == 200, h.text
        e = h.json()["items"][0]
        assert e["source"] == "branch_price" and e["source_label"] == "Harga Cabang" and e["store_id"] == J
        ch = {c["field"]: c for c in e["changes"]}
        assert ch["price"]["before"] == prod0["price"] + 2000 and ch["price"]["after"] == 220000
        assert "tier_prices" in ch and "215.000" in ch["tier_prices"]["after"]
        assert "original_price" in ch and ch["original_price"]["after"] == 230000
        # Jember admin must not see Jombang's entry
        hj = requests.get(f"{API}/history/price-stock", headers=T["jember"], params={"product_id": P}, timeout=30).json()
        assert not any(x["source"] == "branch_price" and x["store_id"] == J for x in hj["items"])

        # buyers
        pj = requests.get(f"{API}/products/{P}", headers={"X-Store-Id": J}, timeout=30).json()
        po = requests.get(f"{API}/products/{P}", headers={"X-Store-Id": OFF}, timeout=30).json()
        pm = requests.get(f"{API}/products/{P}", headers={"X-Store-Id": JEM}, timeout=30).json()
        print("detail prices", pj["price"], pj.get("original_price"), po["price"], pm["price"])
        assert pj["price"] == 220000 and pj["original_price"] == 230000
        assert po["price"] == prod0["price"] and pm["price"] == jem0["price"]
        lst = requests.get(f"{API}/products", headers={"X-Store-Id": J}, params={"q": "Casserole 32 Cm Suggo"}, timeout=30).json()
        items = lst["items"] if isinstance(lst, dict) else lst
        assert next(i for i in items if i["product_id"] == P)["price"] == 220000

        # cart tiers (guest)
        g = {"X-Guest-Id": "TEST_bp_" + uuid.uuid4().hex[:8], "X-Store-Id": J}
        c = requests.post(f"{API}/cart/items", headers=g, json={"product_id": P, "quantity": 1}, timeout=30).json()
        assert c["items"][0]["price"] == 220000, c
        c = requests.put(f"{API}/cart/items/{P}", headers=g, json={"quantity": 6}, timeout=30).json()
        assert c["items"][0]["price"] == 215000, c
        c = requests.put(f"{API}/cart/items/{P}", headers=g, json={"quantity": 12}, timeout=30).json()
        assert c["items"][0]["price"] == 210000, c
        requests.delete(f"{API}/cart", headers=g, timeout=30)

        # seller inventory
        inv = requests.get(f"{API}/seller/inventory", headers=T["jombang"], params={"q": "Casserole 32 Cm Suggo"}, timeout=30)
        assert inv.status_code == 200, inv.text
        assert next(i for i in inv.json() if i["product_id"] == P)["price"] == 220000

    def test_admin_edits_jember(self, T):
        jom0 = strip(db.store_stock.find_one({"store_id": J, "product_id": P2}))
        r = requests.put(f"{API}/branch-prices/{P2}", headers=T["admin"], json={"store_id": JEM, "price": 150000, "tier_prices": {}}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["branch"]["tier_prices"] == {} and r.json()["branch"]["original_price"] == 150000
        assert db.store_stock.find_one({"store_id": JEM, "product_id": P2})["price"] == 150000
        assert strip(db.store_stock.find_one({"store_id": J, "product_id": P2})) == jom0
        # jember user sees own history entry
        hj = requests.get(f"{API}/history/price-stock", headers=T["jember"], params={"product_id": P2}, timeout=30).json()
        assert hj["items"][0]["source"] == "branch_price" and hj["items"][0]["store_id"] == JEM

    def test_noop_no_history(self, T):
        cur = requests.get(f"{API}/branch-prices", headers=T["jombang"], params={"q": "Casserole 32"}, timeout=30).json()
        it = next(i for i in cur["items"] if i["product_id"] == P)["branch"]
        n0 = db.price_history.count_documents({"source": "branch_price", "product_id": P})
        r = requests.put(f"{API}/branch-prices/{P}", headers=T["jombang"], json={"price": it["price"], "original_price": it["original_price"], "tier_prices": it["tier_prices"]}, timeout=30)
        assert r.status_code == 200
        assert db.price_history.count_documents({"source": "branch_price", "product_id": P}) == n0
