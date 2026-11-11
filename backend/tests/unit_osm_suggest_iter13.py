# Iteration 13: unit check of osm_suggest postcode ordering / limit with Photon unreachable (Photon replaced by Nominatim rows)
import sys
sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
import server  # noqa: E402

print("as-is (Photon down):", len(server.osm_suggest("28013", None, 8)), len(server.osm_suggest("Calle Mayor 28013", None, 8)))
server._photon_rows = lambda q, near, limit: server._nominatim_rows(q, near, limit)
for q in ("Calle Mayor 28013", "28013", "Calle Mayor Madrid"):
    rows = server.osm_suggest(q, None, 8)
    print(q, "->", len(rows), [r["description"] for r in rows])
