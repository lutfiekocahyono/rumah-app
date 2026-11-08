"""Order lifecycle helpers: release voucher/stock/saldo on cancel, and the COD pickup auto-cancel loop."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

import seller
import support

RELEASE_STATUSES = ("cancelled", "expired", "failed")
COD_PICKUP_HOURS = 48
COD_REMIND_HOURS = 6  # remind the store admin this long before auto-cancel

logger = logging.getLogger(__name__)


def register(db, notify_user):
    """Returns (release_order, expire_cod_orders, remind_expiring_cod, expire_loop)."""

    async def release_order(order_id: str) -> None:
        """Give a voucher use back once when an order is cancelled/expired/failed; stock and saldo come back too."""
        o = await db.orders.find_one_and_update(
            {"order_id": order_id, "voucher_code": {"$nin": [None, ""]}, "voucher_released": {"$ne": True}},
            {"$set": {"voucher_released": True}})
        if o:
            await db.vouchers.update_one({"code": o["voucher_code"], "used": {"$gt": 0}}, {"$inc": {"used": -1}})
        await seller.restock_once(db, order_id)
        await support.return_balance_once(db, order_id)

    async def expire_cod_orders() -> int:
        """Cancel COD pickup orders the store did not process within the deadline."""
        now = datetime.now(timezone.utc)
        n = 0
        async for o in db.orders.find({"status": "cod", "expires_at": {"$lte": now}}, {"order_id": 1, "user_id": 1}):
            res = await db.orders.update_one({"order_id": o["order_id"], "status": "cod"}, {"$set": {"status": "cancelled", "updated_at": now},
                                             "$push": {"status_history": {"status": "cancelled", "at": now, "note": "Batal otomatis: tidak diproses toko dalam batas waktu"}}})
            if not res.modified_count:
                continue
            await release_order(o["order_id"])
            await notify_user(o.get("user_id"), "order", "Pesanan dibatalkan otomatis",
                              f"Pesanan {o['order_id']} batal karena belum diproses toko dalam batas waktu.", f"/order/{o['order_id']}")
            n += 1
        return n

    async def remind_expiring_cod() -> int:
        """Warn the store admin once when a COD pickup order is close to auto-cancel."""
        now = datetime.now(timezone.utc)
        n = 0
        async for o in db.orders.find({"status": "cod", "expires_at": {"$gt": now, "$lte": now + timedelta(hours=COD_REMIND_HOURS)},
                                       "expiry_reminded": {"$ne": True}}, {"order_id": 1, "store_id": 1, "expires_at": 1}):
            res = await db.orders.update_one({"order_id": o["order_id"], "expiry_reminded": {"$ne": True}}, {"$set": {"expiry_reminded": True}})
            if not res.modified_count:
                continue
            store = await db.stores.find_one({"store_id": o["store_id"]}, {"owner_id": 1})
            if store:
                exp = o["expires_at"].replace(tzinfo=timezone.utc) if o["expires_at"].tzinfo is None else o["expires_at"]
                left = max(1, round((exp - now).total_seconds() / 3600))
                await notify_user(store["owner_id"], "order", "Pesanan COD hampir batal otomatis",
                                  f"Pesanan {o['order_id']} batal otomatis dalam ±{left} jam. Proses atau perpanjang sekarang.",
                                  f"/seller/order/{o['order_id']}")
                n += 1
        return n

    async def expire_loop() -> None:
        while True:
            try:
                await remind_expiring_cod()
                await expire_cod_orders()
            except Exception:
                logger.exception("expire_cod_orders failed")
            await asyncio.sleep(300)

    return release_order, expire_cod_orders, remind_expiring_cod, expire_loop
