# 全市場個股分 k 下載 pipeline — 設計 spec

> 日期：2026-06-07　|　動機：H095 DCI 盤中校準需要個股分 k（dci_spec §6/§7 要求用盤中資料重訂門檻）
> 本次範圍 = **raw 下載 only**。DCI 計算、上市 vs 全市場廣度選擇 → 延後依回測決定，不在本次。

## 1. 背景與動機

H095（reach-ladder-exit）的 DCI（方向共識指標）目前只用**收盤值** 2021–2026 驗證過。
`research/active/H095-reach-ladder-exit/dci_spec.md` §6/§7 明確要求：盤中門檻必須用**盤中即時三序列**重新校準
（W=權值前20大方向、H=成交值前20大方向、B=漲跌家數）。要算盤中 W/H/B，就需要全市場個股的**分 k**資料。

FinMind 已付費（Sponsor 層），其 `TaiwanStockKBar` dataset 提供台股分 k，僅 Sponsor 可用。

## 2. 範圍決策（已與使用者確認）

| 決策 | 選擇 | 理由 |
|---|---|---|
| 涵蓋範圍 | **全市場（上市 TWSE + 上櫃 TPEX）** | raw-first 重用：付費資料只抽一次，上櫃留待日後研究 |
| 時間跨度 | **2021–2026**（與 DCI 收盤驗證同期） | 能逐年查穩定性；上櫃實質 2021-04-13 起（本地 stock_day 上櫃宇宙起點） |
| 存法 | **Raw-first**（存逐檔分 k OHLCV） | 合專案 ticks→ohlcv SSOT 哲學；可重用、可追其他研究 |
| 上櫃在 DCI 怎麼用 | **延後**，先抓資料、之後看回測 | 不急著改 dci_spec 公式；raw 先到位 |
| 抓取層 | **FinMind 官方 SDK** `taiwan_stock_kbar(use_async=True)` | 官方維護、較少踩雷；冪等/續傳/backoff 由我們外層包 |
| 逐日宇宙來源 | **本地 `stock_day`** 逐日 symbols | 含當時上市、現已下市公司，避免 survivorship bias（對 B 家數尤其關鍵）|

**明確延後（不在本次）**：下游 `build_intraday_dci.py`（每分鐘 join 昨收算 W/H/B/DCI）、上市 vs 全市場廣度選擇、W 權值代理方式、昨收來源細節。

## 3. FinMind API 事實（已實測確認 2026-06-07）

- dataset：`TaiwanStockKBar`（**Sponsor 限定**，token 已在 env `FINMIND_API_KEY`）
- 欄位：`date, minute(HH:MM:SS), stock_id, open, high, low, close, volume`
- 個股盤時段：09:00–13:30，單檔單日約 272 根
- **限制：不接受 end_date**，伺服器回「一次只給一天」→ **一個 request = 一檔一天**
- 官方 SDK：`DataLoader().login_by_token(api_token=...)` →
  `taiwan_stock_kbar(stock_id_list=[...], date='YYYY-MM-DD', use_async=True)`，一次一天、async 批多檔
- 官方實測：2175 檔 / 2m31s（≈14 檔/秒）→ 全市場 ~2000 檔單日約 2–3 分
- 全市場 2021–2026 ≈ 1200 交易日 × ~2.5 分 ≈ **數十小時**，可分多段過夜回補
- SponsorPro 才有的「整日 parquet 單檔下載」更快，但目前 Sponsor 沒有（升級路徑備註）

## 4. 資料模型

### 新表 `stock_min`（raw-first、single source of truth）
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
- 不納版控（data/futures.duckdb 既有規範）
- 規模估算：~2000 檔 × ~272 根 × ~1200 日 ≈ ~6–7 億 row，DuckDB 可吞

