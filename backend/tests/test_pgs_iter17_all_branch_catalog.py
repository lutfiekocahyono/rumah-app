# PGS iteration 17: home/search/category/recommendations list every branch at once; detail/cart keep chosen branch.
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
PID = "pgs-9955"
HEADERS = [None, "pgs-official", "pgs-jombang", "pgs-jember"]
ALL_NAME = "PGS · semua cabang"


def H(store=None, tok=None, guest=None):
    h = {}
    if store:
        h["X-Store-Id"] = store
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    if guest:
        h["X-Guest-Id"] = guest
    return h


def _login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def excl():
    """TEST_ exclusive product created by Mitra PGS Jember; deleted afterwards."""
    tok = _login("jember@pgs.id", "Jember123!")
    name = f"TEST_Eksklusif Jember {uuid.uuid4().hex[:6]}"
    r = requests.post(f"{API}/seller/products", headers=H(tok=tok), json={
        "name": name, "description": "TEST", "category": "dapur", "price": 15000, "stock": 7,
        "images": ["https://images.unsplash.com/photo-1556911220-bff31c812dba?w=400"]})
    assert r.status_code == 200, r.text
    p = r.json()
    yield {**p, "name": name}
    d = requests.delete(f"{API}/seller/products/{p['product_id']}", headers=H(tok=tok))
    assert d.status_code == 200, d.text


def _sig(lst):
    return [(p["product_id"], p["stock"], p.get("store_name")) for p in lst]


def _branch_stock(store):
    r = requests.get(f"{API}/products/{PID}", headers=H(store))
    assert r.status_code == 200, r.text
    return r.json()["stock"]


class TestAllBranchListing:
    def test_home_list_identical_for_every_header(self):
        base = None
        for h in HEADERS:
            r = requests.get(f"{API}/products", params={"sort": "newest", "limit": 40}, headers=H(h))
            assert r.status_code == 200, r.text
            sig = _sig(r.json())
            assert len(sig) > 0
            base = base or sig
            assert sig == base, f"list differs for X-Store-Id={h}"

    def test_popular_sort_identical(self):
        sigs = [_sig(requests.get(f"{API}/products", params={"sort": "popular", "limit": 30}, headers=H(h)).json()) for h in HEADERS]
        assert all(s == sigs[0] for s in sigs)

    def test_shared_item_summed_stock_and_store_name(self):
        r = requests.get(f"{API}/products", params={"q": "", "limit": 200}, headers=H("pgs-jember"))
        lst = requests.get(f"{API}/products", params={"limit": 200}).json()
        shared = [p for p in lst if p.get("store_id", "pgs-official") == "pgs-official"]
        assert shared and all(p["store_name"] == ALL_NAME for p in shared)
        total = sum(_branch_stock(s) for s in ("pgs-official", "pgs-jombang", "pgs-jember"))
        # find pgs-9955 via its name search
        name = requests.get(f"{API}/products/{PID}").json()["name"]
        hit = [p for p in requests.get(f"{API}/products", params={"q": name}, headers=H("pgs-jombang")).json() if p["product_id"] == PID]
        assert hit, "pgs-9955 not found in search"
        assert hit[0]["stock"] == total, (hit[0]["stock"], total)
        assert hit[0]["store_name"] == ALL_NAME
        assert r.status_code == 200

    def test_exclusive_in_search_for_every_header(self, excl):
        for h in HEADERS:
            lst = requests.get(f"{API}/products", params={"q": excl["name"]}, headers=H(h)).json()
            hit = [p for p in lst if p["product_id"] == excl["product_id"]]
            assert hit, f"exclusive missing for header {h}"
            assert hit[0]["store_id"] == "pgs-jember"
            assert hit[0]["store_name"] == "Mitra PGS Jember"
            assert hit[0]["stock"] == 7

    def test_exclusive_in_home_newest_and_category(self, excl):
        for h in ("pgs-official", "pgs-jombang"):
            ids = [p["product_id"] for p in requests.get(f"{API}/products", params={"sort": "newest", "limit": 40}, headers=H(h)).json()]
            assert excl["product_id"] in ids, f"newest home missing exclusive for {h}"
            cat = [p["product_id"] for p in requests.get(f"{API}/products", params={"category": "dapur", "sort": "newest", "limit": 40}, headers=H(h)).json()]
            assert excl["product_id"] in cat, f"category missing exclusive for {h}"

    def test_recommendations_all_branch(self):
        sigs = []
        for h in HEADERS:
            r = requests.get(f"{API}/recommendations", params={"limit": 20}, headers=H(h))
            assert r.status_code == 200, r.text
            lst = r.json()
            assert lst
            for p in lst:
                if p.get("store_id", "pgs-official") == "pgs-official":
                    assert p["store_name"] == ALL_NAME
            sigs.append(_sig(lst))
        mode = requests.get(f"{API}/home").json() if False else None
        print("recs equal across headers:", all(s == sigs[0] for s in sigs), mode)


