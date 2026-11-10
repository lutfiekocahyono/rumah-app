# Helper for iter71 UI tests: `create` adds TEST brands/categories + 1 TEST product via API, `check` prints state, `clean` removes by id.
import json
import sys

sys.path.insert(0, "/app/backend/tests")
from test_pgs_iter70_catalog_master import API, DB, H, form, requests  # noqa: E402

STATE = "/tmp/ui_iter71.json"
cmd = sys.argv[1]
t = requests.post(f"{API}/auth/login", json={"email": "admin@pgs.id", "password": "Admin1234!"}).json()["token"]
if cmd == "create":
    s = {"brands": [], "cats": []}
    for n in ("TEST_UIRen71", "TEST_UIDel71"):
        r = requests.post(f"{API}/admin/brands", headers=H(t), json={"name": n, "logo": ""})
        s["brands"].append(r.json()["brand_id"])
    c = requests.post(f"{API}/admin/categories", headers=H(t), json={"name": "TEST_UICat71"}).json()["category_id"]
    sub = requests.post(f"{API}/admin/categories", headers=H(t), json={"name": "TEST_UISub71", "parent": c}).json()["category_id"]
    s["cats"] += [c, sub]
    r = requests.post(f"{API}/product-editor/publish", headers=H(t),
                      json={"data": form(name="TEST_UI71 Panci", brand="TEST_UIRen71", category=c, subcategory=sub, status="inactive")})
    print(r.status_code, r.text[:200])
    s["pid"] = r.json()["product_id"]
    s["lainnya0"] = DB.categories.find_one({"category_id": "lainnya"})["count"]
    json.dump(s, open(STATE, "w"))
    print(s)
elif cmd == "check":
    s = json.load(open(STATE))
    print("product", DB.products.find_one({"product_id": s["pid"]}, {"_id": 0, "brand": 1, "category": 1, "subcategory": 1, "categories": 1}))
    print("brands", list(DB.brands.find({"brand_id": {"$in": s["brands"]}}, {"_id": 0, "name": 1})))
    print("cats", list(DB.categories.find({"category_id": {"$in": s["cats"]}}, {"_id": 0, "category_id": 1})))
elif cmd == "clean":
    s = json.load(open(STATE))
    pid = s["pid"]
    DB.products.delete_one({"product_id": pid, "name": {"$regex": "^TEST_"}})
    for c in ("price_history", "product_events", "product_history"):
        DB[c].delete_many({"product_id": pid})
    for bid in s["brands"]:
        DB.brands.delete_one({"brand_id": bid, "name": {"$regex": "^TEST_"}})
    for cid in s["cats"]:
        DB.categories.delete_one({"category_id": cid, "source": "admin"})
    DB.categories.update_one({"category_id": "lainnya"}, {"$set": {"count": s["lainnya0"]}})
    print("cleaned", s)
