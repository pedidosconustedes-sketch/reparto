# Iteration 8: security audit fixes - photo tokens, upload sniffing, login lockout, change password, demo account removal, business flow
import os
import struct
import uuid
import zlib
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
OWNER = {"email": "admin@delivery.com", "password": "Admin12345"}
C1 = {"phone": "1100000001", "pin": "123456"}
C2 = {"phone": "1100000002", "pin": "654321"}


def png_bytes(w=40, h=40):
    rows = b"".join(b"\x00" + b"".join(bytes([(x * 7) % 256, (y * 5) % 256, 120]) for x in range(w)) for y in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + \
        chunk(b"IDAT", zlib.compress(rows, 0)) + chunk(b"IEND", b"")


def H(t):
    return {"Authorization": f"Bearer {t}"}


def login(path, body):
    r = requests.post(f"{API}{path}", json=body, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def ctx():
    o = login("/auth/login", OWNER)
    c1 = login("/auth/courier/login", C1)
    c2 = login("/auth/courier/login", C2)
    bizs = requests.get(f"{API}/businesses", headers=H(o["token"]), timeout=30).json()
    bid = bizs[0]["id"]
    prev_email = bizs[0].get("account_email")
    email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    pw = "TestPass123"
    r = requests.put(f"{API}/businesses/{bid}/account", json={"email": email, "password": pw}, headers=H(o["token"]), timeout=30)
    assert r.status_code == 200, r.text
    b = login("/auth/login", {"email": email, "password": pw})
    c = {"owner": o["token"], "c1": c1["token"], "c1_user": c1["user"], "c2": c2["token"], "bid": bid,
         "biz": b["token"], "biz_email": email, "biz_pw": pw, "cleanup": [], "prev_email": prev_email}
    yield c
    for oid_ in c["cleanup"]:
        requests.patch(f"{API}/orders/{oid_}/status", json={"status": "cancelado"}, headers=H(o["token"]), timeout=20)
    requests.delete(f"{API}/businesses/{bid}/account", headers=H(o["token"]), timeout=20)


# --- Demo account removal / admin password persistence
class TestDemoAndAdmin:
    def test_cafe_demo_login_fails(self):
        r = requests.post(f"{API}/auth/login", json={"email": "cafe@delivery.com", "password": "Comercio123"}, timeout=30)
        assert r.status_code == 401

    def test_admin_login_ok(self):
        d = login("/auth/login", OWNER)
        assert d["user"]["role"] == "owner" and d["token"]


# --- Photo token separation
class TestPhotoToken:
    def test_photo_token_issued(self, ctx):
        r = requests.get(f"{API}/photo-token", headers=H(ctx["owner"]), timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d["token"], str) and d["expires_in"] > 0

    def test_photo_token_rejected_by_session_api(self, ctx):
        pt = requests.get(f"{API}/photo-token", headers=H(ctx["owner"]), timeout=30).json()["token"]
        r = requests.get(f"{API}/auth/me", headers=H(pt), timeout=30)
        assert r.status_code == 401

    def test_courier_photo_upload_and_fetch(self, ctx):
        # real PNG upload works
        r = requests.post(f"{API}/courier/profile-photo", headers=H(ctx["c1"]),
                          files={"file": ("a.png", png_bytes(), "image/png")}, timeout=60)
        assert r.status_code == 200, r.text
        uid = ctx["c1_user"]["id"]
        pt = requests.get(f"{API}/photo-token", headers=H(ctx["owner"]), timeout=30).json()["token"]
        ok = requests.get(f"{API}/users/{uid}/photo", params={"token": pt}, timeout=60)
        assert ok.status_code == 200
        assert ok.headers["content-type"].startswith("image/png")
        assert ok.headers.get("x-content-type-options") == "nosniff"
        assert "default-src 'none'" in ok.headers.get("content-security-policy", "")
        bad = requests.get(f"{API}/users/{uid}/photo", params={"token": ctx["owner"]}, timeout=30)
        assert bad.status_code == 401

    def test_svg_and_text_upload_rejected(self, ctx):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script>' + b" " * 300 + b"</svg>"
        r = requests.post(f"{API}/courier/profile-photo", headers=H(ctx["c1"]),
                          files={"file": ("x.svg", svg, "image/svg+xml")}, timeout=30)
        assert r.status_code == 400
        r2 = requests.post(f"{API}/courier/profile-photo", headers=H(ctx["c1"]),
                           files={"file": ("x.jpg", b"hello world " * 50, "image/jpeg")}, timeout=30)
        assert r2.status_code == 400

    def test_jpeg_magic_upload_accepted(self, ctx):
        jpg = b"\xff\xd8\xff\xe0" + b"\x00" * 400 + b"\xff\xd9"
        r = requests.post(f"{API}/courier/profile-photo", headers=H(ctx["c1"]),
                          files={"file": ("x.jpg", jpg, "image/jpeg")}, timeout=60)
        assert r.status_code == 200, r.text
        # restore a png avatar
        requests.post(f"{API}/courier/profile-photo", headers=H(ctx["c1"]),
                      files={"file": ("a.png", png_bytes(), "image/png")}, timeout=60)


# --- Business flow + order photo with photo token
class TestBusinessFlow:
    def test_biz_open_order_accepted_by_courier(self, ctx):
        r = requests.post(f"{API}/biz/orders", headers=H(ctx["biz"]), json={
            "business_id": "x", "customer_name": "TEST_Cliente", "customer_phone": "600000000",
            "address": "Calle Mayor 1, Madrid", "amount": 10, "delivery_fee": 3, "open": True}, timeout=60)
        assert r.status_code == 200, r.text
        o = r.json()
        ctx["cleanup"].append(o["id"])
        ctx["order_id"] = o["id"]
        lst = requests.get(f"{API}/courier/open-orders", headers=H(ctx["c1"]), timeout=30).json()
        assert any(x["id"] == o["id"] for x in lst)
        a = requests.post(f"{API}/courier/orders/{o['id']}/accept", headers=H(ctx["c1"]), timeout=30)
        assert a.status_code == 200, a.text
        lst2 = requests.get(f"{API}/courier/open-orders", headers=H(ctx["c2"]), timeout=30).json()
        assert not any(x["id"] == o["id"] for x in lst2)

    def test_order_photo_token(self, ctx):
        oid_ = ctx.get("order_id")
        if not oid_:
            pytest.skip("no order")
        up = requests.post(f"{API}/courier/orders/{oid_}/photo", headers=H(ctx["c1"]),
                           files={"file": ("p.png", png_bytes(), "image/png")}, timeout=60)
        assert up.status_code == 200, up.text
        pt = requests.get(f"{API}/photo-token", headers=H(ctx["owner"]), timeout=30).json()["token"]
        ok = requests.get(f"{API}/orders/{oid_}/photo", params={"token": pt}, timeout=60)
        assert ok.status_code == 200 and ok.headers["content-type"].startswith("image/")
        bad = requests.get(f"{API}/orders/{oid_}/photo", params={"token": ctx["owner"]}, timeout=30)
        assert bad.status_code == 401


# --- Change password (business)
class TestChangePassword:
    def test_change_password_invalidates_old_token(self, ctx):
        old = ctx["biz"]
        bad = requests.post(f"{API}/auth/change-password", headers=H(old),
                            json={"current_password": "wrong", "new_password": "NewPass1234"}, timeout=30)
        assert bad.status_code == 400
        short = requests.post(f"{API}/auth/change-password", headers=H(old),
                              json={"current_password": ctx["biz_pw"], "new_password": "short"}, timeout=30)
        assert short.status_code == 422
        r = requests.post(f"{API}/auth/change-password", headers=H(old),
                          json={"current_password": ctx["biz_pw"], "new_password": "NewPass1234"}, timeout=30)
        assert r.status_code == 200, r.text
        new = r.json()["token"]
        assert requests.get(f"{API}/auth/me", headers=H(old), timeout=30).status_code == 401
        me = requests.get(f"{API}/auth/me", headers=H(new), timeout=30)
        assert me.status_code == 200 and me.json()["email"] == ctx["biz_email"]
        assert requests.post(f"{API}/auth/login", json={"email": ctx["biz_email"], "password": ctx["biz_pw"]}, timeout=30).status_code == 401
        login("/auth/login", {"email": ctx["biz_email"], "password": "NewPass1234"})
        ctx["biz"], ctx["biz_pw"] = new, "NewPass1234"

    def test_courier_cannot_change_password(self, ctx):
        r = requests.post(f"{API}/auth/change-password", headers=H(ctx["c2"]),
                          json={"current_password": "654321", "new_password": "NewPass1234"}, timeout=30)
        assert r.status_code == 403


# --- Lockout (run last, on the test business account only)
class TestLockout:
    def test_lockout_after_5_fails(self, ctx):
        for i in range(5):
            r = requests.post(f"{API}/auth/login", json={"email": ctx["biz_email"], "password": f"bad{i}"}, timeout=30)
            assert r.status_code == 401, f"attempt {i+1}: {r.status_code}"
        r6 = requests.post(f"{API}/auth/login", json={"email": ctx["biz_email"], "password": ctx["biz_pw"]}, timeout=30)
        assert r6.status_code == 429
        assert "min" in r6.json()["detail"]

    def test_unknown_email_no_429(self):
        for i in range(6):
            r = requests.post(f"{API}/auth/login", json={"email": "nobody_x@example.com", "password": "x"}, timeout=30)
        assert r.status_code == 401


# --- Courier lockout on a temporary courier (never lock seeded couriers)
def test_courier_lockout_temp_courier():
    o = login("/auth/login", OWNER)["token"]
    phone = "19" + uuid.uuid4().int.__str__()[:8]
    r = requests.post(f"{API}/couriers", headers=H(o), json={"name": "TEST_Lock", "phone": phone, "pin": "111111", "vehicle": "moto"}, timeout=30)
    assert r.status_code in (200, 201), r.text
    cid = r.json()["id"]
    try:
        for i in range(5):
            assert requests.post(f"{API}/auth/courier/login", json={"phone": phone, "pin": "000000"}, timeout=30).status_code == 401
        assert requests.post(f"{API}/auth/courier/login", json={"phone": phone, "pin": "111111"}, timeout=30).status_code == 429
    finally:
        requests.delete(f"{API}/couriers/{cid}", headers=H(o), timeout=30)
