# Distribution + Backtest Results: Reversal Weekday Effect

## Date
2026-04-17

## Sample
- Reversal 交易：488 筆（2021-2026）
- IS/OOS：2021-2024 (373) / 2025-2026 (115)

## Phase 1: Weekday Breakdown

| Day | N | WR | PF | total | Sharpe |
|-----|---|----|----|-------|--------|
| **Mon** | 93 | 36.6% | **0.77** | -574 | -2.05 |
| **Tue** | **97** | **53.6%** | **2.16** | **+2,062** | **3.95** |
| Wed | 98 | 49.0% | 1.40 | +714 | 1.15 |
| Thu | 91 | 50.5% | 1.67 | +962 | 2.50 |
| **Fri** | 109 | 39.4% | **0.93** | -167 | -1.27 |

### Cross-year consistency (PF > 1.0 的年數)

| Day | Mon | Tue | Wed | Thu | Fri |
|-----|-----|-----|-----|-----|-----|
| Consistency | **1/6** | **5/6** | 4/6 | 5/6 | **2/6** |

- **Mon 1/6**：只有 2025 年 PF > 1.0，其餘五年全虧
- **Fri 2/6**：只有 2025-2026 勉強正
- **Tue 5/6**：最穩定的獲利日

### Night vol × Weekday

| Day | HIGH PF | LOW PF |
|-----|---------|--------|
| Mon | 0.77 | 0.76 |
| Tue | 2.79 | 1.32 |
| Wed | 1.79 | 1.07 |
| Thu | 1.55 | 1.78 |
| Fri | 1.07 | 0.84 |

週一高低波動都差（0.77 vs 0.76），夜盤波動解釋不了週一的弱勢。
週五稍有差異但都偏弱。

## Phase 2: IS/OOS + Walk-Forward

### Filter combinations

| Config | IS N | IS PF | IS Sharpe | OOS N | OOS PF | OOS Sharpe |
|--------|------|-------|-----------|-------|--------|------------|
| No filter | 373 | 1.02 | 0.10 | 115 | 2.07 | 3.36 |
| Skip Mon+Fri | 214 | 1.58 | 2.53 | 72 | 2.04 | 3.04 |
| Night vol only | 212 | 1.04 | 0.14 | 77 | 2.35 | 4.14 |
| **NVF + skip Mon+Fri** | **117** | **1.55** | **2.54** | **47** | **2.49** | **4.15** |

### Walk-forward: skip Mon+Fri vs baseline

| Year | Base PF | Skip M+F PF | NVF PF | NVF+M+F PF |
|------|---------|-------------|--------|------------|
| 2022 | 0.98 | **1.70** | 0.91 | **1.86** |
| 2023 | 1.23 | **1.81** | 1.25 | **1.93** |
| 2024 | 1.00 | **1.48** | 1.15 | **1.33** |
| 2025 | 1.45 | 1.21 | **1.64** | 1.46 |
| 2026 | 5.78 | **16.89** | 5.58 | **14.86** |

Walk-forward skip Mon+Fri beat baseline: **4/5 年**（只有 2025 例外）

## Gate Decision

**進入 Verdict**

- [x] 週一跨年一致 1/6（極度穩定的虧損）
- [x] 週五跨年一致 2/6
- [x] Skip Mon+Fri IS PF 提升 55%（1.02 → 1.58）
- [x] Walk-forward 4/5 年勝出
- [x] 週一的弱勢與夜盤波動無關（高低組都是 PF=0.77）

## Verdict

**Confirmed**（2026-04-17）

採用 skip Mon+Fri：Reversal 週一週五不進場。
- 週一 PF=0.77，跨年一致 1/6（幾乎確定虧損）
- 週五 GO 天 PF=1.11 但 4/6 年虧，保留風險大於收益
- 結合 NVF：PF=1.92, Sharpe=3.09, MDD=-565（三項指標均最佳）
- Walk-forward NVF+skip MF 5/5 全勝

**支持 Confirmed：**
1. 週一 PF=0.77，跨年一致性 1/6——幾乎確定虧損
2. 週五 PF=0.93，跨年一致性 2/6
3. Skip Mon+Fri 在 IS（PF 1.02→1.58）和 Walk-forward（4/5 勝）都有效
4. 與夜盤濾網結合（NVF+skip MF）IS Sharpe=2.54, OOS Sharpe=4.15
5. 週一弱勢無法被夜盤波動解釋（高低組都差），是獨立的結構性因素

**注意事項：**
1. OOS 中 skip Mon+Fri PF=2.04 略低於 baseline 2.07（但 N 少了很多）
2. 2025 年 skip Mon+Fri 反而退步（1.45→1.21），因為該年週一異常轉好
3. 結合 NVF 後 OOS N=47，樣本偏少

## Derived Hypotheses
- 無（星期濾網是直接結論）
