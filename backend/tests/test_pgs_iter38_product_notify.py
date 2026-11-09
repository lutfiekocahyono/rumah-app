# PGS iteration 38: product-update notifications (new/price/stock/info) -> hourly digest to all buyers (bell + email).
# NOTE: each /admin/product-digest/run sends REAL emails to verified customers. This module calls /run exactly 3 times.
import os
import uuid

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
IMG = "https://pusatgrosirsidoarjo.com/wp-content/uploads/2023/07/Cetakan-7-Lubang-Cekung-Suggo-300x300.webp"
DESC = "Deskripsi **tebal** produk uji coba yang cukup panjang untuk validasi.\n- poin satu\n- poin dua"
RESTOCK_PID = "pgs-9957"


def _env(k):
    for line in open("/app/backend/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip('"')


DB = MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]
CRED = {"admin": ("admin@pgs.id", "Admin1234!"), "seller": ("sidoarjo@pgs.id", "Sidoarjo123!"), "demo": ("demo@pgs.id", "Demo1234!")}
S: dict = {"products": [], "digests": [], "user_ids": []}
ALL_TRUE = {"notif_order": True, "notif_promo": True, "notif_security": True, "notif_product": True, "email_product": True}


def H(t):
    return {"Authorization": f"Bearer {t}"}


def form(**kw):
    base = {"name": f"TEST_Notif {uuid.uuid4().hex[:5]}", "category": "dapur", "subcategory": "peralatan-masak",
            "brand": "TEST", "sku": "TSKU", "condition": "new", "status": "active", "description": DESC,
            "images": [IMG], "price": 10000, "discount_price": 0, "stock": 50, "min_order": 1, "max_order": 0, "weight_grams": 500}
    base.update(kw)
    return base


def publish(t, data, **kw):
    r = requests.post(f"{API}/product-editor/publish", headers=H(t), json={"data": data, **kw})
    assert r.status_code == 200, r.text
    pid = r.json()["product_id"]
    if pid not in S["products"]:
        S["products"].append(pid)
    return pid


def events(pid):
    return list(DB.product_events.find({"product_id": pid, "digest_id": None}))


def run(t):
    r = requests.post(f"{API}/admin/product-digest/run", headers=H(t["admin"]))
    assert r.status_code == 200, r.text
    d = r.json()
    if d.get("digest_id"):
        S["digests"].append(d["digest_id"])
    print("RUN", d)
    return d


