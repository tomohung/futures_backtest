# Proposal: CHOP 斬波指標作為 EstHL 盤整日濾網

## ID
H053

## Derived From
H050 Phase 0 批次 1 評估（E1 候選）

## Trading Intuition
EstHL 策略在趨勢日表現好、盤整日容易被停損。CHOP（Choppiness Index）能量化前一日的盤整程度：CHOP > 61.8 表示高度盤整（市場能量被消耗），< 38.2 表示趨勢明確（能量集中在方向上）。

H050 初步測試顯示：前一日 CHOP(14) > 61.8 的日子，次日平均振幅僅 174pt（vs 趨勢日 261pt）。如果跳過這些低振幅日，可能減少 EstHL 的虧損交易。

## Hypothesis
在 EstHL 策略上加入 CHOP(14) 濾網（跳過前一日 CHOP > 61.8 的交易日），能提升 PF 而不顯著減少交易筆數。

## Expected Distribution
- 被過濾的日子 ~5%（CHOP > 61.8 佔 4.6%）
- 被過濾日的 EstHL 交易勝率低於整體
- 過濾後 PF 提升 0.1~0.3

## Invalidation Condition
- 過濾後 PF 提升 < 0.05（濾網無效）
- 被過濾掉的交易中有 > 50% 是獲利交易（誤殺太多好交易）
- CHOP 門檻敏感度高（微調門檻 ±5 就翻轉結論）

## Notes
- CHOP = 100 × LOG10(SUM(ATR, n) / (Highest - Lowest)) / LOG10(n)
- 使用前一日 CHOP 值，無 lookahead
- 也測試 CHOP(10) 和 CHOP(20)
- 除了 EstHL，也可測試對 Reversal 和 Exhaustion 的效果
- 如果 CHOP 區分度不夠，可考慮改用 CMI (Choppy Market Index) 或 ADX
