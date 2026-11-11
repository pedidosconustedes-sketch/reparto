# Iteration 21 UI seed: "create" -> business login on TEST_Num1 + order assigned to Carlos; "incident <oid>"; "cleanup"
import os
import sys
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
API = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
H = {"Authorization": "Bearer " + requests.post(f"{API}/auth/login", json={"email": "admin@delivery.com", "password": "Admin12345"}, timeout=30).json()["token"]}
cmd = sys.argv[1]
if cmd == "create":
    b = db.businesses.find_one({"name": "TEST_Num1"})
    bid = str(b["_id"]) if b else requests.post(f"{API}/businesses", headers=H, json={"name": "TEST_Num1", "address": "Calle Mayor 1, Madrid", "phone": "1100000091"}, timeout=60).json()["id"]
    print(requests.put(f"{API}/businesses/{bid}/account", headers=H, json={"email": "test_num21ui@delivery.com", "password": "NumPass123"}, timeout=30).status_code)
    carlos = requests.post(f"{API}/auth/courier/login", json={"phone": "1100000001", "pin": "123456"}, timeout=30).json()["user"]["id"]
    o = requests.post(f"{API}/orders", headers=H, json={"business_id": bid, "customer_name": "TEST_UICli", "address": "Calle Alcalá 10, Madrid",
                                                        "amount": 10, "delivery_fee": 3, "dest_lat": 40.42, "dest_lng": -3.70, "courier_id": carlos}, timeout=60).json()
    print("BID", bid, "ORDER", o["id"], "NUMBER", o["number"])
elif cmd == "incident":
    t = requests.post(f"{API}/auth/courier/login", json={"phone": "1100000001", "pin": "123456"}, timeout=30).json()["token"]
    r = requests.post(f"{API}/courier/orders/{sys.argv[2]}/incident", headers={"Authorization": "Bearer " + t}, json={"type": "cliente_no_responde", "note": "TEST_ui"}, timeout=30)
    print(r.status_code, r.text[:200])
elif cmd == "cleanup":
    for b in db.businesses.find({"name": {"$regex": "^TEST_"}}):
        requests.delete(f"{API}/businesses/{b['_id']}", headers=H, timeout=30)
    bids = db.orders.distinct("business_id", {"customer_name": {"$regex": "^TEST_"}})
    print("orders deleted:", db.orders.delete_many({"customer_name": {"$regex": "^TEST_"}}).deleted_count)
    for bid in bids:
        if not db.orders.find_one({"business_id": bid}):
            db.counters.delete_one({"_id": f"orders_biz_{bid}"})
    print("biz users left:", db.users.count_documents({"role": "business", "email": {"$regex": "^test_num21"}}))
