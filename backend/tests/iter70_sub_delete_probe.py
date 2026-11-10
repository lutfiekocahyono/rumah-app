# Probe (iter70): deleting only a SUB-category — does the product keep its main category, or is it moved to Lainnya?
import sys
sys.path.insert(0, "/app/backend/tests")
from test_pgs_iter70_catalog_master import API, DB, H, SUF, form, requests  # noqa: E402

t = requests.post(f"{API}/auth/login", json={"email": "admin@pgs.id", "password": "Admin1234!"}).json()["token"]
c = requests.post(f"{API}/admin/categories", headers=H(t), json={"name": f"TEST_P {SUF}"}).json()
s = requests.post(f"{API}/admin/categories", headers=H(t), json={"name": f"TEST_PS {SUF}", "parent": c["category_id"]}).json()
pid = None
try:
    r = requests.post(f"{API}/product-editor/publish", headers=H(t), json={"data": form(name=f"TEST_P {SUF}", category=c["category_id"], subcategory=s["category_id"])})
    pid = r.json()["product_id"]
    imp = requests.get(f"{API}/admin/categories/{s['category_id']}/impact", headers=H(t)).json()
    d = requests.delete(f"{API}/admin/categories/{s['category_id']}", headers=H(t)).json()
    p = DB.products.find_one({"product_id": pid}, {"_id": 0, "category": 1, "subcategory": 1, "categories": 1})
    print("impact", imp, "delete", d, "product after sub delete:", p)
finally:
    if pid:
        DB.products.delete_one({"product_id": pid, "name": {"$regex": "^TEST_"}})
        for col in ("price_history", "product_events", "product_history"):
            DB[col].delete_many({"product_id": pid})
    DB.categories.delete_many({"category_id": {"$in": [c["category_id"], s["category_id"]]}, "source": "admin"})
    DB.categories.update_one({"category_id": "lainnya", "count": {"$gt": 0}}, {"$inc": {"count": -1}})
    print("cleaned", DB.categories.find_one({"category_id": "lainnya"}, {"_id": 0, "count": 1}))
