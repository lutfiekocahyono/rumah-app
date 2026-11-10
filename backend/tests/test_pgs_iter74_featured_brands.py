# PGS iteration 74: Merek Unggulan (featured brands) — public auto list, admin GET/PUT, order, unknown ids, null/empty.
import os

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"


def _env(k):
    for line in open("/app/backend/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip('"')


DB = MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]


def login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def H(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def adm():
    t = login("admin@pgs.id", "Admin1234!")
    yield t
    # restore to automatic no matter what
    requests.put(f"{API}/admin/featured-brands", headers=H(t), json={"items": None})


@pytest.fixture(scope="module")
def brands():
    return {b["name"]: b for b in requests.get(f"{API}/brands").json()}


# --- public automatic list ---
def test_public_auto_top10(adm):
    requests.put(f"{API}/admin/featured-brands", headers=H(adm), json={"items": None})
    r = requests.get(f"{API}/brands/featured")
    assert r.status_code == 200
    d = r.json()
    assert len(d) == 10
    counts = [b["count"] for b in d]
    assert counts == sorted(counts, reverse=True)
    assert all(b["count"] > 0 for b in d)
    assert not any(b["name"].strip().lower() in ("no brand", "tanpa merek", "-") for b in d)
    assert all("_id" not in b and "created_at" not in b for b in d)


def test_auto_matches_product_counts(adm):
    agg = list(DB.products.aggregate([{"$match": {"brand": {"$nin": [None, ""]}}}, {"$group": {"_id": "$brand", "n": {"$sum": 1}}}]))
    real = sorted((a for a in agg if a["_id"].strip().lower() not in ("no brand", "tanpa merek", "-")), key=lambda a: -a["n"])
    d = requests.get(f"{API}/brands/featured").json()
    assert d[0]["count"] == real[0]["n"]
    assert d[-1]["count"] >= real[10]["n"] if len(real) > 10 else True


# --- admin auth ---
def test_admin_get_requires_auth():
    assert requests.get(f"{API}/admin/featured-brands").status_code == 401
    assert requests.put(f"{API}/admin/featured-brands", json={"items": []}).status_code == 401


def test_admin_forbidden_for_store_admin_and_customer():
    for e, p in (("jombang@pgs.id", "Jombang123!"), ("demo@pgs.id", "Demo1234!")):
        t = login(e, p)
        assert requests.get(f"{API}/admin/featured-brands", headers=H(t)).status_code == 403, e
        assert requests.put(f"{API}/admin/featured-brands", headers=H(t), json={"items": []}).status_code == 403, e


def test_admin_get_auto(adm):
    r = requests.get(f"{API}/admin/featured-brands", headers=H(adm))
    assert r.status_code == 200
    d = r.json()
    assert d["custom"] is False and len(d["items"]) == 10


# --- custom order / unknown ids / dedupe ---
def test_put_keeps_order_drops_unknown(adm, brands):
    ids = [brands["Vanstar"]["brand_id"], "doesnotexist", brands["Advance"]["brand_id"], brands["Vanstar"]["brand_id"]]
    r = requests.put(f"{API}/admin/featured-brands", headers=H(adm), json={"items": ids})
    assert r.status_code == 200
    d = r.json()
    assert d["custom"] is True
    assert [b["name"] for b in d["items"]] == ["Vanstar", "Advance"]
    pub = requests.get(f"{API}/brands/featured").json()
    assert [b["name"] for b in pub] == ["Vanstar", "Advance"]
    assert pub[0]["count"] == brands["Vanstar"]["count"]


def test_put_empty_hides(adm):
    r = requests.put(f"{API}/admin/featured-brands", headers=H(adm), json={"items": []})
    assert r.status_code == 200 and r.json() == {"custom": True, "items": []}
    assert requests.get(f"{API}/brands/featured").json() == []


def test_put_null_resets(adm):
    r = requests.put(f"{API}/admin/featured-brands", headers=H(adm), json={"items": None})
    assert r.status_code == 200 and r.json()["custom"] is False and len(r.json()["items"]) == 10
    assert DB.app_settings.find_one({"_id": "featured_brands"}) is None
    assert len(requests.get(f"{API}/brands/featured").json()) == 10


def test_put_empty_body_resets(adm, brands):
    requests.put(f"{API}/admin/featured-brands", headers=H(adm), json={"items": [brands["Vanstar"]["brand_id"]]})
    r = requests.put(f"{API}/admin/featured-brands", headers=H(adm), json={})
    assert r.status_code == 200 and r.json()["custom"] is False


def test_put_validation(adm):
    assert requests.put(f"{API}/admin/featured-brands", headers=H(adm), json={"items": "x"}).status_code == 422
    assert requests.put(f"{API}/admin/featured-brands", headers=H(adm), json={"items": [str(i) for i in range(31)]}).status_code == 422
