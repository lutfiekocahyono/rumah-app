# Helper for iteration-3 promo UI tests: setup guest cart + TEST voucher, cleanup
import os, sys, uuid, requests
API = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"
A = {"Authorization": "Bearer " + requests.post(f"{API}/auth/login", json={"email": "admin@pgs.id", "password": "Admin1234!"}).json()["token"]}
cmd = sys.argv[1]
if cmd == "setup":  # setup <claim:0|1>
    g = {"X-Guest-Id": f"TEST_guest_{uuid.uuid4().hex[:8]}"}
    p = [x for x in requests.get(f"{API}/products", params={"limit": 60}).json() if x["in_stock"] and x["stock"] > 20 and 20000 < x["price"] < 200000][0]
    requests.post(f"{API}/cart/items", headers=g, json={"product_id": p["product_id"], "quantity": 3})
    code = "TESTUI" + uuid.uuid4().hex[:4].upper()
    requests.post(f"{API}/admin/vouchers", headers=A, json={"code": code, "title": "TEST_UI Voucher", "mode": "rupiah", "value": 7000, "min_purchase": 1000, "show_on_home": False})
    if sys.argv[2] == "1":
        requests.post(f"{API}/vouchers/{code}/claim", headers=g)
    print(g["X-Guest-Id"], code, requests.get(f"{API}/cart", headers=g).json()["subtotal"])
elif cmd == "voucher":
    v = [v for v in requests.get(f"{API}/admin/vouchers", headers=A).json() if v["code"] == sys.argv[2]]
    print(v)
elif cmd == "delvoucher":
    for c in sys.argv[2:]:
        print(c, requests.delete(f"{API}/admin/vouchers/{c}", headers=A).status_code)
