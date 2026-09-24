"""
Gate 1 — CWA Open Data API Verification
Dataset: F-C0032-001 (一般天氣預報-今明36小時天氣預報，全台22縣市)

NOTE: CWA server cert is missing Subject Key Identifier extension.
      Python 3.14 strict SSL rejects it. We use the Windows system
      trust store via ssl.SSLContext.load_default_certs() which
      accepts the cert as Windows already trusts the issuer chain.
"""

import os
import sys
import json
import ssl
import urllib.request
import urllib.parse
from dotenv import load_dotenv

# ── Encoding fix for Windows console ──────────────────────────────────────
sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

# ── Helper: HTTP GET using Windows SSL trust store ─────────────────────────
def cwa_get(params: dict) -> dict:
    """Send GET to CWA API using Windows system cert store."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.load_default_certs()          # Windows trusted issuers
    ctx.check_hostname = True
    ctx.verify_mode   = ssl.CERT_REQUIRED

    BASE = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-C0032-001"
    qs   = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    url  = f"{BASE}?{qs}"

    with urllib.request.urlopen(url, context=ctx, timeout=20) as resp:
        status = resp.status
        body   = resp.read().decode("utf-8")
    return status, json.loads(body)

# ── 1. Read API Key from .env ──────────────────────────────────────────────
API_KEY = os.getenv("CWA_API_KEY", "")
if not API_KEY:
    print("❌ CWA_API_KEY not found in .env")
    sys.exit(1)

masked = API_KEY[:7] + "****-****-****-****-" + API_KEY[-4:]
print(f"✅ API Key loaded: {masked}")

# ── 2. Endpoint info ───────────────────────────────────────────────────────
print(f"\n📡 Endpoint : https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-C0032-001")
print(f"📦 Dataset  : F-C0032-001  (一般天氣預報-今明36小時天氣預報)")
print(f"📍 Location : 臺中市 (Step 6 — single location verify first)")

# ── 3 & 4. Send HTTP request & verify status ───────────────────────────────
print("\n🌐 Sending HTTP request …")
try:
    status, data = cwa_get({
        "Authorization": API_KEY,
        "format": "JSON",
        "locationName": "臺中市",
    })
except Exception as e:
    print(f"❌ Request failed: {e}")
    sys.exit(1)

print(f"🔁 HTTP Status: {status}")
assert status == 200, f"Expected 200, got {status}"
print("✅ HTTP 200 OK")

# ── 5. Parse JSON — follow actual schema ──────────────────────────────────
assert data.get("success") == "true", f"success={data.get('success')}"
locations = data["records"]["location"]
assert len(locations) > 0, "Empty location list"

loc = locations[0]
loc_name = loc["locationName"]
weather_elements = {we["elementName"]: we for we in loc["weatherElement"]}

# ── 6. Output for 臺中市 ───────────────────────────────────────────────────
print(f"\n── Location: {loc_name} ──────────────────────────────────────")
for elem_name, label in [
    ("Wx",   "天氣現象"),
    ("MinT", "最低溫 (°C)"),
    ("MaxT", "最高溫 (°C)"),
    ("PoP",  "降雨機率 (%)"),
]:
    elem = weather_elements.get(elem_name)
    if not elem:
        print(f"  ⚠  {elem_name} not in response")
        continue
    print(f"\n  [{elem_name}] {label}:")
    for t in elem["time"]:
        start = t["startTime"]
        end   = t["endTime"]
        val   = t["parameter"]["parameterName"]
        unit  = t["parameter"].get("parameterUnit", "")
        print(f"    {start} ~ {end}  → {val} {unit}")

# Save raw response for schema reference
with open("gate1_taichung_sample.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print(f"\n💾 Raw response saved → gate1_taichung_sample.json")

# ── 7. Verify all 22 locations ─────────────────────────────────────────────
print("\n── Step 7: Checking all Taiwan locations ────────────────────────")
status_all, data_all = cwa_get({
    "Authorization": API_KEY,
    "format": "JSON",
})
assert status_all == 200
all_locs = data_all["records"]["location"]

EXPECTED = [
    "宜蘭縣","桃園市","新竹縣","苗栗縣","彰化縣","南投縣","雲林縣",
    "嘉義縣","屏東縣","臺東縣","花蓮縣","澎湖縣","基隆市","新竹市",
    "嘉義市","臺北市","新北市","臺中市","臺南市","高雄市","連江縣","金門縣",
]
found = {l["locationName"] for l in all_locs}
print(f"  Total locations in response: {len(all_locs)}")

missing = [l for l in EXPECTED if l not in found]
if missing:
    print(f"  ⚠  Missing: {missing}")
    sys.exit(1)

print("  ✅ All 22 Taiwan locations confirmed:")
for name in sorted(found):
    print(f"      • {name}")

# Save full dataset
with open("gate1_all_locations.json", "w", encoding="utf-8") as f:
    json.dump(data_all, f, ensure_ascii=False, indent=2)
print(f"\n💾 Full dataset saved → gate1_all_locations.json")

print("\n" + "=" * 60)
print("✅  GATE 1 = PASS")
print("=" * 60)
