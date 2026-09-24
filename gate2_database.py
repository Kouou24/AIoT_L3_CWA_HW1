"""
Gate 2 — ETL: CWA API → SQLite
Reads real CWA F-C0032-001 data for all 22 Taiwan locations,
performs ETL, stores in SQLite, then verifies with SQL SELECT.
"""

import os
import sys
import json
import ssl
import sqlite3
import urllib.request
import urllib.parse
from datetime import datetime
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()

DB_PATH = "weather.db"

# ── SSL helper (Windows trust store) ──────────────────────────────────────
def cwa_get(params: dict) -> dict:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.load_default_certs()
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED

    BASE = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-C0032-001"
    qs = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    url = f"{BASE}?{qs}"
    with urllib.request.urlopen(url, context=ctx, timeout=20) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))

# ── 1. Create / connect SQLite ─────────────────────────────────────────────
print(f"📂 Database: {DB_PATH}")
conn = sqlite3.connect(DB_PATH)
cur  = conn.cursor()

# ── 2. Schema ─────────────────────────────────────────────────────────────
cur.executescript("""
CREATE TABLE IF NOT EXISTS locations (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS forecasts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id     INTEGER NOT NULL REFERENCES locations(id),
    start_time      TEXT NOT NULL,
    end_time        TEXT NOT NULL,
    weather         TEXT,
    min_temp        INTEGER,
    max_temp        INTEGER,
    pop             INTEGER,       -- Probability of Precipitation (%)
    fetched_at      TEXT NOT NULL, -- ISO8601 timestamp when row was inserted
    UNIQUE (location_id, start_time, end_time)  -- duplicate strategy: IGNORE
);

CREATE INDEX IF NOT EXISTS idx_forecasts_location ON forecasts(location_id);
CREATE INDEX IF NOT EXISTS idx_forecasts_time     ON forecasts(start_time);
""")
conn.commit()
print("✅ Schema created / verified")

# ── 3. Fetch all 22 locations from CWA ─────────────────────────────────────
print("\n🌐 Fetching all Taiwan locations from CWA …")
API_KEY = os.getenv("CWA_API_KEY", "")
status, data = cwa_get({"Authorization": API_KEY, "format": "JSON"})
assert status == 200 and data["success"] == "true"

locations_raw = data["records"]["location"]
print(f"   → {len(locations_raw)} locations received")

# ── 4. ETL & insert ────────────────────────────────────────────────────────
fetched_at = datetime.now().isoformat(timespec="seconds")
inserted = skipped = 0

for loc in locations_raw:
    loc_name = loc["locationName"]

    # Upsert location
    cur.execute("INSERT OR IGNORE INTO locations (name) VALUES (?)", (loc_name,))
    cur.execute("SELECT id FROM locations WHERE name = ?", (loc_name,))
    loc_id = cur.fetchone()[0]

    # Build element map
    elem_map = {we["elementName"]: we for we in loc["weatherElement"]}

    # Align time slots across elements
    wx_times   = elem_map.get("Wx",   {}).get("time", [])
    min_times  = elem_map.get("MinT", {}).get("time", [])
    max_times  = elem_map.get("MaxT", {}).get("time", [])
    pop_times  = elem_map.get("PoP",  {}).get("time", [])

    for i, t in enumerate(wx_times):
        start   = t["startTime"]
        end     = t["endTime"]
        weather = t["parameter"]["parameterName"]
        min_t   = int(min_times[i]["parameter"]["parameterName"]) if i < len(min_times) else None
        max_t   = int(max_times[i]["parameter"]["parameterName"]) if i < len(max_times) else None
        pop_v   = int(pop_times[i]["parameter"]["parameterName"]) if i < len(pop_times) else None

        try:
            cur.execute("""
                INSERT INTO forecasts
                    (location_id, start_time, end_time, weather, min_temp, max_temp, pop, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (loc_id, start, end, weather, min_t, max_t, pop_v, fetched_at))
            inserted += 1
        except sqlite3.IntegrityError:
            skipped += 1  # Duplicate — UNIQUE constraint hit

conn.commit()
print(f"   → Inserted: {inserted}  |  Skipped (duplicate): {skipped}")

# ── 5. SQL Verification ────────────────────────────────────────────────────
print("\n── SQL Verification ────────────────────────────────────────────")

# 5a. Total row count
cur.execute("SELECT COUNT(*) FROM forecasts")
total = cur.fetchone()[0]
print(f"  Total forecast rows : {total}")
assert total > 0, "No rows inserted!"

# 5b. Spot-check 臺中市
print("\n  [臺中市 forecasts]")
cur.execute("""
    SELECT f.start_time, f.end_time, f.weather, f.min_temp, f.max_temp, f.pop
    FROM forecasts f
    JOIN locations l ON l.id = f.location_id
    WHERE l.name = '臺中市'
    ORDER BY f.start_time
""")
rows = cur.fetchall()
assert len(rows) > 0, "No rows for 臺中市"
for r in rows:
    print(f"    {r[0]} ~ {r[1]}  {r[2]:8s}  MinT={r[3]}°C  MaxT={r[4]}°C  PoP={r[5]}%")

# 5c. Multi-location spot check
print("\n  [Multi-location sample — first slot per city]")
cur.execute("""
    SELECT l.name, f.start_time, f.weather, f.min_temp, f.max_temp, f.pop
    FROM forecasts f
    JOIN locations l ON l.id = f.location_id
    WHERE f.start_time = (
        SELECT MIN(f2.start_time) FROM forecasts f2 WHERE f2.location_id = f.location_id
    )
    ORDER BY l.name
""")
multi = cur.fetchall()
for r in multi:
    print(f"    {r[0]:6s}  {r[1]}  {r[2]:8s}  Min={r[3]}°C  Max={r[4]}°C  PoP={r[5]}%")

# 5d. Count distinct locations stored
cur.execute("SELECT COUNT(*) FROM locations")
loc_count = cur.fetchone()[0]
print(f"\n  Distinct locations stored: {loc_count}")
assert loc_count == 22, f"Expected 22, got {loc_count}"

conn.close()

print("\n" + "=" * 60)
print(f"✅  GATE 2 = PASS  (DB: {DB_PATH})")
print("=" * 60)
