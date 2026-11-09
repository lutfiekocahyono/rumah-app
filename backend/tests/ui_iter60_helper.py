# Iteration 60 UI helper: create/delete Jombang-only TEST products for shop search UI. usage: python ui_iter60_helper.py create|delete
import json
import sys
import requests
from test_iter60_suggest_shop_search import API, J

F = "/tmp/iter60_ids.json"
if sys.argv[1] == "create":
    ids = []
    base = {"description": "TEST produk khusus Jombang", "price": 15000, "images": ["https://example.com/a.jpg"]}
    for name, cat, stock in (("Kesxtest Kesehatan Habis", "kesehatan", 0), ("Kesxtest Kesehatan Ada", "kesehatan", 7),
                             ("TEST_Dapur Panci Jombang", "dapur", 3)):
        r = requests.post(f"{API}/seller/products", headers=J(), json={**base, "name": name, "category": cat, "stock": stock}, timeout=30)
        r.raise_for_status()
        ids.append(r.json()["product_id"])
    json.dump(ids, open(F, "w"))
    print(ids)
else:
    for pid in json.load(open(F)):
        print(pid, requests.delete(f"{API}/seller/products/{pid}", headers=J(), timeout=30).status_code)
