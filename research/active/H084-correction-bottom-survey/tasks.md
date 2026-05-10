# Tasks: 多頭修正底部訊號 Survey

> **注意**：H084 是 survey 型假設，傳統的 Phase 1 / Phase 2 不適用。改用 **Phase 0 Survey** 結構，
> 通過 GATE 後衍生新假設進入回測。

---

## Phase 0: Survey

### Step 0.1：資料層補齊

#### 0.1.1 融資餘額 ETL（新增）
- [ ] 確認資料源：TWSE「融資融券彙總表」每日 CSV / API
- [ ] 設計 schema：`margin_balance` 表（trade_date, financing_balance, financing_buy, financing_sell, financing_repay, short_balance, ...）
- [ ] 撰寫 `src/etl/parse_margin.py` 與 download script
- [ ] 回填歷史資料（至少 2010-01 起）
- [ ] 驗證資料連續性（無斷檔）

#### 0.1.2 景氣對策信號 ETL（新增）
- [ ] 確認資料源：國發會「景氣對策信號」月頻公告（CSV/API）
- [ ] 設計 schema：`econ_signal` 表（report_month, total_score, light_color, components_json）
- [ ] 撰寫 `src/etl/parse_econ_signal.py`
- [ ] 回填歷史資料（至少 2008-01 起）
- [ ] 注意：信號公告約有 25 天延遲，要記錄 `published_date` 以便做 point-in-time 分析

#### 0.1.3 既有資料抽出/驗證
- [ ] 確認 `stock_day` 涵蓋 2010 起 TWSE 上市個股（用於 52w 新低家數）
- [ ] 確認 `market_breadth` 涵蓋 2010 起的漲跌家數、漲跌量
- [ ] 確認 `daily_range` 的 VIX 起始日期；若不足回填
- [ ] 確認 `ticks_options` 可算 5 日 P/C ratio（或改用期交所每日彙總）

### Step 0.2：Tier 標定

- [ ] 撰寫 `research/active/H084-correction-bottom-survey/zigzag_tiers.py`
  - Input：TAIEX 日線收盤
  - Algorithm：peaks-and-troughs identification
  - Output：`tiers.csv`（peak_date, peak_price, trough_date, trough_price, drawdown_pct, recovery_pct, tier, duration_days）
- [ ] Tier 閾值設定：
  - A：drawdown ≥30% AND recovery ≥30%
  - B：drawdown 20–30% AND recovery ≥15%
  - C：drawdown 10–20% AND recovery ≥10%
  - D：drawdown 5–10% AND recovery ≥5%
- [ ] 人工檢查 Tier A/B/C 事件是否合理（必抓清單：2008-11、2020-03、2022-10、2024-08、2025-04 應出現於對應 Tier）
- [ ] 輸出：歷史事件清單表（時間軸視覺化 + 表格）

### Step 0.3：指標建置

依下表建置每個指標的日頻時間序列（部分指標為月頻），存於 `results/indicators.parquet`：

| 指標 ID | 名稱 | 計算方式 | 資料來源 |
|---|---|---|---|
| `econ_score` | 景氣對策信號分數 | 月頻原始分數（forward-fill 到日頻，標記 stale 天數） | `econ_signal` |
| `econ_blue_streak` | 景氣藍燈連續月數 | 連續藍燈/黃藍燈累計 | `econ_signal` |
| `taiex_dist_250ma` | TAIEX 距 250MA % | (close - MA250) / MA250 | `stock_day` |
| `taiex_dist_125ma_z` | TAIEX 距 125MA z-score | 標準化 | `stock_day` |
| `margin_drop_pct` | 融資餘額減幅 | (current - 60D high) / 60D high | `margin_balance` |
| `vix_pct` | 台指 VIX 百分位 | rolling 1Y percentile rank | `daily_range` |
| `pc_ratio_5d` | TXO P/C ratio 5日均 | 5 日成交量比平均 | `ticks_options` 或 期交所 |
| `breadth_adv_dec` | 漲跌家數比 | 漲家 / 跌家 | `market_breadth` |
| `breadth_adv_dec_cum` | 累積廣度（McClellan-style） | 漲跌家數差累積 | `market_breadth` |
| `new_lows_52w` | 52週新低家數 | TWSE+TPEX 個股當日收盤 ≤ 252日最低 | `stock_day` |
| `volume_shrink` | 大盤量能萎縮 | 5MA volume / 60MA volume | `stock_day` |

