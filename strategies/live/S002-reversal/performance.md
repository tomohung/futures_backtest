# Performance Log: Reversal v2

## Backtest Summary
### v2（2026-03 回測）
| Metric | Value |
|---|---|
| Trades | 10 |
| Win Rate | 70% |
| PnL | +1,482 pts |
| 實單捕捉率 | 86% (6/7) |

### v1 全期（2021–2026，參考基準）
| Metric | In-Sample | Out-of-Sample |
|---|---|---|
| Sharpe Ratio | 1.34 | — |
| Max Drawdown | — | — |
| Win Rate | 53.9% | — |
| # of Trades | 690 | — |
| PF | 1.49 | — |
| Total PnL | +5,571 pts | — |

## Weekday Breakdown
| Weekday | Trades | Win Rate | PF | Avg PnL | Notes |
|---|---|---|---|---|---|
| Mon | — | — | — | — | |
| Tue | — | — | — | — | |
| Wed | — | — | — | — | |
| Thu | — | — | — | — | |
| Fri | — | — | — | — | |

## Research History
- H005：Reversal v1 → confirmed
- H006：Reversal v2（力竭 + VWAP bypass）→ confirmed
- H001：EstHL 離場機制 → confirmed（共用 SatZone 出場）
- H010：結算日量校正 → confirmed

## Live Performance Log
| Period | Return | Notes |
|---|---|---|
| | | |

## Near-SatZone Gate 改為統一 Latch（2026-03-23）

### 變更
原本 near-SatZone gate 只檢查進場方向（做多檢查上方、做空檢查下方），且每根 bar 重新計算。
改為：任一方向觸及 near-SatZone 即鎖定（latch），當日不再進場。

**核心理念**：振幅用完就是用完，無論多空都不該再進場。

### 四版比較（全期 2021–2026）

| | 舊（各自檢查） | 統一（非 latch） | **Latch 1/8（採用）** | Latch margin=0 |
|---|---|---|---|---|
| 交易數 | 582 | 525 | **472** | 623 |
| 勝率 | 43.8% | 44.4% | 43.9% | 44.1% |
| PF | 1.26 | 1.32 | 1.26 | 1.25 |
| 總 PnL | +3,308 | +3,529 | **+2,640** | +3,349 |

> **Latch margin=0 說明**：margin=0 等於碰到 SatZone 才 latch，跟 `satzone_reached` 幾乎重疊。
> 交易數反而最多（623），因為觸發時機最晚。SatZone 計算本身已內縮 1/8 EmaHL，
> near-sat gate 再用 1/8 EmaHL margin 等於在 EstHighLevel 的 2/8 處提前觸發，
> 過濾效果明顯優於 margin=0。

### 逐年比較

| 年 | 舊 | Latch 1/8 | Latch m=0 |
|---|---|---|---|
| 2021 | -168 | +80 | -366 |
| 2022 | +143 | +115 | +380 |
| 2023 | -64 | -206 | -58 |
| 2024 | +72 | +26 | -55 |
| 2025 | +1,392 | +1,111 | +1,397 |
| 2026 | +1,933 | +1,514 | +2,051 |

### 被 Latch 擋掉的 110 筆交易分析

| | 值 |
|---|---|
| 總數 | 110 筆（Long 63 / Short 47） |
| 勝率 | 43.6% |
| 總 PnL | +668（平均 +6.1/筆） |
| P25 / P50 / P75 | -38 / -4 / +32 |
| Min / Max | -163 / +426 |

**按年度**：
| 年 | n | 方向 | WR | PnL | avg |
|---|---|---|---|---|---|
| 2021 | 27 | L=16/S=11 | 37.0% | -248 | -9.2 |
| 2022 | 18 | L=10/S=8 | 44.4% | +28 | +1.6 |
| 2023 | 24 | L=10/S=14 | 41.7% | +142 | +5.9 |
| 2024 | 24 | L=16/S=8 | 41.7% | +46 | +1.9 |
| 2025 | 12 | L=9/S=3 | 58.3% | +281 | +23.4 |
| 2026 | 5 | L=2/S=3 | 60.0% | +419 | +83.8 |

### 決策
維持 latch 版。被擋掉的交易整體正期望值（+668），但策略實作應配合核心概念。
短期回測數字不足以推翻邏輯正確的設計，需長期失真才考慮修改。

## Review Notes
- exhaust_fraction 敏感度（0.3/0.4/0.5/0.618）待全期回測驗證

## Status
[x] Active　[ ] Under Review　[ ] Retired
