# Iteration 4: fee-only totals (courier history, reports, dashboard), courier payouts, Photon geocoding
from datetime import datetime, timedelta, timezone

import pytest
import requests

from bson import ObjectId
from pymongo import MongoClient

from test_reports_payment_photo import BASE, _h, _env

CARLOS = {"phone": "1100000001", "pin": "123456"}
LUCIA = {"phone": "1100000002", "pin": "654321"}


def _login_courier(c):
    r = requests.post(f"{BASE}/auth/courier/login", json=c)
    assert r.status_code == 200, r.text
    return r.json()["token"], r.json()["user"]["id"]


def _range():
    now = datetime.now(timezone.utc)
    return (now - timedelta(days=1)).isoformat(), (now + timedelta(days=1)).isoformat()


@pytest.fixture(scope="module")
def owner():
    r = requests.post(f"{BASE}/auth/login", json={"email": "admin@delivery.com", "password": "Admin12345"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def biz(owner):
    bs = requests.get(f"{BASE}/businesses", headers=_h(owner)).json()
    b = next(b for b in bs if b.get("lat") is not None)
    return b["id"]


@pytest.fixture(scope="module")
def created(owner):
    ids = []
    yield ids
    db = MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]
    db.orders.delete_many({"_id": {"$in": [ObjectId(i) for i in ids]}, "customer_name": "TEST_cliente"})


def _order(owner, biz, created, courier_id=None, fee=3.25, amount=20.0, address="C. de Bellver, 27, Tetuán, 28039 Madrid"):
    r = requests.post(f"{BASE}/orders", headers=_h(owner), json={
        "business_id": biz, "customer_name": "TEST_cliente", "customer_phone": "600000000",
        "address": address, "amount": amount, "delivery_fee": fee, "items": [],
        "courier_id": courier_id, "payment_method": "efectivo"})
    assert r.status_code in (200, 201), r.text
    o = r.json()
    created.append(o["id"])
    return o


# Geocoding: Photon first
class TestGeocoding:
    def test_bellver_address_geocoded(self, owner, biz, created):
        o = _order(owner, biz, created)
        assert o["dest_lat"] is not None and o["dest_lng"] is not None
        assert 40.3 < o["dest_lat"] < 40.6 and -3.9 < o["dest_lng"] < -3.5


# Fee-only totals
class TestFeeTotals:
    def test_courier_history_sums_fees(self, owner, biz, created):
        tok, cid = _login_courier(LUCIA)
        s, e = _range()
        before = requests.get(f"{BASE}/courier/history", headers=_h(tok), params={"start": s, "end": e}).json()
        o = _order(owner, biz, created, courier_id=cid, fee=4.5, amount=30)
        for st in ("en_camino", "entregado"):
            r = requests.patch(f"{BASE}/courier/orders/{o['id']}/status", headers=_h(tok), json={"status": st, "note": ""})
            assert r.status_code == 200, r.text
        after = requests.get(f"{BASE}/courier/history", headers=_h(tok), params={"start": s, "end": e}).json()
        assert after["count"] == before["count"] + 1
        assert round(after["total_collected"] - before["total_collected"], 2) == 4.5
        assert round(sum(x["delivery_fee"] for x in after["orders"]), 2) == after["total_collected"]

    def test_reports_and_dashboard_use_fees(self, owner, biz, created):
        s, e = _range()
        r0 = requests.get(f"{BASE}/reports", headers=_h(owner), params={"start": s, "end": e}).json()
        d0 = requests.get(f"{BASE}/dashboard", headers=_h(owner)).json()
        _order(owner, biz, created, fee=2.75, amount=50)
        c = _order(owner, biz, created, fee=9.0, amount=50)
        assert requests.patch(f"{BASE}/orders/{c['id']}/status", headers=_h(owner), json={"status": "cancelado"}).status_code == 200
        r1 = requests.get(f"{BASE}/reports", headers=_h(owner), params={"start": s, "end": e}).json()
        d1 = requests.get(f"{BASE}/dashboard", headers=_h(owner)).json()
        assert round(r1["revenue"] - r0["revenue"], 2) == 2.75
        assert round(d1["revenue_today"] - d0["revenue_today"], 2) == 2.75
        exp = round(sum(o["delivery_fee"] for o in r1["orders"] if o["status"] != "cancelado"), 2)
        assert round(r1["revenue"], 2) == exp
        assert round(sum(c["total"] for c in r1["by_courier"]), 2) == exp
        for bc in r1["by_courier"]:
            fees = round(sum(o["delivery_fee"] for o in r1["orders"] if o["status"] != "cancelado" and (o.get("courier_id") or "none") == (bc["courier_id"] or "none")), 2)
            assert bc["total"] == fees, bc


# Courier payouts
class TestPayouts:
    def test_courier_forbidden(self):
        tok, _ = _login_courier(CARLOS)
        assert requests.get(f"{BASE}/payouts", headers=_h(tok)).status_code == 403

    def test_payout_flow_lucia(self, owner, biz, created):
        tok, cid = _login_courier(LUCIA)
        o = _order(owner, biz, created, courier_id=cid, fee=1.5)
        for st in ("en_camino", "entregado"):
            assert requests.patch(f"{BASE}/courier/orders/{o['id']}/status", headers=_h(tok), json={"status": st, "note": ""}).status_code == 200
        rows = requests.get(f"{BASE}/payouts", headers=_h(owner)).json()
        row = next(r for r in rows if r["courier_id"] == cid)
        assert row["pending_count"] >= 1 and row["pending_total"] >= 1.5
        co = requests.get(f"{BASE}/courier/orders", headers=_h(tok)).json()
        assert co["pending_total"] == row["pending_total"] and co["pending_count"] == row["pending_count"]
        p = requests.post(f"{BASE}/payouts/{cid}", headers=_h(owner))
        assert p.status_code == 200, p.text
        assert p.json()["amount"] == row["pending_total"] and p.json()["count"] == row["pending_count"]
        row2 = next(r for r in requests.get(f"{BASE}/payouts", headers=_h(owner)).json() if r["courier_id"] == cid)
        assert row2["pending_total"] == 0 and row2["pending_count"] == 0 and row2["last_paid_at"]
        assert row2["last_paid_amount"] == row["pending_total"]
        assert requests.post(f"{BASE}/payouts/{cid}", headers=_h(owner)).status_code == 400
        h = requests.get(f"{BASE}/payouts/{cid}/history", headers=_h(owner))
        assert h.status_code == 200 and h.json()[0]["amount"] == row["pending_total"]
        co2 = requests.get(f"{BASE}/courier/orders", headers=_h(tok)).json()
        assert co2["pending_total"] == 0

    def test_payout_unknown_courier(self, owner):
        assert requests.post(f"{BASE}/payouts/000000000000000000000000", headers=_h(owner)).status_code in (400, 404)
        assert requests.get(f"{BASE}/payouts/000000000000000000000000/history", headers=_h(owner)).status_code in (400, 404)