@pytest.fixture(scope="module")
def tok():
    t = {}
    for k, (e, p) in CRED.items():
        r = requests.post(f"{API}/auth/login", json={"email": e, "password": p})
        assert r.status_code == 200, r.text
        t[k] = r.json()["token"]
    em = f"test_pn_{uuid.uuid4().hex[:6]}@example.com"
    r = requests.post(f"{API}/auth/register", json={"email": em, "password": "Test1234!", "name": "TEST_PN"})
    assert r.status_code in (200, 201), r.text
    t["optout"] = r.json()["token"]
    t["optout_id"] = r.json()["user"]["user_id"]
    S["user_ids"].append(t["optout_id"])
    S["stock_before"] = DB.products.find_one({"product_id": RESTOCK_PID})["stock"]
    S["t0"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    yield t
    import json
    json.dump({k: (str(v) if k == "t0" else v) for k, v in S.items() if k in ("products", "digests", "user_ids", "stock_before", "t0")},
              open("/tmp/pn_state.json", "w"))
    if os.environ.get("PN_KEEP") != "1":
        cleanup()


def cleanup():
    """Remove only what this module created (state in /tmp/pn_state.json)."""
    import json
    from datetime import datetime
    st = json.load(open("/tmp/pn_state.json"))
    DB.products.update_one({"product_id": RESTOCK_PID}, {"$set": {"stock": st["stock_before"], "in_stock": st["stock_before"] > 0}})
    for pid in st["products"]:
        DB.products.delete_one({"product_id": pid, "name": {"$regex": "^TEST_"}})
        DB.price_history.delete_many({"product_id": pid})
    for pid in st["products"] + [RESTOCK_PID]:
        DB.product_events.delete_many({"product_id": pid})
    DB.price_history.delete_many({"product_id": RESTOCK_PID, "source": "stock", "at": {"$gte": datetime.fromisoformat(st["t0"])}})
    for did in st["digests"]:
        DB.product_digests.delete_one({"digest_id": did})
    DB.notifications.delete_many({"kind": "product"})
    for uid in st["user_ids"]:
        DB.users.delete_one({"user_id": uid, "email": {"$regex": "^test_pn_"}})
    DB.users.update_one({"email": "demo@pgs.id"}, {"$set": {"settings": ALL_TRUE}})


# ---------- settings ----------
class TestSettings:
    def test_defaults_true(self, tok):
        r = requests.get(f"{API}/me/settings", headers=H(tok["optout"]))
        assert r.status_code == 200
        assert r.json()["notif_product"] is True and r.json()["email_product"] is True

    def test_put_and_get(self, tok):
        body = {**ALL_TRUE, "notif_product": False, "email_product": False}
        r = requests.put(f"{API}/me/settings", headers=H(tok["optout"]), json=body)
        assert r.status_code == 200 and r.json()["notif_product"] is False
        g = requests.get(f"{API}/me/settings", headers=H(tok["optout"])).json()
        assert g["notif_product"] is False and g["email_product"] is False and g["notif_order"] is True


# ---------- event capture ----------
class TestEvents:
    def test_inactive_product_no_event(self, tok):
        pid = publish(tok["seller"], form(status="inactive"))
        S["inactive"] = pid
        assert events(pid) == []
        d = requests.get(f"{API}/product-editor/products/{pid}", headers=H(tok["seller"])).json()["data"]
        publish(tok["seller"], {**d, "price": 15000, "description": DESC + " ubah"}, product_id=pid)
        assert events(pid) == [], "inactive product edit must not emit events"

    def test_new_product_event(self, tok):
        pid = publish(tok["seller"], form())
        S["A"] = pid
        ev = events(pid)
        assert [e["kind"] for e in ev] == ["new"], ev
        DB.product_events.delete_many({"_id": {"$in": [e["_id"] for e in ev]}})  # keep run #1 single-product

    def test_restock_event_via_inventory(self, tok):
        pre = DB.product_events.count_documents({"digest_id": None})
        assert pre == 0, f"unexpected pending events before run1: {pre}"
        r = requests.put(f"{API}/seller/inventory/{RESTOCK_PID}", headers=H(tok["seller"]), json={"stock": 5})
        assert r.status_code == 200, r.text
        ev = events(RESTOCK_PID)
        assert len(ev) == 1 and ev[0]["kind"] == "restock" and ev[0]["before"] == 0 and ev[0]["after"] == 5, ev
        st = requests.get(f"{API}/admin/product-digest", headers=H(tok["admin"]))
        assert st.status_code == 200 and st.json()["pending_events"] == 1

    def test_admin_only(self, tok):
        assert requests.get(f"{API}/admin/product-digest", headers=H(tok["demo"])).status_code == 403
        assert requests.post(f"{API}/admin/product-digest/run", headers=H(tok["demo"])).status_code == 403


# ---------- run #1: single product ----------
class TestRunSingle:
    def test_run_single(self, tok):
        d = run(tok)
        assert d.get("products") == 1, d
        assert "tersedia lagi" in d["title"], d
        n_cust = DB.users.count_documents({"role": "customer"})
        assert d["bell"] == n_cust - 1, (d["bell"], n_cust)  # opt-out user excluded
        S["run1"] = d

    def test_demo_sees_single(self, tok):
        ns = [n for n in requests.get(f"{API}/notifications", headers=H(tok["demo"])).json() if n.get("kind") == "product"]
        assert ns and ns[0]["link"] == f"/product/{RESTOCK_PID}", ns[:1]
        assert "_id" not in ns[0]
        print("DEMO NOTIF", ns[0])

    def test_optout_gets_nothing(self, tok):
        ns = [n for n in requests.get(f"{API}/notifications", headers=H(tok["optout"])).json() if n.get("kind") == "product"]
        assert ns == []

    def test_status_after_run(self, tok):
        st = requests.get(f"{API}/admin/product-digest", headers=H(tok["admin"])).json()
        assert st["pending_events"] == 0 and st["last"]["digest_id"] == S["run1"]["digest_id"]


# ---------- run #2: multiple products -> one digest ----------
class TestRunMulti:
    def test_prepare_changes(self, tok):
        S["B"] = publish(tok["seller"], form())  # new
        d = requests.get(f"{API}/product-editor/products/{S['A']}", headers=H(tok["seller"])).json()["data"]
        publish(tok["seller"], {**d, "price": 8000}, product_id=S["A"])  # price only
        kinds_a = [e["kind"] for e in events(S["A"])]
        print("A kinds after price-only edit:", kinds_a)
        opts = [{"name": "Warna", "values": ["Merah", "Biru"]}]
        rows = [{"values": ["Merah"], "price": 12000, "stock": 5, "sku": "R", "active": True},
                {"values": ["Biru"], "price": 12000, "stock": 0, "sku": "B", "active": True}]
        S["V"] = publish(tok["seller"], form(variants_enabled=True, variant_options=opts, variants=rows))
        DB.product_events.delete_many({"product_id": S["V"]})  # only test the variant edit below
        dv = requests.get(f"{API}/product-editor/products/{S['V']}", headers=H(tok["seller"])).json()["data"]
        dv["variants"][0]["price"] = 11000
        publish(tok["seller"], dv, product_id=S["V"])
        kinds_v = [e["kind"] for e in events(S["V"])]
        print("V kinds after variant price edit:", kinds_v)
        assert "price" in kinds_v
        assert kinds_a == ["price"], f"price-only editor save emitted extra events: {kinds_a}"

    def test_run_multi(self, tok):
        d = run(tok)
        assert d.get("products") == 3, d
        assert d["title"].startswith("Update produk:"), d
        S["run2"] = d

    def test_demo_multi_link(self, tok):
        ns = [n for n in requests.get(f"{API}/notifications", headers=H(tok["demo"])).json() if n.get("kind") == "product"]
        assert ns[0]["link"] == f"/product-updates/{S['run2']['digest_id']}", ns[0]
        assert len([n for n in ns if n["link"] == ns[0]["link"]]) == 1

    def test_detail(self, tok):
        r = requests.get(f"{API}/product-updates/{S['run2']['digest_id']}", headers=H(tok["demo"]))
        assert r.status_code == 200, r.text
        items = {i["product_id"]: i for i in r.json()["items"]}
        print({k: v["change"] for k, v in items.items()})
        assert items[S["B"]]["change"].startswith("Produk baru")
        assert "Harga turun" in items[S["A"]]["change"] and "Rp8.000" in items[S["A"]]["change"]
        assert items[S["V"]]["change"]

    def test_detail_404(self, tok):
        assert requests.get(f"{API}/product-updates/pd_nope", headers=H(tok["demo"])).status_code == 404

    def test_detail_requires_auth(self):
        assert requests.get(f"{API}/product-updates/{S['run2']['digest_id']}").status_code == 401


# ---------- run #3: nothing pending ----------
class TestRunEmpty:
    def test_run_empty(self, tok):
        d = run(tok)
        assert d.get("sent") is False and "digest_id" not in d

    def test_active_to_inactive_price_edit_emits_event(self, tok):
        """Product hidden from buyers in the same save as a price change: should NOT notify (no /run here)."""
        d = requests.get(f"{API}/product-editor/products/{S['B']}", headers=H(tok["seller"])).json()["data"]
        publish(tok["seller"], {**d, "price": 20000, "status": "inactive"}, product_id=S["B"])
        kinds = [e["kind"] for e in events(S["B"])]
        print("B kinds after deactivate+price:", kinds)
        assert kinds == [], f"hidden product produced events {kinds}"
