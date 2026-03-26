# Archive: 突破時間點與勝率分析

## Status
Rejected

## Summary
分析 EstHL（N=160）和 ORBLong（N=329）兩策略的精確進場分鐘是否影響勝率。發現特定 5 分鐘 bucket 存在績效差異，但年度穩定性極差，不足以支持加入時間濾網。

## Key Evidence
- EstHL：09:00 bucket 反而是最佳時段（PF 2.99），原假設「現貨開盤假突破多」不成立
- ORBLong：09:35 bucket 是唯一虧損時段（PF 0.96），但年度勝率波動極大（20%~69%）
- 兩策略的「低谷 bucket」在年度穩定性檢查中均不一致，暗示為隨機噪音

## Why Rejected
1. 核心假設（09:00 假突破率高）與數據相反
2. 雖然存在低谷 bucket，但年度間不穩定，無法確認為持續性效應
3. 子樣本過小（各 bucket 年度內常僅個位數），統計顯著性不足
4. 加入時間濾網的 data snooping 風險大於潛在收益

## Derived Hypotheses
- 無

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
