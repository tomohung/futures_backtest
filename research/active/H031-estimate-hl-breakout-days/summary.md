# Archive: EstimateHL 趨勢爆發日與未觸及日分析

## Status
Inconclusive

## Summary
分析兩類極端日：趨勢爆發日（14%，超出 SatZone >100 pts）與完全未觸及日（34%）。分佈分析已完成，但改善方向（動態 SatZone、觀察期等）未驗證。

## Key Evidence
- 趨勢爆發日：14%（181/1251），振幅 1.58x 均值，Vol_ratio 中位數 1.13
- 未觸及日：34%（427/1251），HL_ratio 中位數 0.72
- OR 開盤區間無法預判趨勢爆發（三組 OR_pct 幾乎相同）
- 核心問題：EMA(20) 反應慢導致系統性低估

## Why Inconclusive
分佈分析提供了有價值的洞察（爆發日放量、未觸及日市場不配合），但四個改善方向（盤中放量偵測、觀察期、動態更新、ATR trailing）均未進入回測驗證。需先完成基本 SatZone 策略驗收後再處理。

## Derived Hypotheses
- EMA 更新機制改良（用原始量而非膨脹量）
- 盤中動態 SatZone 目標調整

## Links
- Proposal：research/active/H031-estimate-hl-breakout-days/proposal.md
- Spec：research/active/H031-estimate-hl-breakout-days/spec.md
- Tasks：research/active/H031-estimate-hl-breakout-days/tasks.md
