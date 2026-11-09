# delete UI-test preview docs by id
import os, sys
from pymongo import MongoClient
from dotenv import load_dotenv
load_dotenv('/app/backend/.env')
db = MongoClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]
print(db.branch_copy.delete_many({"preview_id": {"$in": sys.argv[1:]}, "status": "preview"}).deleted_count)
