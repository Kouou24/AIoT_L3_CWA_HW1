# 台灣天氣 GIS Dashboard

**DIC-2 / AIoT L3 CWA HW1**

以中央氣象署（CWA）Open Data 為資料來源，從 API 資料取得開始，經過 ETL 與 SQLite 儲存，再建立本機 Taiwan GIS Web，最後推送 GitHub 並由 Vercel 自動部署。

---

## 架構設計

```
CWA API (F-C0032-001)
      ↓ ETL
   SQLite (weather.db)
      ↓
  Flask Backend
      ↓ /api/weather  /api/geojson
  Leaflet + OpenStreetMap
      ↓
  Interactive GIS Dashboard
```

## 技術堆疊

| 層 | 技術 |
|---|---|
| 資料來源 | CWA Open Data — F-C0032-001 (今明 36 小時天氣預報) |
| 後端 | Python 3.14 + Flask |
| 資料庫 | SQLite (weather.db) |
| 前端 GIS | Leaflet.js + OpenStreetMap tiles |
| 部署 | Vercel (Serverless) |

## 五 Gate 開發流程

```
Gate 1 CWA API  → Gate 2 Database → Gate 3 Local GIS
→ Gate 4 GitHub → Gate 5 Vercel
```

## 快速開始

### 1. 設定環境
```bash
git clone <this-repo>
cd AIoT_L3_CWA_HW1

# 複製 .env.example 並填入 API Key
cp .env.example .env
# 編輯 .env 填入 CWA_API_KEY

pip install -r requirements.txt
```

### 2. 初始化資料庫
```bash
python gate2_database.py
```
這會從 CWA API 取得 22 縣市天氣預報並存入 SQLite。

### 3. 啟動本機 GIS
```bash
python app.py
# 開啟瀏覽器 http://127.0.0.1:5000
```

## API Endpoints

| Endpoint | 說明 |
|---|---|
| `GET /` | 互動式 GIS Dashboard |
| `GET /api/weather` | 全台 22 縣市天氣 JSON（來自 SQLite） |
| `GET /api/geojson` | GeoJSON FeatureCollection |
| `POST /api/refresh` | 從 CWA API 重新取得資料並更新 DB |

## 資料庫 Schema

```sql
CREATE TABLE locations (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE forecasts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id INTEGER NOT NULL REFERENCES locations(id),
    start_time  TEXT NOT NULL,
    end_time    TEXT NOT NULL,
    weather     TEXT,
    min_temp    INTEGER,
    max_temp    INTEGER,
    pop         INTEGER,        -- Probability of Precipitation (%)
    fetched_at  TEXT NOT NULL,
    UNIQUE (location_id, start_time, end_time)
);
```

## 環境變數

| 變數 | 說明 |
|---|---|
| `CWA_API_KEY` | CWA Open Data API Key（必填） |

## 安全說明

- `.env` 已在 `.gitignore` 中，**不會被提交**
- `weather.db` 已在 `.gitignore` 中
- Vercel 部署時透過 Environment Variables 設定 `CWA_API_KEY`

## Dataset

- **F-C0032-001**: 一般天氣預報-今明36小時天氣預報
- 涵蓋全台 22 縣市
- 欄位：天氣現象 (Wx)、最低溫 (MinT)、最高溫 (MaxT)、降雨機率 (PoP)、舒適度 (CI)

## License

MIT
