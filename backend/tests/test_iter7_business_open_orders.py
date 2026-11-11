# Iteration 7: business (comercio) role, open orders/accept, profile photos, business accounts, push register
import io
import os
import struct
import zlib
import uuid
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
OWNER = {"email": "admin@delivery.com", "password": "Admin12345"}
BIZ = {"email": "cafe@delivery.com", "password": "Comercio123"}
C1 = {"phone": "1100000001", "pin": "123456"}
C2 = {"phone": "1100000002", "pin": "654321"}
COORD_KEYS = {"pickup_lat", "pickup_lng", "dest_lat", "dest_lng", "lat", "lng"}


def png_bytes(w=40, h=40):
    raw = b"".join(b"\x00" + bytes([(x * 7) % 256, (y * 5) % 256, 120] * 1)[:3] * 1 for y in range(h) for x in range(1)) 
    rows = b"".join(b"\x00" + b"".join(bytes([(x * 7) % 256, (y * 5) % 256, 120]) for x in range(w)) for y in range(h))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + \
        chunk(b"IDAT", zlib.compress(rows, 0)) + chunk(b"IEND", b"")


def login(path, body):
    r = requests.post(f"{API}{path}", json=body, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def H(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def ctx():
    o = login("/auth/login", OWNER)
    # cafe@delivery.com was removed (iter8): create a temp business account on the first business
    bid0 = requests.get(f"{API}/businesses", headers=H(o["token"]), timeout=30).json()[0]["id"]
    BIZ["email"] = f"test_biz_{uuid.uuid4().hex[:6]}@example.com"
    BIZ["password"] = "Comercio123"
    requests.put(f"{API}/businesses/{bid0}/account", json=BIZ, headers=H(o["token"]), timeout=30)
    b = login("/auth/login", BIZ)
    c1 = login("/auth/courier/login", C1)
    c2 = login("/auth/courier/login", C2)
    return {"owner": o["token"], "owner_user": o["user"], "biz": b["token"], "biz_user": b["user"],
            "c1": c1["token"], "c1_user": c1["user"], "c2": c2["token"], "c2_user": c2["user"], "cleanup": []}


@pytest.fixture(scope="module", autouse=True)
def teardown(ctx):
    yield
    requests.delete(f"{API}/businesses/{ctx['biz_user']['business_id']}/account", headers=H(ctx["owner"]), timeout=20)
    for oid_ in ctx["cleanup"]:
        try:
            requests.patch(f"{API}/orders/{oid_}/status", json={"status": "cancelado"}, headers=H(ctx["owner"]), timeout=20)
        except Exception:
            pass


def biz_order_payload(ctx, **kw):
    p = {"business_id": ctx["biz_user"].get("business_id") or "x", "customer_name": "TEST_Cliente",
         "customer_phone": "600000000", "address": "Calle Mayor 1, Madrid", "amount": 10, "delivery_fee": 3}
    p.update(kw)
    return p


# --- Auth ---
def test_logins_roles(ctx):
    assert ctx["biz_user"]["role"] == "business"
    assert ctx["biz_user"].get("business_id")
    assert ctx["owner_user"]["role"] == "owner"
    assert "password_hash" not in ctx["biz_user"]


# --- Business account mgmt (owner only) ---
def test_business_detail_account_email(ctx):
    r = requests.get(f"{API}/businesses/{ctx['biz_user']['business_id']}", headers=H(ctx["owner"]), timeout=20)
    assert r.status_code == 200
    assert r.json()["account_email"] == BIZ["email"]


def test_business_account_crud_and_conflict(ctx):
    # create a TEST business
    r = requests.post(f"{API}/businesses", json={"name": "TEST_Biz", "address": "Gran Via 1, Madrid", "phone": "911111111"},
                      headers=H(ctx["owner"]), timeout=30)
    assert r.status_code == 200, r.text
    bid = r.json()["id"]
    try:
        email = f"test_{uuid.uuid4().hex[:6]}@delivery.com"
        # conflict with existing cafe account / owner email
        assert requests.put(f"{API}/businesses/{bid}/account", json={"email": BIZ["email"], "password": "Password1"},
                            headers=H(ctx["owner"]), timeout=20).status_code == 409
        assert requests.put(f"{API}/businesses/{bid}/account", json={"email": "admin@delivery.com", "password": "Password1"},
                            headers=H(ctx["owner"]), timeout=20).status_code == 409
        # short password 422
        assert requests.put(f"{API}/businesses/{bid}/account", json={"email": email, "password": "short"},
                            headers=H(ctx["owner"]), timeout=20).status_code == 422
        # non-owner 403
        for t in ("biz", "c1"):
            assert requests.put(f"{API}/businesses/{bid}/account", json={"email": email, "password": "Password1"},
                                headers=H(ctx[t]), timeout=20).status_code == 403
        r = requests.put(f"{API}/businesses/{bid}/account", json={"email": email, "password": "Password1"},
                         headers=H(ctx["owner"]), timeout=20)
        assert r.status_code == 200 and r.json()["account_email"] == email
        assert requests.get(f"{API}/businesses/{bid}", headers=H(ctx["owner"])).json()["account_email"] == email
        t2 = login("/auth/login", {"email": email, "password": "Password1"})["token"]
        # cross-business isolation: TEST biz cannot see cafe orders
        cafe_orders = requests.get(f"{API}/biz/orders", headers=H(ctx["biz"])).json()
        assert requests.get(f"{API}/biz/orders", headers=H(t2)).json() == []
        if cafe_orders:
            oid_ = cafe_orders[0]["id"]
            assert requests.get(f"{API}/biz/orders/{oid_}", headers=H(t2)).status_code == 404
            assert requests.patch(f"{API}/biz/orders/{oid_}/cancel", headers=H(t2)).status_code == 404
        # update password (same email allowed)
        r = requests.put(f"{API}/businesses/{bid}/account", json={"email": email, "password": "Password2"},
                         headers=H(ctx["owner"]), timeout=20)
        assert r.status_code == 200
        assert requests.post(f"{API}/auth/login", json={"email": email, "password": "Password1"}).status_code == 401
        login("/auth/login", {"email": email, "password": "Password2"})
        # delete account
        assert requests.delete(f"{API}/businesses/{bid}/account", headers=H(ctx["owner"])).status_code == 200
        assert requests.get(f"{API}/businesses/{bid}", headers=H(ctx["owner"])).json()["account_email"] is None
        assert requests.post(f"{API}/auth/login", json={"email": email, "password": "Password2"}).status_code == 401
        assert requests.delete(f"{API}/businesses/{bid}/account", headers=H(ctx["biz"])).status_code == 403
    finally:
        requests.delete(f"{API}/businesses/{bid}", headers=H(ctx["owner"]))


# --- Business endpoints ---
def test_biz_me_and_couriers(ctx):
    r = requests.get(f"{API}/biz/me", headers=H(ctx["biz"]))
    assert r.status_code == 200 and r.json()["id"] == ctx["biz_user"]["business_id"]
    r = requests.get(f"{API}/biz/couriers", headers=H(ctx["biz"]))
    assert r.status_code == 200
    cs = r.json()
    assert len(cs) >= 2
    for c in cs:
        assert not (COORD_KEYS & set(c.keys())), c
        assert "name" in c and "phone" in c and "has_photo" in c


def test_biz_forbidden_for_other_roles(ctx):
    for t in ("owner", "c1"):
        for path in ("/biz/me", "/biz/couriers", "/biz/orders"):
            assert requests.get(f"{API}{path}", headers=H(ctx[t])).status_code == 403, (t, path)
        assert requests.post(f"{API}/biz/orders", json=biz_order_payload(ctx), headers=H(ctx[t])).status_code == 403


def test_biz_create_open_order_and_detail(ctx):
    r = requests.post(f"{API}/biz/orders", json=biz_order_payload(ctx), headers=H(ctx["biz"]), timeout=40)
    assert r.status_code == 200, r.text
    o = r.json()
    ctx["cleanup"].append(o["id"])
    ctx["open_order"] = o
    assert o["open"] is True and o["courier_id"] is None and o["created_by"] == "business"
    ctx["create_resp_coord_leak"] = sorted(COORD_KEYS & set(o.keys()))
    d = requests.get(f"{API}/biz/orders/{o['id']}", headers=H(ctx["biz"])).json()
    assert not (COORD_KEYS & set(d.keys())), d.keys()
    assert d["courier"] is None
    lst = requests.get(f"{API}/biz/orders", headers=H(ctx["biz"])).json()
    assert any(x["id"] == o["id"] for x in lst)
    for x in lst:
        assert not (COORD_KEYS & set(x.keys()))


def test_biz_create_order_response_has_no_coords(ctx):
    # Report-only: POST /biz/orders response should not leak coordinates either
    assert ctx.get("create_resp_coord_leak") == [], f"POST /biz/orders leaks {ctx.get('create_resp_coord_leak')}"


def test_open_orders_and_atomic_accept(ctx):
    oid_ = ctx["open_order"]["id"]
    lst = requests.get(f"{API}/courier/open-orders", headers=H(ctx["c1"])).json()
    assert any(x["id"] == oid_ for x in lst)
    r1 = requests.post(f"{API}/courier/orders/{oid_}/accept", headers=H(ctx["c1"]))
    assert r1.status_code == 200, r1.text
    assert r1.json()["courier_id"] == ctx["c1_user"]["id"] and r1.json()["open"] is False
    r2 = requests.post(f"{API}/courier/orders/{oid_}/accept", headers=H(ctx["c2"]))
    assert r2.status_code == 409
    active = requests.get(f"{API}/courier/orders", headers=H(ctx["c1"])).json()["active"]
    assert any(x["id"] == oid_ for x in active)
    lst = requests.get(f"{API}/courier/open-orders", headers=H(ctx["c2"])).json()
    assert not any(x["id"] == oid_ for x in lst)
    # business sees courier card without location
    d = requests.get(f"{API}/biz/orders/{oid_}", headers=H(ctx["biz"])).json()
    assert d["courier"]["name"] == ctx["c1_user"]["name"]
    assert d["courier"]["phone"]
    assert not (COORD_KEYS & set(d["courier"].keys()))
    # forbidden for owner/business
    assert requests.post(f"{API}/courier/orders/{oid_}/accept", headers=H(ctx["owner"])).status_code == 403
    assert requests.get(f"{API}/courier/open-orders", headers=H(ctx["biz"])).status_code == 403


def test_biz_create_assigned_and_cancel_rules(ctx):
    r = requests.post(f"{API}/biz/orders", json=biz_order_payload(ctx, courier_id=ctx["c2_user"]["id"]),
                      headers=H(ctx["biz"]), timeout=40)
    assert r.status_code == 200, r.text
    o = r.json()
    ctx["cleanup"].append(o["id"])
    assert o["courier_id"] == ctx["c2_user"]["id"] and o["open"] is False
    # cancel nuevo -> ok
    r = requests.patch(f"{API}/biz/orders/{o['id']}/cancel", headers=H(ctx["biz"]))
    assert r.status_code == 200 and r.json()["status"] == "cancelado"
    # second cancel -> 400
    assert requests.patch(f"{API}/biz/orders/{o['id']}/cancel", headers=H(ctx["biz"])).status_code == 400
    # en_camino cannot be cancelled by business
    oid_ = ctx["open_order"]["id"]
    assert requests.patch(f"{API}/courier/orders/{oid_}/status", json={"status": "en_camino"}, headers=H(ctx["c1"])).status_code == 200
    assert requests.patch(f"{API}/biz/orders/{oid_}/cancel", headers=H(ctx["biz"])).status_code == 400


def test_biz_cancel_open_order_sets_open_false(ctx):
    r = requests.post(f"{API}/biz/orders", json=biz_order_payload(ctx), headers=H(ctx["biz"]), timeout=40)
    o = r.json()
    ctx["cleanup"].append(o["id"])
    assert requests.patch(f"{API}/biz/orders/{o['id']}/cancel", headers=H(ctx["biz"])).status_code == 200
    d = requests.get(f"{API}/biz/orders/{o['id']}", headers=H(ctx["biz"])).json()
    assert d["open"] is False and d["status"] == "cancelado"
    lst = requests.get(f"{API}/courier/open-orders", headers=H(ctx["c1"])).json()
    assert not any(x["id"] == o["id"] for x in lst)


def test_biz_invalid_courier(ctx):
    r = requests.post(f"{API}/biz/orders", json=biz_order_payload(ctx, courier_id="000000000000000000000000"),
                      headers=H(ctx["biz"]), timeout=40)
    assert r.status_code == 404


# --- Owner open orders ---
def test_owner_open_order_then_assign(ctx):
    bid = ctx["biz_user"]["business_id"]
    r = requests.post(f"{API}/orders", json=biz_order_payload(ctx, business_id=bid, open=True), headers=H(ctx["owner"]), timeout=40)
    assert r.status_code == 200, r.text
    o = r.json()
    ctx["cleanup"].append(o["id"])
    assert o["open"] is True and o["created_by"] == "owner"
    assert any(x["id"] == o["id"] for x in requests.get(f"{API}/courier/open-orders", headers=H(ctx["c2"])).json())
    r = requests.patch(f"{API}/orders/{o['id']}/assign", json={"courier_id": ctx["c2_user"]["id"]}, headers=H(ctx["owner"]))
    assert r.status_code == 200 and r.json()["open"] is False and r.json()["courier_id"] == ctx["c2_user"]["id"]
    assert requests.post(f"{API}/courier/orders/{o['id']}/accept", headers=H(ctx["c1"])).status_code == 409
    # owner default (open omitted, no courier) -> not open
    r = requests.post(f"{API}/orders", json=biz_order_payload(ctx, business_id=bid), headers=H(ctx["owner"]), timeout=40)
    ctx["cleanup"].append(r.json()["id"])
    assert r.json()["open"] is False


# --- Profile photos ---
def test_profile_photo_multipart_and_access(ctx):
    img = png_bytes()
    r = requests.post(f"{API}/courier/profile-photo", files={"file": ("p.png", io.BytesIO(img), "image/png")}, headers=H(ctx["c2"]), timeout=60)
    assert r.status_code == 200, r.text
    assert r.json()["profile_photo"]
    uid = ctx["c2_user"]["id"]
    pt = lambda t: requests.get(f"{API}/photo-token", headers=H(ctx[t]), timeout=20).json()["token"]  # iter8: photo-only tokens
    for t in ("c2", "owner", "biz"):
        g = requests.get(f"{API}/users/{uid}/photo", params={"token": pt(t)}, timeout=60)
        assert g.status_code == 200, (t, g.status_code)
        assert g.headers["content-type"].startswith("image/")
        assert len(g.content) > 200
    assert requests.get(f"{API}/users/{uid}/photo", params={"token": pt("c1")}).status_code == 404
    assert requests.get(f"{API}/users/{uid}/photo", params={"token": "bad"}).status_code == 401
    assert requests.get(f"{API}/users/{ctx['c1_user']['id'] if False else 'zzz'}/photo", params={"token": pt("owner")}).status_code == 404
    cs = requests.get(f"{API}/biz/couriers", headers=H(ctx["biz"])).json()
    assert next(c for c in cs if c["id"] == uid)["has_photo"] is True


def test_profile_photo_b64_and_validation(ctx):
    import base64
    img = png_bytes(30, 30)
    r = requests.post(f"{API}/courier/profile-photo-b64", json={"data": "data:image/png;base64," + base64.b64encode(img).decode(), "mime": "image/png"},
                      headers=H(ctx["c2"]), timeout=60)
    assert r.status_code == 200, r.text
    assert requests.post(f"{API}/courier/profile-photo", files={"file": ("a.txt", b"x" * 500, "text/plain")}, headers=H(ctx["c2"])).status_code == 400
    assert requests.post(f"{API}/courier/profile-photo-b64", json={"data": "abc"}, headers=H(ctx["c2"])).status_code == 400
    assert requests.post(f"{API}/courier/profile-photo-b64", json={"data": "abc"}, headers=H(ctx["owner"])).status_code == 403


# --- Push ---
def test_register_push_clean_error(ctx):
    r = requests.post(f"{API}/register-push", json={"platform": "android", "device_token": "TEST_tok"}, headers=H(ctx["c1"]), timeout=30)
    assert 400 <= r.status_code < 600 or r.status_code == 201
    assert r.headers.get("content-type", "").startswith("application/json"), r.text[:200]
    print("register-push:", r.status_code, r.text[:200])
    assert requests.post(f"{API}/register-push", json={"platform": "android", "device_token": "x"}).status_code in (401, 403)
    assert requests.get(f"{API}/biz/me", headers=H(ctx["biz"])).status_code == 200
