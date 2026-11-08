# Helper for iteration 12 UI test (key check). invalid | setup | cleanup   (never touches api_key_enc / key_hint)
import os, sys, uuid, json, requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
API = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"
STATE = "/tmp/ui_iter12_state.json"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
cmd = sys.argv[1]
if cmd == "invalid":
    print(db.settings.update_one({"key": "shipping_api"}, {"$set": {"key_status.state": "invalid"}}).modified_count)
    print(requests.get(f"{API}/shipping/status").json())
elif cmd == "setup":
    email = f"test_ui12_{uuid.uuid4().hex[:6]}@example.com"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "Test1234!", "name": "TEST_UI12"}).json()
    h = {"Authorization": f"Bearer {r['token']}", "X-Store-Id": "pgs-official"}
    print(requests.post(f"{API}/cart/items", headers=h, json={"product_id": "pgs-9955", "quantity": 1}).status_code)
    json.dump({"email": email, "uid": r["user"]["user_id"], "token": r["token"]}, open(STATE, "w"))
    print(json.dumps({"uid": r["user"]["user_id"], "token": r["token"]}))
elif cmd == "cleanup":
    s = json.load(open(STATE))
    print("user", db.users.delete_one({"user_id": s["uid"]}).deleted_count, "cart", db.carts.delete_many({"owner": f"user:{s['uid']}"}).deleted_count,
          "notif", db.notifications.delete_many({"user_id": s["uid"]}).deleted_count)
elif cmd == "restore":
    t = requests.post(f"{API}/auth/login", json={"email": "admin@pgs.id", "password": "Admin1234!"}).json()["token"]
    d = requests.post(f"{API}/admin/shipping/verify-key", headers={"Authorization": f"Bearer {t}"}, timeout=30).json()
    print(d["key_status"]["state"], requests.get(f"{API}/shipping/status").json())
