# Distribution Research Results: TW Fear & Greed 合成版 forward-return 驗證

## Date
2026-05-11

## Conditions Tested

### 資料窗
- 期間：**2017-08-31 ~ 2026-04-30**（限制於 4 指標皆齊全的日子，VIX_pct 需 1 年 rolling）
- 總交易日：**N=2094**
- 標的：**0050.TW**（yfinance, `auto_adjust=True` → 含息調整收盤）

### 4 個非冗餘指標（H084 通過）
| 指標 | fear 方向 | 來源欄位 |
|---|---|---|
| VIX_pct | high | `vix_pct`（1 年滾動百分位） |
| z 125MA | low | `taiex_dist_125ma_z` |
| margin_drop_60d | low | `margin_drop_60d_pct` |
| econ_score | low | `econ_score`（景氣對策信號 9–45）|

### 三種合成法
| 合成法 | 公式 | 範圍 |
|---|---|---|
| `comp_pct` | 4 指標各自轉 fear-direction 全樣本百分位 → 平均 | 0–100 |
| `comp_z` | 4 指標 `sign·(x−median)/IQR` → 加總 | 連續值 |
| `comp_vote` | 4 指標各自 fear-direction 達 ≥85 百分位 → 1 票 | 0–4 |

注：Phase 1 用全樣本 percentile（含 look-ahead），用於分佈特性描述；Phase 2 改 walk-forward。

### baseline
- **all-day baseline**：每天均勻買入 0050（N=1979 有 +120d 資料）
- **monthly DCA baseline**：每月最後一個交易日買入（N=98）
- **single-factor baseline**：僅看 VIX_pct top 10%/5%

---

## Sample

- 觸發日（comp_pct top 10%，threshold=75.7）：**N=210**，**14 個 cluster**
- 觸發日（comp_pct top 5%，threshold=81.6）：**N=105**，**11 個 cluster**
- 觸發日（comp_z top 10%）：**N=210**，**7 個 cluster**
- 觸發日（comp_vote ≥2）：**N=255**，**16 個 cluster**

定義：相鄰觸發日 gap > 5 個曆日視為新 cluster。

### Cluster 分佈（覆蓋的主要 fear 事件）

由時間分佈可辨識：
1. **2018 Q4** 中美貿易戰
2. **2020 Q1** COVID 崩盤
3. **2022 Q2–Q4** 升息熊市
4. **2025 Q2** 川普關稅事件

每個 cluster 含 ~10–50 個觸發日，**沒有單一事件 < 5 日**。通過 invalidation #2。

---

## Key Findings

### 1️⃣ 合成 score 之間高度相關（comp_pct vs comp_z）

| Pair | Correlation |
|---|---|
| comp_pct ↔ comp_z | **0.943** |
| comp_pct ↔ comp_vote | 0.675 |
| comp_z ↔ comp_vote | 0.775 |

→ percentile-average 與 z-sum 是同類訊號，**vote count 略有差異**（離散化效應）。

### 2️⃣ Forward-return 表現（核心數字）

| Score | Quantile | N | +60d med | +120d med | +250d med | +120d vs DCA | +250d vs DCA | Win@250d |
|---|---|---|---:|---:|---:|---:|---:|---:|
| **DCA baseline** | — | 98 | +3.54% | +7.49% | +22.55% | — | — | — |
| **all-day baseline** | — | 1979 | +3.98% | +7.02% | +21.95% | — | — | — |
| `comp_pct` | top 10% | 210 | +7.66% | **+14.40%** | **+31.20%** | **+6.91%** | **+8.65%** | 73.3% |
| `comp_pct` | top 5% | 105 | +9.73% | +13.61% | **+33.10%** | +6.12% | **+10.55%** | **80.95%** |
| `comp_z` | top 10% | 210 | +12.49% | **+18.37%** | **+31.84%** | **+10.88%** | **+9.29%** | 71.7% |
| `comp_z` | top 5% | 105 | +11.67% | +13.99% | +30.19% | +6.50% | +7.64% | 78.6% |
| `comp_vote` | ≥2 | 255 | +6.76% | +10.23% | +25.70% | +2.73% | +3.15% | 59.9% |
| **VIX_pct alone** | top 10% | 191 | +4.24% | +9.45% | +18.81% | +1.96% | **−3.74%** | — |
| **VIX_pct alone** | top 5% | 107 | +3.97% | +12.65% | +19.34% | +5.16% | −3.21% | — |

