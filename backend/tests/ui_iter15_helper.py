# Iter15 UI helper: TEST buyer with saved area address, one COD pickup order at pgs-official, plus 1 item left in cart
import os, json, uuid, requests
API = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"
email = f"test_ui15_{uuid.uuid4().hex[:6]}@example.com"
t = requests.post(f"{API}/auth/register", json={"email": email, "password": "TestPass123!", "name": "TEST UI15"}).json()["token"]
h = {"Authorization": f"Bearer {t}", "X-Store-Id": "pgs-official"}
d = requests.get(f"{API}/shipping/destinations", params={"q": "gubeng"}, headers=h).json()
r0 = (d.get("data", d) if isinstance(d, dict) else d)[0]
requests.post(f"{API}/me/addresses", headers=h, json={"label": "Rumah", "recipient": "TEST UI15", "phone": "081234567890",
    "address": "Jl. Test No 1", "city": "Surabaya", "destination_id": r0["id"], "destination_label": r0["label"], "is_default": True})
requests.post(f"{API}/cart/items", headers=h, json={"product_id": "pgs-9955", "quantity": 1})
o = requests.post(f"{API}/checkout", headers=h, json={"full_name": "TEST UI15", "phone": "081234567890", "address": "Jl. Test No 1",
    "city": "Surabaya", "payment_method": "cod", "store_id": "pgs-official", "courier": "pickup", "expected_shipping_cost": 0}).json()
requests.post(f"{API}/cart/items", headers=h, json={"product_id": "pgs-9955", "quantity": 1})
print(json.dumps({"email": email, "order_id": o.get("order_id"), "expires_at": o.get("expires_at"), "dest": r0}))
