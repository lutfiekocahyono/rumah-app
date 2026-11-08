import asyncio
import os
import logging
import uuid
import secrets
import re
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

import bcrypt
import jwt
from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
import httpx
import notify
import payments
import account
import marketing
import order_tasks
from order_tasks import COD_PICKUP_HOURS, RELEASE_STATUSES
import promo
import seller
import shipping
import support
import branches
import storage
from pricing import CUSTOMER_TYPES, DEFAULT_PRICING, get_pricing, price_matrix, price_tiers, unit_price
from pymongo import ReturnDocument
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr, Field
from pymongo import ASCENDING, DESCENDING, IndexModel
from starlette.middleware.cors import CORSMiddleware


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

JWT_SECRET = os.environ.get("JWT_SECRET", "pusat-grosir-sidoarjo-secret-change-me")
JWT_ALG = "HS256"
JWT_TTL_DAYS = 7

INDEXES: dict[str, list[IndexModel]] = {
    "users": [
        IndexModel([("email", ASCENDING)], name="email", unique=True),
        IndexModel([("user_id", ASCENDING)], name="user_id", unique=True),
    ],
    "products": [
        IndexModel([("product_id", ASCENDING)], name="product_id", unique=True),
        IndexModel([("category", ASCENDING)], name="category"),
        IndexModel([("categories", ASCENDING)], name="categories"),
        IndexModel([("name", ASCENDING)], name="name"),
        IndexModel([("in_stock", DESCENDING), ("created_at", DESCENDING), ("product_id", DESCENDING)], name="newest"),
        IndexModel([("price", ASCENDING)], name="price"),
        IndexModel([("store_id", ASCENDING), ("created_at", DESCENDING)], name="store"),
    ],
    "categories": [
        IndexModel([("category_id", ASCENDING)], name="category_id", unique=True),
        IndexModel([("parent", ASCENDING), ("count", DESCENDING)], name="parent_count"),
    ],
    "settings": [
        IndexModel([("key", ASCENDING)], name="key", unique=True),
    ],
    **support.INDEXES,
    "carts": [
        IndexModel([("owner", ASCENDING)], name="owner", unique=True),
    ],
    "wishlists": [
        IndexModel([("owner", ASCENDING)], name="owner", unique=True),
    ],
    "orders": [
        IndexModel([("order_id", ASCENDING)], name="order_id", unique=True),
        IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)], name="user_orders"),
        IndexModel([("owner", ASCENDING), ("created_at", DESCENDING)], name="owner_orders"),
    ],
    "banners": [IndexModel([("banner_id", ASCENDING)], name="banner_id", unique=True)],
    "vouchers": [IndexModel([("code", ASCENDING)], name="code", unique=True)],
    "voucher_claims": [IndexModel([("owner", ASCENDING)], name="owner", unique=True)],
    "activity": [IndexModel([("owner", ASCENDING)], name="owner", unique=True)],
    "uploads": [IndexModel([("storage_path", ASCENDING)], name="storage_path", unique=True)],
    "one_time_codes": [IndexModel([("expires_at", ASCENDING)], name="ttl", expireAfterSeconds=0),
                       IndexModel([("user_id", ASCENDING), ("purpose", ASCENDING)], name="user_purpose")],
    "store_stock": [IndexModel([("store_id", ASCENDING), ("product_id", ASCENDING)], name="store_product", unique=True)],
    "rate_limits": [IndexModel([("expires_at", ASCENDING)], name="ttl", expireAfterSeconds=0)],
    "addresses": [IndexModel([("user_id", ASCENDING), ("address_id", ASCENDING)], name="user_addr", unique=True)],
    "activity_logs": [IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)], name="user_time")],
    "notifications": [IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)], name="user_time")],
    "stores": [IndexModel([("store_id", ASCENDING)], name="store_id", unique=True),
               IndexModel([("owner_id", ASCENDING)], name="owner_id", unique=True),
               IndexModel([("status", ASCENDING)], name="status")],
}


async def ensure_indexes() -> None:
    for coll, models in INDEXES.items():
        for model in models:
            try:
                await db[coll].create_indexes([model])
            except Exception as exc:
                logging.getLogger(__name__).error("index(%s.%s): %s", coll, model.document["name"], exc)


SEED_CATEGORIES = [
    {"category_id": "furniture", "name": "Furniture", "icon": "bed-outline", "image": "https://images.unsplash.com/photo-1583847268964-b28dc8f51f92?w=400"},
    {"category_id": "dapur", "name": "Dapur", "icon": "restaurant-outline", "image": "https://images.unsplash.com/photo-1631008789162-950869f41805?w=400"},
    {"category_id": "elektronik", "name": "Elektronik", "icon": "tv-outline", "image": "https://images.unsplash.com/photo-1740803292822-a742c6a4fef0?w=400"},
    {"category_id": "home-living", "name": "Home Living", "icon": "home-outline", "image": "https://images.unsplash.com/photo-1586023492125-27b2c045efd7?w=400"},
    {"category_id": "fashion", "name": "Fashion", "icon": "shirt-outline", "image": "https://images.unsplash.com/photo-1445205170230-053b83016050?w=400"},
    {"category_id": "kecantikan", "name": "Kecantikan", "icon": "sparkles-outline", "image": "https://images.unsplash.com/photo-1522337360788-8b13dee7a37e?w=400"},
    {"category_id": "olahraga", "name": "Olahraga", "icon": "barbell-outline", "image": "https://images.unsplash.com/photo-1517836357463-d25dfeac3438?w=400"},
    {"category_id": "grosir", "name": "Grosir", "icon": "cube-outline", "image": "https://images.unsplash.com/photo-1606824722920-4c652a70f348?w=400"},
]

