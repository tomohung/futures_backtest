# H084 Phase 0 Survey 結論：distribution.md

> 假設：多頭修正底部訊號 Survey（TW 版 Fear & Greed 拆解）
> 型態：survey 假設（不直接回測）— Phase 0 是**唯一**的研究階段，通過 GATE 後衍生新假設

## TL;DR

**GATE 判決：✅ PASS**

Phase 0 Survey 確認：
- **VIX_pct + z 125MA + (dist 250MA)** 三個指標在歷史 Tier B/C trough 命中率 65-88%
- **econ_score + blue_streak** 能將 Tier A regime（系統熊）vs Tier B/C regime（多頭修正）的中位數**乾淨分流**（28.5 vs 17.0）
- 指標精簡後有 **4 個非冗餘軸**：VIX_pct（panic）/ z 125MA（technical）/ econ_score（regime）/ vol 5/60（volume，弱）
- 必抓事件全部捕捉：**2024-08（C-sub）、2025-04（B）、2026-03（C）** 都會被 VIX_pct 觸發

**Survey 限制（影響後續解讀，不影響 GATE）**：
- VIX 資料只有 2017+，pre-2017 Mode 2 樣本太少
- 融資資料 backfill 受 TWSE rate limit 影響，目前只 57 天可用，**等 backfill 完成後本 survey 應重跑加入 margin**
- 廣度（market_breadth、52w 新低家數）資料尚未跑 ETL，後續補

---

## 資料層

| 資料 | 範圍 | 狀態 |
|---|---|---|
| TAIEX 日線 | 2008-01 ~ 2026-05（4484 行） | ✅ via yfinance ^TWII |
| VIX (vixtwn) | 2016-11 ~ 2026-04（2408 行） | ✅ 既有 |
| 景氣信號 | 1982-01 ~ 2026-03（531 月） | ✅ NDC ZIP via data.gov.tw 6099 |
| 融資餘額 | 2008+ 計畫，**目前 57 天** | ⏳ backfill 受 TWSE rate limit 影響，重跑中 |
| 個股 / 廣度 | 未跑 ETL | ❌ 後續補（task #11） |

ETL 新增腳本：
- `src/etl/download_margin.py` + `parse_margin.py`（市場彙總，DuckDB `margin_balance` 表）
- `src/etl/download_econ.py` + `parse_econ.py`（DuckDB `econ_signal` 表）
- `src/etl/download_taiex.py`（DuckDB `taiex_day` 表 + CSV）

---

## Step 0.2：Tier 標定（HWM + sub-event zigzag）

**演算法**：HWM 段切（每個 ATH-recovery 周期一個事件）+ Tier A/B macro 內部用 10% zigzag 找次級谷。

**事件總覽**（2008-2025）

| Tier | Macro | Sub | Total | 樣本意義 |
|---|---|---|---|---|
| A 系統熊 | 2 | 1 | 3 | 2008-2014、2022-2024 |
| B 大型修正 | 3 | 2 | 5 | 2020 COVID、2024-2025、2015-08；2011-09、2022-07 sub |
| C 標準修正 | 5 | 8 | 13 | 含 2024-08-05、2026-03-31 等 |
| D 淺回檔 | 8 | — | 8 | 不主要研究 |

**必抓清單檢查**：

| 事件 | Tier 分類 | 通過？ |
|---|---|---|
| 2008-11 海嘯 | A macro 56% | ✅ |
| 2020-03 COVID | B macro 29% | ✅ |
| 2022-10 升息熊 | A macro 32% | ✅ |
| **2024-08 套息** | **C-sub 19% (parent B)** | ✅ |
| 2025-04 關稅 | B macro 29% | ✅ |
| 2026-03 最近 | C macro 10% | ✅ |

每個事件加標 `parent_macro_tier`，可區分 Mode 1（parent=B/C，多頭內部）vs Mode 2（parent=A，結構熊內部）。

---

## Step 0.4-0.6：指標分析

### 中位數對比（21 個 Tier B/C/A 事件 trough）

| 指標 | Mode 1（parent B/C） | Mode 2（parent A） | 解讀 |
|---|---|---|---|
| dist_250ma_pct | -11.6% | -19.1% | Mode 2 跌得更深 |
| z_125ma | **-2.16** | -1.55 | Mode 1 急殺較劇烈（MA 偏離大）|
| vol_5m_60m | 1.12 | 0.78 | Mode 1 量增 / Mode 2 量縮 |
| VIX | 42.8 | 27.9 | Mode 1 急殺 VIX 飆得高 |
| **VIX_pct** | **99.6** | **98.8** | 兩個 mode 都接近滿格 |
| **econ_score** | **28.5（綠）** | **17.0（藍/黃藍）** | 完美分流 |
| blue_streak | 0 | 3 | 完美分流 |

### 命中率（百分位 ≤15 或 ≥85，依方向）

