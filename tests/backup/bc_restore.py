# Restore store_stock (pgs-jombang/pgs-jember) from backup and remove test artefacts (branch_copy history, previews, guest carts)
import os, json
from pymongo import MongoClient
from bson import json_util
from dotenv import load_dotenv
load_dotenv('/app/backend/.env')
db = MongoClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]
bk = json.load(open('/app/tests/backup/store_stock_backup.json'))
rows = json_util.loads(json.dumps(bk["rows"]))
ids = [r["_id"] for r in rows]
n = 0
for r in rows:
    n += db.store_stock.replace_one({"_id": r["_id"]}, r).modified_count
extra = db.store_stock.delete_many({"store_id": {"$in": ["pgs-jombang", "pgs-jember"]}, "_id": {"$nin": ids}}).deleted_count
print("restored rows modified:", n, "extra removed:", extra)
if bk["counts"]["price_history_branch_copy"] == 0:
    print("price_history branch_copy deleted:", db.price_history.delete_many({"source": "branch_copy"}).deleted_count)
cr = json.load(open('/app/tests/backup/created_ids.json')) if os.path.exists('/app/tests/backup/created_ids.json') else {}
print("previews deleted:", db.branch_copy.delete_many({"preview_id": {"$in": cr.get("preview_ids", [])}}).deleted_count)
print("guest carts deleted:", db.carts.delete_many({"owner": {"$in": [f"guest:{g}" for g in cr.get("guest_ids", [])] + cr.get("guest_ids", [])}}).deleted_count)
print("verify price fields left:", db.store_stock.count_documents({"store_id": {"$in": ["pgs-jombang", "pgs-jember"]}, "price": {"$exists": True}}))
print("counts:", {c: db[c].count_documents({}) for c in ["price_history", "product_events", "notifications", "branch_copy", "store_stock"]})
