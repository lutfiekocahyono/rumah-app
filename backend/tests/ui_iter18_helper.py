# Iter18 UI helper: `setup` -> demo cart has pgs-9955 x1 + TEST voucher (rupiah 1000) ; `cleanup CODE [ORDER]` removes voucher, cancels order.
import os, sys, json, uuid, requests
API = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"
login = lambda e, p: requests.post(f"{API}/auth/login", json={"email": e, "password": p}).json()["token"]
t = login("demo@pgs.id", "Demo1234!")
a = login("admin@pgs.id", "Admin1234!")
h = {"Authorization": f"Bearer {t}", "X-Store-Id": "pgs-official"}
ha = {"Authorization": f"Bearer {a}"}
if sys.argv[1] == "state":
    print(json.dumps({"cart": [(g["product_id"], g["quantity"], g["store_id"]) for g in requests.get(f"{API}/cart", headers=h).json()["items"]],
                      "wallet": requests.get(f"{API}/wallet", headers=h).json() if requests.get(f"{API}/wallet", headers=h).ok else None,
                      "pay": requests.get(f"{API}/payments/methods").json()}))
elif sys.argv[1] == "setup":
    code = f"TSTUI{uuid.uuid4().hex[:4].upper()}"
    v = requests.post(f"{API}/admin/vouchers", headers=ha, json={"code": code, "title": "TEST UI iter18", "mode": "rupiah", "value": 1000, "quota": 5, "show_on_home": False})
    c = requests.post(f"{API}/cart/items", headers=h, json={"product_id": "pgs-9955", "quantity": 1})
    print(json.dumps({"voucher": code, "v": v.status_code, "cart": c.status_code}))
elif sys.argv[1] == "cleanup":
    print(requests.delete(f"{API}/admin/vouchers/{sys.argv[2]}", headers=ha).status_code)
    if len(sys.argv) > 3:
        print(requests.put(f"{API}/admin/orders/{sys.argv[3]}/status", headers=ha, json={"status": "cancelled"}).status_code)
