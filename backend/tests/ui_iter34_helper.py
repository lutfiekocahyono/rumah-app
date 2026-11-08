# PGS iter34 UI helper: create/cleanup a TEST_ COD pickup order for demo@pgs.id (restores stock + cart).
import json
import os
import sys

import requests
from pymongo import MongoClient

API = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/") + "/api"
PID, STORE, STATE = "pgs-9955", "pgs-official", "/tmp/iter34_state.json"


def _env(k):
    for line in open("/app/backend/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip('"')


DB = MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]


def login(e, p):
    return requests.post(f"{API}/auth/login", json={"email": e, "password": p}).json()["token"]


def H(t, store=None):
    return {"Authorization": f"Bearer {t}", **({"X-Store-Id": store} if store else {})}


if sys.argv[1] == "create":
    t = login("demo@pgs.id", "Demo1234!")
    before = DB.products.find_one({"product_id": PID}, {"_id": 0, "stock": 1, "sold": 1})
    cart = requests.get(f"{API}/cart", headers=H(t, STORE)).json()
    requests.delete(f"{API}/cart", headers=H(t))
    requests.post(f"{API}/cart/items", headers=H(t, STORE), json={"product_id": PID, "quantity": 1}).raise_for_status()
    r = requests.post(f"{API}/checkout", headers=H(t), json={"full_name": "TEST_QR UI", "phone": "081234567890", "payment_method": "cod",
                                                              "store_id": STORE, "courier": "pickup"})
    r.raise_for_status()
    o = r.json()
    json.dump({"order_id": o["order_id"], "code": o["pickup_code"], "before": before, "cart": cart.get("items", [])}, open(STATE, "w"))
    print(o["order_id"], o["pickup_code"])
elif sys.argv[1] == "complete":
    s = json.load(open(STATE))
    t = login("admin@pgs.id", "Admin1234!")
    print(requests.post(f"{API}/seller/pickup/complete", headers=H(t), json={"code": s["code"]}).json().get("status"))
else:
    s = json.load(open(STATE))
    t = login("demo@pgs.id", "Demo1234!")
    DB.orders.delete_one({"order_id": s["order_id"]})
    DB.notifications.delete_many({"order_id": s["order_id"]})
    DB.products.update_one({"product_id": PID}, {"$set": s["before"]})
    requests.delete(f"{API}/cart", headers=H(t))
    for it in s["cart"]:
        requests.post(f"{API}/cart/items", headers=H(t, it.get("store_id") or STORE), json={"product_id": it["product_id"], "quantity": it["quantity"],
                                                                                           **({"variant_id": it["variant_id"]} if it.get("variant_id") else {})})
    print("cleaned", s["order_id"], DB.products.find_one({"product_id": PID}, {"_id": 0, "stock": 1, "sold": 1}))
