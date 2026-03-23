# Proposal: ORB Phase 2 全參數掃描（含 Trend MA Filter）

## ID
H024

## Derived From
H023

## Trading Intuition
Trend MA Filter 已證實有效（PF 1.02 → 1.215），固定此濾網後，對其餘 5 個基礎參數進行全面掃描，尋找最佳組合。

## Hypothesis
固定 `trend_ma_days=10`，透過掃描 range_end_minute、entry_end_minute、sl_pct、tp_multiplier、trail_activate_minute 等 5 個參數（共 896 組有效組合），可找到勝率 >= 52%、PF >= 1.2 的穩定組合。

## Expected Distribution
| 指標 | Train 目標 | OOS 門檻 |
|---|---|---|
| 勝率 | >= 52% | >= 50% |
| 平均盈虧比 | >= 1.3 | -- |
| 獲利因子 | >= 1.2 | >= 1.0 |

Train: 2023-2025 | OOS Test: 2026

## Invalidation Condition
896 組參數均無法在 train 期達到 52% 勝率 + 1.2 PF。

## Notes
### 參數網格

| 參數 | 測試值 | 說明 |
|---|---|---|
| `range_end_minute` | 60, 75, 90, 105 | 08:00+N，OR 窗口 15/30/45/60 分鐘 |
| `entry_end_minute` | 75, 90, 105, 120, 150 | 必須 > range_end_minute |
| `sl_pct` | 0.003, 0.005, 0.007, 0.010 | 停損比例 |
| `tp_multiplier` | 1.5, 2.0, 2.5, 3.0 | 停利倍數 |
| `trail_activate_minute` | 30, 45, 60, 90 | 移動停損啟動時間 |
| `trend_ma_days` | **10**（固定） | 兩週交易日 MA |

有效組合：**896 組**（已扣除 entry_end <= range_end 的無效組合）

### Phase 2 各年度結果（最終採用）
| 年度 | 筆數 | 勝率 | PF | 期望值 | 強制出場% |
|---|---|---|---|---|---|
| 2021 | 130 | 43.8% | 1.09 | +3.1 | 27.7% |
| 2022 | 114 | 45.6% | 1.07 | +1.9 | 27.2% |
| 2023 | 111 | 51.4% | 1.11 | +2.4 | 63.1% |
| 2024 | 114 | 50.9% | 1.22 | +8.8 | 35.1% |
| 2025 | 95 | 56.8% | 1.49 | +16.7 | 45.3% |
| **累計** | | | | | **+4,632 pts** |

### 相關檔案
- `src/backtest/optimize.py` — Phase 2 網格搜尋
