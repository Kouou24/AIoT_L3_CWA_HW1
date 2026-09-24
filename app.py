"""
Taiwan Weather GIS — Flask Application
Gate 3 (Local) + Gate 5 (Vercel) compatible

Local mode  : reads weather.db (SQLite)
Vercel mode : fetches CWA API directly (no persistent SQLite in serverless)
"""

import os
import sys
import json
import ssl
import sqlite3
import urllib.request
import urllib.parse
from datetime import datetime
from flask import Flask, render_template, jsonify
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# ── Detect environment ─────────────────────────────────────────────────────
# On Vercel: VERCEL=1 env var is set automatically
IS_VERCEL = bool(os.environ.get("VERCEL"))
DB_PATH   = "/tmp/weather.db" if IS_VERCEL else "weather.db"

# ── Coordinates for all 22 Taiwan locations ────────────────────────────────
LOCATION_COORDS = {
    "臺北市": [25.0330, 121.5654],
    "新北市": [25.0169, 121.4627],
    "基隆市": [25.1276, 121.7392],
    "桃園市": [24.9937, 121.3010],
    "新竹市": [24.8066, 120.9686],
    "新竹縣": [24.7036, 121.1542],
    "苗栗縣": [24.5602, 120.8214],
    "臺中市": [24.1477, 120.6736],
    "彰化縣": [24.0518, 120.5161],
    "南投縣": [23.9609, 120.9718],
    "雲林縣": [23.7092, 120.4313],
    "嘉義市": [23.4800, 120.4491],
    "嘉義縣": [23.4518, 120.2554],
    "臺南市": [23.1417, 120.2513],
    "高雄市": [22.6273, 120.3014],
    "屏東縣": [22.5519, 120.5487],
    "臺東縣": [22.7583, 121.1444],
    "花蓮縣": [23.9871, 121.6015],
    "宜蘭縣": [24.6941, 121.7195],
    "澎湖縣": [23.5711, 119.5793],
    "金門縣": [24.4493, 118.3767],
    "連江縣": [26.1605, 119.9495],
}

# ── SSL context (Windows trust store) ─────────────────────────────────────
def make_ssl_ctx():
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.load_default_certs()
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx

# ── CWA API fetch ──────────────────────────────────────────────────────────
def fetch_cwa_data():
    API_KEY = os.getenv("CWA_API_KEY", "")
    BASE = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-C0032-001"
    qs = urllib.parse.urlencode({"Authorization": API_KEY, "format": "JSON"},
                                 quote_via=urllib.parse.quote)
    url = f"{BASE}?{qs}"
    ctx = make_ssl_ctx()
    with urllib.request.urlopen(url, context=ctx, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))

# ── SQLite helpers ─────────────────────────────────────────────────────────
def ensure_schema(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS locations (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        );
        CREATE TABLE IF NOT EXISTS forecasts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            location_id INTEGER NOT NULL REFERENCES locations(id),
            start_time  TEXT NOT NULL,
            end_time    TEXT NOT NULL,
            weather     TEXT,
            min_temp    INTEGER,
            max_temp    INTEGER,
            pop         INTEGER,
            fetched_at  TEXT NOT NULL,
            UNIQUE (location_id, start_time, end_time)
        );
        CREATE INDEX IF NOT EXISTS idx_fc_loc  ON forecasts(location_id);
        CREATE INDEX IF NOT EXISTS idx_fc_time ON forecasts(start_time);
    """)
    conn.commit()

def etl_to_db(conn, locations_raw):
    cur = conn.cursor()
    fetched_at = datetime.now().isoformat(timespec="seconds")
    inserted = skipped = 0
    for loc in locations_raw:
        loc_name = loc["locationName"]
        cur.execute("INSERT OR IGNORE INTO locations (name) VALUES (?)", (loc_name,))
        cur.execute("SELECT id FROM locations WHERE name = ?", (loc_name,))
        loc_id = cur.fetchone()[0]
        elem_map  = {we["elementName"]: we for we in loc["weatherElement"]}
        wx_times  = elem_map.get("Wx",   {}).get("time", [])
        min_times = elem_map.get("MinT", {}).get("time", [])
        max_times = elem_map.get("MaxT", {}).get("time", [])
        pop_times = elem_map.get("PoP",  {}).get("time", [])
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
                skipped += 1
    conn.commit()
    return inserted, skipped

def get_db_forecasts():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    # If DB is empty (Vercel cold start), seed it first
    cur.execute("SELECT COUNT(*) FROM forecasts")
    if cur.fetchone()[0] == 0:
        conn.close()
        return None   # Caller will fetch from API
    cur.execute("""
        SELECT l.name AS location,
               f.start_time, f.end_time,
               f.weather, f.min_temp, f.max_temp, f.pop
        FROM forecasts f
        JOIN locations l ON l.id = f.location_id
        ORDER BY l.name, f.start_time
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

