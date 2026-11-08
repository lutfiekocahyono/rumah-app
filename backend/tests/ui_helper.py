# Helper for UI tests: setup (pricing + reseller + COD order) and reset
import os, sys, requests
API = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"


def login(e, p):
    return {"Authorization": "Bearer " + requests.post(f"{API}/auth/login", json={"email": e, "password": p}).json()["token"]}


A = login("admin@pgs.id", "Admin1234!")
D = login("demo@pgs.id", "Demo1234!")
uid = requests.get(f"{API}/auth/me", headers=D).json()["user_id"]
cmd = sys.argv[1]
if cmd == "order":
    p = [x for x in requests.get(f"{API}/products").json() if x["in_stock"] and x["stock"] > 20][0]
    requests.delete(f"{API}/cart", headers=D)
    requests.post(f"{API}/cart/items", headers=D, json={"product_id": p["product_id"], "quantity": 1})
    o = requests.post(f"{API}/checkout", headers=D, json={"full_name": "TEST_UIBuyer", "phone": "081234567890", "address": "Jl. Test 1", "city": "Sidoarjo", "payment_method": "cod"}).json()
    print(o["order_id"])
elif cmd == "pricing":
    requests.put(f"{API}/admin/pricing", headers=A, json={"type_discounts": {"langsung": 0, "pengecer": 3, "reseller": 5},
                 "qty_tiers": [{"min_qty": 6, "discount_percent": 2}, {"min_qty": 12, "discount_percent": 4}]})
    requests.put(f"{API}/admin/customers/{uid}", headers=A, json={"customer_type": "reseller"})
    p = [x for x in requests.get(f"{API}/products").json() if x["in_stock"] and x["stock"] > 20][0]
    print(p["product_id"], p["price"])
elif cmd == "reset":
    requests.put(f"{API}/admin/pricing", headers=A, json={"type_discounts": {"langsung": 0, "pengecer": 0, "reseller": 0}, "qty_tiers": []})
    requests.put(f"{API}/admin/customers/{uid}", headers=A, json={"customer_type": "langsung"})
    for pid in sys.argv[2:]:
        requests.put(f"{API}/admin/products/{pid}/tiers", headers=A, json={"tier_prices": {"langsung": [], "pengecer": [], "reseller": []}})
    requests.delete(f"{API}/cart", headers=D)
    print(requests.get(f"{API}/admin/pricing", headers=A).json(), requests.get(f"{API}/auth/me", headers=D).json()["customer_type"])
elif cmd == "cancel":
    for oid in sys.argv[2:]:
        print(requests.put(f"{API}/admin/orders/{oid}/status", headers=A, json={"status": "cancelled"}).json()["status"])
