# Proposal: Strong Night Vol Override on Weak Weekdays

## ID
H069

## Derived From
H066（EstHL night vol filter）、H068（Reversal weekday effect）的交叉分析

## Trading Intuition
弱勢星期（EstHL Thu, Fri；Reversal Mon, Fri）目前一律跳過。但初步分析發現：
- EstHL 週四在 night_norm >= 1.15 時 PF=3.10（N=17），比正常星期還好
- Reversal 週五在 night_norm >= 1.30 時 PF=2.34（N=27），也不錯
- 但 EstHL 週五和 Reversal 週一即使夜盤很強也救不了

夜盤「很強」（非只是「不弱」）可能代表市場有重大事件驅動，打破了星期的結構性弱勢。

## Hypothesis
特定的「弱勢星期 × 強夜盤」組合可以恢復進場：
- EstHL 週四：night_norm >= 1.15 時進場有正期望值
- Reversal 週五：night_norm >= 1.30 時進場有正期望值

## Expected Distribution
- EstHL Thu + norm >= 1.15：PF > 1.5，跨年多數正
- Reversal Fri + norm >= 1.30：PF > 1.5，跨年多數正
- 兩者的 IS/OOS 一致

## Invalidation Condition
- 跨年穩定性 < 3/6（方向不一致太多）
- IS/OOS PF 差異過大（> 100%）
- 樣本太少無法得出結論（N < 15 in IS or OOS）

## Notes
- EstHL 週五和 Reversal 週一即使 norm >= 1.50 也救不了，不測
- 門檻比一般濾網（0.85）高很多，需確認不是少數極端交易撐起來的
- 需逐年驗證 + 逐筆交易明細
