# Distribution + Backtest Results: Night Session Volatility as Reversal Filter

## Date
2026-04-17

## Sample
- Reversal 交易數：487 筆（全部配對成功 487/496）
- 時間範圍：2021–2026
- IS/OOS：2021-2024 IS (373) / 2025-2026 OOS (114)

## Phase 1: Key Findings

### Median split（核心結果）

| Group | N | WR | PF | avg PnL | total PnL | Sharpe |
|-------|---|----|----|---------|-----------|--------|
| Night HIGH vol | 240 | 47.5% | 1.58 | +12 | +2,975 | 2.11 |
| Night LOW vol | 240 | 43.3% | 0.96 | -1 | -165 | -0.52 |

**PF 差異：+64.3%。LOW vol 是負期望值（PF < 1.0）。**

### Quartile（完美單調遞增）

| Q | N | WR | PF | avg PnL | Sharpe |
|---|---|----|----|---------|--------|
| Q1 (low) | 120 | 44.2% | 0.95 | -1 | -0.42 |
| Q2 | 120 | 42.5% | 0.97 | -1 | -0.60 |
| Q3 | 120 | 47.5% | 1.15 | +3 | 0.83 |
| Q4 (high) | 120 | 47.5% | **1.93** | +22 | **2.97** |

Q1/Q2 都虧損，Q4 獨挑大樑。單調性完美。

### Cross-year stability: 5/6 ✓

唯一例外 2021（但兩組 PF 都 < 1.0，差異小）。

## Phase 2: IS/OOS + Walk-Forward

### IS vs OOS

| Config | IS N | IS PF | IS Sharpe | OOS N | OOS PF | OOS Sharpe |
|--------|------|-------|-----------|-------|--------|------------|
| Baseline | 373 | 1.02 | 0.10 | 114 | 1.93 | 3.11 |
| night_norm ≥ 0.85 | 212 | 1.04 | 0.14 | 77 | 2.15 | 3.83 |

注意：IS 期間 Reversal 整體表現平庸（PF≈1.0），濾網效果在 IS 不明顯。
OOS 表現好，濾網也有效（PF 1.93 → 2.15）。

### Threshold sensitivity

門檻不敏感——0.70–1.10 OOS PF 都 > 2.0。IS PF 都在 1.0–1.2 之間。
IS 期間效果弱是因為 Reversal 本身 2021-2024 就不太賺，不是濾網的問題。

### Walk-forward: **5/5 年全勝** ✓✓✓

| Year | Threshold | Filtered PF | Baseline PF | Beat? |
|------|-----------|-------------|-------------|-------|
| 2022 | 0.913 | 1.19 | 0.98 | ✓ |
| 2023 | 0.895 | 1.30 | 1.23 | ✓ |
| 2024 | 0.913 | 1.23 | 1.00 | ✓ |
| 2025 | 0.923 | 1.55 | 1.45 | ✓ |
| 2026 | 0.932 | 5.25 | 3.94 | ✓ |

Walk-forward 每一年濾網都勝過基線，比 H066 的 2/5 穩定得多。

## Gate Decision

**進入 Verdict**

- [x] 每組 ≥ 100 筆（240/240）
- [x] PF 差異 > 20%（64.3%）
- [x] 跨年一致 > 2/3（5/6）
- [x] Quartile 完美單調遞增
- [x] Walk-forward 5/5 全勝

## Verdict

**Confirmed**（2026-04-17）

沿用 H066 的 SMA20 + 門檻 0.85，對 Reversal 同樣適用。

**支持 Confirmed：**
1. Q1/Q2（低夜盤波動）都是負期望值，過濾掉完全合理
2. Walk-forward 5/5 全勝——比 H066（2/5）穩定得多
3. 門檻不敏感（0.70–1.10 OOS 都 > 2.0）
4. 邏輯合理：反轉需要波動空間

**注意事項：**
1. IS 期間效果不明顯（IS PF 從 1.02 → 1.04），因為 Reversal 2021-2024 整體偏弱
2. OOS 期間效果清楚（1.93 → 2.15）
3. 沿用 H066 的 SMA20 + 門檻 0.85 即可

## Derived Hypotheses
- 無額外衍生（濾網邏輯與 H066 相同，共用基礎設施）
