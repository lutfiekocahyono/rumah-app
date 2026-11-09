# Iteration 44: Rapikan kategori Lainnya, lokasi pelanggan, Fonnte settings, dims estimate fixes
import os
import sys
import uuid

import pytest
import requests
from pymongo import MongoClient

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv  # noqa: E402

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
GUEST = f"TEST_{uuid.uuid4().hex[:10]}"


def login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def admin():
    return login("admin@pgs.id", "Admin1234!")


@pytest.fixture(scope="module")
def demo():
    return login("demo@pgs.id", "Demo1234!")


@pytest.fixture(scope="module")
def sda():
    return login("sidoarjo@pgs.id", "Sidoarjo123!")


# ---- Category cleanup (uncategorized) ----
class TestUncategorized:
    state: dict = {}

    def test_summary(self, admin):
        r = requests.get(f"{API}/product-editor/uncategorized/summary", params={"store_id": "pgs-official"}, headers=admin)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["store_id"] == "pgs-official"
        assert d["count"] >= 200, d  # 220 at start of run (minus a few applied by a previous run)
        TestUncategorized.state["count"] = d["count"]

    def test_customer_forbidden(self, demo):
        r = requests.get(f"{API}/product-editor/uncategorized/summary", headers=demo)
        assert r.status_code in (401, 403), r.text

    def test_preview(self, admin):
        r = requests.post(f"{API}/product-editor/uncategorized/preview", params={"store_id": "pgs-official"}, headers=admin)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total"] == TestUncategorized.state["count"] == len(d["items"])
        cats = {c["category_id"] for c in mdb.categories.find({}, {"category_id": 1})}
        for i in d["items"]:
            assert {"product_id", "name", "suggested", "confidence", "reason"} <= set(i)
            assert i["confidence"] in ("tinggi", "sedang", "rendah")
            assert i["suggested"] == "" or i["suggested"] in cats, i
        empty = sum(1 for i in d["items"] if not i["suggested"])
        conf = {k: sum(1 for i in d["items"] if i["confidence"] == k) for k in ("tinggi", "sedang", "rendah")}
        print(f"\nPreview: total={d['total']} no-suggestion={empty} confidence={conf} groups={d['groups'][:8]}")
        TestUncategorized.state["preview"] = d

    def test_invalid_override_400(self, admin):
        d = TestUncategorized.state["preview"]
        pid = d["items"][0]["product_id"]
        r = requests.post(f"{API}/product-editor/uncategorized/{d['preview_id']}/apply", json={"skip": [], "overrides": {pid: "TEST_nope"}}, headers=admin)
        assert r.status_code == 400 and "tidak ditemukan" in r.json()["detail"], r.text

    def test_apply_subset(self, admin):
        d = TestUncategorized.state["preview"]
        items = [i for i in d["items"] if i["suggested"]]
        keep = items[:2]
        override_item = items[2]
        keep_ids = {i["product_id"] for i in keep} | {override_item["product_id"]}
        skip = [i["product_id"] for i in d["items"] if i["product_id"] not in keep_ids]
        ev_before = mdb.product_events.count_documents({})
        r = requests.post(f"{API}/product-editor/uncategorized/{d['preview_id']}/apply",
                          json={"skip": skip, "overrides": {override_item["product_id"]: override_item["suggested"]}}, headers=admin)
        assert r.status_code == 200, r.text
        assert r.json()["saved"] == 3, r.text
        for i in keep:
            p = mdb.products.find_one({"product_id": i["product_id"]})
            assert p["category"] == i["suggested"] and p["categories"] == [i["suggested"]] and p["subcategory"] == ""
        p = mdb.products.find_one({"product_id": override_item["product_id"]})
        assert p["category"] == override_item["suggested"] and p["categories"] == [override_item["suggested"]]  # override = real suggestion to avoid wrong data
        assert mdb.product_events.count_documents({}) == ev_before, "product_events created (buyer notifications)"
        print("\nApplied:", [(i["name"], i["suggested"]) for i in keep], (override_item["name"], override_item["suggested"]))

    def test_summary_after(self, admin):
        r = requests.get(f"{API}/product-editor/uncategorized/summary", params={"store_id": "pgs-official"}, headers=admin)
        assert r.json()["count"] == TestUncategorized.state["count"] - 3

    def test_second_apply_400(self, admin):
        d = TestUncategorized.state["preview"]
        r = requests.post(f"{API}/product-editor/uncategorized/{d['preview_id']}/apply", json={"skip": [i["product_id"] for i in d["items"]]}, headers=admin)
        assert r.status_code == 400, r.text

    def test_unknown_preview_400(self, admin):
        r = requests.post(f"{API}/product-editor/uncategorized/cp_TEST_none/apply", json={}, headers=admin)
        assert r.status_code == 400

    def test_store_admin_other_store(self):
        h = login("jombang@pgs.id", "Jombang123!")
        r = requests.get(f"{API}/product-editor/uncategorized/summary", params={"store_id": "pgs-official"}, headers=h)
        print("\njombang admin uncategorized summary for pgs-official ->", r.status_code, r.text[:120])
        assert r.status_code == 403 or r.json().get("store_id") != "pgs-official"