def ensure_db_seeded():
    """Make sure DB exists and has data; seed from CWA if needed."""
    conn = sqlite3.connect(DB_PATH)
    ensure_schema(conn)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM forecasts")
    if cur.fetchone()[0] == 0:
        data = fetch_cwa_data()
        etl_to_db(conn, data["records"]["location"])
    conn.close()

def rows_to_locations_json(rows):
    locations_data = {}
    for row in rows:
        loc = row["location"]
        if loc not in locations_data:
            coords = LOCATION_COORDS.get(loc, [23.5, 121.0])
            locations_data[loc] = {
                "name": loc,
                "lat": coords[0],
                "lng": coords[1],
                "forecasts": [],
            }
        locations_data[loc]["forecasts"].append({
            "start_time": row["start_time"],
            "end_time":   row["end_time"],
            "weather":    row["weather"],
            "min_temp":   row["min_temp"],
            "max_temp":   row["max_temp"],
            "pop":        row["pop"],
        })
    return list(locations_data.values())

# ── Routes ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/weather")
def api_weather():
    ensure_db_seeded()
    rows = get_db_forecasts()
    if rows is None:
        # Fallback: get fresh from API
        data = fetch_cwa_data()
        conn = sqlite3.connect(DB_PATH)
        ensure_schema(conn)
        etl_to_db(conn, data["records"]["location"])
        conn.close()
        rows = get_db_forecasts()
    return jsonify(rows_to_locations_json(rows))

@app.route("/api/geojson")
def api_geojson():
    ensure_db_seeded()
    rows = get_db_forecasts() or []
    location_map = {}
    for row in rows:
        loc = row["location"]
        if loc not in location_map:
            location_map[loc] = {
                "weather":  row["weather"],
                "min_temp": row["min_temp"],
                "max_temp": row["max_temp"],
                "pop":      row["pop"],
            }
    features = []
    for name, coords in LOCATION_COORDS.items():
        info = location_map.get(name, {})
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [coords[1], coords[0]],
            },
            "properties": {
                "name":     name,
                "weather":  info.get("weather", "N/A"),
                "min_temp": info.get("min_temp"),
                "max_temp": info.get("max_temp"),
                "pop":      info.get("pop"),
            },
        })
    return jsonify({"type": "FeatureCollection", "features": features})

@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    data = fetch_cwa_data()
    conn = sqlite3.connect(DB_PATH)
    ensure_schema(conn)
    inserted, skipped = etl_to_db(conn, data["records"]["location"])
    conn.close()
    return jsonify({
        "inserted":   inserted,
        "skipped":    skipped,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    })

@app.route("/health")
def health():
    return jsonify({"status": "ok", "vercel": IS_VERCEL, "db": DB_PATH})


if __name__ == "__main__":
    # Local development
    if sys.stdout.encoding != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    ensure_db_seeded()
    print("=" * 60)
    print("  Taiwan Weather GIS — Local Dev Server")
    print(f"  DB   : {DB_PATH}")
    print("  URL  : http://127.0.0.1:5000")
    print("=" * 60)
    app.run(debug=False, host="0.0.0.0", port=5000)
