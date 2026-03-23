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
│   └── futures.duckdb    ← DuckDB 資料庫（不納入版控）
├── specs/                ← 交易理念與背景（模板）
│   ├── trading-principles.md
│   ├── market-context.md
│   └── data-sources.md
├── docs/                 ← 系統技術文件
│   └── daily_update.md
├── research/             ← 假設驅動的研究記錄
│   ├── active/HXXX-名稱/    ← 進行中（proposal + tasks + results/）
│   └── archive/
│       ├── confirmed/HXXX-名稱/   ← summary.md + spec.md
│       ├── rejected/HXXX-名稱/
│       └── inconclusive/HXXX-名稱/
├── strategies/
│   ├── live/SXXX-名稱/      ← spec.md + performance.md
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
│   │   └── validate.py         ← 資料驗證 ✅
│   ├── strategies/
│   │   └── orb.py              ← ORBStrategy、ORBPhase4HybridStrategy ✅
│   ├── analysis/
│   │   ├── morning_briefing.py  ← 早盤簡報（ETL + key_prices + daily_range）✅
│   │   ├── key_prices.py        ← 關鍵價格 + 支撐壓力 ✅
│   │   ├── regime_health.py     ← Regime 健康快報（已驗證無交易濾網效果，已從 morning_briefing 移除）
│   │   └── daily_range.py       ← 日盤波動 + VIX 圖表 ✅
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

核心理念與市場背景：`specs/trading-principles.md`、`market-context.md`、`data-sources.md`

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
- 每次對話開始前，主動讀取相關的 specs/ 文件
- 不在未通過 GATE 的情況下執行回測
- 衍生想法記錄在當前結果文件的 Derived Hypotheses，不主動修改其他文件
- 所有數字結論必須附上樣本數
- 參數優化後必須做 out-of-sample 驗證才能標記 Confirmed

---

## 注意事項
- 所有時間為台灣時區 (Asia/Taipei)，raw data 本身即為台灣時間，不需轉換
- 每個 ETL step 都可以獨立重跑（冪等性）
- `build_continuous.py` 重跑時會清除 rollover_log 並重算所有 adjustment
- rpt 檔編碼：優先嘗試 UTF-8，失敗則 Big5 → CP950
- 價差合約（合約代號含 `/`）在 parse_rpt.py 階段過濾，不寫入 ticks
- 期交所僅保留最近 30 個交易日資料，需定期排程避免缺口
- 回答用台灣繁體中文優先，但可視需求保留英文的專有名詞
