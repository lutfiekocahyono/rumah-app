# Iteration 76: map pins (OSM/Leaflet) for buyer addresses + branch store pins, geo proxy, pin-based nearest branch
import os
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
CREDS = {"admin": ("admin@pgs.id", "Admin1234!"), "jombang": ("jombang@pgs.id", "Jombang123!"),
         "jember": ("jember@pgs.id", "Jember123!"), "demo": ("demo@pgs.id", "Demo1234!")}
TOK: dict = {}
ST: dict = {}
PID = "pgs-10062"
BUYER = (-7.38, 112.716)  # Gedangan, Sidoarjo
EDITABLE = ("banner", "logo", "description", "phone", "address", "pickup_hours", "lat", "lng")


def h(who):
    if who not in TOK:
        r = requests.post(f"{API}/auth/login", json={"email": CREDS[who][0], "password": CREDS[who][1]}, timeout=20)
        if r.status_code != 200:
            pytest.skip(f"login {who} failed {r.status_code}")
        TOK[who] = r.json()["token"]
    return {"Authorization": f"Bearer {TOK[who]}"}


def appearance(who, sid):
    r = requests.get(f"{API}/store-appearance", headers=h(who), timeout=20)
    assert r.status_code == 200, r.text
    row = next((x for x in r.json() if x["store_id"] == sid), None)
    assert row is not None
    return row


def body_of(row, **kw):
    b = {k: row.get(k) for k in EDITABLE}
    b = {k: ("" if v is None and k not in ("lat", "lng") else v) for k, v in b.items()}
    b["featured_ids"] = [f["product_id"] for f in row.get("featured", [])]
    b.update(kw)
    return b


ADDR = {"label": "TEST_Pin", "recipient": "TEST Penerima", "phone": "081234567890", "address": "Jl. TEST Pin No. 1 Gedangan",
        "city": "Sidoarjo", "postal_code": "61254"}


# ---------- addresses ----------
class TestAddressPins:
    def test_post_without_pin_rejected(self):
        r = requests.post(f"{API}/me/addresses", headers=h("demo"), json=ADDR, timeout=20)
        assert r.status_code == 400
        assert r.json()["detail"] == "Pasang pin lokasi alamat di peta dulu"

    def test_post_half_pin_rejected(self):
        r = requests.post(f"{API}/me/addresses", headers=h("demo"), json={**ADDR, "lat": -7.38}, timeout=20)
        assert r.status_code == 400

    def test_post_out_of_range_pin_422(self):
        r = requests.post(f"{API}/me/addresses", headers=h("demo"), json={**ADDR, "lat": -100, "lng": 112.7}, timeout=20)
        assert r.status_code == 422

    def test_post_with_pin_saved(self):
        before = {a["address_id"] for a in requests.get(f"{API}/me/addresses", headers=h("demo"), timeout=20).json()}
        r = requests.post(f"{API}/me/addresses", headers=h("demo"), json={**ADDR, "lat": -7.38, "lng": 112.716}, timeout=20)
        assert r.status_code == 200, r.text
        new = [a for a in r.json() if a["address_id"] not in before]
        assert len(new) == 1
        a = new[0]
        assert a["lat"] == -7.38 and a["lng"] == 112.716 and "_id" not in a
        ST["aid"] = a["address_id"]

    def test_put_without_pin_keeps_pin(self):
        aid = ST.get("aid") or pytest.skip("no address")
        r = requests.put(f"{API}/me/addresses/{aid}", headers=h("demo"), json={**ADDR, "address": "Jl. TEST Pin No. 2 Gedangan"}, timeout=20)
        assert r.status_code == 200, r.text
        a = next(x for x in requests.get(f"{API}/me/addresses", headers=h("demo"), timeout=20).json() if x["address_id"] == aid)
        assert a["address"] == "Jl. TEST Pin No. 2 Gedangan"
        assert a["lat"] == -7.38 and a["lng"] == 112.716

    def test_put_with_pin_updates(self):
        aid = ST.get("aid") or pytest.skip("no address")
        r = requests.put(f"{API}/me/addresses/{aid}", headers=h("demo"), json={**ADDR, "lat": -7.4, "lng": 112.7}, timeout=20)
        assert r.status_code == 200
        a = next(x for x in requests.get(f"{API}/me/addresses", headers=h("demo"), timeout=20).json() if x["address_id"] == aid)
        assert a["lat"] == -7.4 and a["lng"] == 112.7

    def test_cleanup_address(self):
        aid = ST.get("aid") or pytest.skip("no address")
        r = requests.delete(f"{API}/me/addresses/{aid}", headers=h("demo"), timeout=20)
        assert r.status_code == 200
        assert all(x["address_id"] != aid for x in r.json())


