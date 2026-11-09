"""Halaman toko cabang: hanya produk yang punya harga cabang (store_stock) + produk khusus cabang itu.
Frontend mengirim header `X-Shop-Page: 1` selama halaman toko cabang terbuka."""
from contextvars import ContextVar
from typing import List, Optional

import seller

ON: ContextVar[bool] = ContextVar("shop_page", default=False)


class Middleware:
    """Pure ASGI middleware: sets ON for the request when the X-Shop-Page header is present."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            on = any(k == b"x-shop-page" and v == b"1" for k, v in scope.get("headers", []))
            token = ON.set(on)
            try:
                return await self.app(scope, receive, send)
            finally:
                ON.reset(token)
        return await self.app(scope, receive, send)


def branch(b: Optional[str]) -> Optional[str]:
    """The branch whose store page is being viewed, or None (not on a branch store page / Sidoarjo = master catalog)."""
    return b if ON.get() and b in seller.OFFICIAL_IDS and b != seller.PGS_STORE_ID else None


async def priced_ids(db, b: str) -> List[str]:
    return await db.store_stock.distinct("product_id", {"store_id": b, "price": {"$gt": 0}})


async def clause(db, b: str) -> dict:
    """Branch price set (salinan massal atau manual, stok 0 ikut) or a product added for this branch only."""
    return {"$or": [{"only_branch": b}, {"product_id": {"$in": await priced_ids(db, b)}}]}
