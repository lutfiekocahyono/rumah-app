# Backup store_stock rows of pgs-jombang / pgs-jember + counts before branch-copy apply test
import os, sys, json
from pymongo import MongoClient
from bson import json_util
from dotenv import load_dotenv
load_dotenv('/app/backend/.env')
db = MongoClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]
rows = list(db.store_stock.find({"store_id": {"$in": ["pgs-jombang", "pgs-jember"]}}))
counts = {c: db[c].count_documents({}) for c in ["price_history", "product_events", "notifications", "branch_copy", "store_stock"]}
counts["price_history_branch_copy"] = db.price_history.count_documents({"source": "branch_copy"})
json.dump({"rows": json.loads(json_util.dumps(rows)), "counts": counts}, open('/app/tests/backup/store_stock_backup.json', 'w'))
print(len(rows), counts)
print({s: db.store_stock.count_documents({"store_id": s}) for s in ["pgs-jombang", "pgs-jember"]})
print("with price:", db.store_stock.count_documents({"store_id": {"$in": ["pgs-jombang", "pgs-jember"]}, "price": {"$exists": True}}))
print("pgs-official products:", db.products.count_documents({"store_id": "pgs-official"}), "no variants:", db.products.count_documents({"store_id": "pgs-official", "variants.0": {"$exists": False}}))
print("sample row:", db.store_stock.find_one({"store_id": "pgs-jombang"}, {"_id": 0}))
print("indexes:", db.store_stock.index_information().keys())