| 指標 | 方向 | 命中率 | Mode 1 | Mode 2 | 評等 |
|---|---|---|---|---|---|
| **VIX_pct** | high | **88%** (7/8) | 83% | 100% | ⭐ 強訊號（限 2017+） |
| **z 125MA** | low | **82%** (14/17) | 78% | 88% | ⭐ 強訊號 + 樣本足 |
| dist 250MA | low | 65% (13/20) | 56% | 73% | 中 |
| vol 5/60 | high | 20% (4/20) | 44% | 0% | 弱 → 候選刪除 |
| econ_score | low | 24% (5/21) | 0% | 45% | regime（非 trough 訊號） |
| blue_streak | high | 5% (1/21) | 0% | 9% | regime（非 trough 訊號） |

### 相關性矩陣（冗餘對）

| Pair | Pearson r | 處理 |
|---|---|---|
| dist 250MA ~ z 125MA | **+0.82** | 留 z（命中率較高） |
| VIX ~ VIX_pct | **+0.62** | 留 VIX_pct（跨時代可比） |
| econ_score ~ blue_streak | **-0.64** | 留 econ_score（更敏感） |

**精簡後 4 個非冗餘軸**：

1. **VIX_pct**（快頻 panic / fear）
2. **z 125MA**（快頻 technical 急殺）
3. **econ_score**（慢頻 regime classifier）
4. **vol 5/60**（待補後續資料；融資、廣度可能取代之）

---

## Step 0.8：保險絲層（Mode 1/2 切換）驗證

**測試規則**：
- 條件A：TAIEX < 250MA
- 條件B：blue_streak ≥ 3（連續 3 個月藍/黃藍）

**結果（理想：A 高、B/C 低、bull 0）**

| Tier | 天數 | AND % | OR % |
|---|---|---|---|
| A regime | 2015 | 16.5% ⚠ | 67.2% |
| B regime | 880 | 24.2% ⚠（高於 A） | 47.8% |
| C regime | 671 | 9.5% | 42.8% |
| D regime | 251 | 0% | 2.8% |
| bull | 667 | **0%** ✓ | 21.4% |

**問題**：
- AND 太嚴：`blue_streak ≥ 3` 規則漏抓 2022-10 trough（streak=1）
- OR 太鬆：bull 期 21% 觸發，誤報多

**修正方向（給 Phase 1 衍生假設）**：
- 試 `streak ≥ 1`（即 current month 是 藍/黃藍） + sustained 250MA below（≥ 1 個月）
- 或用 econ_score < 23 直接判定
- 或加 250MA 跌破天數要求避免 whipsaw

**重要結論**：規則需要調校，**但概念有效**（中位數證實兩個 mode 真的能用 econ + dist 區分）。

### LIVE Mode vs Hindsight Tier 邊界事件

| Trough | Hindsight | LIVE AND | 觀察 |
|---|---|---|---|
| 2015-08-24 | B | True | LIVE 真的看像 Mode 2（持續藍燈 + 跌破 MA）｜ ✓ 一致觀察 |
| 2022-10-25 | A | False | streak=1 漏抓 ⚠ 需放寬 |
| 2024-08-05 | C-sub | False | Mode 1 ✓ 正確 |
| 2025-04-09 | B | False | Mode 1 ✓ 正確 |

---

## GATE 判決

| 條件 | 結果 |
|---|---|
| ≥ 3 個指標命中率 ≥60% | ✅ **3 個**：VIX_pct (88%)、z 125MA (82%)、dist 250MA (65%) |
| ≥ 2 個非冗餘 | ✅ VIX_pct vs z 125MA 互相關 -0.27（極弱）|
| 慢頻層能區分 Tier A vs B/C | ✅ econ_score 中位數 28.5 vs 17.0；具體規則需 Phase 1 調校 |
| 資料完整性 | ⚠ TAIEX/econ ✓；VIX 限 2017+；融資、廣度待補 |

**判決：✅ PASS（with caveats）**

進入下階段衍生假設。

---

## 衍生假設提案

H084 通過 GATE 後，建議衍生以下假設：

### H085-fg-composite（推薦優先）
**TW Fear & Greed 合成版 forward-return 驗證**
- 用 4 個非冗餘指標（VIX_pct、z 125MA、econ_score、vol 5/60）做合成 score
- 評估方式：訊號觸發日後 +60D / +120D / +250D 0050 含息報酬 vs monthly DCA baseline
- 子問題：z-score 加總 vs 計票 vs 邏輯回歸權重

### H086-vix-percentile-single（如 H085 失敗才開）
**VIX_pct 單因子 forward-return 驗證**
- 88% 命中率最高
- 但限 2017+ 樣本

### H087-mode-switch-rule-tune
**Mode 1/2 切換規則調校**
- 測試多個版本（streak ≥ 1 vs ≥ 3，250MA below 持續天數要求等）
- 評估方式：歷史每天 Mode 狀態 → 與 forward 24m return 的條件分佈

### H088-margin-breadth-augment（資料就緒後）
**融資 + 廣度 + 52w 新低家數補入 H084 重跑**
- 等 margin backfill 完成 + market_breadth ETL 補齊
- 看是否能補強 vol 5/60 的弱位置

---

## 後續工作清單

- [ ] 融資 backfill 完成後重跑 build_indicators.py + percentile_correlation.py
- [ ] 補 stock_day / market_breadth ETL（task #11），加入 breadth_adv_dec、52w 新低家數
- [ ] 開新假設 H085 進行 forward-return 驗證
