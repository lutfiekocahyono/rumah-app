# Snapshot / compare / restore admin pricing + demo customer_type + home sections (for safe testing)
import os, sys, json, requests
API = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"
SNAP = "/tmp/iter22_pricing_snapshot.json"


def login(e, p):
    return {"Authorization": "Bearer " + requests.post(f"{API}/auth/login", json={"email": e, "password": p}).json()["token"]}


A = login("admin@pgs.id", "Admin1234!")
D = login("demo@pgs.id", "Demo1234!")
me = requests.get(f"{API}/auth/me", headers=D).json()
pricing = requests.get(f"{API}/admin/pricing", headers=A).json()
cmd = sys.argv[1]
if cmd == "save":
    json.dump({"pricing": pricing, "demo_type": me["customer_type"]}, open(SNAP, "w"))
    print("saved", pricing, me["customer_type"])
elif cmd == "show":
    print(json.dumps(pricing), me["customer_type"])
elif cmd == "compare":
    s = json.load(open(SNAP))
    keys = ("type_discounts", "type_discount_modes", "qty_tiers")
    print("EQUAL" if all(s["pricing"].get(k) == pricing.get(k) for k in keys) else "DIFF", json.dumps(pricing), me["customer_type"])
elif cmd == "restore":
    s = json.load(open(SNAP))
    r = requests.put(f"{API}/admin/pricing", headers=A, json={k: s["pricing"][k] for k in ("type_discounts", "type_discount_modes", "qty_tiers")})
    requests.put(f"{API}/admin/customers/{me['user_id']}", headers=A, json={"customer_type": s["demo_type"]})
    print("restored", r.status_code, requests.get(f"{API}/admin/pricing", headers=A).json())
