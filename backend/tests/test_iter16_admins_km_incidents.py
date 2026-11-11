# Iteration 16: secondary admins (linked/independent), km pricing, default-open, date ranges, incidents, phones, payment
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
MAIN_EMAIL = "admin@delivery.com"
MAIN_PW = "Admin12345"
TAG = uuid.uuid4().hex[:6]
# Madrid: Puerta del Sol -> Plaza de Castilla (~6-7 km by road)
BIZ_LL = (40.4169, -3.7035)
DEST_LL = (40.4669, -3.6889)


def H(t):
    return {"Authorization": f"Bearer {t}"}


def login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def courier_login(phone, pin):
    r = requests.post(f"{API}/auth/courier/login", json={"phone": phone, "pin": pin})
    assert r.status_code == 200, r.text
    return r.json()["token"], r.json()["user"]["id"]


@pytest.fixture(scope="module")
def ctx():
    c = {"main": login(MAIN_EMAIL, MAIN_PW), "cleanup_biz": [], "cleanup_admins": [], "cleanup_couriers": []}
    # secondary admins
    for kind, linked in (("linked", True), ("indep", False)):
        email = f"test_{kind}_{TAG}@example.com"
        r = requests.post(f"{API}/admins", headers=H(c["main"]),
                          json={"name": f"TEST_{kind}", "email": email, "password": "Secret1234", "linked": linked})
        assert r.status_code == 200, r.text
        c[f"{kind}_id"] = r.json()["id"]
        c["cleanup_admins"].append(r.json()["id"])
        c[kind] = login(email, "Secret1234")
    yield c
    # teardown
    for tok_key in ("indep", "main"):
        for cid in c["cleanup_couriers"]:
            requests.delete(f"{API}/couriers/{cid}", headers=H(c[tok_key]))
        for bid in c["cleanup_biz"]:
            requests.delete(f"{API}/businesses/{bid}/account", headers=H(c[tok_key]))
            requests.delete(f"{API}/businesses/{bid}", headers=H(c[tok_key]))
    for aid in c["cleanup_admins"]:
        requests.delete(f"{API}/admins/{aid}", headers=H(c["main"]))


# --- Auth / main admin
def test_main_admin_me(ctx):
    r = requests.get(f"{API}/auth/me", headers=H(ctx["main"]))
    assert r.status_code == 200
    me = r.json()
    assert me["email"] == MAIN_EMAIL and me["is_main"] is True


def test_old_admin_email_fails():
    r = requests.post(f"{API}/auth/login", json={"email": "admin@delivery.com", "password": "wrongpass-x"})
    assert r.status_code in (401, 400)


# --- Admins CRUD permissions
def test_admins_list_and_secondary_forbidden(ctx):
    r = requests.get(f"{API}/admins", headers=H(ctx["main"]))
    ids = {a["id"]: a for a in r.json()}
    assert ctx["linked_id"] in ids and ctx["indep_id"] in ids
    assert ids["%s" % ctx["linked_id"]]["linked"] is True and ids[ctx["indep_id"]]["linked"] is False
    for k in ("linked", "indep"):
        me = requests.get(f"{API}/auth/me", headers=H(ctx[k])).json()
        assert me["is_main"] is False
        assert requests.get(f"{API}/admins", headers=H(ctx[k])).status_code == 403
        assert requests.post(f"{API}/admins", headers=H(ctx[k]), json={"name": "x", "email": f"x{TAG}@e.com", "password": "Secret1234"}).status_code == 403
        assert requests.delete(f"{API}/admins/{ctx['linked_id']}", headers=H(ctx[k])).status_code == 403


def test_admin_duplicate_email_409(ctx):
    r = requests.post(f"{API}/admins", headers=H(ctx["main"]), json={"name": "dup", "email": MAIN_EMAIL, "password": "Secret1234"})
    assert r.status_code == 409


# --- Linked secondary
def test_linked_sees_main_data(ctx):
    for path in ("businesses", "couriers", "orders"):
        a = sorted(x["id"] for x in requests.get(f"{API}/{path}", headers=H(ctx["main"])).json())
        b = sorted(x["id"] for x in requests.get(f"{API}/{path}", headers=H(ctx["linked"])).json())
        assert a == b and len(a) > 0, path


def test_linked_can_create_business_but_not_accounts(ctx):
    r = requests.post(f"{API}/businesses", headers=H(ctx["linked"]),
                      json={"name": f"TEST_LinkedBiz_{TAG}", "address": "Calle Mayor 1, Madrid", "lat": BIZ_LL[0], "lng": BIZ_LL[1], "default_fee": 2})
    assert r.status_code == 200, r.text
    bid = r.json()["id"]
    ctx["cleanup_biz"].append(bid)
    main_ids = [b["id"] for b in requests.get(f"{API}/businesses", headers=H(ctx["main"])).json()]
    assert bid in main_ids
    assert requests.post(f"{API}/couriers", headers=H(ctx["linked"]), json={"name": "TEST_x", "phone": "1199" + TAG[:6].replace("a", "1"), "pin": "123456"}).status_code == 403
    cid = requests.get(f"{API}/couriers", headers=H(ctx["main"])).json()[0]["id"]
    assert requests.delete(f"{API}/couriers/{cid}", headers=H(ctx["linked"])).status_code == 403
    assert requests.put(f"{API}/businesses/{bid}/account", headers=H(ctx["linked"]), json={"email": f"tb{TAG}@e.com", "password": "Secret1234"}).status_code == 403
    assert requests.delete(f"{API}/businesses/{bid}/account", headers=H(ctx["linked"])).status_code == 403
    # linked can create orders on main data
    r = requests.post(f"{API}/orders", headers=H(ctx["linked"]), json={"business_id": bid, "customer_name": "TEST_c", "address": "Gran Vía 1, Madrid", "amount": 10, "open": True, "dest_lat": DEST_LL[0], "dest_lng": DEST_LL[1]})
    assert r.status_code == 200, r.text
    assert r.json()["open"] is True


