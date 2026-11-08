# PGS iteration 15: rejected checkout (COD+courier / online not ready) must not consume voucher quota.
import os
import uuid
from datetime import datetime, timezone

import pytest
import requests
from test_pgs_iter15_cod_pickup_expiry import API, DB, H, _add, _checkout  # noqa: F401

CODE = f"TEST{uuid.uuid4().hex[:6].upper()}"


@pytest.fixture(scope="module", autouse=True)
def voucher():
    DB.vouchers.insert_one({"code": CODE, "title": "TEST voucher", "description": "", "mode": "rupiah", "value": 1000,
                            "max_discount": 0, "min_purchase": 0, "quota": 5, "ends_at": None, "active": True,
                            "show_on_home": False, "used": 0, "created_at": datetime.now(timezone.utc)})
    yield
    DB.vouchers.delete_one({"code": CODE})


@pytest.fixture()
def buyer():
    r = requests.post(f"{API}/auth/register", json={"email": f"test_cod15_{uuid.uuid4().hex[:8]}@example.com",
                                                     "password": "TestPass123!", "name": "TEST V"})
    t = r.json()["token"]
    yield t
    requests.delete(f"{API}/cart", headers=H(t))


@pytest.mark.parametrize("courier,pm", [("jne", "cod"), ("jne", "midtrans")])
def test_rejected_checkout_keeps_voucher_quota(buyer, courier, pm):
    _add(buyer)
    r = _checkout(buyer, courier=courier, pm=pm, voucher_code=CODE)
    assert r.status_code == 400, r.text
    assert DB.vouchers.find_one({"code": CODE})["used"] == 0, "voucher 'used' incremented on rejected checkout"
