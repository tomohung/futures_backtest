# Archive: 星期效應分析與 Weekday Filter

## Status
Confirmed

## Summary
分析 ORBLong 與 EstHL 各星期績效，確認週四對 ORBLong 是致命傷（PF 0.87），週五對 EstHL 是致命傷（PF 0.97）。結論已整合至現行策略參數。

## Key Evidence
- ORBLong 週四：PF 0.87、勝率 43%（唯一虧損日）
- EstHL 週五：PF 0.97、勝率 37%
- ORBLong 維持 `thu_or_pct_min=0.7`（週四需 OR% 夠大才進場）
- EstHL 維持 `skip_thursday=True, skip_friday=True`

## Why Confirmed
星期效應穩定且顯著，weekday filter 已整合至實盤策略參數，直接改善了兩策略的 Sharpe ratio。

## Derived Hypotheses
- H015：Weekday Short Analysis（已 rejected，確認做空無法靠 weekday 修復）

## Links
- Proposal：research/active/H029-weekday-effect/proposal.md
- Spec：research/active/H029-weekday-effect/spec.md
- Tasks：research/active/H029-weekday-effect/tasks.md
