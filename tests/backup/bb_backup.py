# Backup store_stock (pgs-jombang, pgs-jember) + counts before branch-copy pct testing
import os, pickle
from datetime import datetime, timezone
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv('/app/backend/.env')
db = MongoClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]
OUT = '/app/tests/backup/bb_backup.pkl'
docs = list(db.store_stock.find({"store_id": {"$in": ["pgs-jombang", "pgs-jember"]}}))
data = {"t0": datetime.now(timezone.utc), "docs": docs,
        "ph": db.price_history.count_documents({}), "ev": db.product_events.count_documents({}),
        "nt": db.notifications.count_documents({})}
pickle.dump(data, open(OUT, 'wb'))
print("backed up", len(docs), "store_stock docs; price_history", data["ph"], "events", data["ev"], "t0", data["t0"])
print("existing manual_price_at:", db.store_stock.count_documents({"store_id": {"$in": ["pgs-jombang", "pgs-jember"]}, "manual_price_at": {"$exists": True}}))
for s in ("pgs-jombang", "pgs-jember"):
    print(s, db.store_stock.count_documents({"store_id": s}), "with price", db.store_stock.count_documents({"store_id": s, "price": {"$gt": 0}}))
