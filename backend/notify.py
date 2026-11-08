"""WhatsApp notification to the store owner via Fonnte (best-effort, never blocks checkout)."""
import logging
import os

import httpx

log = logging.getLogger("notify")

FONNTE_URL = "https://api.fonnte.com/send"
METHOD_LABEL = {"midtrans": "Midtrans", "xendit": "Xendit", "cod": "COD (Bayar di Tempat)"}


def _rp(n: int) -> str:
    return "Rp" + f"{int(n):,}".replace(",", ".")


def format_order(o: dict) -> str:
    s = o["shipping"]
    lines = [
        "*PESANAN BARU - Pusat Grosir Sidoarjo*",
        f"No: {o['order_id']}",
        f"Pembeli: {s['full_name']} ({s['phone']})",
        f"Kategori: {o.get('customer_type', 'langsung')}",
        f"Alamat: {s['address']}, {s['city']}",
        "",
    ]
    lines += [f"- {i['name']} x{i['quantity']} @ {_rp(i['price'])}" for i in o["items"]]
    lines += [
        "",
        f"Subtotal: {_rp(o['subtotal'])}",
        f"Ongkir: {_rp(o['shipping_cost'])}",
        f"*Total: {_rp(o['total'])}*",
        f"Bayar: {METHOD_LABEL.get(o['payment_method'], o['payment_method'])}",
    ]
    return "\n".join(lines)


async def send_owner_order(order: dict) -> None:
    token = os.environ.get("FONNTE_TOKEN", "")
    target = os.environ.get("OWNER_WHATSAPP", "")
    if not token or not target:
        log.warning("WhatsApp notification skipped (FONNTE_TOKEN/OWNER_WHATSAPP not set) order=%s", order["order_id"])
        return
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(FONNTE_URL, headers={"Authorization": token},
                             data={"target": target, "message": format_order(order), "countryCode": "62"})
        body = r.json()
        if r.is_error or body.get("status") is False:
            log.error("Fonnte failed order=%s http=%s body=%s", order["order_id"], r.status_code, body)
        else:
            log.info("Fonnte queued order=%s", order["order_id"])
    except Exception:
        log.exception("Fonnte exception order=%s", order["order_id"])