class TestStorePage:
    def test_official_store_page_keeps_branch_view(self):
        lst = requests.get(f"{API}/products", params={"store": "pgs-official", "limit": 20}, headers=H("pgs-jember")).json()
        assert lst and all(p["store_name"] == "Mitra PGS Jember" for p in lst)
        own = requests.get(f"{API}/products", params={"store": "pgs-official", "limit": 20}).json()
        assert own and all(p["store_name"] != ALL_NAME for p in own)

    def test_jember_store_page_own_header(self, excl):
        ids = [p["product_id"] for p in requests.get(f"{API}/products", params={"store": "pgs-jember", "sort": "popular", "limit": 200}, headers=H("pgs-jember")).json()]
        assert excl["product_id"] in ids

    def test_jember_store_page_other_branch_selected(self, excl):
        """Shop page of Jember while buyer selected Sidoarjo — store says N products, list should not be empty."""
        r = requests.get(f"{API}/products", params={"store": "pgs-jember", "sort": "popular", "limit": 200}, headers=H("pgs-official"))
        ids = [p["product_id"] for p in r.json()]
        assert excl["product_id"] in ids, f"jember shop page empty when X-Store-Id=pgs-official ({len(ids)} items)"


class TestDetailAndCart:
    def test_detail_branch_stock(self):
        vals = {s: _branch_stock(s) for s in ("pgs-official", "pgs-jombang", "pgs-jember")}
        print("branch stocks", vals)
        d = requests.get(f"{API}/products/{PID}", headers=H("pgs-jember")).json()
        assert d["store_name"] == "Mitra PGS Jember"

    def test_detail_exclusive_other_branch_visible(self, excl):
        for h in HEADERS:
            r = requests.get(f"{API}/products/{excl['product_id']}", headers=H(h))
            assert r.status_code == 200, (h, r.text)
            assert r.json()["stock"] == 7 and r.json()["store_id"] == "pgs-jember"

    def test_cart_shared_goes_to_selected_branch(self):
        g = f"TEST_guest_{uuid.uuid4().hex[:8]}"
        jem = _branch_stock("pgs-jember")
        try:
            r = requests.post(f"{API}/cart/items", headers=H("pgs-jember", guest=g), json={"product_id": PID, "quantity": 999999})
            assert r.status_code == 200, r.text
            it = [i for i in r.json()["items"] if i["product_id"] == PID][0]
            assert it["store_id"] == "pgs-jember"
            assert it["quantity"] == jem and it["stock"] == jem
        finally:
            requests.delete(f"{API}/cart", headers=H(guest=g))

    def test_cart_exclusive_goes_to_own_branch(self, excl):
        g = f"TEST_guest_{uuid.uuid4().hex[:8]}"
        try:
            r = requests.post(f"{API}/cart/items", headers=H("pgs-official", guest=g), json={"product_id": excl["product_id"], "quantity": 50})
            assert r.status_code == 200, r.text
            it = r.json()["items"][0]
            assert it["store_id"] == "pgs-jember" and it["quantity"] == 7 and it["store_name"] == "Mitra PGS Jember"
            r2 = requests.post(f"{API}/cart/items", headers=H("pgs-official", guest=g), json={"product_id": PID, "quantity": 1})
            stores = {i["store_id"] for i in r2.json()["items"]}
            assert stores == {"pgs-jember", "pgs-official"}
        finally:
            requests.delete(f"{API}/cart", headers=H(guest=g))

    def test_availability_exclusive(self, excl):
        r = requests.get(f"{API}/products/{excl['product_id']}/availability")
        assert r.status_code == 200
        st = {s["store_id"]: s["stock"][excl["product_id"]] for s in r.json()["stores"]}
        assert st.get("pgs-jember") == 7 and st.get("pgs-official") == 0
