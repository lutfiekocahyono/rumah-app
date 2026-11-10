# Helper for iter70 UI tests: `create` publishes a TEST product with brand TEST_UIBrand70 (logo), `clean` removes TEST data by id.
import json
import sys

sys.path.insert(0, "/app/backend/tests")
from test_pgs_iter70_catalog_master import API, DB, H, form, requests  # noqa: E402

STATE = "/tmp/ui_iter70.json"
cmd = sys.argv[1]
t = requests.post(f"{API}/auth/login", json={"email": "admin@pgs.id", "password": "Admin1234!"}).json()["token"]
if cmd == "create":
    r = requests.post(f"{API}/product-editor/publish", headers=H(t), json={"data": form(name="TEST_UILogo Panci 70", brand="TEST_UIBrand70")})
    print(r.status_code, r.text[:200])
    json.dump({"pid": r.json()["product_id"]}, open(STATE, "w"))
elif cmd == "clean":
    s = json.load(open(STATE))
    pid = s["pid"]
    DB.products.delete_one({"product_id": pid, "name": {"$regex": "^TEST_"}})
    for c in ("price_history", "product_events", "product_history"):
        DB[c].delete_many({"product_id": pid})
    for bid in s.get("brands", []):
        DB.brands.delete_one({"brand_id": bid, "name": {"$regex": "^TEST_"}})
    for cid in s.get("cats", []):
        DB.categories.delete_one({"category_id": cid, "source": "admin"})
    print("cleaned", s)
