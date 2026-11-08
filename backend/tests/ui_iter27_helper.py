# Iter27 UI helper: create TEST_ products for seller acct1 (bulk/duplicate UI), print tokens; "clean" removes TEST_UI27 products/drafts.
import json
import os
import sys

import requests
from pymongo import MongoClient

API = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"
IMG = "https://pusatgrosirsidoarjo.com/wp-content/uploads/2023/07/Cetakan-7-Lubang-Cekung-Suggo-300x300.webp"
env = {l.split("=", 1)[0]: l.split("=", 1)[1].strip().strip('"') for l in open("/app/backend/.env") if "=" in l}
DB = MongoClient(env["MONGO_URL"])[env["DB_NAME"]]
tok = lambda e, p: requests.post(f"{API}/auth/login", json={"email": e, "password": p}).json()["token"]
if sys.argv[1] == "create":
    s, a = tok("acct1@pgs.id", "Test1234!"), tok("admin@pgs.id", "Admin1234!")
    ids = []
    for i, price in enumerate((20000, 30000)):
        data = {"name": f"TEST_UI27 Panci Uji {i}", "category": "dapur", "subcategory": "peralatan-masak", "sku": f"UI27-{i}",
                "description": "Panci uji coba untuk pengujian edit massal di daftar produk PGS.", "images": [IMG],
                "price": price, "discount_price": 0, "stock": 10, "weight_grams": 500, "status": "active"}
        r = requests.post(f"{API}/product-editor/publish", headers={"Authorization": f"Bearer {s}"}, json={"data": data})
        ids.append(r.json()["product_id"])
    print(json.dumps({"seller": s, "admin": a, "ids": ids}))
elif sys.argv[1] == "clean":
    ids = [p["product_id"] for p in DB.products.find({"name": {"$regex": "^TEST_UI27"}}, {"product_id": 1})]
    print("products", DB.products.delete_many({"product_id": {"$in": ids}, "name": {"$regex": "^TEST_UI27"}}).deleted_count)
    print("drafts", DB.product_drafts.delete_many({"data.name": {"$regex": "^TEST_UI27"}}).deleted_count)
