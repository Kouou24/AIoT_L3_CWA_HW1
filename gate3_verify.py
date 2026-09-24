import urllib.request
import json

# Test /api/weather
resp = urllib.request.urlopen('http://127.0.0.1:5000/api/weather', timeout=10)
data = json.loads(resp.read())
print(f'[/api/weather] {len(data)} locations')
if data:
    loc = data[0]
    n = loc["name"]
    lt = loc["lat"]
    fc_count = len(loc["forecasts"])
    print(f'  First: {n}  lat={lt}  forecasts={fc_count}')
    fc = loc['forecasts'][0]
    wx = fc["weather"]
    mn = fc["min_temp"]
    mx = fc["max_temp"]
    pp = fc["pop"]
    print(f'  Forecast[0]: {wx}  MinT={mn}  MaxT={mx}  PoP={pp}')

# Test /api/geojson
resp2 = urllib.request.urlopen('http://127.0.0.1:5000/api/geojson', timeout=10)
gj = json.loads(resp2.read())
gtype = gj["type"]
fcount = len(gj["features"])
print(f'[/api/geojson] type={gtype}  features={fcount}')
if gj['features']:
    f = gj['features'][0]
    fname = f["properties"]["name"]
    fcoords = f["geometry"]["coordinates"]
    print(f'  First feature: {fname}  geo={fcoords}')

# Test / (homepage)
resp3 = urllib.request.urlopen('http://127.0.0.1:5000/', timeout=10)
html = resp3.read().decode('utf-8')
hlen = len(html)
has_leaflet = 'leaflet' in html.lower()
print(f'[/] status={resp3.status}  len={hlen}  has-leaflet={has_leaflet}')