# ---------- geo proxy ----------
class TestGeo:
    def test_search(self):
        r = requests.get(f"{API}/geo/search", headers=h("demo"), params={"q": "Gedangan Sidoarjo"}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert isinstance(d, list) and len(d) >= 1
        assert isinstance(d[0]["lat"], float) and isinstance(d[0]["lng"], float) and d[0]["label"]
        assert -8 < d[0]["lat"] < -7 and 112 < d[0]["lng"] < 113

    def test_search_short_query(self):
        r = requests.get(f"{API}/geo/search", headers=h("demo"), params={"q": "ab"}, timeout=20)
        assert r.status_code == 200 and r.json() == []

    def test_reverse(self):
        r = requests.get(f"{API}/geo/reverse", headers=h("demo"), params={"lat": -7.38, "lng": 112.716}, timeout=30)
        assert r.status_code == 200, r.text
        assert "Sidoarjo" in r.json()["label"]

    def test_requires_login(self):
        assert requests.get(f"{API}/geo/search", params={"q": "Gedangan"}, timeout=20).status_code == 401

    def test_reverse_invalid(self):
        r = requests.get(f"{API}/geo/reverse", headers=h("demo"), params={"lat": 120, "lng": 112.716}, timeout=20)
        assert r.status_code == 400


# ---------- branch pins + nearest ----------
class TestBranchPins:
    def test_appearance_has_lat_lng(self):
        row = appearance("jombang", "pgs-jombang")
        assert "lat" in row and "lng" in row
        ST["jombang_orig"] = row
        ST["jember_orig"] = appearance("admin", "pgs-jember")

    def test_jombang_cannot_edit_jember(self):
        row = ST.get("jember_orig") or pytest.skip()
        r = requests.put(f"{API}/store-appearance/pgs-jember", headers=h("jombang"), json=body_of(row, lat=-8.1, lng=113.7), timeout=20)
        assert r.status_code == 403

    def test_distance_before_pin(self):
        # clear jombang pin first so the default city centre is used
        row = ST.get("jombang_orig") or pytest.skip()
        r = requests.put(f"{API}/store-appearance/pgs-jombang", headers=h("jombang"), json=body_of(row, lat=None, lng=None), timeout=20)
        assert r.status_code == 200 and r.json()["lat"] is None
        d = requests.get(f"{API}/branches/nearest", params={"lat": BUYER[0], "lng": BUYER[1]}, timeout=20).json()
        ST["d0"] = next(s["distance_km"] for s in d["stores"] if s["store_id"] == "pgs-jombang")

    def test_jombang_sets_own_pin_and_distance_changes(self):
        row = ST.get("jombang_orig") or pytest.skip()
        r = requests.put(f"{API}/store-appearance/pgs-jombang", headers=h("jombang"), json=body_of(row, lat=-7.40, lng=112.40), timeout=20)
        assert r.status_code == 200, r.text
        assert r.json()["lat"] == -7.40 and r.json()["lng"] == 112.40
        # other fields untouched
        assert r.json()["address"] == (row.get("address") or "")
        p = requests.get(f"{API}/stores/pgs-jombang/page", timeout=20).json()
        assert p["lat"] == -7.40 and p["lng"] == 112.40
        d = requests.get(f"{API}/branches/nearest", params={"lat": BUYER[0], "lng": BUYER[1]}, timeout=20).json()
        d1 = next(s["distance_km"] for s in d["stores"] if s["store_id"] == "pgs-jombang")
        assert d1 < ST["d0"], (d1, ST["d0"])

    def test_suggest_uses_branch_pin(self):
        r = requests.post(f"{API}/stores/suggest", json={"area": "", "product_ids": [PID], "quantities": [1], "lat": BUYER[0], "lng": BUYER[1]}, timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d["located"] is True
        j = next(s for s in d["stores"] if s["store_id"] == "pgs-jombang")
        assert j["lat"] == -7.40 and abs(j["distance_km"] - 35) <= 2

    def test_buyer_pin_overrides_area(self):
        # area says Jember but pin is Sidoarjo -> pgs-official nearest
        r = requests.post(f"{API}/stores/suggest", json={"area": "JEMBER", "product_ids": [PID], "quantities": [1], "lat": BUYER[0], "lng": BUYER[1]}, timeout=20)
        assert r.json()["stores"][0]["store_id"] == "pgs-official"
        r2 = requests.post(f"{API}/stores/suggest", json={"area": "JEMBER", "product_ids": [PID], "quantities": [1]}, timeout=20)
        assert r2.json()["stores"][0]["store_id"] == "pgs-jember"

    def test_availability_with_pin(self):
        r = requests.get(f"{API}/products/{PID}/availability", params={"area": "JEMBER", "lat": BUYER[0], "lng": BUYER[1]}, timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d["stores"][0]["store_id"] == "pgs-official"
        j = next(s for s in d["stores"] if s["store_id"] == "pgs-jombang")
        assert abs(j["distance_km"] - 35) <= 2

    def test_admin_can_edit_any_branch_pin(self):
        row = ST.get("jember_orig") or pytest.skip()
        r = requests.put(f"{API}/store-appearance/pgs-jember", headers=h("admin"), json=body_of(row, lat=-8.17, lng=113.70), timeout=20)
        assert r.status_code == 200 and r.json()["lat"] == -8.17
        # restore original
        r = requests.put(f"{API}/store-appearance/pgs-jember", headers=h("admin"), json=body_of(row), timeout=20)
        assert r.status_code == 200 and r.json()["lat"] == row.get("lat")

    def test_restore_jombang(self):
        row = ST.get("jombang_orig") or pytest.skip()
        r = requests.put(f"{API}/store-appearance/pgs-jombang", headers=h("jombang"), json=body_of(row), timeout=20)
        assert r.status_code == 200 and r.json()["lat"] == row.get("lat")
