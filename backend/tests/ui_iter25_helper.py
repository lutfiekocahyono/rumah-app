# Iter25 UI helper: create (or delete) a TEST_ draft with variants for the SEO / preview UI checks.
import json
import os
import sys

import requests

API = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"
IMG = "https://pusatgrosirsidoarjo.com/wp-content/uploads/2023/07/Cetakan-7-Lubang-Cekung-Suggo-300x300.webp"
t = requests.post(f"{API}/auth/login", json={"email": "sidoarjo@pgs.id", "password": "Sidoarjo123!"}).json()["token"]
H = {"Authorization": f"Bearer {t}"}
if sys.argv[1] == "create":
    data = {"name": "TEST_Cetakan Kue Suggo Tujuh Lubang", "category": "dapur", "subcategory": "peralatan-masak",
            "brand": "Suggo", "showcase": "TEST Etalase", "status": "active",
            "description": "Cetakan kue **anti lengket** dengan tujuh lubang cekung, cocok untuk kue lumpur, kue cubit, dan aneka jajanan pasar. Bahan tebal dan awet.",
            "images": [IMG], "price": 20000, "stock": 10, "weight_grams": 700, "specs": {"material": "Aluminium"},
            "variants_enabled": True, "variant_options": [{"name": "Warna", "values": ["Merah", "Biru"]}],
            "variants": [{"values": ["Merah"], "price": 15000, "stock": 5, "active": True},
                         {"values": ["Biru"], "price": 25000, "stock": 7, "active": True}]}
    r = requests.post(f"{API}/product-editor/drafts", headers=H, json={"data": data})
    print(json.dumps({"draft_id": r.json()["draft_id"], "token": t}))
elif sys.argv[1] == "delete":
    print(requests.delete(f"{API}/product-editor/drafts/{sys.argv[2]}", headers=H).json())
