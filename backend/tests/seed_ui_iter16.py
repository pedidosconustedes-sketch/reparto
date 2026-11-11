# Seed/cleanup for iteration 16 UI tests: km-priced TEST business with 2 phones + an order assigned to courier 1
import os
import sys
import json
import requests

API = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"
tok = requests.post(f"{API}/auth/login", json={"email": "admin@delivery.com", "password": "Admin12345"}).json()["token"]
H = {"Authorization": f"Bearer {tok}"}

if sys.argv[1:] == ["cleanup"]:
    for b in requests.get(f"{API}/businesses", headers=H).json():
        if b["name"].startswith("TEST_"):
            for o in requests.get(f"{API}/orders", headers=H, params={"business_id": b["id"]}).json():
                requests.patch(f"{API}/orders/{o['id']}/status", headers=H, json={"status": "cancelado"})
            requests.delete(f"{API}/businesses/{b['id']}", headers=H)
    for a in requests.get(f"{API}/admins", headers=H).json():
        if a["name"].startswith("TEST_") or a["email"].startswith("test_"):
            requests.delete(f"{API}/admins/{a['id']}", headers=H)
    print("cleaned")
    sys.exit()

body = {"name": "TEST_KmUI", "address": "Puerta del Sol, Madrid", "lat": 40.4169, "lng": -3.7035, "default_fee": 5,
        "pricing_mode": "km", "km_base_price": 3, "km_base_km": 2, "km_extra_price": 1,
        "phones": [{"name": "Cocina", "phone": "600111222"}, {"name": "Caja", "phone": "600333444"}]}
bid = requests.post(f"{API}/businesses", headers=H, json=body).json()["id"]
requests.put(f"{API}/businesses/{bid}", headers=H, json=body)
cid = requests.post(f"{API}/auth/courier/login", json={"phone": "1100000001", "pin": "123456"}).json()["user"]["id"]
o = requests.post(f"{API}/orders", headers=H, json={"business_id": bid, "customer_name": "TEST_UIInc", "address": "Plaza de Castilla, Madrid",
                                                    "amount": 10, "delivery_fee": 4, "courier_id": cid, "dest_lat": 40.4669, "dest_lng": -3.6889}).json()
print(json.dumps({"bid": bid, "order_id": o["id"], "number": o["number"]}))
