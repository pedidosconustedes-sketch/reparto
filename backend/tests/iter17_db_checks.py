# Iteration 17: DB-level verification of main admin email fix (no password guessing)
import os, sys, asyncio
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
from bson import ObjectId
import jwt

REAL_ID = "6ae34bf6c4b986a63025ed26"
DEMO_ID = "6ae347236362b29c3e2fb5c8"
EMAIL = "pedidosconustedes@gmail.com"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
mode = sys.argv[1] if len(sys.argv) > 1 else "state"

if mode == "state":
    docs = list(db.users.find({"email": EMAIL}))
    print("count email docs:", len(docs))
    for d in docs:
        print({k: d.get(k) for k in ["_id", "role", "name", "parent_id", "linked", "failed_logins", "locked_until", "auth_version"]})
    print("case-insensitive:", db.users.count_documents({"email": {"$regex": "^pedidosconustedes@gmail.com$", "$options": "i"}}))
    demo = db.users.find_one({"_id": ObjectId(DEMO_ID)})
    print("demo:", {k: demo.get(k) for k in ["email", "role", "parent_id", "failed_logins", "locked_until"]})
    print("owners total:", db.users.count_documents({"role": "owner"}))
    for o in db.users.find({"role": "owner"}):
        print("  owner", o["_id"], o.get("email"), "parent", o.get("parent_id"), "linked", o.get("linked"))
    print("indexes:", {k: v for k, v in db.users.index_information().items() if k == "uniq_role_email"})
    print("real businesses:", [b["name"] for b in db.businesses.find({"owner_id": REAL_ID})])
    print("real orders:", db.orders.count_documents({"owner_id": REAL_ID}), "couriers:", db.users.count_documents({"role": "courier", "owner_id": REAL_ID}))
    print("demo businesses:", [b["name"] for b in db.businesses.find({"owner_id": DEMO_ID})])
    print("hash:", db.users.find_one({"_id": ObjectId(REAL_ID)})["password_hash"])
elif mode == "dup":
    try:
        r = db.users.insert_one({"role": "owner", "name": "TEST_dup", "email": EMAIL, "password_hash": "x"})
        print("DUP INSERTED (BAD)", r.inserted_id)
        db.users.delete_one({"_id": r.inserted_id})
    except DuplicateKeyError as e:
        print("DuplicateKeyError OK:", str(e)[:150])
    print("count after:", db.users.count_documents({"email": EMAIL}))
elif mode == "token":
    d = db.users.find_one({"_id": ObjectId(REAL_ID)})
    tok = jwt.encode({"sub": REAL_ID, "role": "owner", "ver": d.get("auth_version", 0),
                      "exp": datetime.now(timezone.utc) + timedelta(minutes=10)}, os.environ["JWT_SECRET"], algorithm="HS256")
    print(tok)
elif mode == "reset":
    r = db.users.update_one({"_id": ObjectId(REAL_ID)}, {"$set": {"failed_logins": 0, "locked_until": None}})
    d = db.users.find_one({"_id": ObjectId(REAL_ID)})
    print("reset:", d.get("failed_logins"), d.get("locked_until"))
