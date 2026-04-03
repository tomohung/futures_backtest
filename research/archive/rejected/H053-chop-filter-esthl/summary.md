# Archive: CHOP 斬波指標作為 EstHL 盤整日濾網

## Status
Rejected

## Summary
測試 CHOP (Choppiness Index) 作為 EstHL 和 Reversal 策略的盤整日濾網。前一日 CHOP > 61.8 時跳過交易，試圖避開低品質的盤整日交易。

## Key Evidence
- CHOP(10) > 61.8 全期間僅過濾 15 筆 EstHL 交易（5 年），樣本不足
- 被濾交易確實較差（PF 0.46, WR 33%），但每年僅 2-3 筆，實務影響微小
- 年度不一致：2022 年因誤殺好交易反而惡化（PF 3.39→2.82）
- Reversal OOS 幾乎無效（PF 1.56→1.57）
- CHOP 無法取代 weekday filter（全週+CHOP 最佳 PF 2.06 < Mon~Wed PF 2.44）

## Why Rejected
CHOP 有根本性概念缺陷：它衡量的是「波動效率」而非「波動大小」，將高波動盤整（大幅震盪無方向）和低波動盤整混為一談。高波動盤整對 ORB 策略可能反而有利（振幅夠大），但 CHOP 會將其標記為「盤整」而誤殺。加上樣本極少、年度不一致，判定為無效濾網。

## Derived Hypotheses
- H0XX：將盤整判斷改為區分「高波動盤整」vs「低波動盤整」，前者不過濾
- H0XX：CMI (Choppy Market Index) 替代 CHOP，可能有不同特性
- H0XX：CHOP + ADX 複合判斷，用 ADX 衡量方向性、CHOP 衡量效率

## Links
- Proposal: proposal.md
- Distribution: results/distribution.md
- Backtest: results/backtest.md
- Explore script: explore.py
- Backtest script: backtest.py
