# Iteration 5: delivery photo upload (multipart + base64), photo retrieval, empty-file rejection
import base64
import io
import struct
import zlib

import pytest
import requests
from bson import ObjectId
from pymongo import MongoClient

from test_reports_payment_photo import BASE, _h, _env

CARLOS = {"phone": "1100000001", "pin": "123456"}


def _png(w=64, h=64):
    rows = b""
    for y in range(h):
        rows += b"\x00" + b"".join(bytes([(x * 7) % 256, (y * 5) % 256, (x * y) % 256]) for x in range(w))

    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(rows, 0)) + chunk(b"IEND", b"")


@pytest.fixture(scope="module")
def owner():
    r = requests.post(f"{BASE}/auth/login", json={"email": "admin@delivery.com", "password": "Admin12345"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def carlos():
    r = requests.post(f"{BASE}/auth/courier/login", json=CARLOS)
    assert r.status_code == 200, r.text
    return r.json()["token"], r.json()["user"]["id"]


@pytest.fixture(scope="module")
def created():
    ids = []
    yield ids
    db = MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]
    db.orders.delete_many({"_id": {"$in": [ObjectId(i) for i in ids]}, "customer_name": {"$regex": "^TEST_"}})


def _new_order(owner, carlos, created):
    bs = requests.get(f"{BASE}/businesses", headers=_h(owner)).json()
    r = requests.post(f"{BASE}/orders", headers=_h(owner), json={
        "business_id": bs[0]["id"], "customer_name": "TEST_photo", "customer_phone": "600000000",
        "address": "Calle de Alcalá 100, Madrid", "items": [], "amount": 10.0, "delivery_fee": 2.0,
        "payment_method": "efectivo", "courier_id": carlos[1],
    })
    assert r.status_code in (200, 201), r.text
    o = r.json()
    created.append(o["id"])
    if o.get("courier_id") != carlos[1]:
        a = requests.patch(f"{BASE}/orders/{o['id']}/assign", headers=_h(owner), json={"courier_id": carlos[1]})
        assert a.status_code == 200, a.text
    return o["id"]


class TestPhoto:
    def test_empty_file_rejected(self, owner, carlos, created):
        oid = _new_order(owner, carlos, created)
        r = requests.post(f"{BASE}/courier/orders/{oid}/photo", headers=_h(carlos[0]),
                          files={"file": ("x.jpg", b"", "image/jpeg")})
        assert r.status_code == 400, r.text
        assert "vacía" in r.json()["detail"]

    def test_non_image_rejected(self, owner, carlos, created):
        oid = _new_order(owner, carlos, created)
        r = requests.post(f"{BASE}/courier/orders/{oid}/photo", headers=_h(carlos[0]),
                          files={"file": ("x.txt", b"a" * 500, "text/plain")})
        assert r.status_code == 400

    def test_missing_photo_404(self, owner, carlos, created):
        oid = _new_order(owner, carlos, created)
        r = requests.get(f"{BASE}/orders/{oid}/photo", params={"token": owner})
        assert r.status_code == 404

    def test_multipart_upload_and_owner_fetch(self, owner, carlos, created):
        oid = _new_order(owner, carlos, created)
        img = _png()
        r = requests.post(f"{BASE}/courier/orders/{oid}/photo", headers=_h(carlos[0]),
                          files={"file": ("p.png", img, "image/png")})
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True
        g = requests.get(f"{BASE}/orders/{oid}/photo", params={"token": owner})
        assert g.status_code == 200
        assert len(g.content) == len(img) and g.content[:4] == b"\x89PNG"
        assert g.headers["content-type"].startswith("image/")
        # courier can also fetch it; bad token -> 401
        assert requests.get(f"{BASE}/orders/{oid}/photo", params={"token": carlos[0]}).status_code == 200
        assert requests.get(f"{BASE}/orders/{oid}/photo", params={"token": "bad"}).status_code == 401
        # deliver with note -> owner sees note + photo path
        for st in ("en_camino", "entregado"):
            s = requests.patch(f"{BASE}/courier/orders/{oid}/status", headers=_h(carlos[0]), json={"status": st, "note": "TEST nota portero"})
            assert s.status_code == 200, s.text
        d = requests.get(f"{BASE}/orders/{oid}", headers=_h(owner)).json()
        assert d.get("delivery_note") == "TEST nota portero"
        assert d.get("delivery_photo")
        # closed order -> upload rejected
        r2 = requests.post(f"{BASE}/courier/orders/{oid}/photo", headers=_h(carlos[0]), files={"file": ("p.png", img, "image/png")})
        assert r2.status_code == 400

    def test_b64_upload(self, owner, carlos, created):
        oid = _new_order(owner, carlos, created)
        img = _png(48, 48)
        b = base64.b64encode(img).decode()
        r = requests.post(f"{BASE}/courier/orders/{oid}/photo-b64", headers=_h(carlos[0]),
                          json={"data": "data:image/png;base64," + b, "mime": "image/png"})
        assert r.status_code == 200, r.text
        g = requests.get(f"{BASE}/orders/{oid}/photo", params={"token": owner})
        assert g.status_code == 200 and g.content == img
        bad = requests.post(f"{BASE}/courier/orders/{oid}/photo-b64", headers=_h(carlos[0]), json={"data": "AAAA", "mime": "image/png"})
        assert bad.status_code == 400

    def test_other_courier_forbidden(self, owner, carlos, created):
        oid = _new_order(owner, carlos, created)
        t = requests.post(f"{BASE}/auth/courier/login", json={"phone": "1100000002", "pin": "654321"}).json()["token"]
        r = requests.post(f"{BASE}/courier/orders/{oid}/photo", headers=_h(t), files={"file": ("p.png", _png(), "image/png")})
        assert r.status_code in (403, 404)
