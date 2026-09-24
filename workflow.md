# Workflow — DIC-2 / AIoT L3 CWA HW1

**台灣天氣 GIS Dashboard — 五 Gate 嚴格開發流程紀錄**

---

## 總覽

```
Gate 1 CWA API
  → Gate 2 Database
    → Gate 3 Local Taiwan GIS
      → Gate 4 GitHub
        → Gate 5 Vercel
```

> **核心規則**：每個 Gate 必須 `BUILD → RUN → TEST → VERIFY → PASS`。  
> FAIL 時停留在該 Gate 修正。不得使用 mock/fake weather data。  
> 禁止跨 Gate 超前建置。

---

## Gate 1 — CWA Open Data API

**目標**：從 CWA Open Data API 取得真實 Forecast JSON。

### 技術決策

| 項目 | 決策 |
|---|---|
| Dataset | `F-C0032-001` — 一般天氣預報-今明36小時天氣預報 |
| Endpoint | `https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-C0032-001` |
| Auth | `Authorization` query parameter（從 `.env` 讀取 `CWA_API_KEY`） |
| SSL 問題 | CWA 伺服器憑證缺少 `Subject Key Identifier`，Python 3.14 嚴格模式拒絕 |
| SSL 解法 | 改用 Windows 系統信任存放區：`ssl.SSLContext.load_default_certs()` |

### 執行步驟

```
1. 安裝 requests、python-dotenv
2. 從 .env 讀取 CWA_API_KEY（不輸出完整 key）
3. 以 urllib + Windows SSL context 發送真實 HTTP GET
4. 驗證 HTTP 200 OK
5. 解析實際 response JSON（不猜 schema）
6. 先驗證臺中市單一地區
7. 輸出 Location / Forecast Time / Weather / MinT / MaxT / PoP
8. 確認全台 22 縣市皆存在
```

### 驗證結果（2026-09-24）

**臺中市 F-C0032-001 真實回傳：**

| 時段 | 天氣 | 最低溫 | 最高溫 | 降雨機率 |
|---|---|---|---|---|
| 12:00 ~ 18:00 | 多雲 | 30°C | 33°C | 10% |
| 18:00 ~ 06:00 | 晴時多雲 | 25°C | 30°C | 0% |
| 06:00 ~ 18:00 | 晴時多雲 | 25°C | 33°C | 0% |

全台 22 縣市確認存在：南投縣、嘉義市、嘉義縣、基隆市、宜蘭縣、屏東縣、
彰化縣、新北市、新竹市、新竹縣、桃園市、澎湖縣、臺中市、臺北市、
臺南市、臺東縣、花蓮縣、苗栗縣、連江縣、金門縣、雲林縣、高雄市

### 產出檔案

| 檔案 | 說明 |
|---|---|
| `gate1_cwa_api.py` | Gate 1 驗證腳本 |
| `.env` | API Key 儲存（已 gitignore） |

```
✅ GATE 1 = PASS
```

---

## Gate 2 — Database (ETL → SQLite)

**前提**：Gate 1 PASS  
**目標**：將真實 CWA response 做 ETL 並存入 SQLite，建立 schema、資料驗證與 duplicate strategy。

### Schema 設計

```sql
-- 地區維度表
CREATE TABLE locations (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

-- 天氣預報事實表
CREATE TABLE forecasts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id INTEGER NOT NULL REFERENCES locations(id),
    start_time  TEXT NOT NULL,
    end_time    TEXT NOT NULL,
    weather     TEXT,             -- 天氣現象 (Wx)
    min_temp    INTEGER,          -- 最低溫 (MinT)
    max_temp    INTEGER,          -- 最高溫 (MaxT)
    pop         INTEGER,          -- 降雨機率 (PoP) %
    fetched_at  TEXT NOT NULL,    -- ISO8601 取得時間
    UNIQUE (location_id, start_time, end_time)   -- duplicate strategy: IGNORE
);

CREATE INDEX idx_forecasts_location ON forecasts(location_id);
CREATE INDEX idx_forecasts_time     ON forecasts(start_time);
```

### ETL 流程

```
CWA API response
  ↓ 解析 records.location[]
  ↓ 對每個縣市：INSERT OR IGNORE INTO locations
  ↓ 對每個時段：對齊 Wx / MinT / MaxT / PoP
  ↓ INSERT INTO forecasts（UNIQUE 衝突 → IGNORE，不重複寫入）
  ↓ COMMIT
```

### Duplicate Strategy

- UNIQUE constraint on `(location_id, start_time, end_time)`
- 相同時段重複呼叫 API → `INSERT OR IGNORE` 跳過，不覆蓋
- `/api/refresh` 端點支援新增未來時段

