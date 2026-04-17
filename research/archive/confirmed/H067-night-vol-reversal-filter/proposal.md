# Proposal: Night Session Volatility as Reversal Filter

## ID
H067

## Derived From
H066（Night Vol EstHL Filter）confirmed 後，探索同一濾網對 Reversal 策略的適用性

## Trading Intuition
H066 已證實夜盤波動大小能有效區分 EstHL 績效。初步分析顯示 Reversal 策略的效果更極端：低波動夜盤後 Reversal 幾乎不賺錢（PF=0.96），所有利潤集中在高波動夜盤（PF=1.58）。這合理——反轉策略需要足夠波動才有空間反轉，夜盤平靜代表市場缺乏動能，日盤也沒什麼好反轉的。

## Hypothesis
以前一晚夜盤振幅（SMA20 正規化）的高低分組，Reversal 在「夜盤高波動」組的績效顯著優於「夜盤低波動」組。使用 night_norm >= 0.85 門檻可有效過濾低品質交易。

## Expected Distribution
- 夜盤高波動組：PF > 1.5，正期望值
- 夜盤低波動組：PF ≈ 1.0 或更低，近乎無邊際
- Quartile 呈單調遞增（Q1 最差，Q4 最好）
- 跨年一致性 > 4/6

## Invalidation Condition
- 兩組 PF 差異 < 20%
- 跨年穩定性差（半數以上年份方向不一致）
- 門檻在 IS/OOS 間不穩定

## Notes
- 初步分析（N=487）已顯示強信號：HIGH PF=1.58 vs LOW PF=0.96，5/6 年一致
- Quartile 分析：Q1 PF=0.95, Q2 PF=0.97, Q3 PF=1.15, Q4 PF=1.93
- 正規化方式沿用 H066：SMA(20)
- Phase 1 可直接用初步結果補充 IS/OOS 切分與門檻敏感度
