# Iteration 13: business photo visible to whole owner org, autocomplete postcode ordering,
# /orders?active=true filter, courier delivered items with business_photo + history
import io
import os
import time
import base64
from datetime import datetime, timedelta, timezone

import jwt
import pytest
import requests
from PIL import Image
from pymongo import MongoClient
from bson import ObjectId
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
BASE_URL = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/")
API = BASE_URL + "/api"
mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def login(body, path="/auth/login"):
    r = requests.post(f"{API}{path}", json=body, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


def photo_token(h):
    r = requests.get(f"{API}/photo-token", headers=h, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def owner():
    return login({"email": "admin@delivery.com", "password": "Admin12345"})


@pytest.fixture(scope="module")
def courier():
    return login({"phone": "1100000001", "pin": "123456"}, "/auth/courier/login")


@pytest.fixture(scope="module")
def courier2():
    return login({"phone": "1100000002", "pin": "654321"}, "/auth/courier/login")


@pytest.fixture(scope="module")
def env(owner):
    """Two temp businesses with accounts (biz1 has a photo) + orders; cleaned afterwards."""
    cid = str(mdb.users.find_one({"phone": "1100000001", "role": "courier"})["_id"])
    bids = []
    for i in (1, 2):
        r = requests.post(f"{API}/businesses", headers=owner, json={
            "name": f"TEST_Biz13_{i}", "address": "Calle Mayor 5, Madrid", "phone": f"110000009{i}",
            "default_fee": 3.5, "lat": 40.4165, "lng": -3.7058}, timeout=60)
        assert r.status_code == 200, r.text
        bids.append(r.json()["id"])
        r = requests.put(f"{API}/businesses/{bids[-1]}/account", headers=owner,
                         json={"email": f"test_biz13_{i}@delivery.com", "password": "BizPass1234"}, timeout=30)
        assert r.status_code == 200, r.text
    b1 = login({"email": "test_biz13_1@delivery.com", "password": "BizPass1234"})
    buf = io.BytesIO()
    Image.effect_noise((64, 64), 60).convert("RGB").save(buf, "JPEG")
    r = requests.post(f"{API}/biz/photo-b64", headers=b1, json={"data": base64.b64encode(buf.getvalue()).decode()}, timeout=60)
    assert r.status_code == 200, r.text
    base = {"business_id": bids[0], "customer_name": "TEST_Cli13", "address": "Gran Vía 28, 28013 Madrid",
            "dest_lat": 40.4203, "dest_lng": -3.7019, "delivery_fee": 3.5, "amount": 10}
    orders = {}
    for key, extra in (("assigned", {"courier_id": cid}), ("open", {"open": True}), ("deliver", {"courier_id": cid}),
                       ("cancel", {})):
        r = requests.post(f"{API}/orders", headers=owner, json={**base, **extra}, timeout=60)
        assert r.status_code == 200, r.text
        orders[key] = r.json()["id"]
    yield {"bids": bids, "orders": orders, "cid": cid, "photo": r and None}
    for bid in bids:
        requests.delete(f"{API}/businesses/{bid}/account", headers=owner, timeout=30)
        requests.delete(f"{API}/businesses/{bid}", headers=owner, timeout=30)
        mdb.orders.delete_many({"business_id": bid})
    mdb.users.delete_many({"email": {"$in": ["test_biz13_1@delivery.com", "test_biz13_2@delivery.com"]}})
    mdb.businesses.delete_many({"name": {"$regex": "^TEST_Biz13"}})


# ---- Business photo visibility ----
class TestBusinessPhotoAccess:
    def _get(self, bid, tok):
        return requests.get(f"{API}/businesses/{bid}/photo", params={"token": tok}, timeout=60)

    def test_owner_can_see(self, env, owner):
        r = self._get(env["bids"][0], photo_token(owner))
        assert r.status_code == 200 and r.headers["content-type"].startswith("image/")

    def test_couriers_can_see(self, env, courier, courier2):
        for c in (courier, courier2):
            assert self._get(env["bids"][0], photo_token(c)).status_code == 200

    def test_same_business_and_other_business_can_see(self, env):
        for i in (1, 2):
            b = login({"email": f"test_biz13_{i}@delivery.com", "password": "BizPass1234"})
            r = self._get(env["bids"][0], photo_token(b))
            assert r.status_code == 200, f"biz{i}: {r.status_code} {r.text}"

    def test_other_owner_gets_404(self, env):
        res = mdb.users.insert_one({"role": "owner", "name": "TEST_Owner13", "email": "test_owner13@x.com", "auth_version": 0})
        try:
            tok = jwt.encode({"sub": str(res.inserted_id), "role": "owner", "typ": "photo",
                              "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}, os.environ["JWT_SECRET"], algorithm="HS256")
            assert self._get(env["bids"][0], tok).status_code == 404
        finally:
            mdb.users.delete_one({"_id": res.inserted_id})

    def test_no_photo_and_bad_token(self, env, owner):
        assert self._get(env["bids"][1], photo_token(owner)).status_code == 404
        assert self._get(env["bids"][0], "garbage").status_code == 401


# ---- Autocomplete ----
def suggest(h, q):
    time.sleep(1.1)
    r = requests.get(f"{API}/places/autocomplete", headers=h, params={"q": q}, timeout=60)
    assert r.status_code == 200, r.text
    return r.json()


class TestAutocomplete:
    def test_max_8(self, owner):
        d = suggest(owner, "Calle Mayor Madrid")
        print("count:", len(d["suggestions"]), d["source"])
        assert 0 < len(d["suggestions"]) <= 8

    def test_postcode_first(self, owner):
        d = suggest(owner, "Calle Mayor 28013")
        descs = [s["description"] for s in d["suggestions"]]
        print(descs)
        assert descs, "no suggestions"
        flags = ["28013" in x for x in descs]
        assert flags[0], "first result must contain 28013"
        assert flags == sorted(flags, reverse=True), "28013 results must come first"

    def test_postcode_only(self, owner):
        d = suggest(owner, "28013")
        print([s["description"] for s in d["suggestions"]])
        assert len(d["suggestions"]) > 0


# ---- Orders active filter ----
class TestActiveOrders:
    def test_active_only(self, env, owner):
        requests.patch(f"{API}/orders/{env['orders']['cancel']}/status", headers=owner, json={"status": "cancelado"}, timeout=30)
        d = requests.get(f"{API}/orders", headers=owner, params={"active": "true"}, timeout=60).json()
        assert all(o["status"] in ("nuevo", "preparacion", "en_camino") for o in d)
        ids = {o["id"] for o in d}
        assert env["orders"]["assigned"] in ids and env["orders"]["open"] in ids
        assert env["orders"]["cancel"] not in ids
        # owner scoping
        owner_id = str(mdb.users.find_one({"email": "admin@delivery.com"})["_id"])
        assert all(mdb.orders.find_one({"_id": ObjectId(o["id"])})["owner_id"] == owner_id for o in d)

    def test_active_requires_owner(self, courier):
        assert requests.get(f"{API}/orders", headers=courier, params={"active": "true"}, timeout=30).status_code in (401, 403)


# ---- Courier delivered items ----
class TestCourierDelivered:
    def test_delivered_has_photo_and_history(self, env, courier):
        oid_ = env["orders"]["deliver"]
        for st in ("en_camino", "entregado"):
            r = requests.patch(f"{API}/courier/orders/{oid_}/status", headers=courier, json={"status": st}, timeout=30)
            assert r.status_code == 200, r.text
        d = requests.get(f"{API}/courier/orders", headers=courier, timeout=60).json()
        mine = [o for o in d["delivered"] if o["id"] == oid_]
        assert mine, "delivered order missing"
        o = mine[0]
        path = mdb.businesses.find_one({"_id": ObjectId(env["bids"][0])})["photo"]
        assert o["business_photo"] == path
        assert o["business_name"] == "TEST_Biz13_1" and o["address"].startswith("Gran Vía 28")
        assert isinstance(o["history"], list) and any(h["status"] == "entregado" for h in o["history"])
        assert "updated_at" in o

    def test_history_endpoint(self, env, courier):
        now = datetime.now(timezone.utc)
        r = requests.get(f"{API}/courier/history", headers=courier, params={
            "start": (now - timedelta(days=1)).isoformat(), "end": (now + timedelta(days=1)).isoformat()}, timeout=60)
        assert r.status_code == 200, r.text
        print("history keys:", list(r.json().keys()) if isinstance(r.json(), dict) else "list")
