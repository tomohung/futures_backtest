# 台指期回測系統

台指期（TX）當沖策略回測系統，從期交所原始 tick 資料到策略回測的完整工具鏈。

## 前置需求

- macOS
- [asdf](https://asdf-vm.com/)
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code)（需有 Anthropic API 或 Pro/Max 訂閱）

## 安裝

```bash
# 1. Clone 專案
git clone <your-repo-url>
cd futures_backtest

# 2. 安裝 Python 與 uv（透過 asdf）
asdf plugin add python
asdf plugin add uv
asdf install  # 自動讀取 .tool-versions

# 3. 安裝依賴
uv sync
```

`.tool-versions` 鎖定版本：
```
python 3.14.3t
uv 0.10.7
```

## 專案結構

```
futures_backtest/
├── CLAUDE.md              ← Claude Code 的專案說明
├── README.md
├── pyproject.toml
├── .tool-versions         ← asdf 版本鎖定
├── data/
│   ├── raw/               ← 期交所 zip 檔（依年份分目錄）
│   │   ├── 2021/
│   │   │   └── Daily_2021_MM_DD.zip
│   │   ├── 2022/ ...
│   │   └── 2026/
│   └── futures.duckdb     ← 自動產生，勿納入版控
├── src/
│   ├── etl/
│   │   ├── parse_rpt.py       ← zip/rpt → ticks 表
│   │   ├── build_1m.py        ← ticks → ohlcv_1m（1分K）
│   │   ├── build_continuous.py ← Panama 換倉調整
│   │   └── validate.py        ← 資料正確性驗證
│   ├── strategies/            ← 策略邏輯（待實作）
│   └── backtest/              ← 回測執行器（待實作）
├── notebooks/                 ← Jupyter 探索分析
└── tests/
```

## 資料格式

期交所每日 zip 檔，解壓後為 `.rpt`（CSV 格式）：

```
成交日期,商品代號,到期月份(週別),成交時間,成交價格,成交數量(B+S),近月價格,遠月價格,開盤集合競價
20251231,TX     ,202601     ,084530,23150,2,-,-,
```

- 每個 zip 對應一個日曆日（含非交易日，非交易日為 HTML 頁面，自動跳過）
- 價差合約（合約代號含 `/`）自動過濾

## 快速開始

### 1. 準備資料

將期交所 zip 檔依年份放入對應目錄：

```
data/raw/
├── 2021/
│   ├── Daily_2021_01_04.zip
│   └── ...
└── 2026/
    └── Daily_2026_02_27.zip
```

### 2. 建立資料庫（依序執行）

```bash
# Step 1: 解析 zip/rpt → ticks 表（增量，已匯入日期自動跳過）
uv run python src/etl/parse_rpt.py

# Step 2: ticks → 1分K（日盤 08:45~13:45）
uv run python src/etl/build_1m.py

# Step 3: Panama 換倉調整，產生 adj_close
uv run python src/etl/build_continuous.py

# Step 4: 驗證資料正確性
uv run python src/etl/validate.py
```

### 3. 用 Claude Code 開發策略

```bash
claude

# 範例對話：
# > 幫我寫一個策略：日盤開盤後30分鐘內突破高低點就進場，
# >   用15分鐘K的ATR當停損，收盤前5分鐘強制平倉。
# >   回測近2年的TX資料。
```

## 每日更新資料

```bash
# 放入新的 zip 檔
cp Daily_2026_03_03.zip data/raw/2026/

# 增量匯入（已存在的日期自動跳過）
uv run python src/etl/parse_rpt.py
uv run python src/etl/build_1m.py
uv run python src/etl/build_continuous.py  # 會重算所有換倉調整
```

## 常用查詢

```python
import duckdb

conn = duckdb.connect("data/futures.duckdb")

# 拉取 1 分 K（含 Panama 調整後的連續合約價格）
df_1m = conn.execute("""
    SELECT timestamp, open, high, low, close, adj_close, volume
    FROM ohlcv_1m
    WHERE symbol = 'TX' AND timestamp >= '2024-01-01'
    ORDER BY timestamp
""").df()

# 合成 15 分 K
df_15m = df_1m.resample('15min', on='timestamp').agg({
    'open': 'first', 'high': 'max',
    'low': 'min', 'close': 'last',
    'adj_close': 'last', 'volume': 'sum'
}).dropna()

# 查換倉紀錄
conn.execute("""
    SELECT * FROM rollover_log WHERE symbol = 'TX' ORDER BY rollover_date
""").df()
```

## 資料說明

| 表 | 說明 |
|---|---|
| `ticks` | 原始 tick，single source of truth |
| `ohlcv_1m` | 1分K，日盤 08:45~13:45，含 `adj_close` |
| `rollover_log` | 每月換倉記錄，Panama 價差 |

- `adj_close`：Panama backward adjustment，最新合約價格不調整，歷史往前遞增調整
- `adjustment`：累計調整量（`adj_close = close + adjustment`）
- `is_rollover`：換倉日當天的 K 棒標記為 `TRUE`

## 疑難排解

### DuckDB 資料庫損壞或需要重建

```bash
rm data/futures.duckdb
uv run python src/etl/parse_rpt.py
uv run python src/etl/build_1m.py
uv run python src/etl/build_continuous.py
```

### rpt 檔編碼問題

`parse_rpt.py` 會自動嘗試 UTF-8 → Big5 → CP950。

### DuckDB 鎖定錯誤

```
IO Error: Could not set lock on file "futures.duckdb"
```

表示另一個 process 正在使用資料庫。關閉其他連線（如 Jupyter notebook）後重試。
