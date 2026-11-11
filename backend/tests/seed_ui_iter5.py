# Seed helper for iteration 5 UI test: delivered TEST_ order with photo + note for Carlos
import sys
sys.path.insert(0, "/app/backend/tests")
import requests
from test_reports_payment_photo import BASE, _h
from test_photo_upload_iter5 import _png

ow = requests.post(f"{BASE}/auth/login", json={"email": "admin@delivery.com", "password": "Admin12345"}).json()["token"]
cr = requests.post(f"{BASE}/auth/courier/login", json={"phone": "1100000001", "pin": "123456"}).json()
ct, cid = cr["token"], cr["user"]["id"]
bs = requests.get(f"{BASE}/businesses", headers=_h(ow)).json()
o = requests.post(f"{BASE}/orders", headers=_h(ow), json={
    "business_id": bs[0]["id"], "customer_name": "TEST_ui_foto", "customer_phone": "600111222",
    "address": "C. de Bellver, 27, Tetuán, 28039 Madrid", "items": [], "amount": 15.0, "delivery_fee": 3.5,
    "payment_method": "efectivo", "courier_id": cid}).json()
print("order", o["id"], o["number"], o.get("dest_lat"), o.get("courier_id") == cid)
r = requests.post(f"{BASE}/courier/orders/{o['id']}/photo", headers=_h(ct), files={"file": ("p.png", _png(120, 120), "image/png")})
print("photo", r.status_code)
for st in ("en_camino", "entregado"):
    print(st, requests.patch(f"{BASE}/courier/orders/{o['id']}/status", headers=_h(ct), json={"status": st, "note": "TEST dejado en portería"}).status_code)
print("carlos", cid)
print([p for p in requests.get(f"{BASE}/payouts", headers=_h(ow)).json()])
