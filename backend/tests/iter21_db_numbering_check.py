# DB checks: per-business order numbering (iteration 21) - read-only
import os
from collections import defaultdict
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
print("meta flag:", db.meta.find_one({"_id": "biz_numbering_v1"}))
by = defaultdict(list)
for d in db.orders.find({}, {"business_id": 1, "number": 1, "created_at": 1, "business_name": 1}):
    by[d["business_id"]].append(d)
problems = 0
for bid, docs in by.items():
    docs.sort(key=lambda d: d["created_at"])
    nums = [d["number"] for d in docs]
    dup = len(nums) != len(set(nums))
    ordered = nums == sorted(nums)
    contiguous = sorted(nums) == list(range(1, len(nums) + 1))
    c = db.counters.find_one({"_id": f"orders_biz_{bid}"})
    seq = c["seq"] if c else None
    ok = not dup and ordered and seq is not None and seq >= max(nums)
    if not ok:
        problems += 1
    print(f"{docs[0].get('business_name')!s:30} n={len(nums):4} min={min(nums)} max={max(nums)} dup={dup} ordered_by_date={ordered} contiguous={contiguous} counter={seq} {'OK' if ok else 'PROBLEM'}")
print("businesses with problems:", problems)
print("legacy global counter:", list(db.counters.find({"_id": {"$not": {"$regex": "^orders_biz_"}}})))
