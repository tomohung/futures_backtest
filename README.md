# 台指期回測系統

台指期（TX）當沖策略回測系統，從期交所原始 tick 資料到策略回測的完整工具鏈。支援期貨與選擇權（TXO）資料。

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
│   ├── raw/               ← 期貨 zip 檔（依年份分目錄）
│   │   ├── 2021/
│   │   │   └── Daily_2021_MM_DD.zip
│   │   ├── 2022/ ...
│   │   └── 2026/
│   ├── raw_options/       ← 選擇權 zip 檔（依年份分目錄）
│   │   ├── 2025/
│   │   │   └── OptionsDaily_2025_MM_DD.zip
│   │   └── 2026/
│   └── futures.duckdb     ← 自動產生，勿納入版控
├── src/
│   ├── etl/
│   │   ├── download.py         ← 從期交所自動下載期貨每日 zip
│   │   ├── download_options.py ← 從期交所自動下載選擇權每日 zip
│   │   ├── daily_update.py     ← 一鍵更新（下載 + 全 ETL）
│   │   ├── parse_rpt.py        ← 期貨 zip/rpt → ticks 表
│   │   ├── parse_options_rpt.py← 選擇權 zip/rpt → ticks_options 表
│   │   ├── build_1m.py         ← ticks → ohlcv_1m（1分K）
│   │   ├── build_continuous.py ← Panama 換倉調整
│   │   └── validate.py         ← 資料正確性驗證
│   ├── strategies/
│   │   └── orb.py              ← ORBStrategy（Phase 2 基準）、ORBLongStrategy（現行最佳）
│   └── backtest/
│       ├── runner.py            ← 資料載入、TrendMA/ADX 計算
│       ├── estimate_hl.py       ← EstRange 計算（volume-weighted estimated range）
│       ├── backtest_estrange_options.py ← EstRange 選擇權 Credit Spread 回測
│       ├── optimize.py          ← Phase 2 網格搜尋
│       ├── optimize_phase4_hybrid.py ← Phase 4 Hybrid 網格搜尋
│       ├── optimize_phase5.py   ← Rolling OR 濾網實驗
│       ├── optimize_longonly.py ← Long-only + ADX 濾網優化
│       ├── explore_night_day.py ← 夜盤 vs 日盤相關性探索
│       ├── explore_regime.py    ← 市場機制指標探索（ADX/ATR%）
│       ├── analyze.py           ← 交易紀錄分析
│       └── summary_all.py       ← 所有策略跨年度比較總表
├── specs/
│   ├── daily_update.md          ← 每日更新系統規格
│   └── strategies/              ← 策略規格文件（新策略必須先建規格）
│       ├── orb.md
│       ├── orb_phase2.md
│       ├── orb_phase4.md        ← 現行最佳策略
│       ├── orb_longonly.md
│       ├── orb_filters.md
│       └── orb_phase6.md
├── output/                      ← 回測結果 CSV、分析報告（勿納入版控）
├── notebooks/                   ← Jupyter 探索分析
└── tests/
```

## 資料格式

### 期貨（TX）

期交所每日 zip 檔，解壓後為 `.rpt`（CSV 格式）：

```
成交日期,商品代號,到期月份(週別),成交時間,成交價格,成交數量(B+S),近月價格,遠月價格,開盤集合競價
20251231,TX     ,202601     ,084530,23150,2,-,-,
```

- 每個 zip 對應一個日曆日（含非交易日，非交易日為 HTML 頁面，自動跳過）
- 價差合約（合約代號含 `/`）自動過濾

### 選擇權（TXO）

選擇權 zip 檔格式類似，額外包含履約價格與買賣權別：

```
成交日期,商品代號,履約價格,到期月份(週別),買賣權別,成交時間,成交價格,成交數量(B or S),開盤集合競價
20260105,TXO    ,23000,202601     ,P,090703,3.1,1,
```

- 僅匯入 TXO（台指選擇權），過濾 Flex 合約（含 `F`）
- 合約代號：`202601` = 月選，`202601W1` = 週選

## 快速開始

### 1. 下載初始資料

> **注意**：期交所網站只保留最近 **30 個交易日**的資料。超過 30 天的歷史資料可從以下 Google Drive 取得：
>
> - [台指期貨（TX）](https://drive.google.com/drive/folders/1mLvxQdqEQUty9EOeUQ33BoQcqxToM-SE) — 下載後放入 `data/raw/<年份>/`
> - [台指選擇權（TXO）](https://drive.google.com/drive/folders/13IRRQqYpsQ8Au-X0XAjOaPrxgGlKHx0n) — 下載後放入 `data/raw_options/<年份>/`

```bash
# 自動下載（期交所通常於 18:30 前更新當日資料）
uv run python src/etl/download.py