- [ ] 撰寫 `research/active/H084-correction-bottom-survey/build_indicators.py`
- [ ] 驗證每個指標無缺值、極值合理
- [ ] 輸出 `indicators.parquet` 與 schema 文件

### Step 0.4：指標軌跡分析（事件研究）

- [ ] 撰寫 `research/active/H084-correction-bottom-survey/event_study.py`
- [ ] 對每個 Tier B/C 事件，計算每個指標在 trough_date ±30 個交易日的軌跡
- [ ] 輸出：每個指標一張多事件疊圖（每個事件一條線、X = 事件相對天數、Y = 指標值或百分位）
- [ ] 視覺化重點：
  - 哪些指標在底部當天接近極值？
  - 哪些指標領先（極值在 -10 ~ -1 天）？哪些落後（+1 ~ +10 天）？
  - 不同 Tier 的指標型態是否有差異？

### Step 0.5：百分位分析

- [ ] 計算每個指標在歷史 Tier B/C 底部當天的百分位（vs 全樣本分佈）
- [ ] 表格輸出：行 = 事件、列 = 指標、值 = 百分位
- [ ] 標記哪些指標在多數事件中都處於極值（>85 或 <15）
- [ ] 統計每個指標的「在底部呈現極值」的命中率

### Step 0.6：相關性矩陣

- [ ] 計算所有指標兩兩 Pearson + Spearman 相關
- [ ] 視覺化：相關性熱力圖
- [ ] 識別冗餘指標群（|r| ≥ 0.6）
- [ ] 從每個冗餘群中挑出代表指標

### Step 0.7：先導/落後性質分析

- [ ] 對每個指標，找出其極值（在事件 ±30D 內）出現的相對天數
- [ ] 統計每個指標的「極值偏移分佈」（中位數、IQR）
- [ ] 分類：先導（中位數 < -3）、同步（-3 ≤ 中位數 ≤ +3）、落後（中位數 > +3）

### Step 0.8：保險絲層驗證

- [ ] 對歷史每一天，計算「250MA below + 景氣信號 ≥3 月藍燈」雙條件
- [ ] 驗證：
  - Tier A 事件期間是否觸發？（應該是 Yes）
  - Tier B/C 事件期間是否觸發？（應該是 No 或極短時間）
- [ ] 輸出時間軸圖：保險絲狀態 vs 各 Tier 事件區間

---

### GATE

**問題：Survey 結果是否支持進入下一階段（衍生假設）？**

通過 GATE 的條件（皆需成立）：

- [ ] **指標可靠性**：≥ 3 個指標在 Tier B/C 底部事件中呈現可重現極值（命中率 ≥60%）
- [ ] **非冗餘性**：可靠指標中至少有 2 個彼此 |r| < 0.6
- [ ] **保險絲可用性**：250MA + 景氣信號雙條件能正確區分 Tier A vs Tier B/C
- [ ] **資料完整性**：所有指標皆涵蓋 2010-01 至今且無重大缺口

**決定：**

- [ ] 通過 → 衍生新假設：
  - 若 3+ 個獨立指標可靠 → 開「TW F&G 合成版 forward-return 驗證」假設
  - 若 1–2 個指標可靠 → 開「個別指標 forward-return 驗證」假設
- [ ] 修改後重跑 → 調整指標清單、Tier 閾值、或時間範圍
- [ ] Archive 為 inconclusive → 樣本數或資料品質不足以下結論
- [ ] Archive 為 rejected → 指標普遍無法在底部呈現極值

---

## 後續階段（衍生假設，不在 H084 範圍內）

H084 通過 GATE 後，會在 `research/active/` 新建衍生假設處理：

- forward-return 評估（+60D / +120D / +250D vs DCA baseline）
- 訊號合成方式（z-score 加總 / 計票 / 機器學習）
- 訊號穩健性（out-of-sample、不同期間切片）
- 實作為策略：tranche 部位管理、保險絲整合
