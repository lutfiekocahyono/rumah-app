# PGS iter35: Accurate callback page, product-detail chat (branch store), COD pickup order states (open/completed/cancelled).
import os
import sys

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
import ui_iter35_helper as hp  # noqa: E402

API = hp.API


@pytest.fixture(scope="module")
def tok():
    return {"demo": hp.login("demo@pgs.id", "Demo1234!"), "admin": hp.login("admin@pgs.id", "Admin1234!")}


@pytest.fixture(scope="module")
def orders():
    st = hp.create()
    yield st
    hp.clean()


# Accurate: callback page + admin settings still reachable
class TestAccurate:
    def test_callback_html(self):
        r = requests.get(f"{API}/accurate/callback", timeout=20)
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert "Integrasi Accurate Online" in r.text

    def test_settings_admin_only(self, tok):
        assert requests.get(f"{API}/admin/accurate/settings", headers=hp.H(tok["demo"]), timeout=20).status_code == 403
        r = requests.get(f"{API}/admin/accurate/settings", headers=hp.H(tok["admin"]), timeout=20)
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), dict)


# Chat start used by pd-chat-btn
class TestChat:
    def test_guest_401(self):
        assert requests.post(f"{API}/chats", json={"store_id": "pgs-jombang"}, timeout=20).status_code == 401

    @pytest.mark.parametrize("sid", ["pgs-jombang", "pgs-official"])
    def test_start_branch(self, tok, sid):
        before = hp.DB.conversations.count_documents({"store_id": sid})
        r = requests.post(f"{API}/chats", headers=hp.H(tok["demo"]), json={"store_id": sid}, timeout=20)
        assert r.status_code == 200, r.text
        c = r.json()
        assert c["store_id"] == sid and c["conv_id"].startswith("cv_")
        assert hp.DB.conversations.count_documents({"store_id": sid}) == before  # reuses existing conversation
        g = requests.get(f"{API}/chats/{c['conv_id']}", headers=hp.H(tok["demo"]), timeout=20)
        assert g.status_code == 200

    def test_branch_without_order_403(self, tok):
        r = requests.post(f"{API}/chats", headers=hp.H(tok["demo"]), json={"store_id": "pgs-jember"}, timeout=20)
        print("jember ->", r.status_code, r.text)
        assert r.status_code == 403

    def test_unknown_store_404(self, tok):
        r = requests.post(f"{API}/chats", headers=hp.H(tok["demo"]), json={"store_id": "TEST_nope"}, timeout=20)
        assert r.status_code == 404


# COD pickup order states drive order-cod-note
class TestCodStates:
    def test_complete_and_cancel_ok(self, orders):
        assert orders["complete_resp"] == 200 and orders["cancel_resp"] == 200

    @pytest.mark.parametrize("k,status", [("open", "cod"), ("completed", "completed"), ("cancelled", "cancelled")])
    def test_order_status(self, tok, orders, k, status):
        r = requests.get(f"{API}/orders/{orders['orders'][k]['order_id']}", headers=hp.H(tok["demo"]), timeout=20)
        assert r.status_code == 200
        o = r.json()
        assert o["status"] == status and o["payment_method"] == "cod" and o["courier"]["code"] == "pickup"
