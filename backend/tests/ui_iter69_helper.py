# Iter69 UI helper: TEST_ drafts for category auto-suggest UI. usage: python ui_iter69_helper.py create|cleanup
import json
import os
import sys
import requests
from pymongo import MongoClient

API = os.environ["EXPO_BACKEND_URL"].rstrip("/") + "/api"
F = "/tmp/iter69_ids.json"


def tok(e, p):
    return {"Authorization": "Bearer " + requests.post(f"{API}/auth/login", json={"email": e, "password": p}, timeout=20).json()["token"]}


A, J = tok("admin@pgs.id", "Admin1234!"), tok("jombang@pgs.id", "Jombang123!")
if sys.argv[1] == "create":
    src = requests.get(f"{API}/product-editor/products/pgs-10611", headers=A, timeout=30).json()["data"]
    # admin draft whose category was chosen manually (fashion) — must survive opening it while auto-suggest is active
    a = requests.post(f"{API}/product-editor/drafts", headers=A, timeout=30, json={"data": {**src, "name": "TEST_Draft Manual Fashion", "category": "fashion", "subcategory": "", "sku": "", "barcode": ""}}).json()
    # jombang draft with complete data but no category -> UI should auto-fill it, then publish
    data = {**src, "name": "TEST_Panci Stainless 24cm UI", "category": "", "subcategory": "", "sku": "", "barcode": "", "status": "inactive",
            "weight_grams": 1000, "description": "<p>TEST produk panci stainless untuk pengujian otomatis kategori.</p>", "couriers": []}
    for v in data.get("variants") or []:
        v["variant_id"], v["sku"] = "", ""
    j = requests.post(f"{API}/product-editor/drafts", headers=J, timeout=30, json={"data": data}).json()
    json.dump({"admin_draft": a["draft_id"], "jombang_draft": j["draft_id"]}, open(F, "w"))
    print(json.load(open(F)))
else:
    ids = json.load(open(F))
    print(requests.delete(f"{API}/product-editor/drafts/{ids['admin_draft']}", headers=A, timeout=30).status_code)
    print(requests.delete(f"{API}/product-editor/drafts/{ids['jombang_draft']}", headers=J, timeout=30).status_code)
    env = dict(l.strip().split("=", 1) for l in open("/app/backend/.env") if "=" in l)
    db = MongoClient(env["MONGO_URL"].strip('"'))[env["DB_NAME"].strip('"')]
    for p in db.products.find({"name": "TEST_Panci Stainless 24cm UI", "store_id": "pgs-jombang"}, {"product_id": 1}):
        print("delete", p["product_id"], requests.delete(f"{API}/seller/products/{p['product_id']}", headers=J, timeout=30).status_code)
