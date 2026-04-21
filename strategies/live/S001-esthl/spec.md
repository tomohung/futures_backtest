# Strategy Spec: EstHL — ORB + EstRange SatZone Exit

## ID
S001

## Source Hypothesis
H001-estimate-high-low-exit-strategy, H002-orb-with-est-high-low-exit（research/archive/confirmed/）

## Description
早盤 ORB 進場搭配 EstRange SatZone 兩段式出場。定義 08:45–08:57 的 Opening Range，於 08:58–09:15 窗口突破 OR High 做多，經 VWAP 濾網、30 分 K 20MA 方向濾網、OR% 相對寬度濾網篩選。出場採 SatZone 兩段式（觸碰 → 跌破 5MA）+ Dow Theory trailing stop。Long-only，跳過週四/五。

## Entry Conditions
1. OR 定義：08:45–08:57（13 bars）的 High / Low
2. 進場窗口：08:58–09:15
3. 觸發：1 分 K close > OR High
4. 方向：僅做多
5. 濾網：
   - VWAP：近 2 日 VWAP 方向一致
   - 30 分 K 20MA 方向向上
   - OR% 介於 0.3%–1.0%（OR 寬度 / 開盤價 × 100）
   - **夜盤波動 NVF（H066 + H075）**：tonight_range / EMA20(night_range) ≥ expanding_median（當前約 0.93）才進場
6. 排除：週四、週五不交易

## Exit Conditions
- **SatZone 兩段式**：Phase 1 價格觸碰 SatZoneUpper → Phase 2 close 跌破 5MA 出場
- **停損**：進場價 - EmaHL × SL multiplier(0.25)
- **Dow Theory trailing stop**：追蹤 swing low
- **時間停損**：13:45 收盤強制平倉

## Parameters
| Parameter | Value | Sensitivity |
|---|---|---|
| OR period | 08:45–08:57 | Low |
| Entry end | 09:15 | Low |
| SL multiplier | 0.25 | Medium |
| VWAP lookback | 2 days | Low |
| Skip weekdays | Thu, Fri | Low |
| NVF method | EMA20 + expanding median (H075) | Low |
| NVF threshold | dynamic (~0.93) | Low |
| EstRange EMA | 20 | Low |
| Settlement vol mult | 1.9 | Low |
| OR% range | 0.3–1.0% | Medium |

## Universe
- 交易標的：台指期（TX）日盤
- 排除條件：週四、週五、OR% 超出範圍

## Execution
- 頻率：日盤每日（Mon–Wed）
- 下單時機：08:58–09:15 突破時即進場
- 倉位大小：½ 口（與 Reversal 各半，參考 H004 配置）

## Constraints
- 最大持倉數：1
- 單筆最大風險：EmaHL × 0.25（約 27–114 點，視波動度）

## Source Code
- Strategy：`src/strategies/orb.py` — ORBWithEstHLExitStrategy
- Exit mixin：`src/strategies/estimate_hl_exit.py`
- Indicator：`src/backtest/estimate_hl.py`
- Runner：`src/backtest/runner.py`
- Pine Script：`indicators/tradingview/orb_est_hl_tx.pine`
