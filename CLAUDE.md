# 台指期回測系統

## 專案目標
建立一個台指期（TX）當沖策略回測系統，從期交所原始 tick 資料開始，處理成可回測的格式。

## 技術棧
- Python 3.14+（透過 asdf 管理）
- DuckDB 1.x（資料儲存）
- Backtesting.py（回測框架，待整合）
- pandas / numpy

## 資料來源

期交所每日 zip 檔，存放於 `data/raw/<年份>/Daily_YYYY_MM_DD.zip`。

### 目錄結構（raw data）
```
data/raw/
├── 2021/
│   └── Daily_2021_01_04.zip   ← 交易日
│   └── Daily_2021_01_01.zip   ← 非交易日（內容為 HTML，自動跳過）
├── 2022/ ...
└── 2026/
```

### zip 內容
每個 zip 包含一個同名 `.rpt` 檔（CSV 格式）：

```
成交日期,商品代號,到期月份(週別),成交時間,成交價格,成交數量(B+S),近月價格,遠月價格,開盤集合競價
20251231,TX     ,202601     ,084530,23150,2,-,-,
20251231,TX     ,202601     ,084531,23152,4,-,-,
```

### 欄位說明
- 成交日期：YYYYMMDD
- 商品代號：有空白需 trim，TX=台指期，MTX=小台
- 到期月份(週別)：YYYYMM，合約到期月份；**含 `/` 者為價差合約（如 `202409/202410`），需過濾**
- 成交時間：HHMMSS（6位數）
- 成交價格：成交價（價差合約的價格為價差值，可為負數）
- 成交數量(B+S)：買+賣合計口數
- 近月價格/遠月價格：多數為 `-`，忽略
- 開盤集合競價：非空且非 `-` 表示集合競價

### 台指期交易時段
- 日盤：08:45 ~ 13:45
- 夜盤：15:00 ~ 隔日 05:00
- 當沖策略目前只關注日盤

### 資料保存限制
**期交所網站僅保留最近 30 個交易日**的下載檔案。若超過一個月未更新，缺失資料無法從官網補回。建議設定每日自動排程。

## 資料庫 Schema

### DuckDB 檔案：`data/futures.duckdb`（不納入版控）

#### ticks 表（原始 tick，single source of truth）
```sql
CREATE TABLE ticks (
    trade_date   DATE,
    symbol       VARCHAR,
    contract     VARCHAR,
    trade_time   TIME,
    price        DECIMAL(10,2),
    volume       INT,
    is_auction   BOOLEAN
);
```

#### ohlcv_1m 表（1分K，從 tick 合成）
```sql
CREATE TABLE ohlcv_1m (
    timestamp       TIMESTAMP,
    symbol          VARCHAR,
    contract        VARCHAR,     -- 當日主力合約（日成交量最大者）
    open            DECIMAL(10,2),
    high            DECIMAL(10,2),
    low             DECIMAL(10,2),
    close           DECIMAL(10,2),
    volume          INT,
    tick_count      INT,
    is_rollover     BOOLEAN,
    adjustment      DECIMAL(10,2),  -- Panama 累計調整量
    adj_close       DECIMAL(10,2)   -- close + adjustment
);
```

#### rollover_log 表
```sql
CREATE TABLE rollover_log (
    rollover_date    DATE,
    symbol           VARCHAR,
    old_contract     VARCHAR,
    new_contract     VARCHAR,
    old_last_price   DECIMAL(10,2),  -- 前一日收盤（舊合約）
    new_first_price  DECIMAL(10,2),  -- 當日開盤（新合約）
    price_gap        DECIMAL(10,2),  -- old_last - new_first（正值=近月貴）
    method           VARCHAR         -- 'panama'
);
```

