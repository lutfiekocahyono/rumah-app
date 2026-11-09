# Check float rounding of pct formula vs exact Decimal math over real Sidoarjo prices
import os, math
from decimal import Decimal, ROUND_CEILING
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv('/app/backend/.env')
db = MongoClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]
prices = set()
for p in db.products.find({"store_id": "pgs-official", "variants.0": {"$exists": False}}, {"price": 1, "original_price": 1, "tier_prices": 1}):
    prices.add(p.get("price", 0)); prices.add(p.get("original_price") or 0)
    for rows in (p.get("tier_prices") or {}).values():
        for t in rows: prices.add(t["price"])
prices.discard(0)
print("distinct prices", len(prices))
for pct in (1, 2, 3, 5, 7, 10, 0.5, 2.5, 15, 20, -10):
    bad = []
    for v in prices:
        f = max(100, math.ceil(v * (1 + pct / 100) / 100) * 100)
        e = max(100, int((Decimal(v) * (1 + Decimal(str(pct)) / 100) / 100).to_integral_value(ROUND_CEILING)) * 100)
        if f != e: bad.append((v, f, e))
    print(f"pct={pct}: mismatches={len(bad)} sample={sorted(bad)[:4]}")
