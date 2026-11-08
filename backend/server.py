import asyncio
import os
import logging
import uuid
import re
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

import bcrypt
import jwt
from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Request
import httpx
import notify
import payments
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
    ],
    "categories": [
        IndexModel([("category_id", ASCENDING)], name="category_id", unique=True),
        IndexModel([("parent", ASCENDING), ("count", DESCENDING)], name="parent_count"),
    ],
    "settings": [
        IndexModel([("key", ASCENDING)], name="key", unique=True),
    ],
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


app = FastAPI(title="Pusat Grosir Sidoarjo API")


@app.get("/health", include_in_schema=False)
@app.head("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}


api = APIRouter(prefix="/api")


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: str = Field(min_length=1)


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
    address: str = Field(min_length=5)
    city: str = Field(min_length=2)
    payment_method: str = Field(pattern="^(midtrans|xendit|cod)$")


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
    total: int
    shipping: dict
    status: str
    payment_method: str = "cod"
    payment_url: Optional[str] = None
    customer_type: str = "langsung"
    created_at: datetime


class QtyTier(BaseModel):
    min_qty: int = Field(ge=2)
    discount_percent: float = Field(ge=0, le=100)


class PricingIn(BaseModel):
    type_discounts: dict[str, float]
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


def _make_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(days=JWT_TTL_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def _user_out(u: dict) -> User:
    return User(user_id=u["user_id"], email=u["email"], name=u.get("name") or u["email"],
                role=u.get("role", "customer"), customer_type=u.get("customer_type", "langsung"),
                picture=u.get("picture"))


def _decode(authorization: Optional[str]) -> Optional[str]:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    try:
        return jwt.decode(authorization.split(" ", 1)[1].strip(), JWT_SECRET, algorithms=[JWT_ALG]).get("sub")
    except jwt.PyJWTError:
        return None


async def get_current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    uid = _decode(authorization)
    if not uid:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = await db.users.find_one({"user_id": uid}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
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
        "created_at": datetime.now(timezone.utc),
    }
    await db.users.insert_one(user_doc)
    await _merge_guest(x_guest_id, user_doc["user_id"])
    return AuthOut(token=_make_token(user_doc["user_id"]), user=_user_out(user_doc))


@api.post("/auth/login", response_model=AuthOut)
async def login(body: LoginIn, x_guest_id: Optional[str] = Header(default=None)):
    user = await db.users.find_one({"email": body.email.lower()})
    if not user or not _verify(body.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Email atau password salah")
    await _merge_guest(x_guest_id, user["user_id"])
    return AuthOut(token=_make_token(user["user_id"]), user=_user_out(user))


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
            "auth_provider": "google", "created_at": datetime.now(timezone.utc),
        }
        await db.users.insert_one(user)
    await _merge_guest(x_guest_id, user["user_id"])
    return AuthOut(token=_make_token(user["user_id"]), user=_user_out(user))


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


def _product_out(d: dict, ctype: str, pricing: dict) -> Product:
    tiers = price_tiers(d, ctype, pricing)
    matrix = price_matrix(d, pricing)
    all_prices = [r[c] for r in matrix for c in CUSTOMER_TYPES] or [d.get("price", 0)]
    return Product(**{k: v for k, v in d.items() if k in Product.model_fields},
                   my_price=tiers[0]["price"], price_tiers=[PriceTier(**t) for t in tiers],
                   price_min=min(all_prices), price_max=max(all_prices), price_matrix=matrix)


@api.get("/products", response_model=List[Product])
async def list_products(
    category: Optional[str] = None,
    q: Optional[str] = None,
    sort: str = Query("newest", pattern="^(popular|price_asc|price_desc|rating|newest)$"),
    limit: int = Query(40, ge=1, le=200),
    skip: int = Query(0, ge=0),
    user=Depends(get_optional_user),
):
    query: dict = {}
    if category:
        children = [c["category_id"] for c in await db.categories.find({"parent": category}, {"category_id": 1}).to_list(200)]
        query["categories"] = {"$in": [category, *children]}
    if q:
        query["name"] = {"$regex": re.escape(q), "$options": "i"}
    sort_map = {
        "popular": [("in_stock", -1), ("sold", -1), ("updated_at", -1)],
        "price_asc": [("price", 1)],
        "price_desc": [("price", -1)],
        "rating": [("rating", -1)],
        "newest": [("in_stock", -1), ("created_at", -1), ("product_id", -1)],
    }
    docs = await db.products.find(query, {"_id": 0}).sort(sort_map[sort]).skip(skip).limit(limit).to_list(limit)
    pricing = await get_pricing(db)
    ctype = (user or {}).get("customer_type", "langsung")
    return [_product_out(d, ctype, pricing) for d in docs]


@api.get("/products/{product_id}", response_model=Product)
async def get_product(product_id: str, user=Depends(get_optional_user)):
    doc = await db.products.find_one({"product_id": product_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
    return _product_out(doc, (user or {}).get("customer_type", "langsung"), await get_pricing(db))


# ---------------------------------------------------------------------------
# Cart
# ---------------------------------------------------------------------------
async def _load_cart_detailed(owner: str) -> CartOut:
    ctype = await _ctype_for_owner(owner)
    cart = await db.carts.find_one({"owner": owner}, {"_id": 0}) or {"owner": owner, "items": []}
    items = cart.get("items", [])
    if not items:
        return CartOut(items=[], subtotal=0, item_count=0, customer_type=ctype)
    pricing = await get_pricing(db)
    ids = [i["product_id"] for i in items]
    prods = {p["product_id"]: p for p in await db.products.find({"product_id": {"$in": ids}}, {"_id": 0}).to_list(500)}
    detailed: List[CartItemDetailed] = []
    subtotal = savings = 0
    for it in items:
        p = prods.get(it["product_id"])
        if not p:
            continue
        qty = it["quantity"]
        price = unit_price(p, ctype, qty, pricing)
        nxt = next((t for t in price_tiers(p, ctype, pricing) if t["min_qty"] > qty), None)
        detailed.append(CartItemDetailed(
            product_id=it["product_id"], quantity=qty, name=p["name"], price=price, base_price=p["price"],
            original_price=p["original_price"], image=p["image"], stock=p["stock"],
            next_tier=PriceTier(**nxt) if nxt else None,
        ))
        subtotal += price * qty
        savings += max(0, p["price"] - price) * qty
    return CartOut(items=detailed, subtotal=subtotal, savings=savings,
                   item_count=sum(i.quantity for i in detailed), customer_type=ctype)


@api.get("/cart", response_model=CartOut)
async def get_cart(owner: str = Depends(get_owner)):
    return await _load_cart_detailed(owner)


@api.post("/cart/items", response_model=CartOut)
async def add_to_cart(body: CartItemIn, owner: str = Depends(get_owner)):
    product = await db.products.find_one({"product_id": body.product_id})
    if not product:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
    if not product.get("in_stock", True) or product["stock"] <= 0:
        raise HTTPException(status_code=400, detail="Stok habis")
    cart = await db.carts.find_one({"owner": owner}) or {"owner": owner, "items": []}
    items = cart.get("items", [])
    for it in items:
        if it["product_id"] == body.product_id:
            it["quantity"] = min(product["stock"], it["quantity"] + body.quantity)
            break
    else:
        items.append({"product_id": body.product_id, "quantity": min(product["stock"], body.quantity)})
    await db.carts.update_one({"owner": owner}, {"$set": {"items": items, "updated_at": datetime.now(timezone.utc)}}, upsert=True)
    return await _load_cart_detailed(owner)


@api.put("/cart/items/{product_id}", response_model=CartOut)
async def update_cart_item(product_id: str, body: CartQtyIn, owner: str = Depends(get_owner)):
    product = await db.products.find_one({"product_id": product_id}, {"stock": 1})
    if not product:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
    cart = await db.carts.find_one({"owner": owner}) or {"owner": owner, "items": []}
    items = [i for i in cart.get("items", []) if i["product_id"] != product_id]
    if body.quantity > 0:
        old = next((i for i in cart.get("items", []) if i["product_id"] == product_id), None)
        entry = {"product_id": product_id, "quantity": min(product["stock"], body.quantity)}
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
    ctype, pricing = await _ctype_for_owner(owner), await get_pricing(db)
    prods = await db.products.find({"product_id": {"$in": ids}}, {"_id": 0}).to_list(500)
    return WishlistOut(items=[_product_out(p, ctype, pricing) for p in prods])


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
SHIPPING_COST = 25000


def _order_out(d: dict) -> Order:
    return Order(**{k: v for k, v in d.items() if k in Order.model_fields and k != "items"},
                 items=[OrderItem(**i) for i in d.get("items", [])])


@api.post("/checkout", response_model=Order)
async def checkout(body: CheckoutIn, background: BackgroundTasks, owner: str = Depends(get_owner)):
    cart = await _load_cart_detailed(owner)
    if cart.item_count == 0:
        raise HTTPException(status_code=400, detail="Keranjang kosong")
    user_id = owner[5:] if owner.startswith("user:") else None
    user = await db.users.find_one({"user_id": user_id}, {"email": 1}) if user_id else None
    order_doc = {
        "order_id": f"PGS-{datetime.now(timezone.utc).strftime('%y%m%d')}-{uuid.uuid4().hex[:6].upper()}",
        "user_id": user_id,
        "owner": owner,
        "email": (user or {}).get("email"),
        "items": [OrderItem(product_id=i.product_id, name=i.name, price=i.price, quantity=i.quantity, image=i.image).model_dump() for i in cart.items],
        "subtotal": cart.subtotal,
        "shipping_cost": SHIPPING_COST,
        "total": cart.subtotal + SHIPPING_COST,
        "shipping": body.model_dump(exclude={"payment_method"}),
        "payment_method": body.payment_method,
        "customer_type": cart.customer_type,
        "status": "cod" if body.payment_method == "cod" else "pending",
        "created_at": datetime.now(timezone.utc),
    }
    if body.payment_method == "midtrans":
        order_doc.update(await payments.midtrans_create(order_doc))
    elif body.payment_method == "xendit":
        order_doc.update(await payments.xendit_create(order_doc))
    await db.orders.insert_one(order_doc)
    for i in cart.items:  # reserve stock (9999 = unlimited from website import)
        if i.stock < 9999:
            await db.products.update_one({"product_id": i.product_id}, {"$inc": {"stock": -i.quantity}})
    await db.carts.update_one({"owner": owner}, {"$set": {"items": []}}, upsert=True)
    background.add_task(notify.send_owner_order, order_doc)
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
    return _order_out(d)


@api.post("/payments/midtrans/notification")
async def midtrans_notification(request: Request):
    p = await request.json()
    if not payments.midtrans_verify(p):
        raise HTTPException(status_code=403, detail="Invalid signature")
    order = await db.orders.find_one({"order_id": p.get("order_id")}, {"total": 1, "status": 1})
    if not order:
        return {"ok": True}
    if int(float(p.get("gross_amount", 0))) != order["total"]:
        raise HTTPException(status_code=400, detail="Amount mismatch")
    if order["status"] != "paid":
        await db.orders.update_one({"order_id": p["order_id"]}, {"$set": {
            "status": payments.midtrans_map(p), "payment_raw": p, "updated_at": datetime.now(timezone.utc)}})
    return {"ok": True}


@api.post("/payments/xendit/callback")
async def xendit_callback(request: Request, x_callback_token: Optional[str] = Header(default=None)):
    if not payments.xendit_verify(x_callback_token):
        raise HTTPException(status_code=401, detail="Invalid callback token")
    p = await request.json()
    order = await db.orders.find_one({"order_id": p.get("external_id")}, {"total": 1, "status": 1})
    if not order:
        return {"ok": True}
    if int(p.get("amount", 0)) != order["total"]:
        raise HTTPException(status_code=400, detail="Amount mismatch")
    if order["status"] != "paid":
        await db.orders.update_one({"order_id": p["external_id"]}, {"$set": {
            "status": payments.xendit_map(p.get("status")), "payment_raw": p, "updated_at": datetime.now(timezone.utc)}})
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
    return _order_out(d)


@api.get("/admin/pricing")
async def admin_get_pricing(_=Depends(require_admin)):
    return await get_pricing(db)


@api.put("/admin/pricing")
async def admin_set_pricing(body: PricingIn, _=Depends(require_admin)):
    td = {t: max(0.0, min(100.0, float(body.type_discounts.get(t, 0)))) for t in CUSTOMER_TYPES}
    tiers = sorted({t.min_qty: t for t in body.qty_tiers}.values(), key=lambda t: t.min_qty)
    doc = {"key": "pricing", "type_discounts": td, "qty_tiers": [t.model_dump() for t in tiers]}
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


@app.on_event("shutdown")
async def _shutdown():
    app.state.index_task.cancel()
    with suppress(asyncio.CancelledError):
        await app.state.index_task
    client.close()