# --- Independent secondary
def test_independent_isolated(ctx):
    for path in ("businesses", "couriers", "orders"):
        assert requests.get(f"{API}/{path}", headers=H(ctx["indep"])).json() == [], path
    r = requests.post(f"{API}/businesses", headers=H(ctx["indep"]), json={"name": f"TEST_IndBiz_{TAG}", "address": "x", "lat": BIZ_LL[0], "lng": BIZ_LL[1]})
    assert r.status_code == 200
    bid = r.json()["id"]
    ctx["cleanup_biz"].append(bid)
    phone = "1188" + str(int(datetime.now().timestamp()))[-6:]
    r = requests.post(f"{API}/couriers", headers=H(ctx["indep"]), json={"name": "TEST_IndCourier", "phone": phone, "pin": "112233"})
    assert r.status_code == 200, r.text
    ctx["cleanup_couriers"].append(r.json()["id"])
    assert requests.put(f"{API}/businesses/{bid}/account", headers=H(ctx["indep"]), json={"email": f"tind{TAG}@e.com", "password": "Secret1234"}).status_code == 200
    main_b = [b["id"] for b in requests.get(f"{API}/businesses", headers=H(ctx["main"])).json()]
    main_c = [c["id"] for c in requests.get(f"{API}/couriers", headers=H(ctx["main"])).json()]
    assert bid not in main_b and r.json()["id"] not in main_c
    assert requests.get(f"{API}/businesses/{main_b[0]}", headers=H(ctx["indep"])).status_code == 404
    assert requests.get(f"{API}/businesses/{bid}", headers=H(ctx["main"])).status_code == 404
    ind_b = [b["id"] for b in requests.get(f"{API}/businesses", headers=H(ctx["indep"])).json()]
    assert ind_b == [bid]


