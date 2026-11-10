# Helper for iter72 UI: `create` = jombang-owned TEST product (nonaktif, via jombang Excel import) + Super Admin similar list on it; `clean` removes by id.
import json
import sys

sys.path.insert(0, "/app/backend/tests")
from test_pgs_iter72_similar import API, DB, H, imp, login, requests, xlsx  # noqa: E402

STATE = "/tmp/ui_iter72.json"
cmd = sys.argv[1]
adm = login("admin@pgs.id", "Admin1234!")
if cmd == "create":
    jt = login("jombang@pgs.id", "Jombang123!")
    name = "TEST_UI72 Panci Jombang"
    r = imp(jt, xlsx(name, ""), True)
    print(r.status_code, r.json()["rows"])
    pid = DB.products.find_one({"name": name}, {"product_id": 1})["product_id"]
    admin_list = ["pgs-10094", "pgs-10444", "pgs-10062"]
    r = requests.put(f"{API}/product-editor/similar/{pid}", headers=H(adm), json={"items": admin_list})
    print("admin list", r.status_code, [i["product_id"] for i in r.json()["items"]])
    json.dump({"pid": pid, "admin_list": admin_list, "jt": jt}, open(STATE, "w"))
    print({"pid": pid})
elif cmd == "clean":
    s = json.load(open(STATE))
    pid = s["pid"]
    DB.similar_products.delete_many({"product_id": pid})
    DB.products.delete_one({"product_id": pid, "name": {"$regex": "^TEST_"}})
    for c in ("price_history", "product_events", "product_history"):
        DB[c].delete_many({"product_id": pid})
    print("cleaned", pid, "similar docs left:", DB.similar_products.count_documents({}))
