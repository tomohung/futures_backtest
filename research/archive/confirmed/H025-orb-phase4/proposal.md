# Proposal: ORB Phase 4 自適應 TP 優化

## ID
H025

## Derived From
H024

## Trading Intuition
Phase 2 的 TP = entry +/- 0.75% 是固定百分比，與當日實際波動無關。2021/2022 強制出場率僅 27%，代表 TP 根本很少被打到，多數交易在 TP 前就被 SL 或 trailing stop 出場。需要以當日波動度（OR 寬度或含夜盤的 True Range）來動態設定 TP。

## Hypothesis
以 OR 寬度（OR_high - OR_low）乘以倍數作為 TP，可根據當日波動自適應調整停利距離。波動大的日子 TP 遠（讓利潤奔跑），波動小的日子 TP 近（儘早獲利了結）。

### 夜盤波動假設（已探索驗證）
- 情境 A：夜盤動 → 日盤也動（正相關）→ 夜盤 range 大時 TP 設更遠
- 情境 B：夜盤已消化 → 日盤縮量整理（負相關）→ 反向設定
- 需先做探索性分析確認實際關係

## Expected Distribution
| 指標 | Train 目標 | OOS 門檻 |
|---|---|---|
| 勝率 | >= 52% | >= 50% |
| 平均盈虧比 | >= 1.3 | -- |
| 獲利因子 | >= 1.2 | >= 1.0 |
| 2021/2022 期望值 | 明顯高於 Phase 2（+3.1/+1.9 pts） |
| 2021/2022 強制出場% | 高於 27% |
| 6 年累積 PnL | > Phase 2 +4,632 pts |
| 單年最差 | 不低於 -200 pts |

## Invalidation Condition
- 夜盤與日盤波動弱相關（|r| < 0.2）→ 夜盤訊號無效，使用 OR 寬度即可
- 所有 TP 方案均無法改善 2021/2022 的 tp_exit%

## Notes
### Phase 3 結論（SL 優化失敗）

| 策略 | 2021~2026 累積 | 問題 |
|---|---|---|
| Phase 2 Base | **+4,632 pts** | 2021/2022 表現弱 |
| Phase 3A (OR SL + OR TP + bar trail) | +655 pts | 做空爛掉 |
| Phase 3B (OR SL + Super Trend 出場) | +1,913 pts | 仍遜於 Phase 2 |
| Plan C (動量停滯出場) | +1,169 pts | 2021/2022/2024 負 |

**結論：換 SL 不是解答。Phase 2 的固定百分比 SL 已是最穩定的。**

### TP 候選方案
- **方案 A：OR 寬度 TP** — `TP = entry +/- tp_or_multiplier x OR_width`（預設推進）
- **方案 B：含夜盤的 True Range TP** — 夜盤與日盤正相關時
- **方案 C：夜盤條件式 TP** — 夜盤波動大/小用不同乘數

### 優化參數
| 參數 | 測試值 |
|---|---|
| `tp_or_multiplier` | 0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0 |
| `sl_pct` | 0.004, 0.005, 0.006 |

共 7 x 3 = 21 組

### 探索性分析
- `src/backtest/explore_night_day.py` — 夜盤 vs 日盤波動關係

### 相關檔案
- `src/strategies/orb.py` — `ORBPhase4Strategy` / `ORBPhase4HybridStrategy`
- `src/backtest/optimize_phase4.py` — Phase 4 優化
- `src/backtest/optimize_phase4_hybrid.py` — Phase 4 Hybrid 優化
