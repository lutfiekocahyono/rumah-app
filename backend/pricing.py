"""Tiered pricing: customer category discount + quantity tiers (global or per-product manual)."""
from typing import Any

CUSTOMER_TYPES = ("langsung", "pengecer", "reseller")
CUSTOMER_TYPE_LABELS = {"langsung": "Pembeli Langsung", "pengecer": "Pengecer", "reseller": "Reseller"}

DEFAULT_PRICING: dict[str, Any] = {
    "key": "pricing",
    # % discount from the website (eceran) price per customer category
    "type_discounts": {"langsung": 0, "pengecer": 0, "reseller": 0},
    # global quantity tiers: buy >= min_qty -> extra % off
    "qty_tiers": [],
}


async def get_pricing(db) -> dict:
    doc = await db.settings.find_one({"key": "pricing"}, {"_id": 0})
    if not doc:
        return {**DEFAULT_PRICING}
    return {**DEFAULT_PRICING, **doc}


def _pct(value: float, pct: float) -> int:
    return int(round(value * (100 - float(pct or 0)) / 100))


def price_tiers(product: dict, ctype: str, pricing: dict) -> list[dict]:
    """Unit price table [{min_qty, price}] for this customer category, ascending."""
    ctype = ctype if ctype in CUSTOMER_TYPES else "langsung"
    base = _pct(product.get("price", 0), pricing.get("type_discounts", {}).get(ctype, 0))
    rows: dict[int, int] = {1: base}
    manual = (product.get("tier_prices") or {}).get(ctype) or []
    if manual:
        for t in manual:
            q = int(t.get("min_qty") or 0)
            if q >= 1 and int(t.get("price") or 0) > 0:
                rows[q] = int(t["price"])
    else:
        for t in pricing.get("qty_tiers", []) or []:
            q = int(t.get("min_qty") or 0)
            if q > 1:
                rows[q] = _pct(base, t.get("discount_percent", 0))
    return [{"min_qty": q, "price": rows[q]} for q in sorted(rows)]


def unit_price(product: dict, ctype: str, qty: int, pricing: dict) -> int:
    best = None
    for row in price_tiers(product, ctype, pricing):
        if qty >= row["min_qty"]:
            best = row["price"]
    return best if best is not None else int(product.get("price", 0))


def price_matrix(product: dict, pricing: dict) -> list[dict]:
    """Rows [{min_qty, langsung, pengecer, reseller}] covering every tier break of every customer type."""
    qtys = sorted({t["min_qty"] for c in CUSTOMER_TYPES for t in price_tiers(product, c, pricing)})
    return [{"min_qty": q, **{c: unit_price(product, c, q, pricing) for c in CUSTOMER_TYPES}} for q in qtys]
