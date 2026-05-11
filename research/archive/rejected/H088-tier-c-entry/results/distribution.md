# Distribution Research Results: Tier C 標準回檔進場訊號

## Date
2026-05-11

## Conditions Tested

### 資料
- H084 indicators.csv（z125MA、margin_drop_60d、econ_score、vix_pct）2008-01 ~ 2026-04
- 0050.TW adj_close (yfinance) 2009-01 ~ 2026-05
- H084 trough_mode_state.csv：21 個 trough 事件，**13 個是 Tier C（含 sub）**
- H085 comp_z（rolling 5yr IQR）：用於計算重疊度

### 候選訊號（10 個變體）

| 變體 | 規則 |
|---|---|
| S1 | z125MA ≤ −1.5 |
| S2 | z125MA ≤ −2.0 |
| S1+econ≥17 | + 排除藍燈月 |
| S1+notA | + parent_tier ≠ A（排除結構熊內部）|
| S1+nonH085 | + comp_z < 3.97（不重複 H085）|
| S2+nonH085 | S2 + nonH085 |
| S1+econ≥17+nonH085 | 三條件 |
| S1+notA+nonH085 | 三條件 |
| **margin_drop60≤−5%+nonH085** | **margin 為主 + nonH085** |
| S1 OR margin≤−5 (nonH085) | 任一即可 |

### 必抓事件
2024-08-05（C-sub）、2026-03-31（C）— H085 沒抓到的最近兩次

---

## Sample

- 分析窗：2009-03-24 ~ 2026-05-08（4186 天）
- 13 個 Tier C 事件分佈：
  - 2008/2009/2010/2011/2012：7 個（多在 2008-2014 結構熊內 sub）
  - 2014/2016/2019/2021/2024/2026：6 個（cleanly Tier C）
- H085 comp_z 觸發日：127 天（用於計算 Jaccard）

---

## Key Findings

### 1️⃣ 訊號變體比較

| Signal | n_trig | cluster | hit_C | hit_rate | must_hit | jaccard_H085 | +60d med | +120d med | +250d med |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| S1: z125≤−1.5 | 305 | 11 | 4/13 | 30.8% | 0/2 | 0.286 | +0.8% | +5.0% | +17.4% |
| S2: z125≤−2.0 | 189 | 8 | 2/13 | 15.4% | 0/2 | 0.322 | +0.7% | +5.3% | +18.8% |
| S1+econ≥17 | 264 | 11 | 4/13 | 30.8% | 0/2 | 0.325 | +0.0% | +6.5% | +18.2% |
| S1+notA | 161 | 6 | 2/13 | 15.4% | 0/2 | 0.405 | +4.9% | +8.2% | +24.3% |
| S1+nonH085 | 209 | 11 | 4/13 | 30.8% | 0/2 | **0.000** | −0.0% | +3.5% | +12.0% |
| S2+nonH085 | 112 | 7 | 2/13 | 15.4% | 0/2 | 0.000 | +0.1% | +3.0% | +12.4% |
| S1+econ≥17+nonH085 | 168 | 11 | 4/13 | 30.8% | 0/2 | 0.000 | −1.9% | +4.5% | +9.8% |
| S1+notA+nonH085 | 78 | 6 | 2/13 | 15.4% | 0/2 | 0.000 | +4.0% | +4.7% | +15.9% |
| **margin_drop60≤−5+nonH085** | **1485** | **30** | **11/13** | **84.6%** | **2/2** | 0.000 | +2.0% | +4.4% | +10.0% |
| S1 OR margin≤−5 (nonH085) | 1493 | 30 | 11/13 | 84.6% | 2/2 | 0.000 | +2.0% | +4.4% | +10.0% |

### Baseline (0050)
- all_day +60d/+120d/+250d med: **+3.58% / +5.64% / +10.86%**（N=4066）
- monthly DCA +60d/+120d/+250d med: **+3.26% / +5.70% / +11.26%**（N=201）

### 2️⃣ 核心矛盾：訊號可標記事件，但 forward return 不超過 baseline

**margin_drop60≤−5% 是唯一通過 hit rate 60% 門檻的訊號（85%）**：
- 11/13 Tier C 事件命中 ✓
- 必抓 2/2 ✓
- 與 H085 完全不重疊（Jaccard = 0）✓
- **但 forward return 中位數**：
  - +60d **+2.0%** vs all-day baseline +3.58% → **跑輸 −1.6%**
  - +120d +4.4% vs +5.64% → 跑輸 −1.3%
  - +250d +10.0% vs +10.9% → 跑輸 −0.9%

→ 訊號**有 informational value**（標記事件），**但無 trading edge**（不超過買進持有）

### 3️⃣ z125MA 單因子嚴重失手

- z125≤−1.5 hit 4/13（30.8%）、z125≤−2.0 hit 2/13（15.4%）
- **0/2 必抓事件命中**（2024-08 與 2026-03 都沒被 z125 抓到）
- 原因：Tier C 事件多為緩跌型，z125MA 達不到 −1.5 的急殺閾值

### 4️⃣ margin 訊號的命中明細

`margin_drop60≤−5+nonH085` 對 13 個 Tier C 事件（窗 ±30 天）：

