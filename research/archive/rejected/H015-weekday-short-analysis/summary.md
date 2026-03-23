# Archive: 星期效應分析 — 做空交易可行性

## Status
Rejected

## Summary
分析 EstHL 和 ORBLong 做空交易的星期效應，測試「做多不利的週四/五是否做空有利」的假設。結果顯示週四/五兩方都不利，做空整體表現遠不如做多，維持 long-only 配置。

## Key Evidence
- **核心假設被否定**：週四/五不是「空方日」，而是兩方都不利的日子
- ORBLong 做空整體：WR 46.2%, Avg +4.7 pts（vs 做多 WR 55.3%, Avg +19.2）
- EstHL 做空整體：WR 41.1%, Avg +1.5 pts（vs 做多 WR 52.8%, Avg +16.8）
- 週四做空：ORBLong WR 44.4% Avg -0.5；EstHL WR 36.0% Avg -13.0
- 週五做空：ORBLong WR 44.0% Avg -5.3；EstHL WR 38.7% Avg -2.1
- 做空唯一亮點 ORBLong Mon-Wed：165 筆 WR 47.3% Avg +9.2，但 5 年僅 +1,517 pts（年均 +300），邊際效益不足

## Why Rejected
做空勝率低了 9-12%，平均損益低了 3-4 倍。週四/五兩方都不利，可能原因是結算前不確定性與週末前投機者平倉造成的無方向性波動。做空增加的複雜度與心理壓力不值得邊際效益。

## Derived Hypotheses
- 確認 ORBLong 維持 `thu_or_pct_min=0.7` 條件濾網
- 確認 EstHL 維持 `skip_thursday=True, skip_friday=True`
- 兩策略均維持 long-only

## Links
- Proposal: specs/strategies/2026-03-15-weekday-short-analysis.md
