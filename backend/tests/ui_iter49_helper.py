# PGS iter49 helper (Edit Harga Cabang UI): backup / restore store_stock rows of the product edited in the UI.
# usage: python ui_iter49_helper.py backup|restore|show
import os
import pickle
import sys
import datetime as dt

from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
PIDS, STATE = ["pgs-9955", "pgs-9952"], "/tmp/iter49_ui_state.pkl"

if sys.argv[1] == "backup":
    rows = list(DB.store_stock.find({"product_id": {"$in": PIDS}}))
    prods = list(DB.products.find({"product_id": {"$in": PIDS}}))
    pickle.dump({"rows": rows, "prods": prods, "start": dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=5)}, open(STATE, "wb"))
    print("backed up", len(rows), "rows")
elif sys.argv[1] == "restore":
    st = pickle.load(open(STATE, "rb"))
    for r in st["rows"]:
        DB.store_stock.replace_one({"_id": r["_id"]}, r)
    for p in st["prods"]:
        DB.products.replace_one({"_id": p["_id"]}, p)
    ph = DB.price_history.delete_many({"source": "branch_price", "product_id": {"$in": PIDS}, "at": {"$gte": st["start"]}})
    ev = DB.product_events.delete_many({"product_id": {"$in": PIDS}, "at": {"$gte": st["start"]}, "digest_id": None})
    ok = all(DB.store_stock.find_one({"_id": r["_id"]}) == r for r in st["rows"])
    print("restored", len(st["rows"]), "exact:", ok, "deleted ph:", ph.deleted_count, "events:", ev.deleted_count)
else:
    for r in DB.store_stock.find({"product_id": {"$in": PIDS}}, {"_id": 0, "tier_prices": 0}):
        print(r)
    print("branch_price history rows:", DB.price_history.count_documents({"source": "branch_price"}))
