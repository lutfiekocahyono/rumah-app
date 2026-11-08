"""Homepage promo helpers: flash sale prices, vouchers, home settings."""
from datetime import datetime, timedelta, timezone
from typing import Optional

DEFAULT_HOME = {
    "key": "home",
    "free_shipping": {
        "enabled": True,
        "title": "Gratis Ongkir",
        "subtitle": "Area {kota} & sekitarnya, min. belanja Rp500.000",  # {kota} = city of the buyer's chosen branch
        "min_purchase": 500000,
    },
    "recommend_mode": "personal",  # personal | random
}


def aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def now() -> datetime:
    return datetime.now(timezone.utc)


async def get_home(db) -> dict:
    doc = await db.settings.find_one({"key": "home"}, {"_id": 0}) or {}
    fs = {**DEFAULT_HOME["free_shipping"], **(doc.get("free_shipping") or {})}
    fs["subtitle"] = fs["subtitle"].replace("Area Sidoarjo", "Area {kota}")  # older saved text named one branch only
    return {**DEFAULT_HOME, **doc, "free_shipping": fs}


async def active_flash(db) -> Optional[dict]:
    """{title, ends_at, prices: {product_id: flash_price}} when a flash sale is running."""
    doc = await db.settings.find_one({"key": "flash_sale"}, {"_id": 0})
    if not doc or not doc.get("active") or not doc.get("items"):
        return None
    ends = aware(doc.get("ends_at"))
    if not ends or ends <= now():
        return None
    return {"title": doc.get("title") or "Flash Sale", "ends_at": ends,
            "prices": {i["product_id"]: int(i["flash_price"]) for i in doc["items"]}}


def voucher_check(v: Optional[dict], subtotal: int) -> tuple[int, Optional[str]]:
    """Return (discount, error). Discount never exceeds subtotal."""
    if not v or not v.get("active"):
        return 0, "Voucher tidak ditemukan atau tidak aktif"
    ends = aware(v.get("ends_at"))
    if ends and ends <= now():
        return 0, "Voucher sudah berakhir"
    if v.get("quota") and v.get("used", 0) >= v["quota"]:
        return 0, "Kuota voucher sudah habis"
    if subtotal < int(v.get("min_purchase") or 0):
        return 0, f"Minimal belanja Rp{int(v['min_purchase']):,}".replace(",", ".")
    if v.get("mode") == "rupiah":
        disc = int(v.get("value") or 0)
    else:
        disc = int(round(subtotal * float(v.get("value") or 0) / 100))
        if v.get("max_discount"):
            disc = min(disc, int(v["max_discount"]))
    return max(0, min(disc, subtotal)), None


def sample_flash(product_ids: list[str], prices: dict[str, int]) -> dict:
    return {
        "key": "flash_sale", "title": "Flash Sale", "active": True,
        "ends_at": now() + timedelta(days=2),
        "items": [{"product_id": pid, "flash_price": int(round(prices[pid] * 0.95 / 100) * 100)} for pid in product_ids],
    }


SAMPLE_VOUCHERS = [
    {"code": "PGSHEMAT", "title": "Diskon 5% Belanja Grosir", "description": "Maks. potongan Rp25.000",
     "mode": "percent", "value": 5, "max_discount": 25000, "min_purchase": 200000, "quota": 0,
     "used": 0, "active": True, "show_on_home": True, "ends_at": None},
    {"code": "PGS10RB", "title": "Potongan Rp10.000", "description": "Untuk semua produk",
     "mode": "rupiah", "value": 10000, "max_discount": 0, "min_purchase": 150000, "quota": 100,
     "used": 0, "active": True, "show_on_home": True, "ends_at": None},
]

SAMPLE_BANNERS = [
    {"title": "Pusat Grosir Sidoarjo", "subtitle": "Tersedia Partai, Koli, Grosir, dan Ecer",
     "image": "https://images.unsplash.com/photo-1724582586529-62622e50c0b3?w=1200", "link_type": "none", "link_value": ""},
    {"title": "Rumah Tangga & Furniture", "subtitle": "Makin banyak beli, makin hemat",
     "image": "https://images.unsplash.com/photo-1586023492125-27b2c045efd7?w=1200", "link_type": "search", "link_value": "rak"},
    {"title": "Audio & Elektronik", "subtitle": "Kirim ke seluruh Indonesia",
     "image": "https://images.unsplash.com/photo-1740803292822-a742c6a4fef0?w=1200", "link_type": "search", "link_value": "speaker"},
]
