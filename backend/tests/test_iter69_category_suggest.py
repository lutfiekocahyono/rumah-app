# Iter69: auto category suggestion for new products in the product editor
import os
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("EXPO_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
URL = f"{API}/product-editor/category-suggest"
CREATED = []


def login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=20)
    if r.status_code != 200:
        pytest.skip(f"login failed {email}: {r.status_code}")
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def admin():
    return login("admin@pgs.id", "Admin1234!")


@pytest.fixture(scope="module")
def jombang():
    return login("jombang@pgs.id", "Jombang123!")


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    env = dict(l.strip().split("=", 1) for l in open("/app/backend/.env") if "=" in l)
    db = MongoClient(env["MONGO_URL"].strip('"'))[env["DB_NAME"].strip('"')]
    for pid in CREATED:
        db.products.delete_one({"product_id": pid})


# --- auth
def test_requires_auth():
    r = requests.get(URL, params={"name": "Panci Stainless 24cm"}, timeout=20)
    assert r.status_code == 401


def test_customer_forbidden():
    h = login("demo@pgs.id", "Demo1234!")
    r = requests.get(URL, params={"name": "Panci Stainless 24cm"}, headers=h, timeout=20)
    assert r.status_code == 403


# --- suggestions
@pytest.mark.parametrize("who", ["admin", "jombang"])
def test_panci(who, request):
    h = request.getfixturevalue(who)
    r = requests.get(URL, params={"name": "Panci Stainless 24cm"}, headers=h, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    print(d)
    assert d["category"] == "dapur" and d["subcategory"] == "peralatan-masak"
    assert d["confidence"] == "tinggi" and "panci" in d["reason"].lower()


def test_rice_cooker(admin):
    d = requests.get(URL, params={"name": "Rice Cooker Miyako"}, headers=admin, timeout=30).json()
    print(d)
    assert d["category"] == "audio-elektronik" and d["subcategory"] == "elektronik-rumah-tangga"


def test_unknown(admin):
    d = requests.get(URL, params={"name": "Xyzqw Blorpt"}, headers=admin, timeout=30).json()
    print(d)
    assert d["category"] == "" and d["subcategory"] == ""


def test_short_name(admin):
    d = requests.get(URL, params={"name": "ab"}, headers=admin, timeout=30).json()
    assert d["category"] == "" and d["reason"] == ""


def test_empty_name(admin):
    r = requests.get(URL, headers=admin, timeout=30)
    assert r.status_code == 200 and r.json()["category"] == ""


@pytest.mark.parametrize("name", ["Kursi Plastik Napolly", "Piring Melamin", "Kipas Angin Cosmos", "Selimut Rosanna", "Kaos Polos Katun"])
def test_various(admin, name):
    d = requests.get(URL, params={"name": name}, headers=admin, timeout=30).json()
    print(name, d)
    assert d["category"], d
    # a main category returned by itself must have no parent
    cats = {c["category_id"] for c in requests.get(f"{API}/categories", timeout=20).json()}
    assert d["category"] in cats


# --- publish a new product with the suggested category
def test_publish_with_suggested_category(jombang, admin):
    lst = requests.get(f"{API}/product-editor/products", headers=admin, params={"limit": 5}, timeout=30)
    assert lst.status_code == 200, lst.text
    body = lst.json()
    items = body.get("items") if isinstance(body, dict) else body
    if not items:
        pytest.skip("no product to copy form from")
    src = requests.get(f"{API}/product-editor/products/{items[0]['product_id']}", headers=admin, timeout=30).json()
    s = requests.get(URL, params={"name": "TEST_Panci Stainless 24cm"}, headers=jombang, timeout=30).json()
    data = {**src["data"], "name": "TEST_Panci Stainless 24cm", "category": s["category"], "subcategory": s["subcategory"], "sku": "", "barcode": "", "weight_grams": src["data"].get("weight_grams") or 1000}
    for v in data.get("variants") or []:
        v["variant_id"], v["sku"] = "", ""
    r = requests.post(f"{API}/product-editor/publish", json={"data": data}, headers=jombang, timeout=30)
    assert r.status_code == 200, r.text
    pid = r.json()["product_id"]
    CREATED.append(pid)
    g = requests.get(f"{API}/product-editor/products/{pid}", headers=jombang, timeout=30).json()
    assert g["data"]["category"] == "dapur" and g["data"]["subcategory"] == "peralatan-masak"
