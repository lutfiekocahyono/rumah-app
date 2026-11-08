# Iter16 UI helper: demo@pgs.id gets 1 item in cart at pgs-official + a TEST_ saved address. `cleanup <address_id>` removes the address.
import os, sys, json, requests
API = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"
t = requests.post(f"{API}/auth/login", json={"email": "demo@pgs.id", "password": "Demo1234!"}).json()["token"]
h = {"Authorization": f"Bearer {t}", "X-Store-Id": "pgs-official"}
if len(sys.argv) > 2 and sys.argv[1] == "cleanup":
    print(requests.delete(f"{API}/me/addresses/{sys.argv[2]}", headers=h).status_code)
    requests.delete(f"{API}/cart", headers=h)
    sys.exit(0)
d = requests.get(f"{API}/shipping/destinations", params={"q": "gubeng"}, headers=h).json()
r0 = (d.get("data", d) if isinstance(d, dict) else d)[0]
a = requests.post(f"{API}/me/addresses", headers=h, json={"label": "TEST_Rumah", "recipient": "TEST Demo", "phone": "081234567890",
    "address": "Jl. Test No 1", "city": "Surabaya", "destination_id": r0["id"], "destination_label": r0["label"], "is_default": True}).json()
c = requests.post(f"{API}/cart/items", headers=h, json={"product_id": "pgs-9955", "quantity": 1})
print(json.dumps({"address_id": a.get("address_id"), "cart": c.status_code}))
