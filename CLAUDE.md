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
├── specs/
│   ├── daily_update.md   ← 每日更新系統規格
│   └── strategies/       ← 策略規格文件
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
│   └── backtest/
│       ├── runner.py            ← 資料載入、TrendMA/ADX 計算 ✅
│       ├── optimize.py          ← Phase 2 網格搜尋 ✅
│       ├── optimize_phase4_hybrid.py ← Phase 4 Hybrid 優化 ✅
│       ├── optimize_phase5.py   ← Rolling OR 濾網 ✅
│       ├── optimize_longonly.py ← Long-only + ADX 優化 ✅
│       ├── explore_*.py         ← 探索性分析 ✅
│       ├── analyze.py           ← 交易分析 ✅
│       └── summary_all.py       ← 策略跨年度比較 ✅
├── indicators/
│   └── tradingview/      ← TradingView Pine Script 指標
├── output/               ← 回測結果 CSV（不納入版控）
├── notebooks/
└── tests/
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

## EstRange（預估振幅）

跨策略共用的核心指標，用於預估當日振幅、計算 SatZone 出場區和選擇權 credit spread 定價。

### 演算法（Volume-Weighted Estimated Range）

實作：`src/backtest/estimate_hl.py` → `compute_vol_estimated_range()`

1. 將日盤切成 5 分鐘 slot（08:45, 08:50, ..., 13:40，共 60 slots）
2. 維護歷史資料：
   - `ema_range` = EMA(20) of 每日日盤振幅（High - Low）
   - `ema_cum_vol[slot]` = 每個 slot 的累積量 EMA(20)
3. 每個 slot boundary 計算：
   - `vol_ratio = 今日累積量 / ema_cum_vol[slot]`
   - `est_range = ema_range × vol_ratio`
4. **延遲 1 個 slot**（5 分鐘），避免 lookahead
5. 當日 profile 在**收盤後**才加入歷史

### SatZone（滿足區）

```
SatZoneUpper = session_low + est_range - ema_range / 8
SatZoneLower = session_high - est_range + ema_range / 8
```

- `ema_range / 8` 是固定 offset，用前一天的 EMA（非當天 est_range）
- 用途：EstHL 策略的出場信號（Phase 1 觸碰 + Phase 2 跌破 5MA）

### 結算日 Volume 校正

ohlcv_1m 只存主力合約量，結算日（第三週三）量分散到新舊合約（~55/45），
主力量僅為實際的一半，導致 EstRange 低估。

- **乘數 = 1.9**（61 個結算日實測合併量/主力量的中位數，盤中恆定）
- 實作：`runner.py` → `adjust_settlement_volume()` 在載入後直接修改 Volume 欄位
- 結算日偵測：`_settlement_dates()` — 第三個週三，遇假日順延到下一個交易日
- Pine Script 同步：三個 `.pine` 都有 `settle_vol_mult` 偵測邏輯
- 注意：膨脹的量會進入 EMA 歷史，影響隔天 EstRange（已知，目前接受）

### 使用此指標的策略

| 策略 | 用途 |
|------|------|
| ORBWithEstHLExitStrategy | SatZone 出場 + EmaHL 計算 SL |
| EstRange Credit Spread | est_range × fraction 定義 strike |
| Reversal | SatZone 出場 |

### 相關檔案

- `src/backtest/estimate_hl.py` — 核心演算法
- `src/backtest/runner.py` — `adjust_settlement_volume()`, `_settlement_dates()`
- `src/strategies/estimate_hl_exit.py` — SatZone 兩階段出場 mixin
- `indicators/tradingview/est_range_tx.pine` — TradingView 顯示指標
- `indicators/tradingview/orb_est_hl_tx.pine` — 含 SatZone 出場的完整策略
- `specs/strategies/2026-03-20-settlement-volume-satzone.md` — 結算日校正實驗記錄

---

## 外部資料來源

### VIXTWN（台灣波動率指數）
- 路徑：`data/external_sources/VIXTWN.csv`
- 格式：`Date,VIXTWN`（日頻，交易日）
- 範圍：2016-11-25 ~ 2026-03-11（2,374 筆）
- 用途：波動率濾網、高 VIX 環境篩選（如 VIX > 20 避免進場，或反向作為均值回歸的確認）
- 更新：手動補充，不自動下載

---

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

## 策略開發工作流程

**規則：任何新策略或新 Phase 的實作，必須先在 `specs/strategies/` 下建立規格文件，經確認後才開始寫程式碼。**