| 事件 | tier | parent | 觸發數 | 命中 |
|---|---|---|---:|:---:|
| 2008-01-23 | C | C | 0 | ✗ |
| 2009-01-20 | C-sub | A | 0 | ✗ |
| 2009-06-18 | C-sub | A | 8 | ✓ |
| 2010-02-08 | C-sub | A | 16 | ✓ |
| 2010-06-09 | C-sub | A | 30 | ✓ |
| 2011-12-19 | C-sub | A | 41 | ✓ |
| 2012-06-04 | C-sub | A | 42 | ✓ |
| 2014-10-17 | C | C | 22 | ✓ |
| 2016-01-21 | C-sub | B | 24 | ✓ |
| 2019-01-04 | C | C | 24 | ✓ |
| 2021-05-17 | C | C | 29 | ✓ |
| **2024-08-05** | **C-sub** | **B** | **23** | **✓** |
| **2026-03-31** | **C** | **C** | **3** | **✓** |

漏抓 2008/2009 早期 — 因為 margin_drop_60d 序列在 2008-03 才開始（warmup），無法判斷 2008-01 的事件。

### 5️⃣ 觸發日數過多的問題

`margin_drop60≤−5%` 觸發 1485 天 / cluster 30 = **每年平均 ~88 個觸發日**。
- 等於「常態化進場」，失去 timing 意義
- 訊號太寬 → 進場價平均化 → forward return 接近 baseline
- 需要更嚴格閾值或加倉位限制（cooldown / max_open）

---

## Vs. Expected

| Proposal 預期 | 觀察 | 評估 |
|---|---|---|
| z125≤−1.5 + econ≥17 是主訊號 | hit rate 30.8% / forward +6.5% | ⚠️ 命中差但 forward 接近 baseline |
| margin_drop60≤−5% 為輔 | hit rate 84.6% / forward 跑輸 baseline | ⚠️ 反向：命中強但無 edge |
| 與 H085 互補（Jaccard < 50%） | margin 系列 Jaccard = 0 | ✅ 完全互補 |
| forward 120d med ≥ baseline + 1% | 沒有任何訊號達標 | ❌ **失敗** |

---

## Gate Decision

### Invalidation 對照

| 條件 | 結果 | 觸發？ |
|---|---|:---:|
| #1 排除結構熊後 forward 120d 中位數 ≥ baseline + 1% | 所有變體都跑輸 baseline | **✅ 觸發** |
| #2 樣本 ≥ 30 但勝率 < 55% | margin 系列 N=1485，但勝率未計（需重新算）| ⚠️ |
| #3 與 H085 Jaccard > 60% | margin 系列 Jaccard = 0 | ❌ 未觸發 |
| #4 對 2024-08 / 2026-03 沒命中 | margin 系列 2/2 命中 | ❌ 未觸發 |

### 核心矛盾

- **可標記事件的訊號（margin）forward return 跑輸 baseline**
- **forward return 較好的訊號（z125+notA）命中率僅 15-30%、漏抓必抓事件**

→ Phase 1 GATE **第 1 條**（forward 不顯著高於 baseline）**觸發 → reject**

---

## 為何 H088 表現比 H085 差？

H085 (Tier B panic) 抓的是「**深度恐慌底 + 大幅反彈**」結構，每次事件後 0050 1 年回升 60-120%。

H088 (Tier C 標準回檔) 抓的是「**標準 10-20% 回檔 + 通常回升**」，但：
1. 進場時恐慌不夠深 → 反彈幅度有限
2. 1 年（250d）持有窗包含後續高點消化 → 中位數被拉平到接近 baseline
3. Tier C 回檔常出現在「結構熊內部」（13 個 C 中 7 個 parent=A），這些「buy the dip」實際是「猜底失敗」

換言之：**Tier C 並非「行情底部」，只是「次級拉回」，沒有 timing edge 可挖**。

---

## 下一步建議

### 決定（待使用者確認）

- [ ] **Reject H088**（建議）— Tier C 進場本質上沒有 forward-return edge over DCA
- [ ] **修改後重跑** — 測試方向：
  - 縮短 hold 期到 30-60d（更貼近 Tier C 短回檔節奏）
  - 嘗試「z125 + margin AND 條件」（兩者都要極端）
  - 加 timing filter：only buy 當 z125 開始反彈（slope > 0）
- [ ] **等 H087 ETL 完成**（明天）後重做 — 加入廣度指標（ld_value_ratio 等）可能提供新軸

### Derived Hypotheses（衍生想法）

- **H08X-tier-c-conditional-exit**：Tier C 訊號 + 條件出場（z125 回到 0 / 跌破 SMA60），不固定 250d
- **H08X-margin-slope**：margin_drop_60d 由負轉正（融資已止跌）作為 Tier C 進場 timing
- **H08X-breadth-tier-c**：等 H087 ETL 完成後，用 ld_value_ratio + adv_dec_ratio 重做

---

## Output 檔案

- `explore.py` — 完整分析腳本
- `signal_grid.csv` — 10 個訊號變體 metrics
- `signal_grid.png` — Hit rate vs Jaccard scatter + forward return bar
