# 台指期回測系統

## 專案目標
建立一個台指期（TX）當沖策略回測系統，從期交所原始 tick 資料開始，處理成可回測的格式。

## 技術棧
- Python 3.12+
- DuckDB（資料儲存）
- Backtesting.py（回測框架）
- pandas / numpy

## 資料來源
期交所每日成交 tick 資料，格式為 `.rpt` 檔（CSV格式），存放於 `data/raw/` 目錄。

### rpt 檔格式
```
成交日期,商品代號,到期月份(週別),成交時間,成交價格,成交數量(B+S),近月價格,遠月價格,開盤集合競價
20251231,TX     ,202601     ,084530,23150,2,-,-,
20251231,TX     ,202601     ,084531,23152,4,-,-,
```

欄位說明：
- 成交日期：YYYYMMDD
- 商品代號：有空白需 trim，TX=台指期, MTX=小台
- 到期月份(週別)：YYYYMM，合約到期月份
- 成交時間：HHMMSS（6位數）
- 成交價格：成交價
- 成交數量(B+S)：買+賣合計口數
- 近月價格/遠月價格：多數為 `-`，忽略
- 開盤集合競價：標記是否為集合競價

### 台指期交易時段
- 日盤：08:45 ~ 13:45
- 夜盤：15:00 ~ 隔日 05:00
- 當沖策略目前只關注日盤

## 資料庫 Schema

### DuckDB 檔案：`data/futures.duckdb`

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
    contract        VARCHAR,
    open            DECIMAL(10,2),
    high            DECIMAL(10,2),
    low             DECIMAL(10,2),
    close           DECIMAL(10,2),
    volume          INT,
    tick_count      INT,
    is_rollover     BOOLEAN,
    adjustment      DECIMAL(10,2),
    adj_close       DECIMAL(10,2)
);
```

#### rollover_log 表
```sql
CREATE TABLE rollover_log (
    rollover_date    DATE,
    symbol           VARCHAR,
    old_contract     VARCHAR,
    new_contract     VARCHAR,
    old_last_price   DECIMAL(10,2),
    new_first_price  DECIMAL(10,2),
    price_gap        DECIMAL(10,2),
    method           VARCHAR
);
```

## 目錄結構
```
project/
├── CLAUDE.md
├── data/
│   ├── raw/              ← 原始 rpt 檔放這裡
│   └── futures.duckdb    ← DuckDB 資料庫
├── src/
│   ├── etl/
│   │   ├── parse_rpt.py       ← 解析 rpt 檔 → ticks 表
│   │   ├── build_1m.py        ← ticks → ohlcv_1m
│   │   └── build_continuous.py ← 換倉處理 + 連續合約
│   ├── strategies/
│   │   └── (策略邏輯，純函數，不依賴框架)
│   └── backtest/
│       └── runner.py          ← Backtesting.py 膠水碼
├── notebooks/
│   └── (探索性分析用)
└── tests/
    └── (驗證資料正確性)
```

## 換倉邏輯
- 台指期結算日 = 每月第三個週三
- 換倉方式：結算日當天，從近月合約切換到次近月合約
- 價差調整：Panama Method（計算新舊合約價差，累計調整歷史價格）
- 記錄每次換倉到 rollover_log

## 第一階段任務

請按以下順序執行：

### Step 1: parse_rpt.py
- 掃描 `data/raw/` 下所有 rpt 檔
- 解析 CSV，trim 空白，過濾出 TX（台指期）資料
- 寫入 DuckDB ticks 表
- 支援增量匯入（已匯入的日期跳過）
- 印出匯入統計：總筆數、日期範圍、每日平均 tick 數

### Step 2: build_1m.py
- 從 ticks 表合成 1 分 K
- 只處理日盤（08:45 ~ 13:45）
- 每分鐘的 OHLCV：open=第一筆, high=最高, low=最低, close=最後一筆, volume=sum
- 沒有成交的分鐘：用前一分鐘的 close 填充 OHLC，volume=0
- 寫入 ohlcv_1m 表

### Step 3: build_continuous.py
- 計算每月結算日（第三個週三）
- 在結算日偵測近月→次近月的切換
- 計算價差，累計 adjustment
- 更新 ohlcv_1m 的 adjustment 和 adj_close
- 寫入 rollover_log

### Step 4: 驗證
- 印出 ohlcv_1m 的基本統計（日期範圍、總bar數、平均日成交量）
- 隨機抽一天，比對 tick 和 1分K 的 OHLCV 是否一致
- 檢查換倉日前後的價格是否連續（adj_close 不應有跳空）

## 注意事項
- 所有時間用台灣時區 (Asia/Taipei)
- DuckDB 的連線用 context manager 管理
- 每個 step 都可以獨立重跑（冪等性）
- 如果 rpt 檔的編碼不是 UTF-8，試 Big5 或 CP950
