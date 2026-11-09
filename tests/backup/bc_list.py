# list branch_copy docs + verify store_stock still restored
import os
from pymongo import MongoClient
from dotenv import load_dotenv
load_dotenv('/app/backend/.env')
db = MongoClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]
for d in db.branch_copy.find({}, {"_id": 0, "preview_id": 1, "status": 1, "created_at": 1}):
    print(d)
print("price fields:", db.store_stock.count_documents({"store_id": {"$in": ["pgs-jombang", "pgs-jember"]}, "price": {"$exists": True}}),
      "jombang 9955:", db.store_stock.find_one({"store_id": "pgs-jombang", "product_id": "pgs-9955"}, {"_id": 0}),
      "ph:", db.price_history.count_documents({}), "pgs-9955 price:", db.products.find_one({"product_id": "pgs-9955"}, {"price": 1, "_id": 0}))
