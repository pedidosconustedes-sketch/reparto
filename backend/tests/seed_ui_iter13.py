# Iteration 13: seed (arg "create") / cleanup (arg "delete") UI data: temp business + orders for cards, control tower and courier maps
import io
import os
import sys
import json
import base64
import requests
from PIL import Image
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
API = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"
mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
H = {"Authorization": "Bearer " + requests.post(f"{API}/auth/login", json={"email": "admin@delivery.com", "password": "Admin12345"}, timeout=30).json()["token"]}

if sys.argv[1] == "create":
    C = {"Authorization": "Bearer " + requests.post(f"{API}/auth/courier/login", json={"phone": "1100000001", "pin": "123456"}, timeout=30).json()["token"]}
    cid = str(mdb.users.find_one({"phone": "1100000001", "role": "courier"})["_id"])
    bid = requests.post(f"{API}/businesses", headers=H, json={"name": "TEST_UIBiz13", "address": "Calle Mayor 5, Madrid", "phone": "1100000093",
                                                               "default_fee": 3.5, "lat": 40.4165, "lng": -3.7058}, timeout=60).json()["id"]
    requests.put(f"{API}/businesses/{bid}/account", headers=H, json={"email": "test_uibiz13@delivery.com", "password": "UiBizPass1"}, timeout=30)
    B = {"Authorization": "Bearer " + requests.post(f"{API}/auth/login", json={"email": "test_uibiz13@delivery.com", "password": "UiBizPass1"}, timeout=30).json()["token"]}
    buf = io.BytesIO()
    Image.new("RGB", (96, 96), (220, 80, 40)).save(buf, "JPEG")
    requests.post(f"{API}/biz/photo-b64", headers=B, json={"data": base64.b64encode(buf.getvalue()).decode()}, timeout=60)
    base = {"business_id": bid, "address": "Gran Vía 28, 28013 Madrid", "dest_lat": 40.4203, "dest_lng": -3.7019}
    out = {"bid": bid}
    for key, extra in (("cash", {"courier_id": cid, "amount": 12.5, "delivery_fee": 3.5, "customer_name": "TEST_Cash13"}),
                       ("paid", {"courier_id": cid, "amount": 20, "delivery_fee": 4, "payment_method": "pagado", "customer_name": "TEST_Paid13",
                                 "address": "Calle de Alcalá 50, 28014 Madrid", "dest_lat": 40.4189, "dest_lng": -3.6960}),
                       ("none", {"amount": 8, "delivery_fee": 3, "customer_name": "TEST_None13", "address": "Calle de Atocha 20, 28012 Madrid",
                                 "dest_lat": 40.4128, "dest_lng": -3.7025}),
                       ("open", {"open": True, "amount": 9, "delivery_fee": 2.5, "customer_name": "TEST_Open13", "address": "Calle de Toledo 10, 28005 Madrid",
                                 "dest_lat": 40.4120, "dest_lng": -3.7080}),
                       ("done", {"courier_id": cid, "amount": 15, "delivery_fee": 3.25, "customer_name": "TEST_Done13", "address": "Calle de Fuencarral 45, 28004 Madrid",
                                 "dest_lat": 40.4245, "dest_lng": -3.7010})):
        r = requests.post(f"{API}/orders", headers=H, json={**base, **extra}, timeout=60).json()
        out[key] = r["number"]
        if key == "done":
            for st in ("en_camino", "entregado"):
                requests.patch(f"{API}/courier/orders/{r['id']}/status", headers=C, json={"status": st}, timeout=30)
    requests.post(f"{API}/courier/location", headers=C, json={"lat": 40.4170, "lng": -3.7040}, timeout=30)
    print(json.dumps(out))
else:
    for b in mdb.businesses.find({"name": "TEST_UIBiz13"}):
        bid = str(b["_id"])
        requests.delete(f"{API}/businesses/{bid}/account", headers=H, timeout=30)
        requests.delete(f"{API}/businesses/{bid}", headers=H, timeout=30)
        mdb.orders.delete_many({"business_id": bid})
    mdb.users.delete_many({"email": "test_uibiz13@delivery.com"})
    mdb.businesses.delete_many({"name": "TEST_UIBiz13"})
    print("cleaned")
