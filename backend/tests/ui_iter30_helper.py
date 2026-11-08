# Helper for iter30 UI tests (per-product wholesale): `create` publishes TEST products (with/without tiers), `clean` deletes them.
import json
import sys

sys.path.insert(0, "/app/backend/tests")
from test_pgs_iter30_product_wholesale import API, CRED, DB, TIERS, form, requests  # noqa: E402

STATE = "/tmp/ui_iter30.json"
cmd = sys.argv[1]
t = {k: requests.post(f"{API}/auth/login", json={"email": e, "password": p}).json()["token"] for k, (e, p) in CRED.items()}
if cmd == "create":
    h = {"Authorization": f"Bearer {t['seller']}"}
    out = {"tok": t}
    for key, kw in (("tiered", {"tier_prices": TIERS}), ("plain", {})):
        r = requests.post(f"{API}/product-editor/publish", headers=h, json={"data": form(name=f"TEST_Grosir UI {key}", **kw)})
        out[key] = r.json()["product_id"]
    json.dump(out, open(STATE, "w"))
    print(json.dumps(out))
elif cmd == "clean":
    s = json.load(open(STATE))
    ids = [s["tiered"], s["plain"]] + s.get("extra", [])
    for pid in ids:
        DB.products.delete_one({"product_id": pid, "name": {"$regex": "^TEST_"}})
        DB.price_history.delete_many({"product_id": pid})
    print("cleaned", ids)
