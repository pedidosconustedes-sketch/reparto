# Iteration 17 UI seed: linked secondary admin (demo main) + one TEST_ order today. Usage: seed | cleanup
import os, sys, json, requests
from dotenv import load_dotenv
from pymongo import MongoClient
from bson import ObjectId
load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
API = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
STATE = "/tmp/iter17_seed.json"
t = requests.post(f"{API}/auth/login", json={"email": "admin@delivery.com", "password": "Admin12345"}).json()["token"]
H = {"Authorization": f"Bearer {t}"}
if sys.argv[1] == "seed":
    a = requests.post(f"{API}/admins", headers=H, json={"name": "TEST Linked UI", "email": "test_linked_ui17@example.com", "password": "Password123", "linked": True})
    print("admin", a.status_code, a.text[:120])
    biz = requests.get(f"{API}/businesses", headers=H).json()[0]
    o = requests.post(f"{API}/orders", headers=H, json={"business_id": biz["id"], "customer_name": "TEST_UI17", "address": "Calle Mayor 1, Madrid", "amount": 10, "delivery_fee": 2})
    print("order", o.status_code, o.text[:120])
    json.dump({"admin": a.json().get("id"), "order": o.json().get("id")}, open(STATE, "w"))
else:
    st = json.load(open(STATE))
    if st.get("admin"):
        print("del admin", requests.delete(f"{API}/admins/{st['admin']}", headers=H).status_code)
    print("del order", db.orders.delete_many({"customer_name": "TEST_UI17"}).deleted_count)
    print("leftover test users", db.users.count_documents({"email": {"$regex": "^test_"}}))
