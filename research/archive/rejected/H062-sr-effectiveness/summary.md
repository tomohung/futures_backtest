# Archive: S/R 支撐壓力有效性驗證

## Status
Rejected

## Summary
驗證 key_prices.py 計算的 Swing High/Low 聚類與 Volume Profile HVN 支撐壓力是否有效。以 1218 個交易日、1789 次觸及事件做統計分析，比較 S/R vs 隨機價位的反應率。結論：S/R 在觸及後反彈的維度上不優於隨機，甚至顯著更差。

## Key Evidence
- 30分K Swing S/R 命中率 37.2% vs 隨機 39.9%（p=0.026，S/R 顯著更差）
- 日K Swing S/R 命中率 36.0% vs 隨機 38.8%（p=0.203）
- Strength 越高，表現反而越差：str 4+ 命中率 32.5%，反彈 15.7pt
- 排斥效應微弱存在（p=0.0001）但差距僅 8%，不具交易價值

## Why Rejected
三種 S/R 算法（30分K、日K、日K 強聚類）在 5 年資料下一致顯示 S/R 沒有比隨機好。排斥效應雖統計顯著但效果太小（65% 的時間強 S/R 仍被穿越）。結果與交易直覺完全相反 — strength 越高反而命中率越低。

## Derived Hypotheses
- 早盤簡報中的 S/R 展示應降低權重或移除，避免交易者被無效資訊干擾

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- 探索腳本：explore.py（初版 6 個月）、explore_repulsion.py（排斥效應）、explore_extended.py（全期間 + 日K 比較）
