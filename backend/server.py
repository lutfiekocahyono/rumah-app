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
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query
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
        IndexModel([("name", ASCENDING)], name="name"),
    ],
    "categories": [
        IndexModel([("category_id", ASCENDING)], name="category_id", unique=True),
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
    if not await db.users.find_one({"email": "demo@pgs.id"}):
        hashed = bcrypt.hashpw("Demo1234!".encode(), bcrypt.gensalt()).decode()
        await db.users.insert_one({
            "user_id": f"user_{uuid.uuid4().hex[:12]}",
            "email": "demo@pgs.id",
            "name": "Demo User",
            "password_hash": hashed,
            "created_at": datetime.now(timezone.utc),
        })


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


class User(BaseModel):
    user_id: str
    email: EmailStr
    name: str


class AuthOut(BaseModel):
    token: str
    user: User


class Category(BaseModel):
    category_id: str
    name: str
    icon: str
    image: str


class Product(BaseModel):
    product_id: str
    name: str
    category: str
    price: int
    original_price: int
    discount: int
    rating: float
    sold: int
    image: str
    images: List[str] = []
    description: str
    stock: int


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
    price: int
    original_price: int
    image: str
    stock: int


class CartOut(BaseModel):
    items: List[CartItemDetailed]
    subtotal: int
    item_count: int


class WishlistOut(BaseModel):
    items: List[Product]


class CheckoutIn(BaseModel):
    full_name: str
    phone: str
    address: str
    city: str
    payment_method: str = "mock"


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
    total: int
    shipping: dict
    status: str
    created_at: datetime


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


async def get_current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = await db.users.find_one({"user_id": payload.get("sub")}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def get_owner(
    authorization: Optional[str] = Header(default=None),
    x_guest_id: Optional[str] = Header(default=None),
) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
            return f"user:{payload.get('sub')}"
        except jwt.PyJWTError:
            pass
    if x_guest_id:
        return f"guest:{x_guest_id}"
    raise HTTPException(status_code=400, detail="Missing identity")


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


@api.post("/auth/register", response_model=AuthOut)
async def register(body: RegisterIn, x_guest_id: Optional[str] = Header(default=None)):
    existing = await db.users.find_one({"email": body.email.lower()})
    if existing:
        raise HTTPException(status_code=400, detail="Email sudah terdaftar")
    user_doc = {
        "user_id": f"user_{uuid.uuid4().hex[:12]}",
        "email": body.email.lower(),
        "name": body.name.strip(),
        "password_hash": _hash(body.password),
        "created_at": datetime.now(timezone.utc),
    }
    await db.users.insert_one(user_doc)
    await _merge_guest(x_guest_id, user_doc["user_id"])
    token = _make_token(user_doc["user_id"])
    return AuthOut(token=token, user=User(user_id=user_doc["user_id"], email=user_doc["email"], name=user_doc["name"]))


@api.post("/auth/login", response_model=AuthOut)
async def login(body: LoginIn, x_guest_id: Optional[str] = Header(default=None)):
    user = await db.users.find_one({"email": body.email.lower()})
    if not user or not _verify(body.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Email atau password salah")
    await _merge_guest(x_guest_id, user["user_id"])
    token = _make_token(user["user_id"])
    return AuthOut(token=token, user=User(user_id=user["user_id"], email=user["email"], name=user["name"]))


@api.get("/auth/me", response_model=User)
async def me(current=Depends(get_current_user)):
    return User(user_id=current["user_id"], email=current["email"], name=current["name"])


@api.get("/categories", response_model=List[Category])
async def list_categories():
    docs = await db.categories.find({}, {"_id": 0}).to_list(100)
    return [Category(**d) for d in docs]


@api.get("/products", response_model=List[Product])
async def list_products(
    category: Optional[str] = None,
    q: Optional[str] = None,
    sort: str = Query("popular", pattern="^(popular|price_asc|price_desc|rating|newest)$"),
    limit: int = Query(50, ge=1, le=200),
):
    query: dict = {}
    if category:
        query["category"] = category
    if q:
        query["name"] = {"$regex": re.escape(q), "$options": "i"}
    sort_map = {
        "popular": [("sold", -1)],
        "price_asc": [("price", 1)],
        "price_desc": [("price", -1)],
        "rating": [("rating", -1)],
        "newest": [("created_at", -1)],
    }
    docs = await db.products.find(query, {"_id": 0}).sort(sort_map[sort]).limit(limit).to_list(limit)
    return [Product(**d) for d in docs]


@api.get("/products/{product_id}", response_model=Product)
async def get_product(product_id: str):
    doc = await db.products.find_one({"product_id": product_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
    return Product(**doc)


async def _load_cart_detailed(owner: str) -> CartOut:
    cart = await db.carts.find_one({"owner": owner}, {"_id": 0}) or {"owner": owner, "items": []}
    items = cart.get("items", [])
    if not items:
        return CartOut(items=[], subtotal=0, item_count=0)
    ids = [i["product_id"] for i in items]
    prods = {p["product_id"]: p for p in await db.products.find({"product_id": {"$in": ids}}, {"_id": 0}).to_list(200)}
    detailed: List[CartItemDetailed] = []
    subtotal = 0
    for it in items:
        p = prods.get(it["product_id"])
        if not p:
            continue
        detailed.append(CartItemDetailed(
            product_id=it["product_id"], quantity=it["quantity"], name=p["name"],
            price=p["price"], original_price=p["original_price"], image=p["image"], stock=p["stock"],
        ))
        subtotal += p["price"] * it["quantity"]
    return CartOut(items=detailed, subtotal=subtotal, item_count=sum(i.quantity for i in detailed))


@api.get("/cart", response_model=CartOut)
async def get_cart(owner: str = Depends(get_owner)):
    return await _load_cart_detailed(owner)


@api.post("/cart/items", response_model=CartOut)
async def add_to_cart(body: CartItemIn, owner: str = Depends(get_owner)):
    product = await db.products.find_one({"product_id": body.product_id})
    if not product:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
    cart = await db.carts.find_one({"owner": owner}) or {"owner": owner, "items": []}
    items = cart.get("items", [])
    for it in items:
        if it["product_id"] == body.product_id:
            it["quantity"] = min(product["stock"], it["quantity"] + body.quantity)
            break
    else:
        items.append({"product_id": body.product_id, "quantity": body.quantity})
    await db.carts.update_one({"owner": owner}, {"$set": {"items": items, "updated_at": datetime.now(timezone.utc)}}, upsert=True)
    return await _load_cart_detailed(owner)


@api.put("/cart/items/{product_id}", response_model=CartOut)
async def update_cart_item(product_id: str, body: CartQtyIn, owner: str = Depends(get_owner)):
    cart = await db.carts.find_one({"owner": owner}) or {"owner": owner, "items": []}
    items = cart.get("items", [])
    if body.quantity <= 0:
        items = [i for i in items if i["product_id"] != product_id]
    else:
        found = False
        for it in items:
            if it["product_id"] == product_id:
                it["quantity"] = body.quantity
                found = True
                break
        if not found:
            items.append({"product_id": product_id, "quantity": body.quantity})
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


@api.get("/wishlist", response_model=WishlistOut)
async def get_wishlist(owner: str = Depends(get_owner)):
    doc = await db.wishlists.find_one({"owner": owner}, {"_id": 0}) or {"items": []}
    ids = doc.get("items", [])
    if not ids:
        return WishlistOut(items=[])
    prods = await db.products.find({"product_id": {"$in": ids}}, {"_id": 0}).to_list(200)
    return WishlistOut(items=[Product(**p) for p in prods])


@api.post("/wishlist/{product_id}", response_model=WishlistOut)
async def add_wishlist(product_id: str, owner: str = Depends(get_owner)):
    await db.wishlists.update_one({"owner": owner}, {"$addToSet": {"items": product_id}}, upsert=True)
    return await get_wishlist(owner)


@api.delete("/wishlist/{product_id}", response_model=WishlistOut)
async def remove_wishlist(product_id: str, owner: str = Depends(get_owner)):
    await db.wishlists.update_one({"owner": owner}, {"$pull": {"items": product_id}})
    return await get_wishlist(owner)


@api.post("/checkout", response_model=Order)
async def checkout(body: CheckoutIn, owner: str = Depends(get_owner)):
    cart = await _load_cart_detailed(owner)
    if cart.item_count == 0:
        raise HTTPException(status_code=400, detail="Keranjang kosong")

    shipping_cost = 25000
    total = cart.subtotal + shipping_cost
    items = [OrderItem(product_id=i.product_id, name=i.name, price=i.price, quantity=i.quantity, image=i.image) for i in cart.items]
    user_id = owner.split(":", 1)[1] if owner.startswith("user:") else None
    order_doc = {
        "order_id": f"ORD-{uuid.uuid4().hex[:10].upper()}",
        "user_id": user_id,
        "owner": owner,
        "items": [i.dict() for i in items],
        "subtotal": cart.subtotal,
        "shipping_cost": shipping_cost,
        "total": total,
        "shipping": body.dict(),
        "status": "paid",
        "created_at": datetime.now(timezone.utc),
    }
    await db.orders.insert_one(order_doc)
    await db.carts.update_one({"owner": owner}, {"$set": {"items": []}}, upsert=True)
    return Order(order_id=order_doc["order_id"], user_id=user_id, items=items, total=total, shipping=body.dict(), status="paid", created_at=order_doc["created_at"])


@api.get("/orders", response_model=List[Order])
async def list_orders(owner: str = Depends(get_owner)):
    docs = await db.orders.find({"owner": owner}, {"_id": 0}).sort("created_at", -1).to_list(100)
    out: List[Order] = []
    for d in docs:
        items = [OrderItem(**i) for i in d.get("items", [])]
        out.append(Order(
            order_id=d["order_id"], user_id=d.get("user_id"), items=items,
            total=d["total"], shipping=d.get("shipping", {}), status=d.get("status", "paid"),
            created_at=d["created_at"],
        ))
    return out


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
