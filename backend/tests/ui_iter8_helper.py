# Helper for iteration 8 UI tests (unread badges, COD-unpaid complaint, checkout auto ongkir). setup | msg | cleanup
import os, sys, uuid, json, asyncio, requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
API = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"
SHIP = {"full_name": "TEST_UI Ongkir", "phone": "081234567890", "address": "Jl. Test No 8", "city": "Surabaya"}
STATE = "/tmp/ui_iter8_state.json"


def login(e, p):
    return requests.post(f"{API}/auth/login", json={"email": e, "password": p}).json()["token"]


cmd = sys.argv[1]
if cmd == "setup":
    email = f"test_ui_ongkir_{uuid.uuid4().hex[:6]}@example.com"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "Test1234!", "name": "TEST_UIOngkir"}).json()
    bt, st = r["token"], login("sidoarjo@pgs.id", "Sidoarjo123!")
    h = {"Authorization": f"Bearer {bt}", "X-Store-Id": "pgs-official"}
    sh = {"Authorization": f"Bearer {st}"}
    requests.post(f"{API}/cart/items", headers=h, json={"product_id": "pgs-9955", "quantity": 1})
    o = requests.post(f"{API}/checkout", headers=h, json={**SHIP, "payment_method": "cod", "courier": "jne", "store_id": "pgs-official"}).json()
    requests.put(f"{API}/seller/orders/{o['order_id']}/status", headers=sh, json={"status": "processing"})
    requests.put(f"{API}/seller/orders/{o['order_id']}/status", headers=sh, json={"status": "shipped", "tracking_number": "TESTUI8"})
    c = requests.post(f"{API}/complaints", headers=h, json={"order_id": o["order_id"], "reason": "damaged", "description": "TEST_ barang rusak parah", "refund_amount": 5000}).json()
    cv = requests.post(f"{API}/chats", headers=h, json={"store_id": "pgs-official"}).json()
    requests.post(f"{API}/chats/{cv['conv_id']}/messages", headers=sh, json={"text": "TEST_ pesan dari toko"})
    requests.post(f"{API}/cart/items", headers=h, json={"product_id": "pgs-9955", "quantity": 1})  # for UI checkout
    s = {"email": email, "uid": r["user"]["user_id"], "buyer_token": bt, "store_token": st, "order": o["order_id"],
         "cid": c["complaint_id"], "conv": cv["conv_id"]}
    json.dump(s, open(STATE, "w"))
    print(json.dumps({k: v for k, v in s.items() if "token" not in k}))
elif cmd == "msg":  # buyer -> store message
    s = json.load(open(STATE))
    print(requests.post(f"{API}/chats/{s['conv']}/messages", headers={"Authorization": f"Bearer {s['buyer_token']}"}, json={"text": "TEST_ pesan dari pembeli"}).status_code)
elif cmd == "cleanup":
    s = json.load(open(STATE))
    admin = {"Authorization": "Bearer " + login("admin@pgs.id", "Admin1234!")}

    async def clean():
        db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        oids = [o["order_id"] for o in await db.orders.find({"user_id": s["uid"]}, {"order_id": 1}).to_list(20)]
        for oid in oids:  # admin cancel -> restock once
            requests.put(f"{API}/admin/orders/{oid}/status", headers=admin, json={"status": "cancelled"})
        links = [f"/complaint/{s['cid']}", f"/chat/{s['conv']}"] + [f"/order/{o}" for o in oids]
        await db.notifications.delete_many({"link": {"$in": links}})
        await db.complaints.delete_many({"complaint_id": s["cid"]})
        await db.chat_messages.delete_many({"conv_id": s["conv"]})
        await db.conversations.delete_many({"conv_id": s["conv"]})
        await db.orders.delete_many({"order_id": {"$in": oids}})
        await db.wallets.delete_many({"user_id": s["uid"]})
        await db.wallet_tx.delete_many({"user_id": s["uid"]})
        await db.carts.delete_many({"owner": f"user:{s['uid']}"})
        await db.users.delete_many({"user_id": s["uid"]})
        print("cleaned orders", oids)
    asyncio.run(clean())
