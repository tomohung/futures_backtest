# 台指期回測系統

## 專案目標
建立一個台指期（TX）當沖策略回測系統，從期交所原始 tick 資料開始，處理成可回測的格式。

## 技術棧
- Python 3.14+（透過 asdf 管理）
- DuckDB 1.x（資料儲存）
- Backtesting.py（回測框架）
- pandas / numpy

## 資料來源

期交所每日 zip 檔，詳見 README.md。關鍵注意事項：
- 商品代號有空白需 trim
- 含 `/` 者為價差合約，需過濾
- 非交易日 zip 內容為 HTML，自動跳過

### 台指期交易時段
- 日盤：08:45 ~ 13:45
- 夜盤：15:00 ~ 隔日 05:00
- 當沖策略目前只關注日盤

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

#### ticks_options 表（選擇權原始 tick）
```sql
CREATE TABLE ticks_options (
    trade_date     DATE,
    symbol         VARCHAR,        -- 'TXO'
    strike         DECIMAL(10,2),  -- 履約價
    contract       VARCHAR,        -- 到期月份(週別)
    put_call       VARCHAR,        -- 'C' or 'P'
    trade_time     TIME,
    price          DECIMAL(10,2),
    volume         INT,
    is_auction     BOOLEAN
);
```
- 資料來源：`data/raw_options/` 下的 `OptionsDaily_YYYY_MM_DD.zip`
- ETL：`src/etl/parse_options_rpt.py`（只保留 TXO，過濾價差合約）
- 合約格式：`YYYYMM`（月合約，第三週三到期）、`YYYYMMWn`（週三到期）、`YYYYMMFn`（週五到期，2025-06-27 起）

#### stock_min 表（全市場個股分K，H095 DCI 盤中校準用）
```sql
CREATE TABLE stock_min (
    trade_date  DATE,
    stock_id    VARCHAR,
    minute      TIME,
    open   DECIMAL(12,4),
    high   DECIMAL(12,4),
    low    DECIMAL(12,4),
    close  DECIMAL(12,4),
    volume BIGINT,
    PRIMARY KEY (trade_date, stock_id, minute)
);
```
- 資料來源：FinMind `TaiwanStockKBar`（**Sponsor 限定**，6000 req/hr，一 request=一檔一天，token 取自 env `FINMIND_API_KEY`）
- **兩步 ETL（下載與入庫分離，避免長時間鎖住 futures.duckdb）**：
  1. `src/etl/download_stock_min.py`：逐交易日抓 → 寫 `data/stock_min_raw/YYYY-MM-DD.parquet`（**下載期間完全不開 DuckDB**，啟動時一次讀宇宙進記憶體後即不再碰主庫，故可與 daily_update / chart-ui 並行）。檔案存在=該日完成（冪等續傳）；fetched<expected 不寫檔待重抓；內建 5500/hr 節流 + quota gate
  2. `src/etl/load_stock_min.py`：`read_parquet` 全量重建 stock_min 表（預設入 futures.duckdb，`--db` 可改獨立庫）
