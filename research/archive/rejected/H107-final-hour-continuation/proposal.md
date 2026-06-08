# Proposal: 尾盤趨勢延續（Final-Hour Continuation）

## ID
H107

## Derived From
`research/angell-backlog.md` 候選 **GA-09**（Angell 來源 *Trading the Final Hour*：「don't fade the final hour」）。
市場結構類（非心法量化）。**與 H027（ORB 出場交叉，confirmed）、H030（ORBLong，active）的差異**：那兩個是
**開盤** range breakout；本假設專測**尾盤 / time-of-day 調節**，不重疊。

## Trading Intuition
Angell：尾盤的趨勢/突破傾向**續行**（不要逆勢），而早盤突破較易**反轉**（被 fade）。直覺是日內後段
資訊已充分定價、部位調整與收盤效應使既有方向延續；早盤則多試探、假突破多。台指日盤僅 5 小時
（08:45–13:45），「尾盤」切點必須用台指資料校準，不可套美股 6.5 小時的「final hour」。

## Hypothesis
**零策略現象**，兩種操作化都測，並用 time-of-day 對比（早盤 vs 尾盤）當天然對照：

1. **方向動能續行**：在錨點時刻 t，`進場前走勢`（price_t − price_open，或前 Δ 分動能）與
   `t→收盤剩餘走勢`（price_close − price_t）的**同向續行強度**。
2. **突破續行**：t 時突破前 30 分區間 H/L → 收盤是否**延伸**（續行）vs **回補**（fade）。

**陳述**：續行強度（同向相關 / 突破延伸率）在**尾盤錨點顯著高於早盤錨點**；早盤偏 fade（續行≈0 或負）、
尾盤偏續行（正）。切點由資料指出（30 分區塊動能矩陣）再驗證 last 30/45/60 分。

**先驗 / 防偽訊號**（沿用 H105/H106 教訓 [[feedback_excursion_needs_forward_tautology_guard]]）：
- 剩餘走勢隨錨點變晚會**機械性變小**（剩餘時間少），故 forward 必須以**剩餘時間 / ATR 正規化**，否則
  早晚不可比。
- 續行率需對比 baseline（突破延伸率 vs 無條件收盤同向率 / 洗牌虛無），非只看絕對值。
- 早盤 vs 尾盤的**對比**本身是主要控制：尾盤需顯著 > 早盤才算 time-of-day 效應，而非全日皆有的漂移。

## Expected Distribution
- 動能矩陣：續行（正自相關）集中於日內後段，早段近 0 或負（fade）。
- 尾盤錨（如 12:45 起）：同向續行率 > 50% 且 > 早盤錨；突破延伸率 > 回補率。
- 早盤錨（如 09:15）：突破較常被 fade（呼應 GA-11 掃停損反轉、與 H030 ORB 反咬 56–68% 一致）。
- 可能部分成立：續行或只在「趨勢日」尾盤強、震盪日尾盤仍 fade → 需條件化（連結 regime / 當日振幅）。

## Invalidation Condition
- 尾盤續行強度（動能 and 突破）**不顯著高於早盤**（無 time-of-day 調節）→ GA-09 在台指不成立。
- 正規化（剩餘時間/ATR）後，尾盤「續行」只是機械漂移、對比 baseline/洗牌無超額 → 偽訊號。
- 兩種操作化都看不到尾盤效應，或效應僅來自極少數趨勢日無統計力。

## Notes
- 資料就緒：`ohlcv_1m` 日盤，零新資料。錨點走勢用 raw（日內 offset 抵銷）。
- 切點校準為 Phase 1 核心：先 30 分區塊動能矩陣定位，再驗 last 30/45/60；避免事後選點 data snooping。
- 對稱情境各自實測（上行/下行趨勢、早盤/尾盤）——呼應 [[feedback_isolate_phenomenon_and_test_each_cell]]。
- 若成立，衍生「尾盤突破續行進場 / 早盤突破不追（或反 fade）」策略回測為下一假設；與 H030 ORB（開盤）互補。