# 或指定範圍
uv run python src/etl/download.py --start 2025-01-01 --end 2025-12-31
```

### 2. 建立資料庫

```bash
# 期貨資料
uv run python src/etl/parse_rpt.py        # zip/rpt → ticks
uv run python src/etl/build_1m.py         # ticks → 1分K
uv run python src/etl/build_continuous.py # Panama 換倉調整
uv run python src/etl/validate.py         # 驗證

# 選擇權資料（需先將 zip 放入 data/raw_options/）
uv run python src/etl/parse_options_rpt.py # zip/rpt → ticks_options
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
# 一鍵更新：自動下載最新 zip + 跑完整 ETL
uv run python src/etl/daily_update.py

# 只下載，不跑 ETL
uv run python src/etl/download.py

# 已有 zip，只跑 ETL
uv run python src/etl/daily_update.py --skip-download
```

### 設定自動排程（macOS launchd）

建立 `~/Library/LaunchAgents/com.futures-backtest.daily-update.plist`，每天 18:30 自動執行：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.futures-backtest.daily-update</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/YOUR_NAME/.asdf/shims/uv</string>
        <string>run</string>
        <string>python</string>
        <string>src/etl/daily_update.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/YOUR_NAME/Projects/futures_backtest</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>18</integer>
        <key>Minute</key><integer>30</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/Users/YOUR_NAME/Projects/futures_backtest/logs/daily_update.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/YOUR_NAME/Projects/futures_backtest/logs/daily_update.err</string>
    <key>RunAtLoad</key><false/>
</dict>
</plist>
```

載入排程：

```bash
mkdir -p logs
launchctl load ~/Library/LaunchAgents/com.futures-backtest.daily-update.plist
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
| `ticks` | 期貨原始 tick，single source of truth |
| `ohlcv_1m` | 1分K，日盤 08:45~13:45，含 `adj_close` |
| `rollover_log` | 每月換倉記錄，Panama 價差 |
| `ticks_options` | 選擇權原始 tick（TXO），含履約價、買賣權別 |

- `adj_close`：Panama backward adjustment，最新合約價格不調整，歷史往前遞增調整
- `adjustment`：累計調整量（`adj_close = close + adjustment`）
- `is_rollover`：換倉日當天的 K 棒標記為 `TRUE`

## 選擇權策略回測

### EstRange Credit Spread

基於 EstRange（Volume-Weighted Estimated Range）的選擇權賣方策略：

- 09:30 計算 EstRange，定出 Est High / Est Low
- 價格碰到一邊後，賣對側 Credit Spread（月選 TXO）
- 跳過週三（雙邊觸及率高）、12:30 收工

```bash
# 回測 2026 年
uv run python src/backtest/backtest_estrange_options.py --start 2026-01-01 --end 2026-03-18

# 自訂參數
uv run python src/backtest/backtest_estrange_options.py \
  --fraction 0.70 --spread-pct 0.50 --exit-time 12:30
```

詳細規格見 `specs/strategies/2026-03-17-estrange-options.md`。

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