### 規格文件命名慣例
```
specs/strategies/orb_phase<N>.md   ← 策略 Phase 迭代（如 orb_phase6.md）
specs/strategies/orb_<名稱>.md     ← 獨立策略實驗（如 orb_filters.md）
```

### 規格文件應包含
1. **背景與動機** — 上一個 Phase 的結論，本次要解決什麼問題
2. **假設與方向** — 核心假設，為什麼這個方法可能有效
3. **Step 0（探索）** — 實作前的資料分析，避免盲目優化
4. **指標 / 策略設計** — 公式、參數、候選方案
5. **優化網格** — 測試範圍與固定參數
6. **成功標準** — 量化目標（PF、win%、年度 PnL 等）
7. **實作順序** — 需修改 / 新建的檔案清單與順序
8. **備選方案** — 若主方向失敗的下一步

### 現有規格文件索引
- `specs/strategies/2026-03-03-orb.md` — ORB 策略總覽
- `specs/strategies/2026-03-03-orb_phase2.md` — Phase 2：固定百分比 SL/TP + 趨勢濾網
- `specs/strategies/2026-03-04-orb_phase4.md` — Phase 4：自適應 TP（OR 寬度 × 乘數）；`ORBLongStrategy` 為現行最佳
- `specs/strategies/2026-03-04-orb_longonly.md` — Long-only：僅做多 + ADX 進場濾網
- `specs/strategies/2026-03-03-orb_filters.md` — 各種濾網實驗紀錄（Rolling OR、Phase 5/6）
- `specs/strategies/2026-03-04-orb_phase6.md` — Phase 6：市場機制濾網（ADX / ATR% / 滾動勝率）
- `specs/strategies/2026-03-09-orb-with-est-high-low-exit.md` — ORBWithEstHLExitStrategy，entry_end=9:15，EmaHL bfill，2021–2026 總損益 +3720
- `specs/strategies/2026-03-09-orb-exit-crossover.md` — Direction A：EstHL進 × ORBLong出，entry_end=9:15，tp×3.0，2021–2026 總損益 +4221
- `specs/strategies/2026-03-11-portfolio-allocation.md` — **最佳組合**：EstHL + ORBLong 各½口，Sharpe 3.12，固定資金下優於三策略均分
- `specs/strategies/2026-03-20-settlement-volume-satzone.md` — 結算日 Volume ×1.9 校正 + SatZone fraction 實驗（fraction 失敗，維持 -ema/8）

### OR% 濾網（ORBLong 專用）

分析 2023–2025 共 190 筆交易，發現 OR 絕對寬度與勝率的關係依指數水位而異，改用相對比例：

```
OR% = OR寬度（08:45–09:30 最高 - 最低）/ 當日開盤價 × 100
```

**最佳範圍：0.3% ≤ OR% ≤ 1.0%**

| OR% 區間 | 筆數 | 勝率 | 平均損益 |
|----------|------|------|----------|
| < 0.3%   | 22   | 40%  | -9 pts（開盤太安靜，假突破多）|
| 0.3–1.0% | 156  | 62%  | +28 pts（甜蜜帶）|
| > 1.0%   | 12   | 42%  | -12 pts（過度波動，常反轉）|

加入濾網後全期結果（2021–2026）：325筆→274筆，損益 +4,971→+5,262，Sharpe 1.36→1.54。

### 績效標準化原則

**不應直接比較不同年份的絕對損益點數**，因指數水位不同。標準化方式：

```
損益% = 損益點數 / 進場價 × 100
每筆均% = 所有交易損益% 的平均值
```

範例：同樣賺 200 點，指數 20,000 時 = 1.0%，指數 30,000 時 = 0.67%，後者實際上較差。

Sharpe 計算也應基於每日損益%（非點數），才能跨年度公平比較。

---

## 注意事項
- 所有時間為台灣時區 (Asia/Taipei)，raw data 本身即為台灣時間，不需轉換
- 每個 ETL step 都可以獨立重跑（冪等性）
- `build_continuous.py` 重跑時會清除 rollover_log 並重算所有 adjustment
- rpt 檔編碼：優先嘗試 UTF-8，失敗則 Big5 → CP950
- 價差合約（合約代號含 `/`）在 parse_rpt.py 階段過濾，不寫入 ticks
- 期交所僅保留最近 30 個交易日資料，需定期排程避免缺口
- 回答用台灣繁體中文優先，但可視需求保留英文的專有名詞
