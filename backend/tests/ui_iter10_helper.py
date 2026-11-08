# Helper for iteration 10 UI test (ongkir changed guard). setup | cleanup
import os, sys, uuid, json, asyncio, requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
API = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"
STATE = "/tmp/ui_iter10_state.json"

cmd = sys.argv[1]
if cmd == "setup":
    email = f"test_ui10_{uuid.uuid4().hex[:6]}@example.com"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "Test1234!", "name": "TEST_UI10"}).json()
    h = {"Authorization": f"Bearer {r['token']}", "X-Store-Id": "pgs-official"}
    stock = requests.get(f"{API}/products/pgs-9955", headers=h).json()["stock"]
    print(requests.post(f"{API}/cart/items", headers=h, json={"product_id": "pgs-9955", "quantity": 1}).status_code)
    json.dump({"email": email, "uid": r["user"]["user_id"], "token": r["token"], "stock0": stock}, open(STATE, "w"))
    print(json.dumps({"email": email, "uid": r["user"]["user_id"], "stock0": stock}))
elif cmd == "cleanup":
    s = json.load(open(STATE))
    h = {"Authorization": f"Bearer {s['token']}", "X-Store-Id": "pgs-official"}
    orders = requests.get(f"{API}/orders", headers=h).json()
    st = requests.post(f"{API}/auth/login", json={"email": "sidoarjo@pgs.id", "password": "Sidoarjo123!"}).json()["token"]
    oids = []
    for o in orders:
        oids.append(o["order_id"])
        print("order", o["order_id"], o["shipping_cost"], o.get("courier", {}).get("code"), o["status"])
        if o["status"] not in ("cancelled",):
            print("cancel", requests.put(f"{API}/seller/orders/{o['order_id']}/status", headers={"Authorization": f"Bearer {st}"}, json={"status": "cancelled"}).status_code)
    print("stock now", requests.get(f"{API}/products/pgs-9955", headers=h).json()["stock"], "was", s["stock0"])

    async def run():
        db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        await db.notifications.delete_many({"link": {"$in": [f"/order/{x}" for x in oids]}})
        await db.orders.delete_many({"order_id": {"$in": oids}})
        await db.carts.delete_many({"owner": f"user:{s['uid']}"})
        await db.users.delete_many({"user_id": s["uid"]})
    asyncio.run(run())
    print("cleaned")
elif cmd == "token":
    print(json.load(open(STATE))["token"])
