# Iteration 20 UI seed: TEST business + account, order A (2 incidents) + order B (no incident), courier Carlos.
# Usage: seed | incident <A|B> <type> <note> | cleanup
import os, sys, json, requests
from dotenv import load_dotenv
from pymongo import MongoClient
load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
API = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
STATE = "/tmp/iter20_seed.json"
t = requests.post(f"{API}/auth/login", json={"email": "admin@delivery.com", "password": "Admin12345"}).json()["token"]
H = {"Authorization": f"Bearer {t}"}
ct = requests.post(f"{API}/auth/courier/login", json={"phone": "1100000001", "pin": "123456"}).json()
CH = {"Authorization": f"Bearer {ct['token']}"}
cmd = sys.argv[1]
if cmd == "seed":
    b = requests.post(f"{API}/businesses", headers=H, json={"name": "TEST_UI20 Inc", "address": "Calle Mayor 1, Madrid", "default_fee": 4}).json()
    print("acc", requests.put(f"{API}/businesses/{b['id']}/account", headers=H, json={"email": "test_ui20_biz@example.com", "password": "Secret1234"}).status_code)
    st = {"bid": b["id"]}
    for k, name in (("A", "TEST_UI20 Ana"), ("B", "TEST_UI20 Bruno")):
        o = requests.post(f"{API}/orders", headers=H, json={"business_id": b["id"], "customer_name": name, "address": "Calle Alcalá 10, Madrid",
                                                             "amount": 18.5, "delivery_fee": 4, "courier_id": ct["user"]["id"]}, timeout=30).json()
        st[k], st[k + "num"] = o["id"], o["number"]
        print(k, o["id"], o["number"])
    for typ, note in (("cliente_no_responde", ""), ("direccion_incorrecta", "Portal 3B no existe")):
        print("inc A", requests.post(f"{API}/courier/orders/{st['A']}/incident", headers=CH, json={"type": typ, "note": note}).status_code)
    json.dump(st, open(STATE, "w"))
elif cmd == "incident":
    st = json.load(open(STATE))
    print("inc", sys.argv[2], requests.post(f"{API}/courier/orders/{st[sys.argv[2]]}/incident", headers=CH, json={"type": sys.argv[3], "note": sys.argv[4]}).json())
else:
    st = json.load(open(STATE)) if os.path.exists(STATE) else {}
    if st.get("bid"):
        requests.delete(f"{API}/businesses/{st['bid']}/account", headers=H)
        print("del biz", requests.delete(f"{API}/businesses/{st['bid']}", headers=H).status_code)
    print("del orders", db.orders.delete_many({"business_name": {"$regex": "^TEST_"}}).deleted_count)
    print("leftover test biz", db.businesses.count_documents({"name": {"$regex": "^TEST_"}}))
    print("leftover test users", db.users.count_documents({"email": {"$regex": "^(test_|tinc)"}}))
