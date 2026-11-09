# Find sample products (tiers, 9999 stock, low stock) for branch-copy verification
import os
from pymongo import MongoClient
from dotenv import load_dotenv
load_dotenv('/app/backend/.env')
db = MongoClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]
P = {"_id": 0, "product_id": 1, "name": 1, "price": 1, "original_price": 1, "stock": 1, "tier_prices": 1, "status": 1}
q = {"store_id": "pgs-official"}
t = db.products.find_one({**q, "tier_prices.langsung.0": {"$exists": True}, "stock": {"$gt": 10, "$lt": 9999}, "status": {"$ne": "inactive"}}, P)
print("TIER", t)
print("9999", db.products.find_one({**q, "stock": 9999, "status": {"$ne": "inactive"}}, P))
print("LOW", db.products.find_one({**q, "stock": {"$gt": 0, "$lte": 3}, "status": {"$ne": "inactive"}}, P))
print("tier count:", db.products.count_documents({**q, "tier_prices": {"$nin": [None, {}]}}), "stock9999:", db.products.count_documents({**q, "stock": 9999}))
for pid in [t["product_id"]]:
    print([r for r in db.store_stock.find({"product_id": pid}, {"_id": 0})])
print("tier keys sample types:", {k: type(v).__name__ for k, v in (t.get("tier_prices") or {}).items()})