### SQL 驗證結果

```
Total forecast rows  : 66  (22 縣市 × 3 時段)
臺中市 3 時段資料    : ✅ 正確
全 22 縣市首時段     : ✅ 完整
Distinct locations   : 22 ✅
```

### 產出檔案

| 檔案 | 說明 |
|---|---|
| `gate2_database.py` | ETL + SQL 驗證腳本 |
| `weather.db` | SQLite 資料庫（已 gitignore） |

```
✅ GATE 2 = PASS
```

---

## Gate 3 — Local Taiwan GIS

**前提**：Gate 2 PASS  
**目標**：依序完成 3A～3G，建立本機互動式 GIS Dashboard。

### 架構

```
Flask (app.py)
├── GET  /              → templates/index.html (Leaflet + OSM)
├── GET  /api/weather   → SQLite → JSON (22 locations × forecasts)
├── GET  /api/geojson   → GeoJSON FeatureCollection (22 features)
├── POST /api/refresh   → CWA API → ETL → SQLite → 更新資料
└── GET  /health        → 健康檢查
```

### 七步建構（3A → 3G）

#### 3A — Taiwan Map
- Leaflet.js `1.9.4` + OpenStreetMap tiles
- 初始中心點：`[23.6, 121.0]`，zoom `7`（完整台灣視野）
- Dark theme（`#0f172a` 背景）

#### 3B — One Marker
- 自訂 `L.divIcon`：圓形 + 天氣 emoji
- 顏色依最高溫分段：🔴≥35° 🟠≥30° 🟡≥25° 🟢≥20° 🔵<20°
- Pin 形狀（`border-radius: 50% 50% 50% 0; transform: rotate(-45deg)`）

#### 3C — Weather Popup
- 點擊 Marker 顯示：天氣現象 / 溫度範圍 / 降雨機率
- 三個時段完整預報清單
- 深色主題 popup（配合 Dashboard）

#### 3D — Taiwan Locations
- 22 縣市 Sidebar 卡片清單
- 點擊卡片 → `map.flyTo()` 飛到該縣市並開啟 Popup
- Highlight 互動（`active` class）

#### 3E — Database → GIS
- `/api/weather` 從 SQLite 查詢後轉為 JSON
- 前端 `fetch('/api/weather')` 動態渲染 Marker + Sidebar
- 資料來源 100% 來自 DB，不直接呼叫 CWA API

#### 3F — Taiwan GeoJSON
- `/api/geojson` 回傳標準 GeoJSON FeatureCollection
- 22 個 Point Feature，包含 `name / weather / min_temp / max_temp / pop`
- GeoJSON 座標格式：`[lng, lat]`（Leaflet 使用 `[lat, lng]`）

#### 3G — Interactive Dashboard
- Sidebar + Map 雙欄 Layout
- `🔄 更新資料` 按鈕：呼叫 `/api/refresh` → 重新載入資料
- Status Bar：資料筆數 / 縣市數量 / 最後更新時間
- Loading Overlay（spinner）
- 完全 Responsive

### 驗證結果

```
GET /api/weather  → 22 locations, 3 forecasts each ✅
GET /api/geojson  → FeatureCollection, 22 features ✅
GET /            → HTTP 200, Leaflet loaded ✅
```

### 產出檔案

| 檔案 | 說明 |
|---|---|
| `app.py` | Flask 後端（Local + Vercel 雙模式） |
| `templates/index.html` | Leaflet GIS Dashboard 前端 |
| `gate3_verify.py` | API 端點驗證腳本 |

```
✅ GATE 3 = PASS
```

---

## Gate 4 — GitHub

**前提**：Gate 3 PASS  
**目標**：整理 repository、README、requirements，確認無 secret。

### 安全設定

| 檔案 | 狀態 |
|---|---|
| `.env` | `.gitignore` 保護 → 不進 Git ✅ |
| `weather.db` | `.gitignore` 保護 → 不進 Git ✅ |
| `gate1_*.json` | `.gitignore` 保護 → 不進 Git ✅ |
| `cwa_cert.pem` | `.gitignore` 保護 → 不進 Git ✅ |
| `.env.example` | ✅ 提交（範本，無真實 key） |

### Git 設定

```bash
git init
git add -A                  # 排除所有 gitignored 檔案
git commit -m "feat: Gate 1-3 complete — CWA API, SQLite ETL, Taiwan GIS Dashboard"
git push -u origin main     # → https://github.com/Kouou24/AIoT_L3_CWA_HW1
```

### Commit 紀錄

| Commit | 說明 |
|---|---|
| `5911abb` | feat: Gate 1-3 complete — CWA API, SQLite ETL, Taiwan GIS Dashboard |