# --- Km pricing + business order + default open + ranges + incidents + phones
def test_km_pricing_business_order_incident(ctx):
    m = H(ctx["main"])
    r = requests.post(f"{API}/businesses", headers=m, json={"name": f"TEST_KmBiz_{TAG}", "address": "Puerta del Sol, Madrid", "lat": BIZ_LL[0], "lng": BIZ_LL[1], "default_fee": 5})
    bid = r.json()["id"]
    ctx["cleanup_biz"].append(bid)
    body = {"name": f"TEST_KmBiz_{TAG}", "address": "Puerta del Sol, Madrid", "lat": BIZ_LL[0], "lng": BIZ_LL[1], "default_fee": 5,
            "pricing_mode": "km", "km_base_price": 3, "km_base_km": 2, "km_extra_price": 1,
            "phones": [{"name": "Cocina", "phone": "600111222"}, {"name": "Caja", "phone": "600333444"}]}
    r = requests.put(f"{API}/businesses/{bid}", headers=m, json=body)
    assert r.status_code == 200, r.text
    assert r.json()["pricing_mode"] == "km" and len(r.json()["phones"]) == 2
    q = requests.get(f"{API}/businesses/{bid}/quote", headers=m, params={"lat": DEST_LL[0], "lng": DEST_LL[1]}, timeout=30).json()
    print("quote", q)
    assert q["distance_km"] and q["distance_km"] > 2
    assert abs(q["fee"] - round(3 + max(0, q["distance_km"] - 2) * 1, 2)) < 0.011
    # business account + business order
    em = f"tkm{TAG}@example.com"
    assert requests.put(f"{API}/businesses/{bid}/account", headers=m, json={"email": em, "password": "Secret1234"}).status_code == 200
    bt = requests.post(f"{API}/auth/login", json={"email": em, "password": "Secret1234"}).json()["token"]
    me = requests.get(f"{API}/biz/me", headers=H(bt)).json()
    assert "km_base_price" not in me and "default_fee" not in me and "pricing_mode" not in me
    r = requests.post(f"{API}/biz/orders", headers=H(bt), json={"business_id": bid, "customer_name": "TEST_km", "address": "Plaza de Castilla, Madrid",
                                                               "amount": 0, "delivery_fee": 99, "dest_lat": DEST_LL[0], "dest_lng": DEST_LL[1]}, timeout=30)
    assert r.status_code == 200, r.text
    bo = r.json()
    # Iteration 18: businesses now see delivery fee + distance (but not coords / courier_paid); client's 99 is ignored
    assert bo["delivery_fee"] != 99 and bo["distance_km"] and "dest_lat" not in bo and "courier_paid" not in bo
    assert bo["payment_method"] == "pagado" and bo["open"] is True
    od = requests.get(f"{API}/orders/{bo['id']}", headers=m).json()
    print("biz order", od["distance_km"], od["delivery_fee"])
    assert od["distance_km"] and abs(od["delivery_fee"] - round(3 + max(0, od["distance_km"] - 2), 2)) < 0.011
    # range filter (today includes, last year excludes)
    now = datetime.now(timezone.utc)
    s, e = (now - timedelta(hours=1)).isoformat(), (now + timedelta(hours=1)).isoformat()
    ids = [o["id"] for o in requests.get(f"{API}/orders", headers=m, params={"start": s, "end": e}).json()]
    assert bo["id"] in ids
    ids_old = [o["id"] for o in requests.get(f"{API}/orders", headers=m, params={"start": "2024-01-01T00:00:00+00:00", "end": "2024-01-02T00:00:00+00:00"}).json()]
    assert bo["id"] not in ids_old
    assert requests.get(f"{API}/orders", headers=m, params={"start": "bad", "end": "bad"}).status_code == 400
    # biz range
    bids = [o["id"] for o in requests.get(f"{API}/biz/orders", headers=H(bt), params={"start": s, "end": e}).json()]
    assert bo["id"] in bids
    # courier: assign, incidents
    ct, cid = courier_login("1100000001", "123456")
    assert requests.patch(f"{API}/orders/{bo['id']}/assign", headers=m, json={"courier_id": cid}).status_code == 200
    co = requests.get(f"{API}/courier/orders", headers=H(ct)).json()
    mine = [o for o in co["active"] if o["id"] == bo["id"]][0]
    assert [p["name"] for p in mine["pickup_phones"]] == ["Cocina", "Caja"]
    r = requests.post(f"{API}/courier/orders/{bo['id']}/incident", headers=H(ct), json={"type": "cliente_no_localizable", "note": "TEST nadie abre"})
    assert r.status_code == 200 and r.json()["incident"]["label"] == "Cliente no localizable"
    assert requests.post(f"{API}/courier/orders/{bo['id']}/incident", headers=H(ct), json={"type": "nope"}).status_code == 422
    ct2, _ = courier_login("1100000002", "654321")
    assert requests.post(f"{API}/courier/orders/{bo['id']}/incident", headers=H(ct2), json={"type": "otro"}).status_code == 404
    od = requests.get(f"{API}/orders/{bo['id']}", headers=m).json()
    assert od["incidents"][0]["note"] == "TEST nadie abre" and od["incidents"][0]["by"]
    # cleanup order
    requests.patch(f"{API}/orders/{bo['id']}/status", headers=m, json={"status": "cancelado"})
    requests.delete(f"{API}/businesses/{bid}/account", headers=m)


def test_owner_order_default_open_and_payment(ctx):
    m = H(ctx["main"])
    bid = requests.get(f"{API}/businesses", headers=m).json()[0]["id"]
    r = requests.post(f"{API}/orders", headers=m, json={"business_id": bid, "customer_name": "TEST_open", "address": "Calle Alcalá 1, Madrid", "amount": 0, "payment_method": "datafono", "open": True, "dest_lat": DEST_LL[0], "dest_lng": DEST_LL[1]})
    assert r.status_code == 200, r.text
    o = r.json()
    assert o["open"] is True and o["courier_id"] is None and o["payment_method"] == "pagado"
    r2 = requests.post(f"{API}/orders", headers=m, json={"business_id": bid, "customer_name": "TEST_pay", "address": "Calle Alcalá 1, Madrid", "amount": 12, "payment_method": "datafono", "dest_lat": DEST_LL[0], "dest_lng": DEST_LL[1]}).json()
    assert r2["payment_method"] == "datafono"
    for oid_ in (o["id"], r2["id"]):
        requests.patch(f"{API}/orders/{oid_}/status", headers=m, json={"status": "cancelado"})


def test_emergency_phones_settings(ctx):
    m = H(ctx["main"])
    orig = requests.get(f"{API}/settings", headers=m).json()["emergency_phones"]
    r = requests.put(f"{API}/settings", headers=m, json={"emergency_phones": [{"name": "TEST_Jefe", "phone": "600999888"}]})
    assert r.status_code == 200 and r.json()["emergency_phones"][0]["name"] == "TEST_Jefe"
    ct, _ = courier_login("1100000001", "123456")
    ep = requests.get(f"{API}/courier/orders", headers=H(ct)).json()["emergency_phones"]
    assert ep[0] == {"name": "TEST_Jefe", "phone": "600999888"}
    # linked admin shares main settings
    assert requests.get(f"{API}/settings", headers=H(ctx["linked"])).json()["emergency_phones"][0]["name"] == "TEST_Jefe"
    requests.put(f"{API}/settings", headers=m, json={"emergency_phones": orig})
    assert requests.get(f"{API}/settings", headers=m).json()["emergency_phones"] == orig
