# PGS iteration 75: Merek Unggulan per branch store page — public list, branch-admin GET/PUT, permissions, order, null/[].
import os

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
STORES = ("pgs-official", "pgs-jombang", "pgs-jember")


def login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def H(t):
    return {"Authorization": f"Bearer {t}"}


def restore_all(adm):
    for s in STORES:
        requests.put(f"{API}/store-appearance/{s}/featured-brands", headers=H(adm), json={"items": None})
    requests.put(f"{API}/admin/featured-brands", headers=H(adm), json={"items": None})


@pytest.fixture(scope="module")
def adm():
    t = login("admin@pgs.id", "Admin1234!")
    restore_all(t)
    yield t
    restore_all(t)  # always back to automatic


@pytest.fixture(scope="module")
def jomb():
    return login("jombang@pgs.id", "Jombang123!")


@pytest.fixture(scope="module")
def jemb():
    return login("jember@pgs.id", "Jember123!")


@pytest.fixture(scope="module")
def brands():
    return {b["name"]: b for b in requests.get(f"{API}/brands").json()}


# --- public list ---
def test_public_auto_jombang(adm):
    r = requests.get(f"{API}/stores/pgs-jombang/featured-brands")
    assert r.status_code == 200
    d = r.json()
    assert 0 < len(d) <= 10
    assert all("_id" not in b and "created_at" not in b for b in d)
    assert all(b["name"].strip().lower() != "no brand" for b in d)
    counts = [b["count"] for b in d]
    assert counts == sorted(counts, reverse=True)


def test_public_non_official_empty():
    for sid in ("st_c789b1a7c3", "toko-xyz-none"):  # Toko Satu (marketplace seller) + unknown id
        r = requests.get(f"{API}/stores/{sid}/featured-brands")
        assert r.status_code == 200 and r.json() == []


def test_logos_present():
    d = {b["name"]: b for b in requests.get(f"{API}/stores/pgs-jombang/featured-brands").json()}
    for n in ("Kimplast", "Advance", "Apollystar"):
        assert d.get(n, {}).get("logo"), f"{n} has no logo"
    assert not d.get("Vanstar", {}).get("logo")


# --- permissions ---
def test_unauth_401():
    assert requests.get(f"{API}/store-appearance/pgs-jombang/featured-brands").status_code == 401
    assert requests.put(f"{API}/store-appearance/pgs-jombang/featured-brands", json={"items": None}).status_code == 401


def test_jombang_cannot_edit_jember(jomb):
    assert requests.get(f"{API}/store-appearance/pgs-jember/featured-brands", headers=H(jomb)).status_code == 403
    r = requests.put(f"{API}/store-appearance/pgs-jember/featured-brands", headers=H(jomb), json={"items": []})
    assert r.status_code == 403


def test_customer_403():
    t = login("demo@pgs.id", "Demo1234!")
    assert requests.get(f"{API}/store-appearance/pgs-jombang/featured-brands", headers=H(t)).status_code == 403


def test_admin_unknown_store_403(adm):
    assert requests.put(f"{API}/store-appearance/toko-none/featured-brands", headers=H(adm), json={"items": []}).status_code == 403


# --- jombang edits own ---
def test_jombang_get_auto(jomb):
    r = requests.get(f"{API}/store-appearance/pgs-jombang/featured-brands", headers=H(jomb))
    assert r.status_code == 200
    d = r.json()
    assert d["custom"] is False and len(d["items"]) > 0


def test_jombang_put_order_unknown_dupes(adm, jomb, jemb, brands):
    ids = [brands["Kimplast"]["brand_id"], "nope-123", brands["Advance"]["brand_id"], brands["Kimplast"]["brand_id"], brands["Apollystar"]["brand_id"]]
    jember_before = [b["brand_id"] for b in requests.get(f"{API}/stores/pgs-jember/featured-brands").json()]
    beranda_before = [b["brand_id"] for b in requests.get(f"{API}/brands/featured").json()]
    r = requests.put(f"{API}/store-appearance/pgs-jombang/featured-brands", headers=H(jomb), json={"items": ids})
    assert r.status_code == 200, r.text
    d = r.json()
    want = [brands[n]["brand_id"] for n in ("Kimplast", "Advance", "Apollystar")]
    assert d["custom"] is True and [b["brand_id"] for b in d["items"]] == want
    pub = requests.get(f"{API}/stores/pgs-jombang/featured-brands").json()
    assert [b["brand_id"] for b in pub] == want
    assert all(isinstance(b["count"], int) for b in pub)
    # other branch + Beranda untouched
    assert [b["brand_id"] for b in requests.get(f"{API}/stores/pgs-jember/featured-brands").json()] == jember_before
    assert [b["brand_id"] for b in requests.get(f"{API}/brands/featured").json()] == beranda_before
    # jember admin sees own auto
    g = requests.get(f"{API}/store-appearance/pgs-jember/featured-brands", headers=H(jemb)).json()
    assert g["custom"] is False


def test_jombang_empty_hides(jomb):
    r = requests.put(f"{API}/store-appearance/pgs-jombang/featured-brands", headers=H(jomb), json={"items": []})
    assert r.status_code == 200 and r.json() == {"custom": True, "items": []}
    assert requests.get(f"{API}/stores/pgs-jombang/featured-brands").json() == []


def test_jombang_null_back_to_auto(jomb):
    r = requests.put(f"{API}/store-appearance/pgs-jombang/featured-brands", headers=H(jomb), json={"items": None})
    assert r.status_code == 200 and r.json()["custom"] is False and len(r.json()["items"]) > 0
    assert len(requests.get(f"{API}/stores/pgs-jombang/featured-brands").json()) > 0


def test_superadmin_edits_jember(adm, brands):
    want = [brands["Advance"]["brand_id"]]
    r = requests.put(f"{API}/store-appearance/pgs-jember/featured-brands", headers=H(adm), json={"items": want})
    assert r.status_code == 200 and [b["brand_id"] for b in r.json()["items"]] == want
    assert [b["brand_id"] for b in requests.get(f"{API}/stores/pgs-jember/featured-brands").json()] == want
    r = requests.put(f"{API}/store-appearance/pgs-jember/featured-brands", headers=H(adm), json={"items": None})
    assert r.json()["custom"] is False


def test_validation_422(jomb):
    r = requests.put(f"{API}/store-appearance/pgs-jombang/featured-brands", headers=H(jomb), json={"items": "x"})
    assert r.status_code == 422
    r = requests.put(f"{API}/store-appearance/pgs-jombang/featured-brands", headers=H(jomb), json={"items": [f"i{n}" for n in range(31)]})
    assert r.status_code == 422


def test_store_appearance_list_jombang(jomb):
    r = requests.get(f"{API}/store-appearance", headers=H(jomb))
    assert r.status_code == 200 and [s["store_id"] for s in r.json()] == ["pgs-jombang"]