- 宇宙取自 stock_day 當日 symbols（含已下市公司，避免 survivorship bias）
- **邊界**：上市 TWSE 全段、上櫃 TPEX 實質 2021-04-13 起（stock_day 上櫃宇宙起點）

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
│   ├── raw/              ← 期貨原始 zip 檔（依年份子目錄，不納入版控）
│   ├── raw_options/      ← 選擇權原始 zip 檔（依年份子目錄，不納入版控）
│   ├── stock_min_raw/    ← 個股分k parquet 落地區（每日一檔，不納入版控）
│   └── futures.duckdb    ← DuckDB 資料庫（不納入版控）
├── docs/                 ← 系統技術文件
│   └── daily_update.md
├── research/             ← 假設驅動的研究記錄
│   ├── active/HXXX-名稱/    ← 進行中（proposal + tasks + results/）
│   └── archive/
│       ├── confirmed/HXXX-名稱/   ← summary.md + spec.md
│       ├── rejected/HXXX-名稱/
│       └── inconclusive/HXXX-名稱/
├── strategies/
│   ├── live/SXXX-名稱/      ← spec.md + performance.md + backtest.py
│   └── retired/
├── .claude/skills/       ← 研究工作流程 skills
├── src/
│   ├── etl/
│   │   ├── download.py         ← 從期交所自動下載每日 zip ✅
│   │   ├── daily_update.py     ← 一鍵更新（下載 + 全 ETL）✅
│   │   ├── parse_rpt.py        ← zip/rpt → ticks 表 ✅
│   │   ├── build_1m.py         ← ticks → ohlcv_1m ✅
│   │   ├── build_continuous.py ← 換倉 + Panama adj_close ✅
│   │   ├── parse_options_rpt.py ← options zip → ticks_options 表 ✅
│   │   ├── download_stock_market.py ← TWSE/TPEX 廣度資料下載（H079 用）✅
│   │   ├── parse_stock_market.py ← TWSE/TPEX → market_breadth + stock_day ✅
│   │   ├── download_stock_min.py ← 個股分k下載→parquet 落地（FinMind TaiwanStockKBar，DCI 校準用）✅
│   │   ├── load_stock_min.py    ← parquet → DuckDB stock_min 表（phase 2）✅
│   │   └── validate.py         ← 資料驗證 ✅
│   ├── strategies/
│   │   ├── orb.py              ← ORBStrategy（開盤區間突破）✅
│   │   ├── reversal.py         ← ReversalStrategy（BB 反轉）✅
│   │   ├── exhaustion.py       ← ExhaustionStrategy（趨勢耗竭反轉）✅
│   │   ├── estimate_hl_exit.py ← EstHL 出場策略 ✅
│   │   └── reversal_follow.py  ← Reversal 跟隨策略 ✅
│   ├── analysis/
│   │   ├── morning_briefing.py  ← 早盤簡報（ETL + key_prices + h103_alert + daily_range + breadth + fg_composite_monitor）✅
│   │   ├── key_prices.py        ← 關鍵價格 + 支撐壓力 ✅
│   │   ├── h103_alert.py        ← H103 跳空下方遠做多盤前提醒（觀察用，夜收預判 + 觸發價 X）✅
│   │   ├── regime_health.py     ← Regime 健康快報（已驗證無交易濾網效果，已從 morning_briefing 移除）
│   │   ├── daily_range.py       ← 日盤波動 + VIX 圖表 ✅
│   │   ├── breadth_thermometer.py ← H079 漲停萎縮溫度計（觀察用 alert，預設 RATIO ma7 pct=0.15）✅
│   │   └── fg_composite_monitor.py ← S004 fg-composite 每日監控（comp_z + 觸發狀態 + 4 指標分項）✅
│   └── backtest/
│       ├── runner.py            ← 資料載入、TrendMA/ADX 計算 ✅
│       ├── strategy_health.py   ← 策略健康監測（完整版，含回測交叉分析）✅
│       ├── optimize.py          ← Phase 2 網格搜尋 ✅
│       ├── optimize_phase4_hybrid.py ← Phase 4 Hybrid 優化 ✅
│       ├── optimize_phase5.py   ← Rolling OR 濾網 ✅
│       ├── optimize_longonly.py ← Long-only + ADX 優化 ✅
│       ├── explore_*.py         ← 探索性分析 ✅
│       ├── analyze.py           ← 交易分析 ✅
│       └── summary_all.py       ← 策略跨年度比較 ✅
├── indicators/
│   └── tradingview/      ← TradingView Pine Script 指標
└── output/               ← 回測結果 CSV（不納入版控）
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

詳見 `docs/daily_update.md`。

## 換倉邏輯

- 台指期結算日 = 每月第三個週三
- 換倉偵測：比較連續交易日的主力合約，當合約代號改變時即為換倉
- 主力合約：當日日盤成交量最大的合約
- 價差調整：**Panama backward method**
  - `adj_close = close + adjustment`
  - `adjustment`：累計所有後續換倉的 `(new_first - old_last)`
  - 最新合約 `adjustment = 0`，越早的歷史調整量越大
  - 換倉切換點：`adj_close(舊合約最後一根) == adj_close(新合約第一根)` ✅

