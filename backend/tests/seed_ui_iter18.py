# Iteration 18 UI seed: TEST km-priced business + business account + owner order accepted by courier with incident.
# Usage: seed | cleanup
import os, sys, json, requests
from dotenv import load_dotenv
from pymongo import MongoClient
from bson import ObjectId
load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
API = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
STATE = "/tmp/iter18_seed.json"
t = requests.post(f"{API}/auth/login", json={"email": "admin@delivery.com", "password": "Admin12345"}).json()["token"]
H = {"Authorization": f"Bearer {t}"}
if sys.argv[1] == "seed":
    b = requests.post(f"{API}/businesses", headers=H, json={
        "name": "TEST_UI18 Km", "address": "Puerta del Sol, Madrid", "default_fee": 4, "pricing_mode": "km",
        "km_base_price": 3, "km_base_km": 2, "km_extra_price": 0.5, "lat": 40.4168, "lng": -3.7038}).json()
    print("acc", requests.put(f"{API}/businesses/{b['id']}/account", headers=H, json={"email": "test_ui18_biz@example.com", "password": "Secret1234"}).status_code)
    bt = requests.post(f"{API}/auth/login", json={"email": "test_ui18_biz@example.com", "password": "Secret1234"}).json()["token"]
    o = requests.post(f"{API}/biz/orders", headers={"Authorization": f"Bearer {bt}"}, json={
        "business_id": "x", "customer_name": "TEST_UI18 Cliente", "address": "Estadio Bernabéu, Madrid", "amount": 15,
        "dest_lat": 40.4530, "dest_lng": -3.6883}).json()
    print("order", o.get("id"), o.get("distance_km"), o.get("delivery_fee"))
    ct = requests.post(f"{API}/auth/courier/login", json={"phone": "1100000001", "pin": "123456"}).json()["token"]
    CH = {"Authorization": f"Bearer {ct}"}
    print("accept", requests.post(f"{API}/courier/orders/{o['id']}/accept", headers=CH).status_code)
    print("incident", requests.post(f"{API}/courier/orders/{o['id']}/incident", headers=CH, json={"type": "direccion_incorrecta", "note": "Portal no existe"}).status_code)
    json.dump({"bid": b["id"], "order": o["id"]}, open(STATE, "w"))
else:
    st = json.load(open(STATE)) if os.path.exists(STATE) else {}
    if st.get("bid"):
        requests.delete(f"{API}/businesses/{st['bid']}/account", headers=H)
        print("del biz", requests.delete(f"{API}/businesses/{st['bid']}", headers=H).status_code)
    # Orders of deleted TEST_ businesses (pytest + UI) are orphaned -> remove so courier payouts are not polluted.
    print("del orders", db.orders.delete_many({"business_name": {"$regex": "^TEST_"}}).deleted_count)
    print("leftover test biz", db.businesses.count_documents({"name": {"$regex": "^TEST_"}}))
    print("leftover test users", db.users.count_documents({"email": {"$regex": "^test_"}}))
