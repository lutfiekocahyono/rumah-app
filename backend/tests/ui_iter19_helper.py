# PGS iteration 19 UI helper: create/cancel TEST COD pickup orders at pgs-official (one urgent, one normal).
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
STATE = "/tmp/ui_iter19_orders.json"


def _env(k):
    for line in open("/app/backend/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip('"')


DB = MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]


def login(e, p):
    return requests.post(f"{API}/auth/login", json={"email": e, "password": p}).json()["token"]


def setup():
    email = f"test_iter19ui_{uuid.uuid4().hex[:8]}@example.com"
    t = requests.post(f"{API}/auth/register", json={"email": email, "password": "TestPass123!", "name": "TEST UI19"}).json()["token"]
    ids = []
    for _ in range(2):
        requests.post(f"{API}/cart/items", headers={"Authorization": f"Bearer {t}", "X-Store-Id": "pgs-official"},
                      json={"product_id": "pgs-9955", "quantity": 1})
        r = requests.post(f"{API}/checkout", headers={"Authorization": f"Bearer {t}"}, json={
            "full_name": "TEST UI19", "phone": "081234567890", "address": "", "city": "", "payment_method": "cod",
            "store_id": "pgs-official", "courier": "pickup"})
        r.raise_for_status()
        ids.append(r.json()["order_id"])
    DB.orders.update_one({"order_id": ids[0]}, {"$set": {"expires_at": datetime.now(timezone.utc) + timedelta(hours=3)}})
    json.dump({"urgent": ids[0], "normal": ids[1]}, open(STATE, "w"))
    print(json.dumps({"urgent": ids[0], "normal": ids[1]}))


def cleanup():
    s = json.load(open(STATE))
    t = login("sidoarjo@pgs.id", "Sidoarjo123!")
    for oid in s.values():
        r = requests.put(f"{API}/seller/orders/{oid}/status", headers={"Authorization": f"Bearer {t}"}, json={"status": "cancelled"})
        print(oid, r.status_code)


if __name__ == "__main__":
    setup() if sys.argv[1] == "setup" else cleanup()