SEED_PRODUCTS = [
    {"product_id": "p-sofa-01", "name": "Sofa Minimalis 3 Seater Abu-Abu", "category": "furniture", "price": 3999000, "original_price": 5499000, "discount": 27, "rating": 4.8, "sold": 128, "image": "https://images.unsplash.com/photo-1555041469-a586c61ea9bc?w=600", "images": ["https://images.unsplash.com/photo-1555041469-a586c61ea9bc?w=800", "https://images.unsplash.com/photo-1540574163026-643ea20ade25?w=800"], "description": "Sofa 3 seater dengan rangka kayu solid dan bantalan busa tebal. Cocok untuk ruang tamu modern.", "stock": 12},
    {"product_id": "p-meja-01", "name": "Meja Makan Kayu Jati 6 Kursi", "category": "furniture", "price": 5250000, "original_price": 6800000, "discount": 23, "rating": 4.9, "sold": 56, "image": "https://images.unsplash.com/photo-1617806118233-18e1de247200?w=600", "images": ["https://images.unsplash.com/photo-1617806118233-18e1de247200?w=800"], "description": "Set meja makan kayu jati asli dengan 6 kursi. Finishing natural tahan lama.", "stock": 7},
    {"product_id": "p-lemari-01", "name": "Lemari Pakaian 3 Pintu Sliding", "category": "furniture", "price": 2799000, "original_price": 3500000, "discount": 20, "rating": 4.7, "sold": 211, "image": "https://images.unsplash.com/photo-1595428774223-ef52624120d2?w=600", "images": ["https://images.unsplash.com/photo-1595428774223-ef52624120d2?w=800"], "description": "Lemari pakaian modern dengan pintu sliding dan kaca cermin.", "stock": 20},
    {"product_id": "p-kasur-01", "name": "Spring Bed 160x200 Premium", "category": "furniture", "price": 4299000, "original_price": 5999000, "discount": 28, "rating": 4.9, "sold": 340, "image": "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?w=600", "images": ["https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?w=800"], "description": "Spring bed queen size dengan pocket spring dan latex topper.", "stock": 15},
    {"product_id": "p-panci-01", "name": "Set Panci Stainless Steel 7 Pcs", "category": "dapur", "price": 599000, "original_price": 899000, "discount": 33, "rating": 4.6, "sold": 892, "image": "https://images.unsplash.com/photo-1584990347449-a2d4c2d3db8d?w=600", "images": ["https://images.unsplash.com/photo-1584990347449-a2d4c2d3db8d?w=800"], "description": "Set panci stainless steel food grade 7 pcs lengkap dengan tutup kaca.", "stock": 50},
    {"product_id": "p-blender-01", "name": "Blender 2 in 1 Multifungsi", "category": "dapur", "price": 349000, "original_price": 499000, "discount": 30, "rating": 4.7, "sold": 1245, "image": "https://images.unsplash.com/photo-1619066045029-54fa1738af2f?w=600", "images": ["https://images.unsplash.com/photo-1619066045029-54fa1738af2f?w=800"], "description": "Blender 2 in 1 dengan jug kaca dan dry mill untuk bumbu kering.", "stock": 80},
    {"product_id": "p-rice-01", "name": "Rice Cooker Digital 1.8L", "category": "dapur", "price": 429000, "original_price": 599000, "discount": 28, "rating": 4.8, "sold": 2103, "image": "https://images.unsplash.com/photo-1585515320310-259814833e62?w=600", "images": ["https://images.unsplash.com/photo-1585515320310-259814833e62?w=800"], "description": "Rice cooker digital dengan 8 preset menu dan inner pot anti lengket.", "stock": 120},
    {"product_id": "p-piring-01", "name": "Set Piring Keramik 16 Pcs", "category": "dapur", "price": 299000, "original_price": 450000, "discount": 34, "rating": 4.5, "sold": 567, "image": "https://images.unsplash.com/photo-1604177175912-9ca6c04a0e48?w=600", "images": ["https://images.unsplash.com/photo-1604177175912-9ca6c04a0e48?w=800"], "description": "Set piring keramik untuk 4 orang - piring, mangkuk, cangkir, lepek.", "stock": 60},
    {"product_id": "p-tv-01", "name": "Smart TV LED 43 Inch 4K UHD", "category": "elektronik", "price": 4599000, "original_price": 6299000, "discount": 27, "rating": 4.8, "sold": 456, "image": "https://images.unsplash.com/photo-1593359677879-a4bb92f829d1?w=600", "images": ["https://images.unsplash.com/photo-1593359677879-a4bb92f829d1?w=800"], "description": "Smart TV 43 inch 4K UHD dengan Android TV dan Google Assistant.", "stock": 25},
    {"product_id": "p-kulkas-01", "name": "Kulkas 2 Pintu Inverter 240L", "category": "elektronik", "price": 3799000, "original_price": 4999000, "discount": 24, "rating": 4.7, "sold": 234, "image": "https://images.unsplash.com/photo-1571175443880-49e1d25b2bc5?w=600", "images": ["https://images.unsplash.com/photo-1571175443880-49e1d25b2bc5?w=800"], "description": "Kulkas 2 pintu kapasitas 240L hemat energi dengan teknologi inverter.", "stock": 18},
    {"product_id": "p-mesin-01", "name": "Mesin Cuci Front Loading 8kg", "category": "elektronik", "price": 5499000, "original_price": 7200000, "discount": 24, "rating": 4.8, "sold": 189, "image": "https://images.unsplash.com/photo-1626806787461-102c1bfaaea1?w=600", "images": ["https://images.unsplash.com/photo-1626806787461-102c1bfaaea1?w=800"], "description": "Mesin cuci front loading 8kg dengan 15 program cuci.", "stock": 10},
    {"product_id": "p-ac-01", "name": "AC 1 PK Low Watt Inverter", "category": "elektronik", "price": 3299000, "original_price": 4500000, "discount": 27, "rating": 4.6, "sold": 678, "image": "https://images.unsplash.com/photo-1585338447937-7082f8fc763d?w=600", "images": ["https://images.unsplash.com/photo-1585338447937-7082f8fc763d?w=800"], "description": "AC 1 PK low watt hanya 320W dengan teknologi inverter hemat listrik.", "stock": 30},
    {"product_id": "p-karpet-01", "name": "Karpet Bulu Rasfur 150x200", "category": "home-living", "price": 249000, "original_price": 399000, "discount": 38, "rating": 4.7, "sold": 1543, "image": "https://images.unsplash.com/photo-1600166898405-da9535204843?w=600", "images": ["https://images.unsplash.com/photo-1600166898405-da9535204843?w=800"], "description": "Karpet bulu rasfur lembut ukuran 150x200 cm. Anti slip.", "stock": 100},
    {"product_id": "p-lampu-01", "name": "Lampu LED Minimalis Modern", "category": "home-living", "price": 189000, "original_price": 279000, "discount": 32, "rating": 4.6, "sold": 892, "image": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=600", "images": ["https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=800"], "description": "Lampu gantung LED minimalis dengan 3 warna cahaya adjustable.", "stock": 70},
    {"product_id": "p-gorden-01", "name": "Gorden Blackout 2 Panel", "category": "home-living", "price": 349000, "original_price": 499000, "discount": 30, "rating": 4.8, "sold": 456, "image": "https://images.unsplash.com/photo-1513694203232-719a280e022f?w=600", "images": ["https://images.unsplash.com/photo-1513694203232-719a280e022f?w=800"], "description": "Gorden blackout 2 panel 140x270 cm. Menghalau 95% cahaya.", "stock": 45},
    {"product_id": "p-kaos-01", "name": "Kaos Polos Katun Premium Pria", "category": "fashion", "price": 89000, "original_price": 149000, "discount": 40, "rating": 4.7, "sold": 3210, "image": "https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=600", "images": ["https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=800"], "description": "Kaos polos cotton combed 30s. Tersedia berbagai warna dan size.", "stock": 300},
    {"product_id": "p-sepatu-01", "name": "Sepatu Sneakers Casual Unisex", "category": "fashion", "price": 349000, "original_price": 599000, "discount": 42, "rating": 4.8, "sold": 1876, "image": "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=600", "images": ["https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=800"], "description": "Sneakers casual bahan kanvas premium. Nyaman untuk aktivitas harian.", "stock": 150},
    {"product_id": "p-skincare-01", "name": "Paket Skincare Glowing 5 Pcs", "category": "kecantikan", "price": 199000, "original_price": 350000, "discount": 43, "rating": 4.9, "sold": 2345, "image": "https://images.unsplash.com/photo-1556228720-195a672e8a03?w=600", "images": ["https://images.unsplash.com/photo-1556228720-195a672e8a03?w=800"], "description": "Paket skincare lengkap: cleanser, toner, serum, moisturizer, sunscreen.", "stock": 200},
    {"product_id": "p-matras-01", "name": "Matras Yoga Anti Slip 8mm", "category": "olahraga", "price": 149000, "original_price": 229000, "discount": 35, "rating": 4.7, "sold": 1245, "image": "https://images.unsplash.com/photo-1601925260368-ae2f83cf8b7f?w=600", "images": ["https://images.unsplash.com/photo-1601925260368-ae2f83cf8b7f?w=800"], "description": "Matras yoga TPE anti slip ketebalan 8mm. Ringan dan mudah dibawa.", "stock": 180},
    {"product_id": "p-sembako-01", "name": "Paket Sembako Hemat 10 Item", "category": "grosir", "price": 299000, "original_price": 399000, "discount": 25, "rating": 4.8, "sold": 5432, "image": "https://images.unsplash.com/photo-1542838132-92c53300491e?w=600", "images": ["https://images.unsplash.com/photo-1542838132-92c53300491e?w=800"], "description": "Paket sembako lengkap: beras 5kg, minyak 2L, gula 2kg, tepung, dll.", "stock": 500},
    {"product_id": "p-detergen-01", "name": "Detergen Cair 5L Grosir", "category": "grosir", "price": 89000, "original_price": 129000, "discount": 31, "rating": 4.7, "sold": 2100, "image": "https://images.unsplash.com/photo-1583947215259-38e31be8751f?w=600", "images": ["https://images.unsplash.com/photo-1583947215259-38e31be8751f?w=800"], "description": "Detergen cair kemasan 5 liter. Harga grosir hemat untuk stok rumah.", "stock": 250},
]


async def seed_data() -> None:
    if await db.categories.count_documents({}) == 0:
        await db.categories.insert_many([{**c} for c in SEED_CATEGORIES])
    if await db.products.count_documents({}) == 0:
        now = datetime.now(timezone.utc)
        await db.products.insert_many([{**p, "created_at": now} for p in SEED_PRODUCTS])
    seeds = [
        ("demo@pgs.id", "Demo1234!", "Demo User", "customer"),
        (os.environ["ADMIN_EMAIL"], os.environ["ADMIN_PASSWORD"], "Admin PGS", "admin"),
    ]
    for email, pw, name, role in seeds:
        existing = await db.users.find_one({"email": email})
        if not existing:
            await db.users.insert_one({
                "user_id": f"user_{uuid.uuid4().hex[:12]}", "email": email, "name": name,
                "password_hash": bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode(),
                "role": role, "customer_type": "langsung", "created_at": datetime.now(timezone.utc),
            })
        elif existing.get("role") != role or not _verify(pw, existing.get("password_hash", "")):
            await db.users.update_one({"email": email}, {"$set": {
                "role": role, "password_hash": bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()}})
    await db.users.update_many({"customer_type": {"$exists": False}}, {"$set": {"customer_type": "langsung"}})
    await db.users.update_many({"role": {"$exists": False}}, {"$set": {"role": "customer"}})
    if not await db.settings.find_one({"key": "pricing"}):
        await db.settings.insert_one({**DEFAULT_PRICING})
    admin_u = await db.users.find_one({"email": os.environ["ADMIN_EMAIL"]}, {"user_id": 1})
    if admin_u and not await db.stores.find_one({"store_id": seller.PGS_STORE_ID}):
        await db.stores.insert_one({"store_id": seller.PGS_STORE_ID, "owner_id": admin_u["user_id"], "name": "PGS Official",
                                    "name_lower": "pgs official", "description": "Toko resmi Pusat Grosir Sidoarjo",
                                    "city": "Sidoarjo", "phone": os.environ.get("OWNER_WHATSAPP", ""), "logo": "",
                                    "status": "active", "note": "", "created_at": datetime.now(timezone.utc)})
    await db.products.update_many({"store_id": {"$exists": False}}, {"$set": {"store_id": seller.PGS_STORE_ID, "store_name": "PGS Sidoarjo"}})
    await seller.seed_branches(db, _hash)
    await db.orders.update_many({"store_id": {"$exists": False}}, {"$set": {"store_id": seller.PGS_STORE_ID, "store_name": "PGS Sidoarjo"}})
    await db.users.update_many({"email_verified": {"$exists": False}, "auth_provider": "google"}, {"$set": {"email_verified": True}})
    await db.users.update_many({"email": {"$in": ["demo@pgs.id", os.environ["ADMIN_EMAIL"]]}}, {"$set": {"email_verified": True}})
    # homepage promo sample content (editable in Admin > Promo & Beranda)
    if await db.banners.count_documents({}) == 0:
        await db.banners.insert_many([{**b, "banner_id": f"bn_{uuid.uuid4().hex[:10]}", "order": i, "active": True}
                                      for i, b in enumerate(promo.SAMPLE_BANNERS)])
    if await db.vouchers.count_documents({}) == 0:
        await db.vouchers.insert_many([{**v, "created_at": datetime.now(timezone.utc)} for v in promo.SAMPLE_VOUCHERS])
    if not await db.settings.find_one({"key": "home"}):
        await db.settings.insert_one({**promo.DEFAULT_HOME})
    if not await db.settings.find_one({"key": "flash_sale"}):
        top = await db.products.find({"in_stock": {"$ne": False}, "price": {"$gt": 10000}}, {"product_id": 1, "price": 1}).sort("sold", -1).limit(8).to_list(8)
        await db.settings.insert_one(promo.sample_flash([p["product_id"] for p in top], {p["product_id"]: p["price"] for p in top}))


app = FastAPI(title="Pusat Grosir Sidoarjo API")


@app.get("/health", include_in_schema=False)
@app.head("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}


api = APIRouter(prefix="/api")


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=60)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class SessionIn(BaseModel):
    session_id: str = Field(min_length=1)


class User(BaseModel):
    user_id: str
    email: EmailStr
    name: str
    role: str = "customer"
    customer_type: str = "langsung"
    picture: Optional[str] = None
    email_verified: bool = False
    phone: Optional[str] = None
    phone_verified: bool = False
    gender: str = ""
    birthdate: str = ""
    has_password: bool = True


class AuthOut(BaseModel):
    token: str
    user: User


class Category(BaseModel):
    category_id: str
    name: str
    icon: str
    image: str = ""
    parent: Optional[str] = None
    count: int = 0


class PriceTier(BaseModel):
    min_qty: int = Field(ge=1)
    price: int = Field(ge=0)


class Product(BaseModel):
    product_id: str
    name: str
    category: str
    categories: List[str] = []
    price: int
    original_price: int
    discount: int
    rating: float
    sold: int
    image: str
    images: List[str] = []
    description: str
    stock: int
    in_stock: bool = True
    my_price: int = 0
    price_tiers: List[PriceTier] = []
    price_min: int = 0
    price_max: int = 0
    price_matrix: List[dict] = []
    store_id: str = "pgs-official"
    store_name: str = "PGS Official"
    flash_price: Optional[int] = None
    flash_ends_at: Optional[datetime] = None


class CartItemIn(BaseModel):
    product_id: str
    quantity: int = Field(ge=1, default=1)


class CartQtyIn(BaseModel):
    product_id: Optional[str] = None
    quantity: int = Field(ge=0)


class CartItemDetailed(BaseModel):
    product_id: str
    quantity: int
    name: str
    price: int  # unit price after tier rules
    base_price: int  # website eceran price
    original_price: int
    image: str
    stock: int
    next_tier: Optional[PriceTier] = None
    store_id: str = seller.PGS_STORE_ID
    store_name: str = "PGS Sidoarjo"


class CartOut(BaseModel):
    items: List[CartItemDetailed]
    subtotal: int
    savings: int = 0
    item_count: int
    customer_type: str = "langsung"


class WishlistOut(BaseModel):
    items: List[Product]


class CheckoutIn(BaseModel):
    full_name: str = Field(min_length=1)
    phone: str = Field(min_length=6)
    address: str = Field(default="", max_length=500)  # required only for courier delivery (checked in checkout)
    city: str = Field(default="", max_length=100)
    payment_method: str = Field(pattern="^(midtrans|xendit|cod|saldo)$")
    use_balance: bool = False
    voucher_code: Optional[str] = None
    store_id: Optional[str] = None
    courier: str = "pickup"
    destination_id: Optional[int] = None
    expected_shipping_cost: Optional[int] = Field(default=None, ge=0)  # cost the buyer saw; order is refused if the fresh quote differs
    destination_label: str = Field(default="", max_length=200)


class OrderItem(BaseModel):
    product_id: str
    name: str
    price: int
    quantity: int
    image: str


class Order(BaseModel):
    order_id: str
    user_id: Optional[str] = None
    items: List[OrderItem]
    subtotal: int = 0
    shipping_cost: int = 0
    discount: int = 0
    voucher_code: Optional[str] = None
    total: int
    shipping: dict
    status: str
    payment_method: str = "cod"
    payment_url: Optional[str] = None
    customer_type: str = "langsung"
    store_id: str = seller.PGS_STORE_ID
    store_name: str = "PGS Sidoarjo"
    courier: Optional[dict] = None
    tracking_number: str = ""
    status_history: List[dict] = []
    balance_used: int = 0
    refunded: int = 0
    complaint_id: Optional[str] = None
    pickup_code: Optional[str] = None  # shown by the buyer at the counter
    expires_at: Optional[datetime] = None  # COD pickup: auto-cancel time if the store has not processed it
    ready_at: Optional[datetime] = None  # pickup order marked "Siap diambil"
    created_at: datetime


class QtyTier(BaseModel):
    min_qty: int = Field(ge=2)
    mode: str = Field(default="percent", pattern="^(percent|rupiah)$")
    value: float = Field(ge=0)


class PricingIn(BaseModel):
    type_discounts: dict[str, float]
    type_discount_modes: dict[str, str] = {}
    qty_tiers: List[QtyTier] = []


class CustomerTypeIn(BaseModel):
    customer_type: str = Field(pattern="^(langsung|pengecer|reseller)$")


class ProductTiersIn(BaseModel):
    tier_prices: dict[str, List[PriceTier]]


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False


def _make_token(user_id: str, av: int = 0) -> str:
    payload = {
        "sub": user_id,
        "av": av,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(days=JWT_TTL_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def _user_out(u: dict) -> User:
    return User(user_id=u["user_id"], email=u["email"], name=u.get("name") or u["email"],
                role=u.get("role", "customer"), customer_type=u.get("customer_type", "langsung"),
                picture=u.get("picture"), email_verified=bool(u.get("email_verified")), phone=u.get("phone"),
                phone_verified=bool(u.get("phone_verified")), gender=u.get("gender") or "",
                birthdate=u.get("birthdate") or "", has_password=u["has_pw"] if "has_pw" in u else bool(u.get("password_hash", True)))


def _claims(authorization: Optional[str]) -> Optional[dict]:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    try:
        return jwt.decode(authorization.split(" ", 1)[1].strip(), JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.PyJWTError:
        return None


def _decode(authorization: Optional[str]) -> Optional[str]:
    return (_claims(authorization) or {}).get("sub")


async def get_current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    c = _claims(authorization)
    if not c or not c.get("sub"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = await db.users.find_one({"user_id": c["sub"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if c.get("av", 0) != user.get("auth_version", 0):  # password changed -> old sessions revoked
        raise HTTPException(status_code=401, detail="Sesi berakhir, silakan masuk lagi")
    user["has_pw"] = bool(user.pop("password_hash", None))
    return user


async def get_optional_user(authorization: Optional[str] = Header(default=None)) -> Optional[dict]:
    uid = _decode(authorization)
    if not uid:
        return None
    return await db.users.find_one({"user_id": uid}, {"_id": 0, "password_hash": 0})


async def require_admin(current=Depends(get_current_user)) -> dict:
    if current.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Khusus admin")
    return current


async def get_owner(
    authorization: Optional[str] = Header(default=None),
    x_guest_id: Optional[str] = Header(default=None),
) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        uid = _decode(authorization)
        if not uid:
            raise HTTPException(status_code=401, detail="Sesi berakhir, silakan masuk lagi")
        return f"user:{uid}"
    if x_guest_id:
        return f"guest:{x_guest_id}"
    raise HTTPException(status_code=400, detail="Missing identity")


async def _ctype_for_owner(owner: str) -> str:
    if owner.startswith("user:"):
        u = await db.users.find_one({"user_id": owner[5:]}, {"customer_type": 1})
        return (u or {}).get("customer_type", "langsung")
    return "langsung"


async def _merge_guest(guest_id: Optional[str], user_id: str) -> None:
    """Move a guest's cart and wishlist into the user's account on login/register."""
    if not guest_id:
        return
    g_owner, u_owner = f"guest:{guest_id}", f"user:{user_id}"
    g_cart = await db.carts.find_one({"owner": g_owner})
    if g_cart and g_cart.get("items"):
        u_cart = await db.carts.find_one({"owner": u_owner}) or {"items": []}
        merged = {i["product_id"]: i["quantity"] for i in u_cart.get("items", [])}
        for it in g_cart["items"]:
            merged[it["product_id"]] = merged.get(it["product_id"], 0) + it["quantity"]
        await db.carts.update_one({"owner": u_owner}, {"$set": {"items": [{"product_id": k, "quantity": v} for k, v in merged.items()]}}, upsert=True)
        await db.carts.update_one({"owner": g_owner}, {"$set": {"items": []}})
    g_wl = await db.wishlists.find_one({"owner": g_owner})
    if g_wl and g_wl.get("items"):
        await db.wishlists.update_one({"owner": u_owner}, {"$addToSet": {"items": {"$each": g_wl["items"]}}}, upsert=True)
        await db.wishlists.update_one({"owner": g_owner}, {"$set": {"items": []}})


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
@api.post("/auth/register", response_model=AuthOut)
async def register(body: RegisterIn, x_guest_id: Optional[str] = Header(default=None)):
    if await db.users.find_one({"email": body.email.lower()}):
        raise HTTPException(status_code=400, detail="Email sudah terdaftar")
    user_doc = {
        "user_id": f"user_{uuid.uuid4().hex[:12]}",
        "email": body.email.lower(),
        "name": body.name.strip(),
        "password_hash": _hash(body.password),
        "role": "customer",
        "customer_type": "langsung",
        "email_verified": False,
        "created_at": datetime.now(timezone.utc),
    }
    await db.users.insert_one(user_doc)
    await _merge_guest(x_guest_id, user_doc["user_id"])
    await ACCT["log_activity"](user_doc["user_id"], "auth", "Akun dibuat")
    await ACCT["notify_user"](user_doc["user_id"], "security", "Selamat datang di Pusat Grosir Sidoarjo",
                              "Verifikasi email & nomor HP Anda di menu Profil.", "/account/profile")
    return AuthOut(token=_make_token(user_doc["user_id"]), user=_user_out(user_doc))


@api.post("/auth/login", response_model=AuthOut)
async def login(body: LoginIn, request: Request, x_guest_id: Optional[str] = Header(default=None)):
    email = body.email.lower()
    fails = await db.rate_limits.find_one({"_id": f"loginfail:{email}", "expires_at": {"$gt": datetime.now(timezone.utc)}})
    if fails and fails.get("count", 0) >= 10:
        raise HTTPException(status_code=429, detail="Terlalu banyak percobaan login, coba lagi 15 menit lagi")
    user = await db.users.find_one({"email": email})
    if not user or not _verify(body.password, user.get("password_hash", "")):
        await ACCT["rate_limit"](f"loginfail-ip", request.client.host if request.client else "x", 1000, 900)
        if fails:
            await db.rate_limits.update_one({"_id": f"loginfail:{email}"}, {"$inc": {"count": 1}})
        else:
            await db.rate_limits.replace_one({"_id": f"loginfail:{email}"}, {"count": 1, "expires_at": datetime.now(timezone.utc) + timedelta(minutes=15)}, upsert=True)
        raise HTTPException(status_code=401, detail="Email atau password salah")
    await db.rate_limits.delete_one({"_id": f"loginfail:{email}"})
    await _merge_guest(x_guest_id, user["user_id"])
    await ACCT["log_activity"](user["user_id"], "auth", "Masuk dengan email")
    return AuthOut(token=_make_token(user["user_id"], user.get("auth_version", 0)), user=_user_out(user))


@api.post("/auth/session", response_model=AuthOut)
async def google_session(body: SessionIn, x_guest_id: Optional[str] = Header(default=None)):
    """Exchange the one-time Emergent Google session_id for our own 7-day token."""
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get("https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
                        headers={"X-Session-ID": body.session_id})
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Login Google gagal")
    data = r.json()
    email = (data.get("email") or "").lower()
    if not email:
        raise HTTPException(status_code=401, detail="Login Google gagal")
    user = await db.users.find_one({"email": email})
    if user:
        await db.users.update_one({"email": email}, {"$set": {"picture": data.get("picture")}})
        user["picture"] = data.get("picture")
    else:
        user = {
            "user_id": f"user_{uuid.uuid4().hex[:12]}", "email": email, "name": data.get("name") or email,
            "picture": data.get("picture"), "role": "customer", "customer_type": "langsung",
            "auth_provider": "google", "email_verified": True, "created_at": datetime.now(timezone.utc),
        }
        await db.users.insert_one(user)
    await db.users.update_one({"email": email}, {"$set": {"email_verified": True}})
    user["email_verified"] = True
    await _merge_guest(x_guest_id, user["user_id"])
    await ACCT["log_activity"](user["user_id"], "auth", "Masuk dengan Google")
    return AuthOut(token=_make_token(user["user_id"], user.get("auth_version", 0)), user=_user_out(user))


@api.get("/auth/me", response_model=User)
async def me(current=Depends(get_current_user)):
    return _user_out(current)


# ---------------------------------------------------------------------------
# Store info & catalog
# ---------------------------------------------------------------------------
@api.get("/store")
async def store_info():
    doc = await db.settings.find_one({"key": "store"}, {"_id": 0, "key": 0})
    return doc or {}


@api.get("/categories", response_model=List[Category])
async def list_categories(parent: Optional[str] = None, all: bool = False):
    query: dict = {} if all else {"parent": parent}
    docs = await db.categories.find(query, {"_id": 0}).sort("count", -1).to_list(200)
    return [Category(**d) for d in docs]


ALL_BRANCHES = "all"  # listing context: shared catalog + every branch's own products, stock summed


def _ctx(x_store_id: Optional[str]) -> str:
    return x_store_id if x_store_id in seller.OFFICIAL_IDS else seller.PGS_STORE_ID


async def _visible(ctx: str) -> dict:
    """Hide inactive stores and the *own* products of other official branches (catalog is shared)."""
    if ctx == ALL_BRANCHES:
        return {"store_id": {"$nin": await _hidden_stores()}}
    others = [s for s in seller.OFFICIAL_IDS if s not in (seller.PGS_STORE_ID, ctx)]
    return {"store_id": {"$nin": await _hidden_stores() + others}}


async def _apply_stock(docs: List[dict], ctx: str) -> List[dict]:
    """Catalog items show the stock of the buyer's chosen branch (or the total of all branches)."""
    if ctx == seller.PGS_STORE_ID:
        return docs
    ids = [d["product_id"] for d in docs if d.get("store_id", seller.PGS_STORE_ID) == seller.PGS_STORE_ID]
    if ctx == ALL_BRANCHES:
        hidden = await _hidden_stores()
        per = [await seller.branch_stocks(db, b, ids) for b in seller.OFFICIAL_IDS if b != seller.PGS_STORE_ID and b not in hidden]
        for d in docs:
            if d["product_id"] in ids:
                own = d.get("stock", 0) if d.get("in_stock", True) else 0
                d["stock"] = own + sum(p.get(d["product_id"], 0) for p in per)
                d["in_stock"] = d["stock"] > 0
                d["store_name"] = "PGS · semua cabang"
        return docs
    stocks = await seller.branch_stocks(db, ctx, ids)
    for d in docs:
        if d["product_id"] in stocks or d["product_id"] in ids:
            d["stock"] = stocks.get(d["product_id"], 0)
            d["in_stock"] = d["stock"] > 0
            d["store_name"] = next(o["name"] for o in seller.OFFICIAL if o["store_id"] == ctx)
    return docs


async def _hidden_stores() -> List[str]:
    """Stores that are not active (pending/rejected/suspended): their products stay hidden from buyers."""
    return [s["store_id"] for s in await db.stores.find({"status": {"$ne": "active"}}, {"store_id": 1}).to_list(5000)]


def _product_out(d: dict, ctype: str, pricing: dict, flash: Optional[dict] = None) -> Product:
    tiers = price_tiers(d, ctype, pricing)
    matrix = price_matrix(d, pricing)
    all_prices = [r[c] for r in matrix for c in CUSTOMER_TYPES] or [d.get("price", 0)]
    fp = (flash or {}).get("prices", {}).get(d["product_id"])
    return Product(**{k: v for k, v in d.items() if k in Product.model_fields},
                   my_price=min(tiers[0]["price"], fp) if fp else tiers[0]["price"],
                   price_tiers=[PriceTier(**t) for t in tiers],
                   price_min=min(all_prices), price_max=max(all_prices), price_matrix=matrix,
                   flash_price=fp, flash_ends_at=flash["ends_at"] if fp else None)


@api.get("/products", response_model=List[Product])
async def list_products(
    category: Optional[str] = None,
    q: Optional[str] = None,
    sort: str = Query("newest", pattern="^(popular|price_asc|price_desc|rating|newest)$"),
    limit: int = Query(40, ge=1, le=200),
    skip: int = Query(0, ge=0),
    store: Optional[str] = None,
    user=Depends(get_optional_user),
    x_store_id: Optional[str] = Header(default=None),
):
    # Home, search & categories list every branch at once; a store page (?store=) keeps the chosen branch's view
    ctx = _ctx(x_store_id) if store else ALL_BRANCHES
    query: dict = await _visible(ctx)
    if category:
        children = [c["category_id"] for c in await db.categories.find({"parent": category}, {"category_id": 1}).to_list(200)]
        query["categories"] = {"$in": [category, *children]}
    if q:
        query["name"] = {"$regex": re.escape(q), "$options": "i"}
    if store:
        if store in await _hidden_stores():
            return []
        query["store_id"] = store
    sort_map = {
        "popular": [("in_stock", -1), ("sold", -1), ("updated_at", -1), ("product_id", -1)],
        "price_asc": [("price", 1), ("product_id", 1)],
        "price_desc": [("price", -1), ("product_id", -1)],
        "rating": [("rating", -1), ("product_id", -1)],
        "newest": [("in_stock", -1), ("created_at", -1), ("product_id", -1)],
    }
    docs = await _apply_stock(await db.products.find(query, {"_id": 0}).sort(sort_map[sort]).skip(skip).limit(limit).to_list(limit), ctx)
    if ctx == ALL_BRANCHES and sort in ("popular", "newest"):
        docs.sort(key=lambda d: not d.get("in_stock", True))  # stable: in-stock (any branch) first within the page
    pricing, flash = await get_pricing(db), await promo.active_flash(db)
    ctype = (user or {}).get("customer_type", "langsung")
    return [_product_out(d, ctype, pricing, flash) for d in docs]


@api.get("/products/{product_id}", response_model=Product)
async def get_product(product_id: str, user=Depends(get_optional_user), x_store_id: Optional[str] = Header(default=None)):
    ctx = _ctx(x_store_id)
    doc = await db.products.find_one({"product_id": product_id, **await _visible(ALL_BRANCHES)}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
    await _apply_stock([doc], ctx)
    return _product_out(doc, (user or {}).get("customer_type", "langsung"), await get_pricing(db), await promo.active_flash(db))


# ---------------------------------------------------------------------------
# Cart
# ---------------------------------------------------------------------------
async def _load_cart_detailed(owner: str, only_store: Optional[str] = None) -> CartOut:
    ctype = await _ctype_for_owner(owner)
    cart = await db.carts.find_one({"owner": owner}, {"_id": 0}) or {"owner": owner, "items": []}
    items = [i for i in cart.get("items", []) if not only_store or i.get("store_id", seller.PGS_STORE_ID) == only_store]
    if not items:
        return CartOut(items=[], subtotal=0, item_count=0, customer_type=ctype)
    pricing, flash = await get_pricing(db), await promo.active_flash(db)
    flash_prices = (flash or {}).get("prices", {})
    ids = [i["product_id"] for i in items]
    prods = {p["product_id"]: p for p in await db.products.find({"product_id": {"$in": ids}}, {"_id": 0}).to_list(500)}
    names = await seller.store_names(db)
    stock_by: dict = {}
    for sid in {i.get("store_id", seller.PGS_STORE_ID) for i in items} - {seller.PGS_STORE_ID}:
        stock_by[sid] = await seller.branch_stocks(db, sid, ids)
    detailed: List[CartItemDetailed] = []
    subtotal = savings = 0
    for it in items:
        p = prods.get(it["product_id"])
        if not p:
            continue
        sid = it.get("store_id", seller.PGS_STORE_ID)
        stock = stock_by[sid].get(p["product_id"], 0) if sid in stock_by and p.get("store_id") == seller.PGS_STORE_ID else p["stock"]
        qty = it["quantity"]
        price = unit_price(p, ctype, qty, pricing)
        if flash_prices.get(p["product_id"]):
            price = min(price, flash_prices[p["product_id"]])
        nxt = next((t for t in price_tiers(p, ctype, pricing) if t["min_qty"] > qty), None)
        detailed.append(CartItemDetailed(
            product_id=it["product_id"], quantity=qty, name=p["name"], price=price, base_price=p["price"],
            original_price=p["original_price"], image=p["image"], stock=stock,
            next_tier=PriceTier(**nxt) if nxt else None, store_id=sid, store_name=names.get(sid, sid),
        ))
        subtotal += price * qty
        savings += max(0, p["price"] - price) * qty
    return CartOut(items=detailed, subtotal=subtotal, savings=savings,
                   item_count=sum(i.quantity for i in detailed), customer_type=ctype)


@api.get("/cart", response_model=CartOut)
async def get_cart(owner: str = Depends(get_owner)):
    return await _load_cart_detailed(owner)


@api.post("/cart/items", response_model=CartOut)
async def add_to_cart(body: CartItemIn, owner: str = Depends(get_owner), x_store_id: Optional[str] = Header(default=None)):
    ctx = _ctx(x_store_id)
    product = await db.products.find_one({"product_id": body.product_id, **await _visible(ALL_BRANCHES)})
    if not product:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
    await _apply_stock([product], ctx)
    item_store = ctx if product.get("store_id", seller.PGS_STORE_ID) == seller.PGS_STORE_ID else product["store_id"]
    if not product.get("in_stock", True) or product["stock"] <= 0:
        raise HTTPException(status_code=400, detail="Stok habis")
    cart = await db.carts.find_one({"owner": owner}) or {"owner": owner, "items": []}
    items = cart.get("items", [])
    for it in items:
        if it["product_id"] == body.product_id:
            it["quantity"] = min(product["stock"], it["quantity"] + body.quantity) if it.get("store_id", seller.PGS_STORE_ID) == item_store else min(product["stock"], body.quantity)
            it["store_id"] = item_store
            break
    else:
        items.append({"product_id": body.product_id, "quantity": min(product["stock"], body.quantity), "store_id": item_store})
    await db.carts.update_one({"owner": owner}, {"$set": {"items": items, "updated_at": datetime.now(timezone.utc)}}, upsert=True)
    return await _load_cart_detailed(owner)


@api.put("/cart/items/{product_id}", response_model=CartOut)
async def update_cart_item(product_id: str, body: CartQtyIn, owner: str = Depends(get_owner)):
    product = await db.products.find_one({"product_id": product_id}, {"stock": 1, "product_id": 1, "store_id": 1})
    if not product:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
    cart = await db.carts.find_one({"owner": owner}) or {"owner": owner, "items": []}
    items = [i for i in cart.get("items", []) if i["product_id"] != product_id]
    if body.quantity > 0:
        old = next((i for i in cart.get("items", []) if i["product_id"] == product_id), None)
        sid = (old or {}).get("store_id", seller.PGS_STORE_ID)
        await _apply_stock([product], sid) if sid in seller.OFFICIAL_IDS else None
        entry = {"product_id": product_id, "quantity": min(product["stock"], body.quantity), "store_id": sid}
        if old:
            items = [entry if i["product_id"] == product_id else i for i in cart["items"]]
        else:
            items.append(entry)
    await db.carts.update_one({"owner": owner}, {"$set": {"items": items, "updated_at": datetime.now(timezone.utc)}}, upsert=True)
    return await _load_cart_detailed(owner)


@api.delete("/cart/items/{product_id}", response_model=CartOut)
async def delete_cart_item(product_id: str, owner: str = Depends(get_owner)):
    await db.carts.update_one({"owner": owner}, {"$pull": {"items": {"product_id": product_id}}})
    return await _load_cart_detailed(owner)


@api.delete("/cart", response_model=CartOut)
async def clear_cart(owner: str = Depends(get_owner)):
    await db.carts.update_one({"owner": owner}, {"$set": {"items": []}}, upsert=True)
    return await _load_cart_detailed(owner)


# ---------------------------------------------------------------------------
# Wishlist
# ---------------------------------------------------------------------------
@api.get("/wishlist", response_model=WishlistOut)
async def get_wishlist(owner: str = Depends(get_owner)):
    doc = await db.wishlists.find_one({"owner": owner}, {"_id": 0}) or {"items": []}
    ids = doc.get("items", [])
    if not ids:
        return WishlistOut(items=[])
    ctype, pricing, flash = await _ctype_for_owner(owner), await get_pricing(db), await promo.active_flash(db)
    prods = await db.products.find({"product_id": {"$in": ids}}, {"_id": 0}).to_list(500)
    return WishlistOut(items=[_product_out(p, ctype, pricing, flash) for p in prods])


@api.post("/wishlist/{product_id}", response_model=WishlistOut)
async def add_wishlist(product_id: str, owner: str = Depends(get_owner)):
    if not await db.products.find_one({"product_id": product_id}, {"_id": 1}):
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
    await db.wishlists.update_one({"owner": owner}, {"$addToSet": {"items": product_id}}, upsert=True)
    return await get_wishlist(owner)


@api.delete("/wishlist/{product_id}", response_model=WishlistOut)
async def remove_wishlist(product_id: str, owner: str = Depends(get_owner)):
    await db.wishlists.update_one({"owner": owner}, {"$pull": {"items": product_id}})
    return await get_wishlist(owner)


# ---------------------------------------------------------------------------
# Orders & payments
# ---------------------------------------------------------------------------
def _order_out(d: dict) -> Order:
    return Order(**{k: v for k, v in d.items() if k in Order.model_fields and k != "items"},
                 items=[OrderItem(**i) for i in d.get("items", [])])


@api.post("/checkout", response_model=Order)
async def checkout(body: CheckoutIn, background: BackgroundTasks, owner: str = Depends(get_owner)):
    full = await _load_cart_detailed(owner)
    stores = {i.store_id for i in full.items}
    store_id = body.store_id or (stores.pop() if len(stores) == 1 else None)
    if not store_id:
        raise HTTPException(status_code=400, detail="Pilih toko yang akan di-checkout")
    cart = await _load_cart_detailed(owner, store_id)
    if cart.item_count == 0:
        raise HTTPException(status_code=400, detail="Keranjang kosong")
    for i in cart.items:
        if i.quantity > i.stock:
            raise HTTPException(status_code=400, detail=f"Stok {i.name} tidak cukup (sisa {i.stock})")
    store = await db.stores.find_one({"store_id": store_id, "status": "active"})
    if not store:
        raise HTTPException(status_code=400, detail="Toko tidak aktif")
    options = await SHIP_QUOTE(store, body.destination_id, cart.item_count)
    courier = next((c for c in options if c["code"] == body.courier), None)
    if not courier:
        raise HTTPException(status_code=409, detail="Kurir yang dipilih tidak tersedia lagi. Tarif ongkir sudah dimuat ulang, silakan pilih kurir lagi.")
    SHIPPING_COST = int(courier["cost"])
    if body.expected_shipping_cost is not None and body.expected_shipping_cost != SHIPPING_COST:
        rp = lambda n: f"Rp{n:,}".replace(",", ".")
        raise HTTPException(status_code=409, detail=f"Ongkir {courier['name']} berubah dari {rp(body.expected_shipping_cost)} menjadi {rp(SHIPPING_COST)}. Tarif sudah dimuat ulang, periksa lalu buat pesanan lagi.")
    user_id = owner[5:] if owner.startswith("user:") else None
    user = await db.users.find_one({"user_id": user_id}, {"email": 1}) if user_id else None
    discount, vcode = 0, None
    if body.voucher_code and body.voucher_code.strip():
        vcode = body.voucher_code.strip().upper()
        discount, verr = promo.voucher_check(await db.vouchers.find_one({"code": vcode}), cart.subtotal)
        if verr:
            raise HTTPException(status_code=400, detail=verr)
    total = cart.subtotal - discount + SHIPPING_COST
    balance_used = 0
    if body.use_balance or body.payment_method == "saldo":
        if not user_id:
            raise HTTPException(status_code=400, detail="Masuk dulu untuk memakai saldo")
        balance_used = min(await support.balance_of(db, user_id), total)
        if body.payment_method == "saldo" and balance_used < total:
            raise HTTPException(status_code=400, detail="Saldo tidak cukup, pilih metode bayar lain untuk sisanya")
    pay_method = "saldo" if balance_used and balance_used >= total else body.payment_method
    if pay_method == "saldo" and not balance_used:
        raise HTTPException(status_code=400, detail="Saldo tidak cukup")
    if (pay_method == "midtrans" and not payments.midtrans_ready()) or (pay_method == "xendit" and not payments.xendit_ready()):
        raise HTTPException(status_code=400, detail="Pembayaran online belum aktif. Pilih Ambil di toko dengan COD")
    if courier["code"] != "pickup" and (len(body.address.strip()) < 5 or len(body.city.strip()) < 2):
        raise HTTPException(status_code=400, detail="Lengkapi alamat dan kota pengiriman")
    if pay_method == "cod" and courier["code"] != "pickup":
        raise HTTPException(status_code=400, detail="COD hanya untuk Ambil di toko. Pengiriman kurir wajib bayar online")
    if vcode:  # claim the voucher only after every validation passed, so rejected checkouts don't burn quota
        claimed = await db.vouchers.find_one_and_update(
            {"code": vcode, "$or": [{"quota": 0}, {"quota": None}, {"$expr": {"$lt": ["$used", "$quota"]}}]},
            {"$inc": {"used": 1}})
        if not claimed:
            raise HTTPException(status_code=400, detail="Kuota voucher sudah habis")
    status0 = "paid" if pay_method == "saldo" else "cod" if pay_method == "cod" else "pending"
    order_doc = {
        "order_id": f"PGS-{datetime.now(timezone.utc).strftime('%y%m%d')}-{uuid.uuid4().hex[:6].upper()}",
        "user_id": user_id,
        "owner": owner,
        "email": (user or {}).get("email"),
        "items": [OrderItem(product_id=i.product_id, name=i.name, price=i.price, quantity=i.quantity, image=i.image).model_dump() for i in cart.items],
        "subtotal": cart.subtotal,
        "shipping_cost": SHIPPING_COST,
        "discount": discount,
        "voucher_code": vcode,
        "total": total,
        "balance_used": balance_used,
        "shipping": body.model_dump(exclude={"payment_method", "store_id", "courier", "voucher_code", "destination_id", "use_balance", "expected_shipping_cost"}),
        "store_id": store_id,
        "store_name": store["name"],
        "courier": {k: courier.get(k) for k in ("code", "name", "cost", "eta", "source")},
        **({"pickup_code": f"{secrets.randbelow(900000) + 100000}"} if courier["code"] == "pickup" else {}),
        "tracking_number": "",
        "status_history": [{"status": status0, "at": datetime.now(timezone.utc), "note": "Pesanan dibuat" + (" (dibayar dengan saldo)" if pay_method == "saldo" else "")}],
        "payment_method": pay_method,
        "customer_type": cart.customer_type,
        "status": status0,
        **({"expires_at": datetime.now(timezone.utc) + timedelta(hours=COD_PICKUP_HOURS)} if status0 == "cod" else {}),
        "created_at": datetime.now(timezone.utc),
    }
    if balance_used and not await support.debit(db, user_id, balance_used, order_doc["order_id"]):
        if vcode:
            await db.vouchers.update_one({"code": vcode}, {"$inc": {"used": -1}})
        raise HTTPException(status_code=400, detail="Saldo berubah, coba lagi")
    try:
        if pay_method == "midtrans":
            order_doc.update(await payments.midtrans_create(order_doc))
        elif pay_method == "xendit":
            order_doc.update(await payments.xendit_create(order_doc))
    except Exception:
        if vcode:  # give the voucher use back when payment creation fails
            await db.vouchers.update_one({"code": vcode}, {"$inc": {"used": -1}})
        if balance_used:
            await support.credit(db, user_id, balance_used, "return", order_doc["order_id"], "Saldo dikembalikan, pembayaran gagal dibuat")
        raise
    await db.orders.insert_one(order_doc)
    await _track(owner, [p["category"] for p in await db.products.find(
        {"product_id": {"$in": [i.product_id for i in cart.items]}}, {"category": 1}).to_list(500)], weight=3)
    await seller.adjust_stock(db, order_doc, -1)
    await db.carts.update_one({"owner": owner}, {"$pull": {"items": {"product_id": {"$in": [i.product_id for i in cart.items]}}}})
    background.add_task(notify.send_owner_order, order_doc)
    await ACCT["notify_user"](user_id, "order", "Pesanan dibuat", f"Pesanan {order_doc['order_id']} berhasil dibuat.", f"/order/{order_doc['order_id']}")
    await ACCT["log_activity"](user_id, "order", f"Membuat pesanan {order_doc['order_id']}")
    return _order_out(order_doc)


@api.get("/orders", response_model=List[Order])
async def list_orders(owner: str = Depends(get_owner)):
    docs = await db.orders.find({"owner": owner}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return [_order_out(d) for d in docs]


@api.get("/orders/{order_id}", response_model=Order)
async def get_order(order_id: str, owner: str = Depends(get_owner)):
    d = await db.orders.find_one({"order_id": order_id, "owner": owner}, {"_id": 0})
    if not d:
        raise HTTPException(status_code=404, detail="Pesanan tidak ditemukan")
    return _order_out(d)


@api.post("/orders/{order_id}/confirm", response_model=Order)
async def confirm_received(order_id: str, owner: str = Depends(get_owner)):
    d = await db.orders.find_one_and_update(
        {"order_id": order_id, "owner": owner, "status": "shipped"},
        {"$set": {"status": "completed", "completed_at": datetime.now(timezone.utc)},
         "$push": {"status_history": {"status": "completed", "at": datetime.now(timezone.utc), "note": "Diterima pembeli"}}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    if not d:
        raise HTTPException(status_code=400, detail="Pesanan belum dikirim atau tidak ditemukan")
    await ACCT["log_activity"](d.get("user_id"), "order", f"Mengonfirmasi pesanan {order_id} diterima")
    return _order_out(d)


@api.post("/orders/{order_id}/refresh", response_model=Order)
async def refresh_order(order_id: str, owner: str = Depends(get_owner)):
    """Ask the payment provider for the real status (server-to-server)."""
    d = await db.orders.find_one({"order_id": order_id, "owner": owner}, {"_id": 0})
    if not d:
        raise HTTPException(status_code=404, detail="Pesanan tidak ditemukan")
    if d["status"] == "pending":
        new = None
        if d["payment_method"] == "midtrans":
            new = await payments.midtrans_status(order_id)
        elif d["payment_method"] == "xendit" and d.get("payment_ref"):
            new = await payments.xendit_status(d["payment_ref"])
        if new and new != d["status"]:
            await db.orders.update_one({"order_id": order_id}, {"$set": {"status": new, "updated_at": datetime.now(timezone.utc)}})
            d["status"] = new
            if new in RELEASE_STATUSES:
                await _release_voucher(order_id)
    return _order_out(d)


@api.post("/payments/midtrans/notification")
async def midtrans_notification(request: Request):
    p = await request.json()
    if not payments.midtrans_verify(p):
        raise HTTPException(status_code=403, detail="Invalid signature")
    order = await db.orders.find_one({"order_id": p.get("order_id")}, {"total": 1, "status": 1, "balance_used": 1})
    if not order:
        return {"ok": True}
    if int(float(p.get("gross_amount", 0))) != order["total"] - order.get("balance_used", 0):
        raise HTTPException(status_code=400, detail="Amount mismatch")
    if order["status"] != "paid":
        new = payments.midtrans_map(p)
        await db.orders.update_one({"order_id": p["order_id"]}, {"$set": {
            "status": new, "payment_raw": p, "updated_at": datetime.now(timezone.utc)}})
        if new in RELEASE_STATUSES:
            await _release_voucher(p["order_id"])
    return {"ok": True}


@api.post("/payments/xendit/callback")
async def xendit_callback(request: Request, x_callback_token: Optional[str] = Header(default=None)):
    if not payments.xendit_verify(x_callback_token):
        raise HTTPException(status_code=401, detail="Invalid callback token")
    p = await request.json()
    order = await db.orders.find_one({"order_id": p.get("external_id")}, {"total": 1, "status": 1, "balance_used": 1})
    if not order:
        return {"ok": True}
    if int(p.get("amount", 0)) != order["total"] - order.get("balance_used", 0):
        raise HTTPException(status_code=400, detail="Amount mismatch")
    if order["status"] != "paid":
        new = payments.xendit_map(p.get("status"))
        await db.orders.update_one({"order_id": p["external_id"]}, {"$set": {
            "status": new, "payment_raw": p, "updated_at": datetime.now(timezone.utc)}})
        if new in RELEASE_STATUSES:
            await _release_voucher(p["external_id"])
    return {"ok": True}


# ---------------------------------------------------------------------------
# Admin panel
# ---------------------------------------------------------------------------
@api.get("/admin/stats")
async def admin_stats(_=Depends(require_admin)):
    wib_now = datetime.now(timezone.utc) + timedelta(hours=7)
    start = wib_now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(hours=7)
    today = await db.orders.find({"created_at": {"$gte": start}}, {"total": 1, "status": 1}).to_list(5000)
    return {
        "orders_today": len(today),
        "revenue_today": sum(o["total"] for o in today if o["status"] not in ("cancelled", "expired", "failed")),
        "need_action": await db.orders.count_documents({"status": {"$in": ["paid", "cod", "processing"]}}),
        "waiting_payment": await db.orders.count_documents({"status": "pending"}),
        "customers": await db.users.count_documents({"role": {"$ne": "admin"}}),
        "products": await db.products.count_documents({}),
    }


ADMIN_ORDER_STATUSES = ("processing", "shipped", "completed", "cancelled")


class OrderStatusIn(BaseModel):
    status: str = Field(pattern="^(processing|shipped|completed|cancelled)$")


@api.get("/admin/orders", response_model=List[Order])
async def admin_orders(status: Optional[str] = None, q: Optional[str] = None, _=Depends(require_admin)):
    query: dict = {}
    if status:
        query["status"] = status
    if q:
        rx = {"$regex": re.escape(q), "$options": "i"}
        query["$or"] = [{"order_id": rx}, {"shipping.full_name": rx}, {"shipping.phone": rx}]
    docs = await db.orders.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)
    return [_order_out(d) for d in docs]


@api.get("/admin/orders/{order_id}", response_model=Order)
async def admin_order(order_id: str, _=Depends(require_admin)):
    d = await db.orders.find_one({"order_id": order_id}, {"_id": 0})
    if not d:
        raise HTTPException(status_code=404, detail="Pesanan tidak ditemukan")
    return _order_out(d)


@api.put("/admin/orders/{order_id}/status", response_model=Order)
async def admin_order_status(order_id: str, body: OrderStatusIn, _=Depends(require_admin)):
    d = await db.orders.find_one_and_update(
        {"order_id": order_id}, {"$set": {"status": body.status, "updated_at": datetime.now(timezone.utc)}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    if not d:
        raise HTTPException(status_code=404, detail="Pesanan tidak ditemukan")
    if body.status == "cancelled":
        await _release_voucher(order_id)
        await seller.restock_once(db, order_id)
    await db.orders.update_one({"order_id": order_id}, {"$push": {"status_history": {"status": body.status, "at": datetime.now(timezone.utc), "note": "Admin"}}})
    label = {"processing": "sedang diproses", "shipped": "sedang dikirim", "completed": "selesai", "cancelled": "dibatalkan"}[body.status]
    await ACCT["notify_user"](d.get("user_id"), "order", "Status pesanan diperbarui", f"Pesanan {order_id} {label}.", f"/order/{order_id}")
    return _order_out(d)


@api.get("/admin/pricing")
async def admin_get_pricing(_=Depends(require_admin)):
    return await get_pricing(db)


@api.put("/admin/pricing")
async def admin_set_pricing(body: PricingIn, _=Depends(require_admin)):
    modes = {t: ("rupiah" if body.type_discount_modes.get(t) == "rupiah" else "percent") for t in CUSTOMER_TYPES}
    td = {}
    for t in CUSTOMER_TYPES:
        v = max(0.0, float(body.type_discounts.get(t, 0)))
        if modes[t] == "percent" and v > 100:
            raise HTTPException(status_code=400, detail="Potongan persen maksimal 100%")
        td[t] = v
    for t in body.qty_tiers:
        if t.mode == "percent" and t.value > 100:
            raise HTTPException(status_code=400, detail="Potongan persen maksimal 100%")
    tiers = sorted({t.min_qty: t for t in body.qty_tiers}.values(), key=lambda t: t.min_qty)
    doc = {"key": "pricing", "type_discounts": td, "type_discount_modes": modes, "qty_tiers": [t.model_dump() for t in tiers]}
    await db.settings.update_one({"key": "pricing"}, {"$set": doc}, upsert=True)
    return doc


@api.get("/admin/customers", response_model=List[User])
async def admin_customers(q: Optional[str] = None, _=Depends(require_admin)):
    query: dict = {}
    if q:
        rx = {"$regex": re.escape(q), "$options": "i"}
        query = {"$or": [{"email": rx}, {"name": rx}]}
    docs = await db.users.find(query, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(200)
    return [_user_out(d) for d in docs]


@api.put("/admin/customers/{user_id}", response_model=User)
async def admin_set_customer_type(user_id: str, body: CustomerTypeIn, _=Depends(require_admin)):
    res = await db.users.find_one_and_update({"user_id": user_id}, {"$set": {"customer_type": body.customer_type}},
                                             projection={"_id": 0, "password_hash": 0}, return_document=ReturnDocument.AFTER)
    if not res:
        raise HTTPException(status_code=404, detail="Pelanggan tidak ditemukan")
    return _user_out(res)


@api.get("/admin/products/{product_id}/tiers")
async def admin_get_tiers(product_id: str, _=Depends(require_admin)):
    d = await db.products.find_one({"product_id": product_id}, {"_id": 0, "product_id": 1, "name": 1, "price": 1, "image": 1, "tier_prices": 1})
    if not d:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
    d["tier_prices"] = {t: (d.get("tier_prices") or {}).get(t, []) for t in CUSTOMER_TYPES}
    return d


@api.put("/admin/products/{product_id}/tiers")
async def admin_set_tiers(product_id: str, body: ProductTiersIn, _=Depends(require_admin)):
    clean = {}
    for t in CUSTOMER_TYPES:
        rows = {r.min_qty: r for r in body.tier_prices.get(t, []) if r.price > 0}
        clean[t] = [r.model_dump() for r in sorted(rows.values(), key=lambda r: r.min_qty)]
    res = await db.products.update_one({"product_id": product_id}, {"$set": {"tier_prices": clean}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
    return {"product_id": product_id, "tier_prices": clean}


# ---------------------------------------------------------------------------
# Homepage: banners, flash sale, vouchers, recommendations, settings
# ---------------------------------------------------------------------------
async def get_optional_owner(
    authorization: Optional[str] = Header(default=None),
    x_guest_id: Optional[str] = Header(default=None),
) -> Optional[str]:
    uid = _decode(authorization)
    if uid:
        return f"user:{uid}"
    return f"guest:{x_guest_id}" if x_guest_id else None


async def _track(owner: Optional[str], cats: List[str], weight: int = 1, product_id: Optional[str] = None) -> None:
    if not owner:
        return
    upd: dict = {"$set": {"updated_at": datetime.now(timezone.utc)}}
    inc = {f"cats.{c.replace('.', '_')}": weight for c in cats if c}
    if inc:
        upd["$inc"] = inc
    if product_id:
        upd["$push"] = {"recent": {"$each": [product_id], "$slice": -30}}
    await db.activity.update_one({"owner": owner}, upd, upsert=True)


@api.post("/activity/view/{product_id}")
async def track_view(product_id: str, owner: Optional[str] = Depends(get_optional_owner)):
    p = await db.products.find_one({"product_id": product_id}, {"category": 1, "categories": 1})
    if p:
        await _track(owner, [p.get("category", "")], 1, product_id)
    return {"ok": True}


@api.get("/recommendations", response_model=List[Product])
async def recommendations(
    limit: int = Query(20, ge=1, le=60), skip: int = Query(0, ge=0),
    owner: Optional[str] = Depends(get_optional_owner), user=Depends(get_optional_user),
    x_store_id: Optional[str] = Header(default=None),
):
    mode = (await promo.get_home(db))["recommend_mode"]
    base = {**await _visible(ALL_BRANCHES)}  # stock is checked after summing all branches
    docs: list = []
    if mode == "random":
        docs = await db.products.aggregate([{"$match": base}, {"$sample": {"size": limit}}, {"$project": {"_id": 0}}]).to_list(limit)
    else:
        act = await db.activity.find_one({"owner": owner}) if owner else None
        cats = [c for c, _ in sorted((act or {}).get("cats", {}).items(), key=lambda kv: -kv[1])[:5]]
        recent = (act or {}).get("recent", [])[-10:]
        # one stable ordering: products from favourite categories first, then best sellers
        docs = await db.products.aggregate([
            {"$match": {**base, "product_id": {"$nin": recent}}},
            {"$addFields": {"_fav": {"$cond": [{"$gt": [{"$size": {"$setIntersection": [{"$ifNull": ["$categories", []]}, cats]}}, 0]}, 1, 0]}}},
            {"$sort": {"_fav": -1, "sold": -1, "created_at": -1, "product_id": -1}},
            {"$skip": skip}, {"$limit": limit}, {"$project": {"_id": 0, "_fav": 0}},
        ]).to_list(limit)
    await _apply_stock(docs, ALL_BRANCHES)
    docs = [d for d in docs if d.get("in_stock", True) and d.get("stock", 0) > 0]
    pricing, flash = await get_pricing(db), await promo.active_flash(db)
    ctype = (user or {}).get("customer_type", "langsung")
    return [_product_out(d, ctype, pricing, flash) for d in docs]

async def _product_out_for_user(d: dict, user: dict) -> Product:
    return _product_out(d, user.get("customer_type", "langsung"), await get_pricing(db), await promo.active_flash(db))


ACCT = account.register(api, db, get_current_user, _user_out, _make_token)
_release_voucher, expire_cod_orders, remind_expiring_cod, _expire_loop = order_tasks.register(db, ACCT["notify_user"])
marketing.register(api, db, require_admin=require_admin, get_owner=get_owner, get_optional_owner=get_optional_owner,
                   get_optional_user=get_optional_user, product_out=_product_out, load_cart_detailed=_load_cart_detailed,
                   broadcast_promo=ACCT["broadcast_promo"])
seller.register(api, db, get_current_user, require_admin, _product_out_for_user, ACCT["notify_user"], ACCT["log_activity"],
                _release_voucher, _order_out)

support.register(api, db, get_current_user, require_admin, ACCT["notify_user"], ACCT["log_activity"])

payments.register_settings(api, db, require_admin)
branches.register(api, db, get_owner, seller)

SHIP_QUOTE = shipping.register(api, db, require_admin, get_owner, seller.OFFICIAL_IDS, seller.couriers_of)

app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@app.on_event("startup")
async def _startup():
    app.state.index_task = asyncio.create_task(ensure_indexes())
    await seed_data()
    await payments.load_config(db)
    app.state.expire_task = asyncio.create_task(_expire_loop())
    try:
        await run_in_threadpool(storage.init_storage)
    except Exception:
        logger.exception("object storage init failed")


@app.on_event("shutdown")
async def _shutdown():
    app.state.index_task.cancel()
    with suppress(asyncio.CancelledError):
        await app.state.index_task
    client.close()
