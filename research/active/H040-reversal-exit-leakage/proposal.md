# Proposal: Reversal Exit Leakage — 方向對但出場賺不到

## ID
H040

## Derived From
H039 的 Phase 1 vs Phase 2 落差觀察

## Trading Intuition
H039 Phase 1 探索顯示 2nd BB touch exclusive 的 MFE > MAE 勝率為 58.8%（全期）、72%（2025），
表示進場方向有 edge。但實際回測（含完整出場邏輯）的勝率只有 ~46%。

這代表出場邏輯（SL、SatZone、pivot trailing stop、13:40 強平）正在消耗進場的 edge。
可能的問題：
- SL 太緊，在反轉完成前被止損打掉
- Trailing stop 太早鎖定，錯過後續利潤
- SatZone 出場時機不佳
- 13:40 強平的影響

## Hypothesis
Reversal 策略的出場邏輯存在可量化的「leakage」——進場方向正確的交易中，
有顯著比例因出場規則不佳而變成虧損。透過分析各出場類型的 PnL 分佈，
可以找到改善空間。

## Expected Distribution
- SL 出場的交易中，部分是「先被止損再反轉」的假性虧損
- Trailing stop 出場的交易，可能出場太早（後續還有空間）
- 不同出場類型的 PnL 分佈有顯著差異
- 至少一種出場類型的調整可以改善整體績效

## Invalidation Condition
- 各出場類型的 PnL 分佈無顯著差異（出場邏輯不是瓶頸）
- 或 SL 出場的交易中，「先止損再反轉」的比例 < 10%（SL 不是問題）
- 或調整出場參數後 in-sample 改善但 out-of-sample 退步（過度擬合）

## Notes
- 需要在回測中記錄每筆交易的出場原因（SL / SatZone / Trail / Force）
- 對 SL 出場的交易，追蹤止損後的 MFE（如果沒被止損，後續能走多遠）
- 這是出場優化，不是進場條件的研究
