"""Per-product wholesale pricing: rupiah per quantity tier and customer category (no global discounts).

product.tier_prices = {"langsung": [{min_qty, price}], "pengecer": [...], "reseller": [...]}
- "Pembeli Langsung" without a qty-1 row pays the product's normal selling price for small quantities.
- Pengecer / Reseller without their own rows use the Pembeli Langsung table."""
CUSTOMER_TYPES = ("langsung", "pengecer", "reseller")
CUSTOMER_TYPE_LABELS = {"langsung": "Pembeli Langsung", "pengecer": "Pengecer", "reseller": "Reseller"}
MAX_TIERS = 10

# One-time migration of the former global settings (owner's values): category discount % and qty tiers %
LEGACY_GLOBAL = {"type_discounts": {"langsung": 0, "pengecer": 3, "reseller": 5}, "qty_tiers": [(6, 2), (12, 4)]}


def _pct(value: float, pct: float) -> int:
    return int(round(value * (100 - float(pct or 0)) / 100))


def clean_tiers(raw: dict) -> dict:
    """Valid rows only (qty >= 1, price > 0), one per qty, ascending; empty types dropped."""
    out = {}
    for t in CUSTOMER_TYPES:
        rows = {}
        for r in (raw or {}).get(t) or []:
            q, p = int(r.get("min_qty") or 0), int(r.get("price") or 0)
            if q >= 1 and p > 0:
                rows[q] = p
        if rows:
            out[t] = [{"min_qty": q, "price": rows[q]} for q in sorted(rows)][:MAX_TIERS]
    return out


def legacy_tiers(product: dict) -> dict:
    """The tiers the old global settings produced for this product, written as rupiah per product."""
    price, out = int(product.get("price", 0)), {}
    manual = clean_tiers(product.get("tier_prices") or {})
    for t in CUSTOMER_TYPES:
        base = _pct(price, LEGACY_GLOBAL["type_discounts"][t])
        if manual.get(t):  # the product already had its own table: keep it, make the qty-1 price explicit
            rows = {r["min_qty"]: r["price"] for r in manual[t]}
            if t != "langsung":
                rows.setdefault(1, base)
        else:
            rows = {q: _pct(base, pct) for q, pct in LEGACY_GLOBAL["qty_tiers"]}
            if t != "langsung":
                rows[1] = base
        out[t] = [{"min_qty": q, "price": rows[q]} for q in sorted(rows)]
    return out


def scale_tiers(tiers: dict, old: int, new: int) -> dict:
    """Selling price changed old -> new: move every tier price by the same ratio (min Rp100)."""
    if not old or old == new:
        return tiers
    return {t: [{**r, "price": max(100, int(round(r["price"] * new / old)))} for r in rows] for t, rows in (tiers or {}).items()}


def price_tiers(product: dict, ctype: str) -> list[dict]:
    """Unit price table [{min_qty, price}] for this customer category, ascending."""
    ctype = ctype if ctype in CUSTOMER_TYPES else "langsung"
    tiers = product.get("tier_prices") or {}
    rows: dict[int, int] = {1: int(product.get("price", 0))}
    for t in (tiers.get(ctype) or tiers.get("langsung") or []):
        q, p = int(t.get("min_qty") or 0), int(t.get("price") or 0)
        if q >= 1 and p > 0:
            rows[q] = p
    return [{"min_qty": q, "price": rows[q]} for q in sorted(rows)]


def unit_price(product: dict, ctype: str, qty: int) -> int:
    best = None
    for row in price_tiers(product, ctype):
        if qty >= row["min_qty"]:
            best = row["price"]
    return best if best is not None else int(product.get("price", 0))


def price_matrix(product: dict) -> list[dict]:
    """Rows [{min_qty, langsung, pengecer, reseller}] covering every tier break of every customer type."""
    qtys = sorted({t["min_qty"] for c in CUSTOMER_TYPES for t in price_tiers(product, c)})
    return [{"min_qty": q, **{c: unit_price(product, c, q) for c in CUSTOMER_TYPES}} for q in qtys]


async def migrate_global(db) -> None:
    """Copy the former global discounts into every catalogue product once, then drop the global settings."""
    if await db.settings.find_one({"key": "pricing_per_product"}):
        return
    from pymongo import UpdateOne
    ops = []
    async for p in db.products.find({"store_id": "pgs-official", "variants": {"$in": [[], None]}},
                                    {"_id": 1, "price": 1, "tier_prices": 1}):
        ops.append(UpdateOne({"_id": p["_id"]}, {"$set": {"tier_prices": legacy_tiers(p)}}))
        if len(ops) >= 1000:
            await db.products.bulk_write(ops)
            ops = []
    if ops:
        await db.products.bulk_write(ops)
    await db.settings.delete_one({"key": "pricing"})
    await db.settings.insert_one({"key": "pricing_per_product", "migrated": True})