# ---- weight/dims routes still work (route order) ----
class TestEstimateRoutes:
    @pytest.mark.parametrize("kind", ["weight", "dims"])
    def test_summary(self, admin, kind):
        r = requests.get(f"{API}/product-editor/{kind}/summary", params={"store_id": "pgs-official"}, headers=admin)
        assert r.status_code == 200 and "missing" in r.json(), r.text

    def test_dims_preview(self, admin):
        r = requests.post(f"{API}/product-editor/dims/preview", params={"store_id": "pgs-official"}, headers=admin)
        assert r.status_code == 200 and "preview_id" in r.json(), r.text
        big = [i for i in r.json()["items"] if max(i["dims"]) > 150]
        print(f"\nDims preview total={r.json()['total']} >150cm side: {[(i['name'][:40], i['dims'], i['rule']) for i in big[:10]]}")

    def test_unknown_kind_404(self, admin):
        r = requests.get(f"{API}/product-editor/foo/summary", headers=admin)
        assert r.status_code == 404


# ---- dims estimate unit ----
class TestDimsEstimate:
    def est(self, name, cat=""):
        from weight_estimate import estimate_dims
        return estimate_dims({"name": name, "category": cat}, {})

    def test_name_size(self):
        dims, rule = self.est("Lemari Pakaian Plastik (185x120x50Cm)")
        assert rule == "Ukuran dari nama produk" and dims == [187, 122, 52], (dims, rule)

    @pytest.mark.parametrize("name", ["Kelambu Lipat 180x200x150", "Bendera Merah Putih 120x80x1", "Karpet Bulu 150x200x2"])
    def test_soft_ignored(self, name):
        dims, rule = self.est(name)
        assert rule != "Ukuran dari nama produk", (name, dims, rule)

    def test_chest_freezer(self):
        dims, rule = self.est("Chest Freezer Aqua 200 Liter")
        assert dims == [110, 65, 90], (dims, rule)

    def test_sofa_angin(self):
        dims, rule = self.est("Sofa Angin Lazy Bag")
        assert max(dims) <= 40, (dims, rule)


# ---- Customer location ----
class TestLocation:
    def test_guest_saved(self):
        h = {"X-Guest-Id": GUEST}
        r = requests.post(f"{API}/location", json={"lat": -7.45, "lng": 112.71, "accuracy": 20, "platform": "web"}, headers=h)
        assert r.status_code == 200 and r.json()["saved"] is True, r.text
        r = requests.post(f"{API}/location", json={"lat": -7.46, "lng": 112.72, "accuracy": 15, "platform": "web"}, headers=h)
        assert r.status_code == 200 and r.json()["saved"] is True, r.text  # second ping exercises history_at compare
        doc = mdb.customer_locations.find_one({"owner": f"guest:{GUEST}"})
        assert doc["guest"] is True and doc["pings"] == 2 and abs(doc["lat"] + 7.46) < 1e-6
        assert mdb.location_history.count_documents({"owner": f"guest:{GUEST}"}) == 1

    def test_invalid_lat_422(self):
        r = requests.post(f"{API}/location", json={"lat": 91, "lng": 112.7}, headers={"X-Guest-Id": GUEST})
        assert r.status_code == 422

    def test_no_identity_400(self):
        r = requests.post(f"{API}/location", json={"lat": 1, "lng": 1})
        assert r.status_code == 400

    @pytest.mark.parametrize("who", ["admin", "sda"])
    def test_staff_not_saved(self, who, admin, sda):
        h = admin if who == "admin" else sda
        r = requests.post(f"{API}/location", json={"lat": -7.4, "lng": 112.7, "platform": "web"}, headers=h)
        assert r.status_code == 200 and r.json()["saved"] is False, r.text

    def test_customer_saved_and_guest_dropped(self, demo):
        uid = requests.get(f"{API}/auth/me", headers=demo).json()["user_id"]
        TestLocation.demo_pre = mdb.customer_locations.find_one({"owner": f"user:{uid}"}) is not None
        TestLocation.uid = uid
        r = requests.post(f"{API}/location", json={"lat": -7.44, "lng": 112.70, "platform": "web"}, headers={**demo, "X-Guest-Id": GUEST})
        assert r.status_code == 200 and r.json()["saved"] is True
        doc = mdb.customer_locations.find_one({"owner": f"user:{uid}"})
        assert doc["guest"] is False and doc["email"] == "demo@pgs.id"
        assert mdb.customer_locations.find_one({"owner": f"guest:{GUEST}"}) is None

    def test_admin_list(self, admin):
        r = requests.get(f"{API}/admin/customer-locations", params={"days": 1, "guests": "true"}, headers=admin)
        assert r.status_code == 200, r.text
        d = r.json()
        assert {"total", "customers", "guests", "active_24h", "active_7d", "buyers"} <= set(d["stats"])
        row = next(x for x in d["items"] if x.get("user_id") == TestLocation.uid)
        assert isinstance(row["orders"], int) and isinstance(row["spent"], (int, float))
        assert "_id" not in row
        r2 = requests.get(f"{API}/admin/customer-locations", params={"guests": "false"}, headers=admin)
        assert all(not x["guest"] for x in r2.json()["items"])

    def test_customer_403(self, demo, sda):
        assert requests.get(f"{API}/admin/customer-locations", headers=demo).status_code == 403
        assert requests.get(f"{API}/admin/customer-locations", headers=sda).status_code == 403

    def test_zz_cleanup(self):
        mdb.customer_locations.delete_one({"owner": f"guest:{GUEST}"})
        mdb.location_history.delete_many({"owner": f"guest:{GUEST}"})
        if not TestLocation.demo_pre:
            mdb.customer_locations.delete_one({"owner": f"user:{TestLocation.uid}"})
            mdb.location_history.delete_many({"owner": f"user:{TestLocation.uid}"})


