# Iteration 3: payment_method, owner reports, courier delivery photo + note, photo download
import io
import os
import struct
import zlib
from datetime import datetime, timedelta, timezone

import pytest
import requests
from pymongo import MongoClient


def _base():
    url = os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    if not url:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
                    url = line.split("=", 1)[1].strip().strip('"')
    return url.rstrip("/")


BASE = _base() + "/api"


def _h(t):
    return {"Authorization": f"Bearer {t}"}


def _env(key):
    with open("/app/backend/.env") as f:
        for line in f:
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"')


def _png():
    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    raw = b"\x00\xff\x00\x00"
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


@pytest.fixture(scope="module")
def owner():
    r = requests.post(f"{BASE}/auth/login", json={"email": "admin@delivery.com", "password": "Admin12345"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def courier():
    r = requests.post(f"{BASE}/auth/courier/login", json={"phone": "1100000001", "pin": "123456"})
    assert r.status_code == 200, r.text
    d = r.json()
    return d["token"], d["user"]["id"]


@pytest.fixture(scope="module")
def courier2():
    r = requests.post(f"{BASE}/auth/courier/login", json={"phone": "1100000002", "pin": "654321"})
    assert r.status_code == 200, r.text
    d = r.json()
    return d["token"], d["user"]["id"]


@pytest.fixture(scope="module")
def business(owner):
    r = requests.get(f"{BASE}/businesses", headers=_h(owner))
    assert r.status_code == 200
    return r.json()[0]["id"]


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    db = MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]
    db.orders.delete_many({"customer_name": {"$regex": "^TEST_"}})


def _mk(owner, business, pm=None, courier_id=None, amount=10.0, fee=2.0):
    body = {"business_id": business, "customer_name": "TEST_rep", "address": "TEST st 1",
            "amount": amount, "delivery_fee": fee}
    if pm:
        body["payment_method"] = pm
    if courier_id:
        body["courier_id"] = courier_id
    return requests.post(f"{BASE}/orders", headers=_h(owner), json=body)


def _rep(tok, s, e):
    return requests.get(f"{BASE}/reports", headers=_h(tok), params={"start": s.isoformat(), "end": e.isoformat()})


# Payment method on create / update
class TestPayment:
    def test_default_efectivo(self, owner, business):
        r = _mk(owner, business)
        assert r.status_code == 200, r.text
        assert r.json()["payment_method"] == "efectivo"

    @pytest.mark.parametrize("pm", ["pagado", "datafono", "efectivo"])
    def test_create_with_pm(self, owner, business, pm):
        r = _mk(owner, business, pm)
        assert r.status_code == 200
        oid_ = r.json()["id"]
        g = requests.get(f"{BASE}/orders/{oid_}", headers=_h(owner))
        assert g.json()["payment_method"] == pm

    def test_invalid_pm_422(self, owner, business):
        assert _mk(owner, business, "bitcoin").status_code == 422

    def test_patch_payment(self, owner, business):
        oid_ = _mk(owner, business, "efectivo").json()["id"]
        r = requests.patch(f"{BASE}/orders/{oid_}/payment", headers=_h(owner), json={"payment_method": "datafono"})
        assert r.status_code == 200 and r.json()["payment_method"] == "datafono"
        assert requests.get(f"{BASE}/orders/{oid_}", headers=_h(owner)).json()["payment_method"] == "datafono"
        bad = requests.patch(f"{BASE}/orders/{oid_}/payment", headers=_h(owner), json={"payment_method": "x"})
        assert bad.status_code == 422

    def test_patch_payment_courier_forbidden(self, owner, business, courier):
        oid_ = _mk(owner, business).json()["id"]
        r = requests.patch(f"{BASE}/orders/{oid_}/payment", headers=_h(courier[0]), json={"payment_method": "pagado"})
        assert r.status_code == 403


# Owner reports
class TestReports:
    def test_report_totals_delta(self, owner, business):
        now = datetime.now(timezone.utc)
        s, e = now - timedelta(hours=1), now + timedelta(hours=1)
        before = _rep(owner, s, e).json()
        _mk(owner, business, "pagado", amount=10, fee=2)
        _mk(owner, business, "datafono", amount=20, fee=3)
        c = _mk(owner, business, "efectivo", amount=100, fee=5).json()["id"]
        requests.patch(f"{BASE}/orders/{c}/status", headers=_h(owner), json={"status": "cancelado"})
        after = _rep(owner, s, e).json()
        assert after["count"] - before["count"] == 3
        assert after["cancelled"] - before["cancelled"] == 1
        assert round(after["revenue"] - before["revenue"], 2) == 35.0
        assert round(after["fees"] - before["fees"], 2) == 5.0
        assert round(after["by_payment"]["pagado"] - before["by_payment"]["pagado"], 2) == 12.0
        assert round(after["by_payment"]["datafono"] - before["by_payment"]["datafono"], 2) == 23.0
        assert round(after["by_payment"]["efectivo"] - before["by_payment"]["efectivo"], 2) == 0.0
        assert len(after["orders"]) == after["count"]
        assert all("_id" not in o for o in after["orders"])

    def test_report_month_has_history(self, owner):
        e = datetime.now(timezone.utc) + timedelta(days=1)
        r = _rep(owner, e - timedelta(days=60), e)
        assert r.status_code == 200
        d = r.json()
        assert d["delivered"] > 0 and d["revenue"] > 0
        assert set(d["by_payment"].keys()) == {"pagado", "efectivo", "datafono"}
        assert round(sum(d["by_payment"].values()), 2) == d["revenue"]

    def test_report_courier_403(self, courier):
        now = datetime.now(timezone.utc)
        assert _rep(courier[0], now - timedelta(days=1), now).status_code == 403

    def test_report_invalid_dates_400(self, owner):
        r = requests.get(f"{BASE}/reports", headers=_h(owner), params={"start": "abc", "end": "xyz"})
        assert r.status_code == 400

    def test_report_noauth(self):
        r = requests.get(f"{BASE}/reports", params={"start": "2026-01-01T00:00:00Z", "end": "2026-02-01T00:00:00Z"})
        assert r.status_code in (401, 403)


# Courier delivery photo + note
class TestPhotoNote:
    def test_full_flow(self, owner, business, courier, courier2):
        tok, cid = courier
        oid_ = _mk(owner, business, "datafono", courier_id=cid).json()["id"]
        # courier2 not assigned -> 404
        r = requests.post(f"{BASE}/courier/orders/{oid_}/photo", headers=_h(courier2[0]),
                          files={"file": ("p.png", _png(), "image/png")})
        assert r.status_code == 404
        # non image rejected
        r = requests.post(f"{BASE}/courier/orders/{oid_}/photo", headers=_h(tok),
                          files={"file": ("a.txt", b"hello", "text/plain")})
        assert r.status_code == 400
        # owner cannot upload
        r = requests.post(f"{BASE}/courier/orders/{oid_}/photo", headers=_h(owner),
                          files={"file": ("p.png", _png(), "image/png")})
        assert r.status_code == 403
        # valid upload
        r = requests.post(f"{BASE}/courier/orders/{oid_}/photo", headers=_h(tok),
                          files={"file": ("p.png", _png(), "image/png")})
        assert r.status_code == 200, r.text
        d = requests.get(f"{BASE}/orders/{oid_}", headers=_h(owner)).json()
        assert d["delivery_photo"]
        # deliver with note
        r = requests.patch(f"{BASE}/courier/orders/{oid_}/status", headers=_h(tok),
                           json={"status": "entregado", "note": "  TEST nota portero  "})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "entregado"
        d = requests.get(f"{BASE}/orders/{oid_}", headers=_h(owner)).json()
        assert d["delivery_note"] == "TEST nota portero"
        # closed order rejects photo
        r = requests.post(f"{BASE}/courier/orders/{oid_}/photo", headers=_h(tok),
                          files={"file": ("p.png", _png(), "image/png")})
        assert r.status_code == 400
        # download photo as owner / courier
        for t in (owner, tok):
            g = requests.get(f"{BASE}/orders/{oid_}/photo", params={"token": t})
            assert g.status_code == 200
            assert g.headers["content-type"].startswith("image/")
            assert g.content[:4] == b"\x89PNG"
        # courier2 -> 404, bad token -> 401
        assert requests.get(f"{BASE}/orders/{oid_}/photo", params={"token": courier2[0]}).status_code == 404
        assert requests.get(f"{BASE}/orders/{oid_}/photo", params={"token": "bad"}).status_code == 401

    def test_photo_missing_404(self, owner, business):
        oid_ = _mk(owner, business).json()["id"]
        assert requests.get(f"{BASE}/orders/{oid_}/photo", params={"token": owner}).status_code == 404

    def test_note_too_long_422(self, owner, business, courier):
        oid_ = _mk(owner, business, courier_id=courier[1]).json()["id"]
        r = requests.patch(f"{BASE}/courier/orders/{oid_}/status", headers=_h(courier[0]),
                           json={"status": "entregado", "note": "x" * 501})
        assert r.status_code == 422

    def test_deliver_without_note(self, owner, business, courier):
        oid_ = _mk(owner, business, courier_id=courier[1]).json()["id"]
        r = requests.patch(f"{BASE}/courier/orders/{oid_}/status", headers=_h(courier[0]), json={"status": "entregado"})
        assert r.status_code == 200
        assert r.json()["delivery_note"] == ""