### 3️⃣ 合成顯著優於單因子 VIX_pct

- comp_pct top 10% **+250d diff = +8.65%** vs VIX_pct top 10% **+250d diff = −3.74%**
- **差距 +12.4%** > invalidation #4 門檻（1%）✅ 大幅通過
- VIX_pct 單獨在 +250d **甚至跑輸 DCA**（−3.74%），說明高 VIX 後常有「先漲後跌」二次回測，需與其他慢指標（econ_score, margin）一起確認

### 4️⃣ comp_vote 表現遠遜於 comp_pct/comp_z

vote count 要求嚴格（≥2 票才入選），但 4 指標性質差異大（VIX 是 fast / econ 是 very slow），同時達 85 百分位的事件非常少（4 票 N=1，3 票 N=85）。連續訊號（pct/z）能捕捉「2 個極端 + 2 個半極端」的灰色地帶，反而表現更穩。

### 5️⃣ 分 macro_tier 看（comp_pct top 10%）

| macro_tier | N | +120d med | +250d med |
|---|---:|---:|---:|
| **A**（Mode 2 deep correction） | 69 | +12.72% | +22.65% |
| **B**（Mode 1 邊界）| 68 | **+31.91%** | **+74.02%** |
| **C**（淺修正） | 73 | +7.66% | +25.69% |

→ **tier=B 觸發日 +250d 中位數 +74%**，是最強的 buy zone。tier=B 對應 H084 framework 中的「Mode 1 邊界」（cond_A 或 cond_B 成立但非全部）。這是非常驚人的訊號，可能是 H087 mode-切換規則的最佳目標 segment。

### 6️⃣ comp_pct 與 comp_z 觸發點時間分佈

從 `composite_timeseries.png` 看，top 10%/5% 觸發點主要集中在：
- 2018-10 ~ 2018-12（貿易戰）
- 2020-03 ~ 2020-05（COVID）
- 2022-05 ~ 2022-11（升息熊）
- 2025-04 ~ 2025-05（關稅）

中間 2019/2021/2023/2024 多頭階段幾乎沒有觸發 → score 篩出來的就是「市場恐慌期」。

---

## Vs. Expected

| Proposal 預期 | 觀察 | 評估 |
|---|---|---|
| 合成 score 右偏（多數日子在低分區） | comp_pct mean ~50, max 90.5，分佈合理 | ✅ 部分符合（max 未達 100 因 4 指標難同時齊聚） |
| 高分區事件少而集中（2008、2020、2022、2025） | 14 個 cluster, 集中於 2018/2020/2022/2025 | ✅ 完全符合 |
| 觸發日 100–300 天 | top 10%=210, top 5%=105 | ✅ 符合 |
| forward return 高分日右尾較厚 | top 10% +120d med 約為 baseline 2x | ✅ 強烈符合 |
| hypothesis: +120d/+250d med ≥ baseline + 3% | comp_pct: +6.9% / +8.7%; comp_z: +10.9% / +9.3% | ✅ **大幅通過** |

---

## Gate Decision

### GATE 條件逐項檢查

| 條件 | 要求 | 結果 | 通過 |
|---|---|---|:---:|
| 1. top 10% +120d/+250d med ≥ baseline + 3% | +3% 絕對值 | comp_pct: +6.9% / +8.7%; comp_z: +10.9% / +9.3% | ✅ |
| 2. 樣本 ≥ 30 且 cluster ≥ 5 | N≥30, cluster≥5 | N=210, cluster=14 | ✅ |
| 3. 至少一種合成法通過 | 1 種以上 | comp_pct 與 comp_z 都通過 | ✅ |
| 4. 合成優於 VIX_pct 單因子 ≥ 1% | diff ≥ 1% | +120d 差 +4.95%；+250d 差 +12.4% | ✅ |
| 5. 樣本不集中於 1–2 事件 | 每 cluster ≥ 5 | 14 cluster 散佈 4 個事件 | ✅ |

