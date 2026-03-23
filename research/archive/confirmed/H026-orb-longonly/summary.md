# Archive: ORB Long-Only 做多專注策略

## Status
Confirmed

## Summary
放棄做空，專注做多。搭配 ADX 濾網（ADX > threshold），成為現行最佳做多策略 ORBLongStrategy。做空勝率常年低於 50%，放棄做空換取心理穩定性與績效一致性。

## Key Evidence
- 做空勝率常年低於 50%（2021: 44%, 2022: 42%）
- ADX Q4（>32.7）：win% 57%, exp +29.9 pts/筆
- Long-only 策略為現行最佳做多策略
- 用戶決策：聚焦做多，放棄做空

## Why Confirmed
Long-only + ADX 濾網組合成功解決了做空端的長期虧損，ORBLongStrategy 成為實盤策略。

## Derived Hypotheses
- H030：ORBLong 進一步研究（Regime 交叉、SatZone 出場等）

## Links
- Proposal：research/active/H026-orb-longonly/proposal.md
- Spec：research/active/H026-orb-longonly/spec.md
- Tasks：research/active/H026-orb-longonly/tasks.md
