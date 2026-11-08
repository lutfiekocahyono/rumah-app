# Helper for iteration 11 UI test (smart saved address). setup | check | cleanup
import os, sys, uuid, json, asyncio, requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
API = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"
STATE = "/tmp/ui_iter11_state.json"

cmd = sys.argv[1]
if cmd == "setup":
    email = f"test_ui11_{uuid.uuid4().hex[:6]}@example.com"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "Test1234!", "name": "TEST_UI11"}).json()
    h = {"Authorization": f"Bearer {r['token']}", "X-Store-Id": "pgs-official"}
    stock = requests.get(f"{API}/products/pgs-9955", headers=h).json()["stock"]
    print(requests.post(f"{API}/cart/items", headers=h, json={"product_id": "pgs-9955", "quantity": 1}).status_code)
    lst = requests.post(f"{API}/me/addresses", headers=h, json={"label": "TEST_Kantor", "recipient": "TEST Budi", "phone": "081200000001", "address": "Jl. TEST Kantor 5", "city": "Sidoarjo", "postal_code": "", "is_default": True}).json()
    b = lst[0]["address_id"]
    json.dump({"email": email, "uid": r["user"]["user_id"], "token": r["token"], "stock0": stock, "b": b}, open(STATE, "w"))
    print(json.dumps({"email": email, "uid": r["user"]["user_id"], "stock0": stock, "b": b}))
elif cmd == "check":
    s = json.load(open(STATE))
    h = {"Authorization": f"Bearer {s['token']}"}
    print(json.dumps([{k: a.get(k) for k in ("address_id", "label", "city", "postal_code", "is_default", "destination_id", "destination_label")} for a in requests.get(f"{API}/me/addresses", headers=h).json()], indent=1))
    for o in requests.get(f"{API}/orders", headers=h).json():
        print("order", o["order_id"], o.get("shipping_cost"), (o.get("courier") or {}).get("code"), o.get("payment_method"), o["status"], o.get("destination_id"), o.get("shipping", {}) if isinstance(o.get("shipping"), dict) else "")
elif cmd == "cleanup":
    s = json.load(open(STATE))
    h = {"Authorization": f"Bearer {s['token']}", "X-Store-Id": "pgs-official"}
    orders = requests.get(f"{API}/orders", headers=h).json()
    st = requests.post(f"{API}/auth/login", json={"email": "sidoarjo@pgs.id", "password": "Sidoarjo123!"}).json()["token"]
    oids = []
    for o in orders:
        oids.append(o["order_id"])
        if o["status"] != "cancelled":
            print("cancel", o["order_id"], requests.put(f"{API}/seller/orders/{o['order_id']}/status", headers={"Authorization": f"Bearer {st}"}, json={"status": "cancelled"}).status_code)
    for a in requests.get(f"{API}/me/addresses", headers=h).json():
        requests.delete(f"{API}/me/addresses/{a['address_id']}", headers=h)
    print("stock now", requests.get(f"{API}/products/pgs-9955", headers=h).json()["stock"], "was", s["stock0"])

    async def run():
        db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        await db.notifications.delete_many({"link": {"$in": [f"/order/{x}" for x in oids]}})
        await db.orders.delete_many({"order_id": {"$in": oids}})
        await db.carts.delete_many({"owner": f"user:{s['uid']}"})
        await db.users.delete_many({"user_id": s["uid"]})
    asyncio.run(run())
    print("cleaned")