# ---- Fonnte settings ----
class TestFonnte:
    def test_get_default(self, admin):
        r = requests.get(f"{API}/admin/fonnte", headers=admin)
        assert r.status_code == 200, r.text
        d = r.json()
        print("\nFonnte initial:", d)
        assert d["otp_mode"] == "uji" and d["has_token"] is False

    def test_non_admin_403(self, demo, sda):
        assert requests.get(f"{API}/admin/fonnte", headers=demo).status_code == 403
        assert requests.put(f"{API}/admin/fonnte", json={"token": "x" * 12}, headers=sda).status_code == 403

    def test_test_otp_without_token(self, admin):
        r = requests.post(f"{API}/admin/fonnte/test-otp", json={"phone": "081234567890"}, headers=admin)
        assert r.status_code == 400 and "mode uji" in r.json()["detail"], r.text

    def test_test_without_token(self, admin):
        r = requests.post(f"{API}/admin/fonnte/test", json={}, headers=admin)
        assert r.status_code == 400, r.text

    def test_phone_request_dev_code(self, demo):
        r = requests.post(f"{API}/auth/phone/request", json={"phone": "081299990001"}, headers=demo)
        print("\nphone/request:", r.status_code, r.text[:200])
        assert r.status_code == 200 and r.json().get("dev_code"), r.text

    def test_test_typed_fake_token(self, admin):
        r = requests.post(f"{API}/admin/fonnte/test", json={"token": "TESTfaketoken12345"}, headers=admin)
        assert r.status_code == 200, r.text
        print("\nfake token test:", r.json())
        assert r.json()["ok"] is False and r.json()["reason"]

    def test_invalid_token_and_owner(self, admin):
        assert requests.put(f"{API}/admin/fonnte", json={"token": "short"}, headers=admin).status_code == 400
        assert requests.put(f"{API}/admin/fonnte", json={"owner_whatsapp": "12345"}, headers=admin).status_code == 400

    def test_save_token(self, admin):
        r = requests.put(f"{API}/admin/fonnte", json={"token": "TESTfaketoken9876", "owner_whatsapp": "0812-3456-7890"}, headers=admin)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["has_token"] and d["source"] == "admin" and d["token_hint"] == "••••9876" and d["otp_mode"] == "asli"
        assert d["owner_whatsapp"] == "6281234567890", d
        s = mdb.settings.find_one({"key": "fonnte"})
        assert "TESTfaketoken9876" not in str(s.get("token_enc")), "token not encrypted"
        assert "TESTfaketoken9876" not in requests.get(f"{API}/admin/fonnte", headers=admin).text

    def test_saved_fake_token_test(self, admin):
        r = requests.post(f"{API}/admin/fonnte/test", json={}, headers=admin)
        assert r.status_code == 200 and r.json()["ok"] is False, r.text
        assert requests.get(f"{API}/admin/fonnte", headers=admin).json()["last_test"]["ok"] is False

    def test_saved_fake_token_test_otp(self, admin):
        r = requests.post(f"{API}/admin/fonnte/test-otp", json={"phone": "081234567890"}, headers=admin)
        print("\ntest-otp fake token:", r.status_code, r.text[:200])
        assert r.status_code == 400 and "Fonnte menolak" in r.json()["detail"]

    def test_zz_clear(self, admin):
        r = requests.put(f"{API}/admin/fonnte", json={"token": "", "owner_whatsapp": ""}, headers=admin)
        assert r.status_code == 200
        d = r.json()
        assert d["has_token"] is False and d["otp_mode"] == "uji" and d["token_hint"] == ""
