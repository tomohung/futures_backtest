# Strategy Spec: Reversal v2 — 力竭 + VWAP Bypass 均值回歸

## ID
S002

## Source Hypothesis
H005-reversal, H006-reversal-v2（research/archive/confirmed/）

## Description
均值回歸策略，利用 Bollinger Band 觸碰建立 latch，搭配成交量確認與力竭判定（EstRange × 0.5）確認單邊波動耗盡後進場。09:30 後 VWAP bypass 解決 CCD 結構性為負的問題。SatZone 兩段式出場（與 EstHL 共用模組）。v2 相比 v1 將實單關鍵價轉折捕捉率從 43% 提升至 73–86%。

## Entry Conditions
1. **BB latch**：價格觸碰 BB(20, 2.0) 上軌或下軌，setup window 從 08:45 開始
2. **力竭判定**：當日已走幅度 ≥ EstRange × exhaust_fraction(0.5)
3. **成交量確認**：vol_ratio 達標
4. **進場信號**：5MA crossing 確認反轉
5. **VWAP bypass**：09:30 後可繞過 CCD 方向限制，以 VWAP 作為盤中成本確認

## Exit Conditions
- **SatZone 兩段式**：Phase 1 價格觸碰 SatZone → Phase 2 close 跌破 5MA 出場
- **時間停損**：13:45 收盤強制平倉

## Parameters
| Parameter | Value | Sensitivity |
|---|---|---|
| BB period | 20 | Low |
| BB std | 2.0 | Low |
| exhaust_fraction | 0.5 | Medium |
| VWAP bypass start | 09:30 | Low |
| EstRange EMA | 20 | Low |
| Settlement vol mult | 1.9 | Low |

## Universe
- 交易標的：台指期（TX）日盤
- 排除條件：無特定週間排除

## Execution
- 頻率：日盤每日
- 下單時機：BB latch + 力竭 + 5MA crossing 同時滿足時進場
- 倉位大小：½ 口（與 EstHL 各半，參考 H004 配置）

## Constraints
- 最大持倉數：1
- 單筆最大風險：依 SatZone 反向計算

## Source Code
- Strategy：`src/strategies/orb.py` — ReversalStrategy
- Exit mixin：`src/strategies/estimate_hl_exit.py`
- Indicator：`src/backtest/estimate_hl.py`
- Pine Script：`indicators/tradingview/orb_est_hl_tx.pine`
