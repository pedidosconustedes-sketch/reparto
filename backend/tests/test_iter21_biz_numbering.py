# Iteration 21: per-business order numbering (#01, #02...) + push text format + incident regression
import os
import re
import concurrent.futures as cf

import pytest
import requests

BASE_URL = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def admin():
    r = requests.post(f"{API}/auth/login", json={"email": "admin@delivery.com", "password": "Admin12345"}, timeout=30)
    assert r.status_code == 200, r.text
    s = requests.Session()
    s.headers["Authorization"] = "Bearer " + r.json()["token"]
    return s


@pytest.fixture(scope="module")
def courier():
    r = requests.post(f"{API}/auth/courier/login", json={"phone": "1100000001", "pin": "123456"}, timeout=30)
    assert r.status_code == 200, r.text
    s = requests.Session()
    s.headers["Authorization"] = "Bearer " + r.json()["token"]
    s.me = r.json()["user"]
    return s


@pytest.fixture(scope="module")
def two_biz(admin):
    """Two fresh TEST_ businesses (+ business login on the first). Deleted at teardown."""
    ids = []
    for i in (1, 2):
        r = admin.post(f"{API}/businesses", json={"name": f"TEST_Num{i}", "address": "Calle Mayor 1, Madrid", "phone": f"110000009{i}"}, timeout=60)
        assert r.status_code in (200, 201), r.text
        ids.append(r.json()["id"])
    r = admin.put(f"{API}/businesses/{ids[0]}/account", json={"email": "test_num21@delivery.com", "password": "NumPass123"}, timeout=30)
    assert r.status_code == 200, r.text
    yield ids
    for bid in ids:
        admin.delete(f"{API}/businesses/{bid}/account", timeout=30)
        admin.delete(f"{API}/businesses/{bid}", timeout=30)


@pytest.fixture(scope="module")
def biz(two_biz):
    r = requests.post(f"{API}/auth/login", json={"email": "test_num21@delivery.com", "password": "NumPass123"}, timeout=30)
    assert r.status_code == 200, r.text
    s = requests.Session()
    s.headers["Authorization"] = "Bearer " + r.json()["token"]
    return s


def owner_order(admin, bid, **kw):
    body = {"business_id": bid, "customer_name": "TEST_Cli", "address": "Calle Alcalá 10, Madrid", "amount": 10,
            "delivery_fee": 3, "dest_lat": 40.42, "dest_lng": -3.70, **kw}
    r = admin.post(f"{API}/orders", json=body, timeout=60)
    assert r.status_code in (200, 201), r.text
    return r.json()


# --- Numbering per business ---
class TestNumbering:
    def test_new_business_first_order_is_1(self, admin, two_biz):
        o = owner_order(admin, two_biz[0])
        assert o["number"] == 1

    def test_second_business_also_starts_at_1(self, admin, two_biz):
        o = owner_order(admin, two_biz[1])
        assert o["number"] == 1

    def test_biz_endpoint_continues_sequence(self, biz, two_biz):
        r = biz.post(f"{API}/biz/orders", json={"business_id": "x", "customer_name": "TEST_BizCli", "address": "Calle Alcalá 10, Madrid",
                                                 "amount": 5, "dest_lat": 40.42, "dest_lng": -3.70}, timeout=60)
        assert r.status_code in (200, 201), r.text
        assert r.json()["number"] == 2

    def test_owner_after_biz_gets_3(self, admin, two_biz):
        assert owner_order(admin, two_biz[0])["number"] == 3

    def test_other_business_independent(self, admin, two_biz):
        assert owner_order(admin, two_biz[1])["number"] == 2

    def test_concurrent_creation_unique(self, admin, two_biz):
        with cf.ThreadPoolExecutor(5) as ex:
            nums = list(ex.map(lambda _: owner_order(admin, two_biz[1])["number"], range(5)))
        assert sorted(nums) == [3, 4, 5, 6, 7], nums

    def test_list_filtered_by_business(self, admin, two_biz):
        r = admin.get(f"{API}/orders", params={"business_id": two_biz[1]}, timeout=30)
        nums = sorted(o["number"] for o in r.json())
        assert nums == list(range(1, 8))

    def test_biz_list_numbers(self, biz):
        nums = sorted(o["number"] for o in biz.get(f"{API}/biz/orders", timeout=30).json())
        assert nums == [1, 2, 3]

    def test_existing_businesses_numbered_1_to_n(self, admin):
        bizs = admin.get(f"{API}/businesses", timeout=30).json()
        orders = admin.get(f"{API}/orders", timeout=30).json()
        per = {}
        for o in orders:
            per.setdefault(o["business_id"], []).append(o)
        for bid, lst in per.items():
            nums = [o["number"] for o in lst]
            assert len(nums) == len(set(nums)), f"dup numbers in {bid}"
            lst.sort(key=lambda o: o["created_at"])
            assert [o["number"] for o in lst] == sorted(nums), f"not ordered by date in {bid}"
        assert any(b["id"] in per for b in bizs)

    def test_no_numbers_over_1000(self, admin):
        assert all(o["number"] < 1000 for o in admin.get(f"{API}/orders", timeout=30).json())


# --- Courier sees same number; incident regression ---
class TestCourierAndIncident:
    def test_courier_sees_number_and_incident(self, admin, courier, two_biz):
        o = owner_order(admin, two_biz[0], courier_id=courier.me["id"])
        assert o["number"] == 4
        r = courier.get(f"{API}/courier/orders", timeout=30)
        assert r.status_code == 200
        mine = [x for x in r.json()["active"] if x["id"] == o["id"]]
        assert mine and mine[0]["number"] == 4
        r = courier.post(f"{API}/courier/orders/{o['id']}/incident", json={"type": "otro", "note": "TEST_inc"}, timeout=30)
        assert r.status_code == 200, r.text
        d = admin.get(f"{API}/orders/{o['id']}", timeout=30).json()
        assert d["number"] == 4 and len(d["incidents"]) == 1 and d["incidents"][0]["note"] == "TEST_inc"


# --- Push texts use 2-digit format (static check of server source) ---
def test_push_texts_two_digit():
    src = open("/app/backend/server.py").read()
    raw = re.findall(r"#\{o\.number\}", src)
    assert not raw, f"unpadded push texts: {len(raw)}"
    assert len(re.findall(r"#\{o\.number:02d\}", src)) >= 8
