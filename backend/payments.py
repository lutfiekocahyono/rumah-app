"""Midtrans Snap + Xendit Invoice helpers. Keys come from backend/.env only."""
import base64
import hashlib
import hmac
import os

import httpx
from fastapi import HTTPException


def _midtrans_key() -> str:
    key = os.environ.get("MIDTRANS_SERVER_KEY", "")
    if not key:
        raise HTTPException(status_code=503, detail="Pembayaran Midtrans belum dikonfigurasi")
    return key


def _midtrans_urls() -> tuple[str, str]:
    prod = os.environ.get("MIDTRANS_IS_PRODUCTION", "false").lower() == "true"
    if prod:
        return "https://app.midtrans.com/snap/v1/transactions", "https://api.midtrans.com/v2"
    return "https://app.sandbox.midtrans.com/snap/v1/transactions", "https://api.sandbox.midtrans.com/v2"


def _midtrans_headers() -> dict:
    token = base64.b64encode(f"{_midtrans_key()}:".encode()).decode()
    return {"Accept": "application/json", "Content-Type": "application/json", "Authorization": f"Basic {token}"}


async def midtrans_create(order: dict) -> dict:
    snap_url, _ = _midtrans_urls()
    items = [
        {"id": i["product_id"][:50], "price": i["price"], "quantity": i["quantity"], "name": i["name"][:50]}
        for i in order["items"]
    ]
    if order.get("shipping_cost"):
        items.append({"id": "ongkir", "price": order["shipping_cost"], "quantity": 1, "name": "Ongkos Kirim"})
    ship = order["shipping"]
    payload = {
        "transaction_details": {"order_id": order["order_id"], "gross_amount": order["total"]},
        "item_details": items,
        "customer_details": {"first_name": ship["full_name"][:50], "phone": ship["phone"][:20],
                              **({"email": order["email"]} if order.get("email") else {})},
        "enabled_payments": ["other_qris", "gopay", "shopeepay", "bca_va", "bni_va", "bri_va", "permata_va", "echannel"],
    }
    async with httpx.AsyncClient(timeout=25) as c:
        r = await c.post(snap_url, json=payload, headers=_midtrans_headers())
    if r.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Midtrans error: {r.text[:300]}")
    data = r.json()
    return {"payment_url": data["redirect_url"], "payment_ref": data["token"]}


async def midtrans_status(order_id: str) -> str | None:
    _, status_url = _midtrans_urls()
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(f"{status_url}/{order_id}/status", headers=_midtrans_headers())
    if r.status_code >= 400:
        return None
    p = r.json()
    if str(p.get("status_code")) == "404":
        return None
    return midtrans_map(p)


def midtrans_map(p: dict) -> str:
    ts = p.get("transaction_status")
    if ts in ("settlement", "capture") and p.get("fraud_status", "accept").lower() == "accept":
        return "paid"
    if ts == "expire":
        return "expired"
    if ts in ("deny", "cancel", "failure"):
        return "failed"
    return "pending"


def midtrans_verify(p: dict) -> bool:
    raw = f'{p.get("order_id")}{p.get("status_code")}{p.get("gross_amount")}{_midtrans_key()}'
    expected = hashlib.sha512(raw.encode()).hexdigest()
    return hmac.compare_digest(expected, str(p.get("signature_key", "")))


def _xendit_key() -> str:
    key = os.environ.get("XENDIT_SECRET_KEY", "")
    if not key:
        raise HTTPException(status_code=503, detail="Pembayaran Xendit belum dikonfigurasi")
    return key


async def xendit_create(order: dict) -> dict:
    payload = {
        "external_id": order["order_id"],
        "amount": order["total"],
        "currency": "IDR",
        "description": f"Pesanan {order['order_id']} - Pusat Grosir Sidoarjo",
        "invoice_duration": 86400,
        "customer": {"given_names": order["shipping"]["full_name"][:50], "mobile_number": order["shipping"]["phone"][:20]},
        "items": [{"name": i["name"][:100], "quantity": i["quantity"], "price": i["price"]} for i in order["items"]],
        "fees": [{"type": "Ongkos Kirim", "value": order.get("shipping_cost", 0)}] if order.get("shipping_cost") else [],
    }
    if order.get("email"):
        payload["payer_email"] = order["email"]
    async with httpx.AsyncClient(base_url="https://api.xendit.co", auth=(_xendit_key(), ""), timeout=25) as c:
        r = await c.post("/v2/invoices", json=payload)
    if r.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Xendit error: {r.text[:300]}")
    inv = r.json()
    return {"payment_url": inv["invoice_url"], "payment_ref": inv["id"]}


def xendit_map(status: str) -> str:
    s = (status or "").upper()
    if s in ("PAID", "SETTLED"):
        return "paid"
    if s == "EXPIRED":
        return "expired"
    if s == "FAILED":
        return "failed"
    return "pending"


async def xendit_status(invoice_id: str) -> str | None:
    async with httpx.AsyncClient(base_url="https://api.xendit.co", auth=(_xendit_key(), ""), timeout=20) as c:
        r = await c.get(f"/v2/invoices/{invoice_id}")
    if r.status_code >= 400:
        return None
    return xendit_map(r.json().get("status"))


def xendit_verify(token: str | None) -> bool:
    expected = os.environ.get("XENDIT_WEBHOOK_TOKEN", "")
    return bool(expected) and hmac.compare_digest(expected, token or "")