## 目錄結構
```
futures_backtest/
├── CLAUDE.md
├── pyproject.toml
├── .tool-versions
├── data/
│   ├── raw/              ← 原始 zip 檔（依年份子目錄，不納入版控）
│   └── futures.duckdb    ← DuckDB 資料庫（不納入版控）
├── specs/
│   └── daily_update.md   ← 每日更新系統規格
├── src/
│   ├── etl/
│   │   ├── download.py         ← 從期交所自動下載每日 zip ✅
│   │   ├── daily_update.py     ← 一鍵更新（下載 + 全 ETL）✅
│   │   ├── parse_rpt.py        ← zip/rpt → ticks 表 ✅
│   │   ├── build_1m.py         ← ticks → ohlcv_1m ✅
│   │   ├── build_continuous.py ← 換倉 + Panama adj_close ✅
│   │   └── validate.py         ← 資料驗證 ✅
│   ├── strategies/
│   │   └── (策略邏輯，純函數，不依賴框架)
│   └── backtest/
│       └── runner.py           ← Backtesting.py 膠水碼（待實作）
├── notebooks/
│   └── (探索性分析用)
└── tests/
    └── (驗證資料正確性)
```

## ETL 執行順序

### 每日更新（建議）
```bash
uv run python src/etl/daily_update.py
```
自動偵測起始日，下載今日資料，依序執行 Step 1–4。

### 單步執行
```bash
uv run python src/etl/download.py         # Step 0: 下載 zip
uv run python src/etl/parse_rpt.py        # Step 1: zip → ticks
uv run python src/etl/build_1m.py         # Step 2: ticks → ohlcv_1m
uv run python src/etl/build_continuous.py # Step 3: 換倉 + Panama
uv run python src/etl/validate.py         # Step 4: 驗證
```

每個 step 都可獨立重跑（冪等性）。

## 下載邏輯（download.py）

- URL：`https://www.taifex.com.tw/file/taifex/Dailydownload/Dailydownload/Daily_YYYY_MM_DD.zip`
- 期交所通常於 **18:30 前**更新當日資料，預設結束日為今天
- 自動起始日：磁碟上最新 zip 的隔天
- 非交易日偵測：HTTP 404 或 magic-byte 檢查（非 `PK\x03\x04` 開頭）
- 原子性寫入：`.zip.tmp` → rename，防止部分下載殘留

## 換倉邏輯

- 台指期結算日 = 每月第三個週三
- 換倉偵測：比較連續交易日的主力合約，當合約代號改變時即為換倉
- 主力合約：當日日盤成交量最大的合約
- 價差調整：**Panama backward method**
  - `adj_close = close + adjustment`
  - `adjustment`：累計所有後續換倉的 `(new_first - old_last)`
  - 最新合約 `adjustment = 0`，越早的歷史調整量越大
  - 換倉切換點：`adj_close(舊合約最後一根) == adj_close(新合約第一根)` ✅

## 資料現況（截至 2026-03）

| 項目 | 數值 |
|------|------|
| 日期範圍 | 2020-12-31 ~ 2026-03-02 |
| ticks 總筆數 | ~1.24 億筆 |
| 交易日數 | 1,248 天 |
| ohlcv_1m 總 bar 數 | 375,648 根 |
| 每日 bar 數 | 301 根（08:45~13:45） |
| 每日平均成交量 | ~17.9 萬口 |
| 換倉次數 | 62 次 |

## DuckDB 注意事項

### 已知型別陷阱
- `TIME` 型別無法直接轉 `INTERVAL`，需用字串拼接：
  ```sql
  (trade_date::VARCHAR || ' ' || trade_time::VARCHAR)::TIMESTAMP
  ```
- 外層 query 無法引用子查詢裡 `GROUP BY` 用的原始欄位，需在子查詢中先 alias
- Window function 不能放在 aggregate 的 `FILTER` 子句中

### 連線管理
```python
with duckdb.connect("data/futures.duckdb") as conn:
    ...
```
DuckDB 同時只允許一個寫入連線；多個 process 同時開啟同一 .duckdb 會報 lock error。

## 注意事項
- 所有時間為台灣時區 (Asia/Taipei)，raw data 本身即為台灣時間，不需轉換
- 每個 ETL step 都可以獨立重跑（冪等性）
- `build_continuous.py` 重跑時會清除 rollover_log 並重算所有 adjustment
- rpt 檔編碼：優先嘗試 UTF-8，失敗則 Big5 → CP950
- 價差合約（合約代號含 `/`）在 parse_rpt.py 階段過濾，不寫入 ticks
- 期交所僅保留最近 30 個交易日資料，需定期排程避免缺口
