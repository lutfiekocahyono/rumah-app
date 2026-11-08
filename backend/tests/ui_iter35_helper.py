# PGS iter35 helper: create 3 TEST_ COD pickup orders for demo@pgs.id (open / completed / cancelled), cleanup restores stock + cart.
import json
import os
import sys

import requests
from pymongo import MongoClient

API = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/") + "/api"
PID, STORE, STATE = "pgs-9955", "pgs-official", "/tmp/iter35_state.json"


def _env(k):
    for line in open("/app/backend/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip('"')


DB = MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]


def login(e, p):
    r = requests.post(f"{API}/auth/login", json={"email": e, "password": p}, timeout=20)
    r.raise_for_status()
    return r.json()["token"]


def H(t, store=None):
    return {"Authorization": f"Bearer {t}", **({"X-Store-Id": store} if store else {})}


def _order(t, name):
    requests.delete(f"{API}/cart", headers=H(t), timeout=20)
    requests.post(f"{API}/cart/items", headers=H(t, STORE), json={"product_id": PID, "quantity": 1}, timeout=20).raise_for_status()
    r = requests.post(f"{API}/checkout", headers=H(t), json={"full_name": name, "phone": "081234567890", "payment_method": "cod",
                                                              "store_id": STORE, "courier": "pickup"}, timeout=30)
    r.raise_for_status()
    return r.json()


def create():
    t = login("demo@pgs.id", "Demo1234!")
    before = DB.products.find_one({"product_id": PID}, {"_id": 0, "stock": 1, "sold": 1})
    cart = requests.get(f"{API}/cart", headers=H(t, STORE), timeout=20).json()
    st = {"before": before, "cart": cart.get("items", []), "orders": {}}
    json.dump(st, open(STATE, "w"))
    for k in ("open", "completed", "cancelled"):
        o = _order(t, f"TEST_COD {k}")
        st["orders"][k] = {"order_id": o["order_id"], "code": o.get("pickup_code")}
        json.dump(st, open(STATE, "w"))
    adm = login("admin@pgs.id", "Admin1234!")
    r = requests.post(f"{API}/seller/pickup/complete", headers=H(adm), json={"code": st["orders"]["completed"]["code"]}, timeout=20)
    st["complete_resp"] = r.status_code
    sa = login("sidoarjo@pgs.id", "Sidoarjo123!")
    r = requests.put(f"{API}/seller/orders/{st['orders']['cancelled']['order_id']}/status", headers=H(sa), json={"status": "cancelled"}, timeout=20)
    st["cancel_resp"] = r.status_code
    json.dump(st, open(STATE, "w"))
    return st


def clean():
    st = json.load(open(STATE))
    t = login("demo@pgs.id", "Demo1234!")
    for o in st["orders"].values():
        DB.orders.delete_one({"order_id": o["order_id"]})
        DB.notifications.delete_many({"order_id": o["order_id"]})
    DB.products.update_one({"product_id": PID}, {"$set": st["before"]})
    requests.delete(f"{API}/cart", headers=H(t), timeout=20)
    for it in st["cart"]:
        requests.post(f"{API}/cart/items", headers=H(t, it.get("store_id") or STORE), json={"product_id": it["product_id"], "quantity": it["quantity"],
                                                                                           **({"variant_id": it["variant_id"]} if it.get("variant_id") else {})}, timeout=20)
    return DB.products.find_one({"product_id": PID}, {"_id": 0, "stock": 1, "sold": 1})


if __name__ == "__main__":
    if sys.argv[1] == "create":
        print(json.dumps(create(), default=str))
    else:
        print("cleaned", clean())