### Invalidation 條件未觸發

- ❌ #1 (高分日 forward 不顯著高於 baseline) — 反向，顯著高出
- ❌ #2 (集中於 1–2 個事件) — 4 個事件、14 cluster
- ❌ #3 (OOS 不穩定) — Phase 1 用全樣本，留 Phase 2 walk-forward 驗證
- ❌ #4 (合成不勝過單因子) — 合成大幅勝出

### 決定

- [x] **進入 Phase 2** — GATE PASS，所有條件大幅通過
- [ ] Archive
- [ ] 修改假設

---

## Derived Hypotheses

衍生想法，記錄但不主動修改其他文件。**範圍界定**：純參數 sweep、OOS 驗證、tier 子分群描述屬於 H085 Phase 2；以下是「改變訊號公式或策略結構」、超出 H085 範圍的新假設。

- **H088（候選）**：「**tier=B 單一 segment 策略**」— Phase 1 觀察 tier=B × comp_pct top 10% +250d med +74%。H088 不是「分組看表現」（那是 Phase 2 描述性分析），而是「**只在 tier=B 進場、其他 tier 完全不進場 OR 用更小 tranche**」的可下單策略框架。需要驗證 tier=B 訊號的可行性與重複性，含 OOS。
- **H089（候選）**：「Composite slope as trigger」— 改變訊號公式：不看 `comp_pct` 絕對值，看 60 日內的上升斜率（捕捉 fear 加速期，避免高分區鈍化）。是新 trigger formula，不是 H085 參數變體。
- **H091（候選）**：「Mixed-frequency vote」— 改寫 `comp_vote` 公式為「至少 2 個 fast 指標（VIX/125MA z）+ 1 個 slow 指標（margin/econ）達 ≥85 percentile」。也是新訊號設計。

---

## Phase 2 建議

GATE 通過，建議 Phase 2 重點：

1. **In-sample/OOS split**：2017-08 ~ 2022-12 為 in-sample 找 optimal threshold；2023-01 ~ 2026-04 為 OOS 驗證
2. **Walk-forward percentile**：取代全樣本 percentile，每天用過去 5 年的 expanding 百分位
3. **進場規則**：
   - 主測 `comp_pct` 與 `comp_z` 兩種
   - 閾值 top 10% / top 5%
   - 連續觸發 ≥ 1 天 vs ≥ 3 天（避免雜訊）
4. **出場規則**：固定持有 60/120/250 個交易日 vs 條件出場（comp_pct < 50 或 +250d 到期）
5. **Mode-conditional 子假設**：分別比較 macro_tier A / B / C 下的策略表現（H088 候選的核心）
6. **與 DCA 對戰**：累計報酬 / Sharpe / MaxDD vs monthly DCA over 同期間

---

## 注意事項與限制

1. **資料窗較短**（9 年）：只包含 4 個主要 fear 事件，OOS sample 可能不足
2. **全樣本 percentile 含 look-ahead**：Phase 1 用於描述，Phase 2 必改 walk-forward
3. **0050 起始於 2009-01**：與指標起點 2017-08 後 alignment 是 inclusive 的，沒有額外 truncation
4. **VIX TWN 始於 2016-11**：是限制 sample window 的瓶頸；如要把分析延伸到 2008（含金融海嘯），需用 US VIX 代理或捨棄 VIX_pct

---

## Output 檔案

- `composite_with_returns.csv` — 完整每日 score + forward returns + macro_tier
- `threshold_summary.csv` — 各閾值的觸發數與 cluster 數
- `trigger_returns.csv` — 每筆觸發日的個別報酬（2871 筆，含三種合成 × 三閾值）
- `trigger_summary.csv` — 各合成法×閾值的彙總統計
- `vix_pct_baseline.csv` — 單因子 VIX_pct baseline 對照
- `composite_timeseries.png` — 0050 + composite score 時序，標 top-decile 觸發
- `forward_return_dist.png` — boxplot 對比 baseline vs triggers vs VIX-only