### 進度 ledger `stock_min_progress`（續傳 + 安全）
```sql
CREATE TABLE stock_min_progress (
    trade_date   DATE PRIMARY KEY,
    expected     INTEGER,   -- 當日宇宙檔數（來自 stock_day）
    fetched      INTEGER,   -- 成功回應檔數（含當日無資料 = fetched-empty）
    failed       INTEGER,   -- 重試後仍失敗檔數
    n_rows       BIGINT,    -- 寫入 stock_min 的 row 數
    status       VARCHAR,   -- 'complete' | 'partial'
    fetched_at   TIMESTAMP
);
```

## 5. 元件：`src/etl/download_stock_min.py`

**主流程（逐交易日 loop）**
1. 參數 `--start`（預設 2021-01-01）`--end`（預設 today）`--market`（預設 both）
2. 交易日清單：取 `stock_day` 中該區間實際有資料的 `trade_date`（即交易日）
3. 對每個交易日 `d`：
   - 若 ledger 已 `status='complete'` → **跳過**（續傳）
   - 取當日宇宙 = `SELECT DISTINCT symbol FROM stock_day WHERE trade_date=d`（TWSE+TPEX）
   - 呼叫 SDK `taiwan_stock_kbar(stock_id_list=univ, date=d, use_async=True)`
   - **DELETE FROM stock_min WHERE trade_date=d** → **INSERT** 回傳資料（以日為冪等單位）
   - 寫/更新 ledger（expected/fetched/failed/n_rows/status）
4. 非交易日 / 空宇宙 → 跳過

**穩健性**
- **自適應 backoff**：SDK 呼叫包 try/except，遇 rate-limit / 連線錯誤 → 指數退避重試（上限數次）
- **個股當日無資料**（停牌/無成交）→ 視為 fetched-empty，非失敗
- **部分失敗**：當日有檔抓不到 → ledger 記 `status='partial'` + failed 數；可重跑該日補齊（DELETE+INSERT 冪等）
- **絕不清整表**：所有刪改以「日」為單位（呼應 memory：parse_stock_market 全量重跑中途 kill 大批遺失的教訓）
- kill 中途：已 complete 的日不受影響，重跑從未完成日續

**相依**
- 新增 `FinMind` 套件到 pyproject（SDK 抓取層）
- token 取自 env `FINMIND_API_KEY`

## 6. 已知邊界 / 風險

- 上櫃 raw 實質從 2021-04-13 起（本地 `stock_day` 上櫃宇宙起點）；TWSE 全段 2021。
- `stock_day` 只含「當日有成交」的代號 → 零成交股不在宇宙（對 DCI 無影響，無價變化不計家數）。
- 宇宙以 `STOCK_SYMBOL_RE = ^\d{4}[A-Z]?$` 篩出（既有 parse_stock_market 規則），含 ETF；raw 全收，下游 DCI 再篩。
- 全量回補耗時數十小時 → 設計為可分段、可續傳，非一次跑完。
- Sponsor rate limit 官方未明列數字 → 靠 backoff 自適應，不寫死門檻。

## 7. 驗收標準

- `stock_min` 表建立，2021–2026 全市場分 k 回補完成（上櫃 2021-04-13 起）
- `stock_min_progress` 每個交易日 `status='complete'`（或已知 partial 原因記錄）
- 抽樣驗證：任取數個交易日，`stock_min` 該日檔數 ≈ `stock_day` 該日宇宙數，分 k 根數合理（~272/檔）
- 腳本可中斷後續傳，重跑冪等（同日 DELETE+INSERT 不增量重複）
- 腳本保留在 `src/etl/`，符合「研究/ETL 腳本必須保留」鐵律

## 8. 延後項目（後續假設 / 任務）

- `build_intraday_dci.py`：每分鐘 join 昨收（stock_day 前一日 close）算 W/H/B/DCI_long/DCI_short → 盤中 DCI 序列表
- 依回測決定：DCI 廣度是否納入上櫃、W 權值代理方式（成交金額 vs 市值 vs 指數權重）
- 每日增量整合進 `daily_update.py`（先一次性回補，穩定後再接每日）
