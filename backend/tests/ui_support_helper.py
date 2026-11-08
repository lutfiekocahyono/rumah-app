# Helper for iteration 7 UI tests (komplain / chat / saldo): setup TEST buyer with shipped order, and cleanup.
import os, sys, uuid, asyncio, requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
API = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"
SHIP = {"full_name": "TEST_UI Komplain", "phone": "081234567890", "address": "Jl. Test No 7", "city": "Sidoarjo"}


def login(e, p):
    return {"Authorization": "Bearer " + requests.post(f"{API}/auth/login", json={"email": e, "password": p}).json()["token"]}


cmd = sys.argv[1]
if cmd == "setup":
    email = f"test_ui_kmp_{uuid.uuid4().hex[:6]}@example.com"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "Test1234!", "name": "TEST_UIKomplain"}).json()
    h = {"Authorization": f"Bearer {r['token']}", "X-Store-Id": "pgs-official"}
    sid = login("sidoarjo@pgs.id", "Sidoarjo123!")
    requests.post(f"{API}/cart/items", headers=h, json={"product_id": "pgs-9955", "quantity": 1})
    o = requests.post(f"{API}/checkout", headers=h, json={**SHIP, "payment_method": "cod", "courier": "jne", "store_id": "pgs-official"}).json()
    requests.put(f"{API}/seller/orders/{o['order_id']}/status", headers=sid, json={"status": "processing"})
    requests.put(f"{API}/seller/orders/{o['order_id']}/status", headers=sid, json={"status": "shipped", "tracking_number": "TESTUI123"})
    print(email, r["user"]["user_id"], o["order_id"], o["total"])
elif cmd == "cleanup":
    uid = sys.argv[2]

    async def clean():
        db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        orders = await db.orders.find({"user_id": uid}).to_list(50)
        for o in orders:
            if not o.get("restocked"):
                for i in o["items"]:
                    await db.products.update_one({"product_id": i["product_id"], "stock": {"$ne": 9999}}, {"$inc": {"stock": i["quantity"]}})
        oids = [o["order_id"] for o in orders]
        cids = [c["complaint_id"] for c in await db.complaints.find({"user_id": uid}).to_list(50)]
        convs = [c["conv_id"] for c in await db.conversations.find({"user_id": uid}).to_list(50)]
        links = [f"/complaint/{c}" for c in cids] + [f"/chat/{c}" for c in convs] + [f"/order/{o}" for o in oids]
        await db.notifications.delete_many({"link": {"$in": links}})
        await db.chat_messages.delete_many({"conv_id": {"$in": convs}})
        await db.conversations.delete_many({"conv_id": {"$in": convs}})
        await db.complaints.delete_many({"complaint_id": {"$in": cids}})
        await db.orders.delete_many({"order_id": {"$in": oids}})
        for c in ("wallets", "wallet_tx", "notifications"):
            await db[c].delete_many({"user_id": uid})
        await db.carts.delete_many({"owner": f"user:{uid}"})
        await db.users.delete_many({"user_id": uid})
        print("cleaned", oids, cids, convs)
    asyncio.run(clean())
