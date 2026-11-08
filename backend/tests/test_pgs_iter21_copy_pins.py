# Iteration 21: Super admin "Salin ke Semua Cabang" - POST /api/admin/home-sections/{store_id}/copy-pins
import copy
import os

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
OFFICIAL = ["pgs-official", "pgs-jombang", "pgs-jember"]
KEYS = ("popular", "newest", "recommended")
USER_POPULAR = ["pgs-45768", "pgs-29488", "pgs-51234", "pgs-51477"]


def _env(k):
    for line in open("/app/backend/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip('"')


DB = MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]


def login(e, p):
    r = requests.post(f"{API}/auth/login", json={"email": e, "password": p}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def H(t):
    return {"Authorization": f"Bearer {t}"}


def body_of(cfg):
    return {k: {f: cfg["sections"][k][f] for f in ("enabled", "title", "limit", "sort", "pinned", "categories", "days")} for k in KEYS}


@pytest.fixture(scope="module")
def ctx():
    snap = {d["store_id"]: d for d in DB.home_sections.find({"store_id": {"$in": OFFICIAL}})}
    admin = login("admin@pgs.id", "Admin1234!")
    jombang = login("jombang@pgs.id", "Jombang123!")
    pids = [p["product_id"] for p in DB.products.find({"product_id": {"$nin": USER_POPULAR, "$regex": "^pgs-"}}, {"product_id": 1}).limit(4)]
    cats = [c["category_id"] for c in DB.categories.find({}, {"category_id": 1}).limit(2)]
    yield {"admin": admin, "jombang": jombang, "pids": pids, "cats": cats}
    # restore exact snapshot (user's real pins)
    for sid in OFFICIAL:
        if sid in snap:
            DB.home_sections.replace_one({"store_id": sid}, snap[sid], upsert=True)
        else:
            DB.home_sections.delete_one({"store_id": sid})


def get_cfg(t, sid):
    r = requests.get(f"{API}/admin/home-sections/{sid}", headers=H(t), timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


class TestCopyPins:
    def test_copy_from_jember_keeps_order_and_target_rules(self, ctx):
        a, p, cats = ctx["admin"], ctx["pids"], ctx["cats"]
        # give jombang distinct rules
        jb = body_of(get_cfg(a, "pgs-jombang"))
        jb["popular"].update(title="TEST_JB Populer", limit=5, sort="rating", categories=cats[:1], pinned=[p[3]])
        jb["newest"].update(enabled=False, days=14)
        jb["recommended"].update(title="TEST_JB Rek", sort="random")
        r = requests.put(f"{API}/admin/home-sections/pgs-jombang", headers=H(a), json=jb, timeout=30)
        assert r.status_code == 200, r.text
        sd_before = body_of(get_cfg(a, "pgs-official"))
        # jember source pins
        je = body_of(get_cfg(a, "pgs-jember"))
        je["popular"]["pinned"] = [p[2], p[0], p[1]]
        je["newest"]["pinned"] = [p[3]]
        je["recommended"]["pinned"] = [p[1], p[0]]
        r = requests.put(f"{API}/admin/home-sections/pgs-jember", headers=H(a), json=je, timeout=30)
        assert r.status_code == 200, r.text

        r = requests.post(f"{API}/admin/home-sections/pgs-jember/copy-pins", headers=H(a), timeout=30)
        assert r.status_code == 200, r.text
        out = r.json()
        assert sorted(out["copied_to"]) == ["pgs-jombang", "pgs-official"]
        assert out["counts"] == {"popular": 3, "newest": 1, "recommended": 2}

        for sid, before in (("pgs-jombang", jb), ("pgs-official", sd_before)):
            after = body_of(get_cfg(a, sid))
            assert after["popular"]["pinned"] == [p[2], p[0], p[1]]
            assert after["newest"]["pinned"] == [p[3]]
            assert after["recommended"]["pinned"] == [p[1], p[0]]
            for k in KEYS:
                for f in ("enabled", "title", "limit", "sort", "categories", "days"):
                    assert after[k][f] == before[k][f], f"{sid}.{k}.{f} changed: {before[k][f]} -> {after[k][f]}"
        # source unchanged
        src = body_of(get_cfg(a, "pgs-jember"))
        assert src == je

    def test_pinned_products_returned_in_order(self, ctx):
        c = get_cfg(ctx["admin"], "pgs-official")
        p = ctx["pids"]
        assert [x["product_id"] for x in c["sections"]["popular"]["pinned_products"]] == [p[2], p[0], p[1]]

    def test_copy_empty_pins_clears_targets(self, ctx):
        a = ctx["admin"]
        je = body_of(get_cfg(a, "pgs-jember"))
        for k in KEYS:
            je[k]["pinned"] = []
        assert requests.put(f"{API}/admin/home-sections/pgs-jember", headers=H(a), json=je, timeout=30).status_code == 200
        r = requests.post(f"{API}/admin/home-sections/pgs-jember/copy-pins", headers=H(a), timeout=30)
        assert r.status_code == 200 and r.json()["counts"] == {"popular": 0, "newest": 0, "recommended": 0}
        for sid in ("pgs-official", "pgs-jombang"):
            c = get_cfg(a, sid)
            assert all(c["sections"][k]["pinned"] == [] for k in KEYS)

    def test_copy_from_sidoarjo(self, ctx):
        a = ctx["admin"]
        sd = body_of(get_cfg(a, "pgs-official"))
        sd["popular"]["pinned"] = USER_POPULAR
        assert requests.put(f"{API}/admin/home-sections/pgs-official", headers=H(a), json=sd, timeout=30).status_code == 200
        r = requests.post(f"{API}/admin/home-sections/pgs-official/copy-pins", headers=H(a), timeout=30)
        assert r.status_code == 200
        assert sorted(r.json()["copied_to"]) == ["pgs-jember", "pgs-jombang"]
        for sid in ("pgs-jombang", "pgs-jember"):
            assert get_cfg(a, sid)["sections"]["popular"]["pinned"] == USER_POPULAR

    def test_branch_admin_forbidden(self, ctx):
        r = requests.post(f"{API}/admin/home-sections/pgs-jombang/copy-pins", headers=H(ctx["jombang"]), timeout=30)
        assert r.status_code == 403

    def test_no_token_unauthorized(self):
        r = requests.post(f"{API}/admin/home-sections/pgs-jombang/copy-pins", timeout=30)
        assert r.status_code in (401, 403)

    def test_unknown_store_404(self, ctx):
        r = requests.post(f"{API}/admin/home-sections/toko-tidak-ada/copy-pins", headers=H(ctx["admin"]), timeout=30)
        assert r.status_code == 404
        assert "Cabang" in r.json().get("detail", "")
