# Distribution Research Results: Reversal CCD Bypass Conditions Audit

## Date
2026-03-26

## Conditions Tested
精確重建 Reversal 策略的 setup 邏輯，對每個觸發進場的事件記錄 4 種條件的狀態：
- **A: CCD correct** — CCD_5m > 0 (long) / < 0 (short)
- **B: Exhaustion** — price moved >= 0.5 × EmaHL from day extreme
- **C: Intraday VWAP** — close > intraday VWAP (long, 09:30+)
- **D: 2nd BB touch** — bb_count >= 2

成功定義：entry 後 60 根 bar 的 MFE > MAE

## Sample
- 觸發進場數：734（long: 433, short: 301）
- 時間範圍：2020-12-31 ~ 2026-03-25（約 5.25 年）
- 市場：TX 台指期日盤

## Key Findings

### 1. CCD 不是最重要的條件 — 反而是最弱的

| 條件 | 頻率 | Prof% (all) | Exclusive N | Exclusive Prof% |
|------|------|-------------|-------------|-----------------|
| CCD correct | 43.1% | 49.7% | 94 | 51.1% |
| Exhaustion | 43.3% | 50.6% | 105 | 51.4% |
| VWAP bypass | 18.8% | 51.4% | 5 | 60.0% (N太小) |
| **2nd BB touch** | **60.1%** | **51.5%** | **119** | **58.8%** |

**CCD correct 的勝率（49.7%）竟然低於 bypass 進場（53.3%）。**

### 2. 2nd BB touch 是最有價值的條件

- Exclusive trigger（只靠 2nd BB 才能進場）：N=119，勝率 **58.8%**
- 方向分拆：long 55.4%, short **64.4%**
- 如果移除 2nd BB touch：損失 119 筆交易（16.2%），且這些交易勝率最高
- 移除後剩餘交易勝率從 51.8% 降到 50.4%

### 3. Exhaustion 增加交易量但不改善品質

- Exclusive trigger：N=105，勝率 51.4%（與全體 51.8% 幾乎相同）
- 移除後損失 105 筆，但這些交易的勝率跟保留的一樣
- 結論：Exhaustion 不是 bad signal，但也沒有 edge，只是增加了 exposure

### 4. VWAP bypass 實際上幾乎不起作用

- Exclusive trigger 只有 **5 筆**（0.7%）
- 絕大多數 VWAP bypass 成立時，其他條件也同時成立
- 可以安全移除，幾乎零影響

### 5. 條件越多重疊，勝率越低

| Combination | N | Prof% |
|-------------|---|-------|
| 2nd BB only | 119 | **58.8%** |
| Exhaust only | 105 | 51.4% |
| CCD only | 94 | 51.1% |
| CCD + 2nd | 75 | 49.3% |
| CCD + Exh + 2nd | 20 | **35.0%** |

多條件同時成立反而勝率降低，這暗示條件之間可能存在衝突（如 CCD correct + exhaustion 同時成立的情境可能是趨勢末段震盪）。

### 6. 年度穩定性：bypass > CCD

| Year | CCD Prof% | Bypass Prof% | Delta |
|------|-----------|-------------|-------|
| 2021 | 49.1% | 50.7% | +1.6% |
| 2022 | 47.8% | 52.4% | +4.6% |
| 2023 | 51.6% | 50.0% | -1.6% |
| 2024 | 46.8% | 56.4% | +9.6% |
| 2025 | 49.1% | 55.7% | +6.6% |

5 年中 4 年 bypass 進場優於 CCD 正確的進場。

## Vs. Expected

**部分符合、部分出乎意料。**

- ✅ 預期「部分 bypass 有正貢獻」→ 2nd BB touch 確實有 edge（58.8%）
- ✅ 預期「部分 bypass ≈ noise」→ Exhaustion 和 VWAP bypass 符合
- ❌ 預期「CCD 應為基準線、最穩定」→ 實際上 CCD 是最弱的條件（49.7%）
- 🔍 意外發現：bypass 進場整體勝率（53.3%）> CCD 正確進場（49.7%）

## Gate Decision

建議進入 Phase 2 做 ablation 回測，具體驗證：
1. 移除 VWAP bypass（幾乎零影響）
2. 移除 Exhaustion（增加 exposure 但無 edge）
3. 甚至考慮：移除 CCD 要求，改為只靠 2nd BB touch

[ ] 進入 Phase 2
[ ] Archive（原因：）
[ ] 修改假設（修改內容：）

## Derived Hypotheses
- **HXXX-2nd-bb-standalone**：2nd BB touch 作為獨立進場條件（不需任何 CCD/exhaustion），是否足夠？
- **HXXX-ccd-inversion**：CCD correct 反而表現最差，是否暗示 CCD 在 reversal 情境下是反向指標？
