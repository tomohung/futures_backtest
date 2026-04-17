# Archive: Reversal Weekday Effect

## Status
Confirmed

## Summary
Reversal 在週一（PF=0.77, 1/6 年正）和週五（PF=0.93, 2/6 年正）表現差，跳過後結合夜盤濾網 PF 從 1.04 提升至 1.92，Sharpe 從 0.14 至 3.09。Walk-forward NVF+skip Mon+Fri 5/5 全勝。

## Key Evidence
- Mon PF=0.77, consistency 1/6。高低夜盤波動都差（0.77 vs 0.76），非夜盤因素
- Fri GO 天 PF=1.11 但 4/6 年虧，保留風險 > 收益
- NVF+skip MF: IS PF=1.55, OOS PF=2.49, Sharpe=3.09, MDD=-565
- Walk-forward 5/5 全勝（唯一全勝組合）

## Why Confirmed
1. 週一弱勢極度穩定（5/6 年虧損），與夜盤波動無關
2. 跳過後品質指標全面改善（PF、Sharpe、MDD）
3. Walk-forward 全勝驗證

## Derived Hypotheses
無

## Links
- Proposal：proposal.md
- Results：results/distribution.md
- Explore script：explore.py
