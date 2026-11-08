# Iter14 UI helper: create TEST buyers with saved default address that carries a RajaOngkir area (destination_id/label)
import os, sys, json, uuid, requests
API = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"
def buyer(q, city):
    email = f"test_ui14_{uuid.uuid4().hex[:6]}@example.com"
    t = requests.post(f"{API}/auth/register", json={"email": email, "password": "TestPass123!", "name": "TEST UI14"}).json()["token"]
    h = {"Authorization": f"Bearer {t}"}
    d = requests.get(f"{API}/shipping/destinations", params={"q": q}, headers=h).json()
    rows = d.get("data", d) if isinstance(d, dict) else d
    r0 = rows[0]
    a = requests.post(f"{API}/me/addresses", headers=h, json={"label": "Rumah", "recipient": "TEST UI14", "phone": "081234567890",
        "address": "Jl. Test No 1", "city": city, "destination_id": r0["id"], "destination_label": r0["label"], "is_default": True})
    return {"email": email, "token": t, "dest": r0, "addr": a.status_code}
print(json.dumps({"gubeng": buyer("gubeng", "Surabaya"), "patrang": buyer("patrang", "Jember")}))
