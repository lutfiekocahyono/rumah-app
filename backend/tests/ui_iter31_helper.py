# Helper for iter31 UI tests: `create` makes a pickup COD order (demo@pgs.id at pgs-official), `clean` deletes it and restores stock/sold.
import json
import os
import sys

sys.path.insert(0, "/app/backend/tests")
os.environ.setdefault("EXPO_PUBLIC_BACKEND_URL", [l.split("=", 1)[1].strip() for l in open("/app/frontend/.env") if l.startswith("EXPO_PUBLIC_BACKEND_URL=")][0])
from test_pgs_iter31_scan_export import API, DB, H, PID, STORE, requests  # noqa: E402

STATE = "/tmp/ui_iter31.json"
cmd = sys.argv[1]
if cmd == "create":
    t = requests.post(f"{API}/auth/login", json={"email": "demo@pgs.id", "password": "Demo1234!"}).json()["token"]
    before = DB.products.find_one({"product_id": PID}, {"_id": 0, "stock": 1, "sold": 1})
    requests.delete(f"{API}/cart", headers=H(t))
    requests.post(f"{API}/cart/items", headers=H(t, STORE), json={"product_id": PID, "quantity": 1}).raise_for_status()
    r = requests.post(f"{API}/checkout", headers=H(t), json={"full_name": "TEST Scan UI", "phone": "081234567890", "payment_method": "cod",
                                                              "store_id": STORE, "courier": "pickup"})
    r.raise_for_status()
    o = r.json()
    json.dump({"order_id": o["order_id"], "code": o["pickup_code"], "before": before}, open(STATE, "w"))
    print(o["order_id"], o["pickup_code"], o["total"], o["status"])
elif cmd == "clean":
    s = json.load(open(STATE))
    DB.orders.delete_one({"order_id": s["order_id"]})
    DB.products.update_one({"product_id": PID}, {"$set": s["before"]})
    print("cleaned", s["order_id"])
