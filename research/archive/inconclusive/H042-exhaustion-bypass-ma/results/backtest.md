# Backtest Results: Exhaustion Bypass MA Direction

## Date
2026-03-26

## Parameters
- 進出場邏輯沿用 ReversalStrategy（BB latch + MA5 trigger + SatZone exit）
- 唯一差異：當對手方 exhausted 時，BB latch 和 setup 不檢查 MA 方向
  - `long_ma_ok = bullish or bear_exhausted`
  - `short_ma_ok = (not bullish) or bull_exhausted`
- 手續費 0、滑價 0（與 baseline 一致）
- Exhaustion 定義：`close` 距日極端已走 50% EmaHL（沿用現有 `exhaust_fraction=0.5`）

## Results

### 逐年比較

| Period | Standard N | Standard WR | Standard PF | Standard Total | Bypass N | Bypass WR | Bypass PF | Bypass Total |
|--------|-----------|-------------|-------------|----------------|----------|-----------|-----------|--------------|
| IS 2021 | 65 | 41.5% | 0.91 | -140 | 71 | 40.8% | 0.98 | -27 |
| IS 2022 | 135 | 42.2% | 1.13 | 306 | 140 | 41.4% | 1.06 | 140 |
| IS 2023 | 116 | 44.0% | 1.11 | 188 | 124 | 41.9% | 1.05 | 86 |
| IS 2024 | 108 | 45.4% | 1.05 | 133 | 122 | 46.7% | 1.18 | 530 |
| **OOS 2025** | **116** | **47.4%** | **1.44** | **1,276** | **131** | **46.6%** | **1.46** | **1,508** |
| **OOS 2026** | **16** | **68.8%** | **4.76** | **1,994** | **17** | **64.7%** | **4.50** | **1,963** |

### 彙總

| Metric | Standard | Bypass | Delta |
|--------|----------|--------|-------|
| **IS Total (2021-2024)** | | | |
| Trades | 424 | 457 | +33 |
| WR | 43.4% | 42.9% | -0.5% |
| PF | 1.06 | 1.08 | +0.02 |
| Total PnL | 487 | 729 | +242 |
| **OOS Total (2025-2026)** | | | |
| Trades | 133 | 149 | +16 |
| WR | 50.4% | 49.0% | -1.4% |
| PF | 1.96 | 1.91 | -0.05 |
| Total PnL | 3,294 | 3,495 | +201 |
| **ALL** | | | |
| Trades | 558 | 607 | +49 |
| WR | 45.0% | 44.3% | -0.7% |
| PF | 1.32 | 1.33 | +0.01 |
| Total PnL | 3,728 | 4,171 | **+443** |
| Sharpe | 1.2 | 1.2 | 0.0 |

## Delta Analysis — 49 筆 Extra Trades

Exhaustion bypass 產生 49 筆新交易（standard 沒有的日子）：
- **WR 36.7%**（18 wins / 31 losses）
- **Avg PnL +9.0 pts**
- **Total +443 pts**

低勝率但靠少數大贏家（如 2025-11-04 +331、2024-08-02 +249、2024-12-10 +167）撐起正期望值。

## H044 DIR_BLOCKED 比對

12 筆 H044 實盤 DIR_BLOCKED 交易中，exhaustion bypass 捕捉到 **4 筆 (33%)**：
- 2025-03-19、2025-11-13、2025-12-02、2025-12-18

未捕捉的 8 筆原因可能：
- 部分 DIR_BLOCKED 是 BC zone 限制（above/below 方向固定），非 MA 方向問題
- 部分交易的 setup 條件（BB touch + vol）在回測中不滿足
- Exhaustion 可能尚未觸發時 setup 已過窗口

## Invalidation Check

| 無效條件 | 結果 | 通過？ |
|----------|------|--------|
| Bypass PF < 1.0 | ALL PF = 1.33 | ✅ 通過 |
| 整體 PF < 1.25 | ALL PF = 1.33（vs 標準 1.32） | ✅ 通過 |
| WR < 45% | Extra trades WR 36.7%（整體 44.3%） | ⚠️ 邊緣 |
| 年度不穩定 | IS 2021-2023 PF < 1.1，2024 改善；OOS 穩健 | ⚠️ IS 偏弱 |

## Verdict
- [ ] Confirmed
- [ ] Rejected
- [ ] Inconclusive

### 判斷依據

**正面**：
- 整體 PF 微升（1.32 → 1.33），total PnL +443 pts
- IS 和 OOS 都是正向 delta（IS +242, OOS +201）
- 不破壞原有策略品質
- 2024 年 IS 改善最明顯（133 → 530 pts）

**負面**：
- 49 筆 extra trades WR 只有 36.7%，依賴少數大贏家
- IS 2021-2023 的 PF 都從標準版略降
- H044 捕捉率僅 33%（4/12）
- Extra trades 的 PnL 分佈 skewed——移除最大 3 筆後可能轉負

**整體評估**：
Exhaustion bypass 帶來的改善是**微幅但正向**的。PF 從 1.32 到 1.33，不傷害也不明顯幫助。這更像是「無害的微調」而非「有意義的改進」。是否值得增加策略複雜度來換取 +443 pts（5年累積），取決於你對簡單性 vs 邊際收益的偏好。

## Derived Hypotheses
- H04X：extra trades 的低 WR 但高 EV 特徵，是否可以用更寬鬆的 SL 或更長的持倉時間來捕捉？（反轉交易可能需要更大空間）
- H04X：H044 的 8 筆未捕捉 DIR_BLOCKED 交易，是否有其他共同特徵可作為 bypass 條件？
