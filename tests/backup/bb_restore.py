# Restore store_stock (pgs-jombang, pgs-jember) exactly from bb_backup.pkl; remove test history rows/events/previews
import os, pickle, json
from pymongo import MongoClient, ReplaceOne
from dotenv import load_dotenv

load_dotenv('/app/backend/.env')
db = MongoClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]
data = pickle.load(open('/app/tests/backup/bb_backup.pkl', 'rb'))
t0, docs = data["t0"], data["docs"]
STORES = ["pgs-jombang", "pgs-jember"]
ops = [ReplaceOne({"_id": d["_id"]}, d, upsert=True) for d in docs]
for i in range(0, len(ops), 1000):
    db.store_stock.bulk_write(ops[i:i + 1000], ordered=False)
ids = [d["_id"] for d in docs]
extra = db.store_stock.delete_many({"store_id": {"$in": STORES}, "_id": {"$nin": ids}}).deleted_count
ph = db.price_history.delete_many({"source": {"$in": ["branch_copy", "branch_price", "branch_bulk"]}, "store_id": {"$in": STORES}, "at": {"$gte": t0}}).deleted_count
ev = db.product_events.delete_many({"store_id": {"$in": STORES}, "at": {"$gte": t0}}).deleted_count if db.product_events.count_documents({}) > data["ev"] else 0
cr = '/app/tests/backup/bb_created.json'
pv = 0
if os.path.exists(cr):
    pids = json.load(open(cr)).get("preview_ids", [])
    pv = db.branch_copy.delete_many({"preview_id": {"$in": pids}}).deleted_count
    os.remove(cr)
print(f"restored {len(docs)} docs, removed extra {extra}, price_history {ph}, events {ev}, previews {pv}")
# verify
cur = {d["_id"]: d for d in db.store_stock.find({"store_id": {"$in": STORES}})}
diff = sum(1 for d in docs if cur.get(d["_id"]) != d)
print("mismatched docs after restore:", diff, "| manual_price_at left:", db.store_stock.count_documents({"store_id": {"$in": STORES}, "manual_price_at": {"$exists": True}}))
print("price_history count", db.price_history.count_documents({}), "(backup", data["ph"], ") events", db.product_events.count_documents({}), "(backup", data["ev"], ") notifications", db.notifications.count_documents({}), "(backup", data["nt"], ")")
bp = db.branch_price_previews.delete_many({"store_id": {"$in": STORES}, "created_at": {"$gte": t0}}).deleted_count
nt = db.notifications.delete_many({"created_at": {"$gte": t0}, "kind": {"$in": ["product_update", "price", "wishlist"]}}).deleted_count if db.notifications.count_documents({}) > data["nt"] else 0
print("branch_price_previews deleted:", bp, "| notifications deleted:", nt, "| notif now", db.notifications.count_documents({}))
