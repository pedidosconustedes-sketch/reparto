# Iteration 14: seed (arg "create") / cleanup (arg "delete"): delivered order for Lucía whose 'entregado' event time differs from updated_at
import os
import sys
import json
from datetime import datetime, timezone, timedelta
import requests
from bson import ObjectId
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
API = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"
mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
H = {"Authorization": "Bearer " + requests.post(f"{API}/auth/login", json={"email": "admin@delivery.com", "password": "Admin12345"}, timeout=30).json()["token"]}

if sys.argv[1] == "create":
    C = {"Authorization": "Bearer " + requests.post(f"{API}/auth/courier/login", json={"phone": "1100000002", "pin": "654321"}, timeout=30).json()["token"]}
    cid = str(mdb.users.find_one({"phone": "1100000002", "role": "courier"})["_id"])
    bid = requests.post(f"{API}/businesses", headers=H, json={"name": "TEST_UIBiz14", "address": "Calle Mayor 5, Madrid", "phone": "1100000094",
                                                               "default_fee": 3.5, "lat": 40.4165, "lng": -3.7058}, timeout=60).json()["id"]
    r = requests.post(f"{API}/orders", headers=H, json={"business_id": bid, "address": "Gran Vía 28, 28013 Madrid", "dest_lat": 40.4203, "dest_lng": -3.7019,
                                                        "courier_id": cid, "amount": 10, "delivery_fee": 3.0, "customer_name": "TEST_Hist14"}, timeout=60).json()
    for st in ("en_camino", "entregado"):
        requests.patch(f"{API}/courier/orders/{r['id']}/status", headers=C, json={"status": st}, timeout=30)
    now = datetime.now(timezone.utc)
    ev = now - timedelta(minutes=17)
    if ev.date() != now.date():
        ev = now.replace(hour=0, minute=1, second=0, microsecond=0)
    doc = mdb.orders.find_one({"_id": ObjectId(r["id"])})
    hist = doc["history"]
    for h in hist:
        if h["status"] == "entregado":
            h["at"] = ev.isoformat()
    mdb.orders.update_one({"_id": doc["_id"]}, {"$set": {"history": hist, "updated_at": now.isoformat()}})
    print(json.dumps({"bid": bid, "number": r["number"], "event_utc": ev.strftime("%H:%M"), "updated_utc": now.strftime("%H:%M")}))
else:
    for b in mdb.businesses.find({"name": "TEST_UIBiz14"}):
        bid = str(b["_id"])
        requests.delete(f"{API}/businesses/{bid}", headers=H, timeout=30)
        mdb.orders.delete_many({"business_id": bid})
    mdb.businesses.delete_many({"name": "TEST_UIBiz14"})
    print("cleaned")
