# Iter16 UI helper: set/restore pgs-official pickup address+hours via sidoarjo@pgs.id. Usage: set | restore '<json-orig>'
import os, sys, json, requests
API = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"
t = requests.post(f"{API}/auth/login", json={"email": "sidoarjo@pgs.id", "password": "Sidoarjo123!"}).json()["token"]
h = {"Authorization": f"Bearer {t}"}
cur = requests.get(f"{API}/me/store", headers=h).json()
base = {k: cur.get(k) or "" for k in ("name", "description", "city", "phone", "logo", "address", "pickup_hours")}
if sys.argv[1] == "set":
    print("ORIG", json.dumps(base))
    r = requests.put(f"{API}/me/store", headers=h, json={**base, "address": "TEST_Jl. Raya Sidoarjo No. 10", "pickup_hours": "TEST_Senin-Sabtu 08.00-16.00"})
    print(r.status_code, r.json().get("address"), r.json().get("pickup_hours"))
else:
    orig = json.loads(sys.argv[2])
    r = requests.put(f"{API}/me/store", headers=h, json=orig)
    print(r.status_code, {k: r.json().get(k) for k in ("phone", "address", "pickup_hours")})
