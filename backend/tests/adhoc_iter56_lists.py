# Ad-hoc: does Jombang upcoming schedule also hide flash in product list / wishlist / home recs?
import sys
from datetime import timedelta
sys.path.insert(0, "/app/backend/tests")
import requests
from test_iter56_flash_schedules import API, H, put, iso, now

pid = requests.get(f"{API}/flash-sale", headers=H(store="pgs-official"), timeout=30).json()["items"][0]["product_id"]
r = put("admin", "pgs-jombang", {"follow": False, "starts_at": iso(now() + timedelta(hours=3)), "ends_at": iso(now() + timedelta(hours=6))})
print("put", r.status_code, r.json()["status"])
try:
    for path in ("/products?limit=200", "/recommendations", "/products/recommended"):
        rr = requests.get(f"{API}{path}", headers=H("demo", "pgs-jombang"), timeout=30)
        if rr.status_code != 200:
            print(path, rr.status_code); continue
        d = rr.json(); items = d if isinstance(d, list) else d.get("items", d.get("products", []))
        flashy = [i["product_id"] for i in items if i.get("flash_price")]
        print(path, "items", len(items), "with flash_price in Jombang:", flashy[:5])
    h = H("demo", "pgs-jombang")
    w = requests.get(f"{API}/wishlist", headers=h, timeout=30).json()
    had = any(i["product_id"] == pid for i in w.get("items", []))
    if not had:
        print("wishlist add", requests.post(f"{API}/wishlist/{pid}", headers=h, timeout=30).status_code)
    w = requests.get(f"{API}/wishlist", headers=h, timeout=30).json()
    it = next((i for i in w.get("items", []) if i["product_id"] == pid), None)
    print("wishlist item flash_price for Jombang buyer:", it and it.get("flash_price"), "my_price", it and it.get("my_price"))
    if not had:
        print("wishlist remove", requests.delete(f"{API}/wishlist/{pid}", headers=h, timeout=30).status_code)
    # invalid store id
    print("admin PUT unknown store:", put("admin", "pgs-xyz", {"follow": True}).status_code)
finally:
    print("restore", put("admin", "pgs-jombang", {"follow": True}).json()["follows_sidoarjo"])