## EstRange（預估振幅）

跨策略共用的核心指標。實作：`src/backtest/estimate_hl.py`
- SatZone 公式：`Upper = session_low + est_range - ema_range/8`
- 結算日量校正：×1.9（`runner.py` → `adjust_settlement_volume()`）
- 詳細演算法見原始碼，策略用法見 `strategies/live/S001-esthl/spec.md`


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

## 研究與策略開發

所有研究遵循假設驅動的迭代循環：理念 → 假設 → 分佈探索 → 回測驗證 → 歸檔
Confirmed 的假設才進入 `strategies/live/`。

### 命名慣例
- 假設：HXXX-簡短名稱（如 H032-gap-reversal），編號從最大號 +1
- 策略：SXXX-簡短名稱（如 S001-esthl）
- 現有研究索引：使用 `/status` 查看

### Skills

以下工作流程已建為 skills（`.claude/skills/`），可透過 slash command 觸發：

| Command | 用途 |
|---------|------|
| `/new-hypothesis` | 建立新假設研究（proposal.md + tasks.md） |
| `/explore` | 執行 Phase 1 分佈探索，產出 distribution.md + GATE |
| `/backtest` | 執行 Phase 2 回測驗證，產出 backtest.md + Verdict |
| `/archive` | 歸檔完成的假設到 confirmed/rejected/inconclusive |
| `/status` | 顯示所有假設的進度總覽 |

### 績效標準化
跨年度比較用 `損益% = 損益點數 / 進場價 × 100`，Sharpe 也基於損益%。

### Behavior Rules
- 每次對話開始前，主動讀取 `memory/MEMORY.md`
- 不在未通過 GATE 的情況下執行回測
- 衍生想法記錄在當前結果文件的 Derived Hypotheses，不主動修改其他文件
- 所有數字結論必須附上樣本數
- 參數優化後必須做 out-of-sample 驗證才能標記 Confirmed
- **研究腳本必須保留**：Phase 1（explore）和 Phase 2（backtest）產出的 Python 腳本必須存放在假設目錄下（如 `research/active/HXXX-名稱/explore.py`、`backtest.py`），不可只輸出 markdown 結果而不保存腳本。這些腳本是後續比對、衍生假設、重跑驗證的基礎。
- **Live 策略必須有可執行的回測腳本**：Confirmed 假設晉升到 `strategies/live/SXXX-名稱/` 時，必須包含最新版的回測腳本（`backtest.py`），確保任何時候都能重跑回測驗證。若策略邏輯有更新（參數調整、濾網修改），回測腳本也需同步更新。

---

## 常用分析指令
```bash
uv run python src/analysis/morning_briefing.py    # 早盤簡報（含 ETL 更新）
uv run python src/backtest/strategy_health.py     # 策略健康監測
uv run python src/backtest/summary_all.py         # 跨年度策略比較
```

## 注意事項
- 所有時間為台灣時區 (Asia/Taipei)，raw data 本身即為台灣時間，不需轉換
- 每個 ETL step 都可以獨立重跑（冪等性）
- `build_continuous.py` 重跑時會清除 rollover_log 並重算所有 adjustment
- 回答用台灣繁體中文優先，但可視需求保留英文的專有名詞
- K線圖配色遵循台灣慣例：**漲紅跌綠**（上漲=紅色、下跌=綠色）

## Chart UI（行情瀏覽 app）
```bash
uv run chart-ui            # 啟動，預設 http://127.0.0.1:8888/
./run-chart-ui-tailscale.sh                          # 綁 tailscale（自動抓 tailscale ip -4）
```
- 讀 `data/futures.duckdb` 的 `ohlcv_1m`；清單放 `data/chart_lists/*.json`（不納版控）。
- 回測腳本輸出清單：`from src.chart_ui.list_writer import write_chart_list_from_backtesting`。
- 內建『所有交易日』清單，點日期跳到當天 08:45。