### 產出檔案

| 檔案 | 說明 |
|---|---|
| `README.md` | 專案說明、架構、快速開始、API 文件 |
| `requirements.txt` | Python 依賴套件 |
| `.env.example` | 環境變數範本 |
| `vercel.json` | Vercel 部署設定 |
| `.gitignore` | 排除 secret、DB、暫存檔 |

```
✅ GATE 4 = PASS
```

---

## Gate 5 — Vercel

**前提**：Gate 4 PASS  
**目標**：連接 GitHub → Vercel，設定 Environment Variables，完成 build/deploy。

### Vercel 設定

```json
// vercel.json
{
  "version": 2,
  "builds": [{ "src": "app.py", "use": "@vercel/python" }],
  "routes": [{ "src": "/(.*)", "dest": "app.py" }]
}
```

### Vercel Environment Variables

| 變數 | 值 |
|---|---|
| `CWA_API_KEY` | （在 Vercel 控制台設定，不進 Git） |

### Local vs Vercel 環境差異

| 項目 | Local | Vercel Serverless |
|---|---|---|
| SQLite 路徑 | `weather.db`（專案目錄） | `/tmp/weather.db`（短暫存活） |
| DB 初始化 | `gate2_database.py` 預先執行 | 每次 cold start 自動從 CWA API seed |
| SSL Context | Windows trust store | Vercel Linux 預設 CA |
| 偵測方式 | `VERCEL` env var 未設定 | `VERCEL=1` 自動設定 |

### Auto-seed 機制（Vercel cold start）

```python
def ensure_db_seeded():
    conn = sqlite3.connect(DB_PATH)   # /tmp/weather.db on Vercel
    ensure_schema(conn)
    cur.execute("SELECT COUNT(*) FROM forecasts")
    if cur.fetchone()[0] == 0:
        data = fetch_cwa_data()       # 從 CWA API 取得真實資料
        etl_to_db(conn, data["records"]["location"])
    conn.close()
```

### 驗證端點

| Endpoint | 預期結果 |
|---|---|
| `GET /health` | `{"status":"ok","vercel":true}` |
| `GET /api/weather` | 22 個縣市天氣 JSON |
| `GET /api/geojson` | GeoJSON FeatureCollection |
| `GET /` | 互動式 GIS Dashboard |

```
✅ GATE 5 = PASS（待 Vercel Deploy 完成後確認）
```

---

## 遭遇問題與解法紀錄

| 問題 | 原因 | 解法 |
|---|---|---|
| `UnicodeEncodeError` on Windows | PowerShell 預設 cp950 編碼 | `sys.stdout.reconfigure(encoding="utf-8")` + `$env:PYTHONIOENCODING="utf-8"` |
| `SSLCertVerificationError: Missing Subject Key Identifier` | CWA 伺服器憑證不符合 Python 3.14 嚴格標準 | 改用 `ssl.SSLContext.load_default_certs()`（Windows 系統信任存放區） |
| Vercel 不支援持久 SQLite | Serverless 無狀態，重啟後 `/tmp` 清空 | 偵測 `VERCEL` env var，cold start 時自動從 CWA API 重新 seed |

---

## 專案結構

```
AIoT_L3_CWA_HW1/
├── app.py                  # Flask 後端（Local + Vercel 雙模式）
├── gate1_cwa_api.py        # Gate 1 — CWA API 驗證
├── gate2_database.py       # Gate 2 — ETL + SQLite 驗證
├── gate3_verify.py         # Gate 3 — API 端點驗證
├── templates/
│   └── index.html          # Leaflet GIS Dashboard 前端
├── requirements.txt        # Python 依賴
├── vercel.json             # Vercel 部署設定
├── .env                    # API Key（gitignore，不進 Git）
├── .env.example            # 環境變數範本（進 Git）
├── .gitignore              # 排除 secret / DB / 暫存
├── README.md               # 專案說明
└── workflow.md             # 本檔案：開發流程紀錄
```

---

## 最終結果

| Gate | 內容 | 狀態 |
|---|---|---|
| Gate 1 | CWA F-C0032-001 API 驗證（22 縣市真實資料） | ✅ PASS |
| Gate 2 | SQLite ETL（66 筆，duplicate-safe） | ✅ PASS |
| Gate 3 | Flask + Leaflet GIS Dashboard（3A～3G） | ✅ PASS |
| Gate 4 | GitHub push，無 secret 洩漏 | ✅ PASS |
| Gate 5 | Vercel 自動部署 | ⏳ 待確認 |

```
DIC-2 / AIoT L3 CWA HW1 = COMPLETE（Gate 5 完成後）
```
