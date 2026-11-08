# Iter29 UI helper: "create" seeds TEST_UI29 products with price/stock history (acct1) + one jombang branch stock log (restored),
# prints tokens/ids as JSON; "clean" removes TEST_UI29 products, their logs and the logged branch-stock log_ids.
import json
import os
import sys
from datetime import datetime, timezone

import requests
from pymongo import MongoClient

API = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"
IMG = "https://pusatgrosirsidoarjo.com/wp-content/uploads/2023/07/Cetakan-7-Lubang-Cekung-Suggo-300x300.webp"
env = {l.split("=", 1)[0]: l.split("=", 1)[1].strip().strip('"') for l in open("/app/backend/.env") if "=" in l}
DB = MongoClient(env["MONGO_URL"])[env["DB_NAME"]]
STATE = "/tmp/ui29_state.json"
SHARED = "pgs-9957"
tok = lambda e, p: requests.post(f"{API}/auth/login", json={"email": e, "password": p}).json()["token"]
H = lambda t: {"Authorization": f"Bearer {t}"}

if sys.argv[1] == "create":
    start = datetime.now(timezone.utc)
    s, a, j = tok("acct1@pgs.id", "Test1234!"), tok("admin@pgs.id", "Admin1234!"), tok("jombang@pgs.id", "Jombang123!")
    ids = []
    for i in range(2):
        data = {"name": f"TEST_UI29 Panci Riwayat {i}", "category": "dapur", "subcategory": "peralatan-masak", "sku": f"UI29-{i}",
                "description": "Panci uji coba untuk pengujian riwayat harga dan stok di PGS.", "images": [IMG],
                "price": 20000, "discount_price": 0, "stock": 10, "weight_grams": 500, "status": "active"}
        pid = requests.post(f"{API}/product-editor/publish", headers=H(s), json={"data": data}).json()["product_id"]
        ids.append(pid)
        d = requests.get(f"{API}/product-editor/products/{pid}", headers=H(s)).json()["data"]
        d.update(price=25000 + i * 1000)
        requests.post(f"{API}/product-editor/publish", headers=H(s), json={"data": d, "product_id": pid})
    requests.post(f"{API}/product-editor/bulk", headers=H(s), json={"product_ids": ids, "stock_mode": "set", "stock_value": 40})
    orig = (DB.store_stock.find_one({"store_id": "pgs-jombang", "product_id": SHARED}) or {}).get("stock", 0)
    requests.put(f"{API}/seller/inventory/{SHARED}", headers=H(j), json={"stock": orig + 3})
    requests.put(f"{API}/seller/inventory/{SHARED}", headers=H(j), json={"stock": orig})
    logs = [d["log_id"] for d in DB.price_history.find({"product_id": SHARED, "at": {"$gte": start}})]
    json.dump({"ids": ids, "shared_logs": logs}, open(STATE, "w"))
    print(json.dumps({"seller": s, "admin": a, "jombang": j, "ids": ids, "orig": orig}))
elif sys.argv[1] == "clean":
    st = json.load(open(STATE))
    print("logs", DB.price_history.delete_many({"product_id": {"$in": st["ids"]}}).deleted_count,
          DB.price_history.delete_many({"log_id": {"$in": st["shared_logs"]}}).deleted_count)
    print("products", DB.products.delete_many({"product_id": {"$in": st["ids"]}, "name": {"$regex": "^TEST_UI29"}}).deleted_count)
