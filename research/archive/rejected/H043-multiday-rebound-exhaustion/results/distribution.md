# Distribution Research Results: Multi-Day Rebound Exhaustion

## Date
2026-03-27

## Conditions Tested
- 資料期間：2021-01-04 ~ 2026-03-26（1264 個交易日）
- 情境分類：開盤價 vs BC zone（VWAP1, VWAP2）+ 5m 120MA 方向
  - **rebound_exhaust_short**：開盤 > BC zone 上緣，但 MA 向下（反彈竭盡做空）
  - **pullback_exhaust_long**：開盤 < BC zone 下緣，但 MA 向上（回調竭盡做多）
  - **aligned_long/short**：BC zone 和 MA 方向一致（現行 Reversal 場景）
- BB Setup：沿用 Reversal 的 BB latch（close >= BB_Upper 或 <= BB_Lower + vol > 1.2 × VolMA20）+ MA5 trigger
- MFE/MAE 從 trigger 點到收盤計算，以 EmaHL 標準化

## Sample
- H043 目標情境：263 天（20.8%）
  - rebound_exhaust_short：134 天
  - pullback_exhaust_long：129 天
- BB setup 觸發：214 筆（rebound_short 112 + pullback_long 102）
- 對照組（aligned）：511 筆
- 時間範圍：2021-01-04 ~ 2026-03-26
- 市場：TX 台指期日盤

## Key Findings

### Task 1: 情境出現頻率

| 情境 | 天數 | 比例 |
|------|------|------|
| rebound_exhaust_short | 134 | 10.6% |
| pullback_exhaust_long | 129 | 10.2% |
| aligned_long | 436 | 34.5% |
| aligned_short | 263 | 20.8% |
| inside | 302 | 23.9% |

逐年穩定：rebound_short 每年 10-11%，pullback_long 7-13%。

### Task 2: BB Setup 觸發率

| 情境 | Setup/Days | 觸發率 |
|------|-----------|--------|
| rebound_exhaust_short | 112/134 | **83.6%** |
| pullback_exhaust_long | 102/129 | **79.1%** |
| aligned_long | 327/436 | 75.0% |
| aligned_short | 184/263 | 70.0% |

H043 情境的 BB 觸發率比 aligned 更高（80% vs 72%），這符合直覺：反彈/回調到成本區上方，BB 被推到極端的機率更高。

### Task 3: MFE/MAE 比較（核心）

| 情境 | N | MFE/EmaHL | MAE/EmaHL | MFE>MAE% | Net |
|------|---|-----------|-----------|----------|-----|
| rebound_exhaust_short | 112 | 0.300 | 0.328 | 49.1% | **-0.027** |
| pullback_exhaust_long | 102 | 0.298 | 0.338 | 48.0% | **-0.040** |
| aligned_long | 327 | 0.325 | 0.334 | 47.1% | -0.009 |
| aligned_short | 184 | 0.365 | 0.285 | **53.8%** | **+0.081** |

**H043 目標情境的 MFE/MAE 沒有 edge**：
- MFE > MAE 比例僅 48-49%（低於 50%）
- Net（MFE - MAE）為負值（-0.027 ~ -0.040）
- 不優於 aligned 場景（尤其 aligned_short 有明顯正 edge）

### Task 4: 逐年穩定性

**rebound_exhaust_short（N=112）：**

| Year | N | MFE | MAE | MFE>MAE |
|------|---|-----|-----|---------|
| 2021 | 23 | 0.346 | 0.487 | 48% |
| 2022 | 22 | 0.374 | 0.369 | 50% |
| 2023 | 23 | 0.443 | 0.365 | 43% |
| 2024 | 19 | 0.302 | 0.307 | 58% |
| 2025 | 23 | 0.235 | 0.298 | 48% |

**pullback_exhaust_long（N=102）：**

| Year | N | MFE | MAE | MFE>MAE |
|------|---|-----|-----|---------|
| 2021 | 20 | 0.256 | 0.374 | 45% |
| 2022 | 27 | 0.355 | 0.357 | 52% |
| 2023 | 18 | 0.269 | 0.287 | 44% |
| 2024 | 21 | 0.417 | 0.277 | 57% |
| 2025 | 11 | 0.126 | 0.336 | **36%** |

pullback_exhaust_long 在 2025 年特別差（MFE>MAE 僅 36%，N=11）。整體而言逐年不穩定，沒有持續性的正 edge。

### Task 5: VWAP vs Close 定義

| 定義 | 天數 | 重疊 |
|------|------|------|
| VWAP（BC zone） | 263 | 256 |
| 前日 Close | 642 | 256 |

Close 定義產生 2.4 倍的候選日（642 vs 263），但 VWAP 已包含 2 天歷史且更具「機構成本」意義。97% 的 VWAP 候選都被 Close 覆蓋。建議沿用 VWAP。

## Vs. Expected

| 項目 | 預期 | 實際 | 評估 |
|------|------|------|------|
| BB 極端 + MA 反向的頻率 | 有一定頻率 | 20.8%（263 天），穩定 | **符合** |
| MFE 較一般 Reversal 大 | MFE 應更大 | MFE 0.300 vs aligned 0.332，反而更小 | **不符合** |
| 勝率 > 40% | 需 > 40% | 48-49%（但 PF 估計 < 1.0） | **邊緣** |
| MAE < MFE | 反彈竭盡後應有效反轉 | MAE > MFE（-0.027 ~ -0.040） | **不符合** |

## Gate Decision
[ ] 進入 Phase 2
[ ] Archive（原因：）
[ ] 修改假設（修改內容：）

### GATE 問題

1. **樣本數是否足夠？**
   - 214 筆 BB setup，各子類 100+ 筆，逐年 11-27 筆。樣本尚可。

2. **分佈方向是否符合預期？**
   - **不符合**。H043 情境的 MFE 不優於 aligned，MAE 反而略大。MFE > MAE 比例低於 50%。
   - 反彈到 BC zone 之上但 MA 仍向下 → 做空，理論上順趨勢。但數據顯示這些反彈往往不是「竭盡」，而是「趨勢正在轉向」（MA 還沒跟上）。

3. **是否有明顯的 data snooping 疑慮？**
   - 無。分析使用固定的 Reversal 參數，無參數搜尋。

4. **無效條件檢查**：
   - 勝率 48-49%（邊緣，但 PF 估計 < 1.0 因 MAE > MFE）
   - MAE > MFE → invalidation condition 成立

**等待使用者決定。**

## Derived Hypotheses
- 無。aligned_short（BC zone 下方 + MA 向下）是唯一有正 edge 的情境（MFE>MAE 53.8%，Net +0.081），但這已是現行 Reversal 策略的核心場景。
