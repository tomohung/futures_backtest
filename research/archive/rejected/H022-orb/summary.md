# Archive: Opening Range Breakout 基礎策略

## Status
Rejected

## Summary
以開盤區間高低點定義突破方向，配合固定停損/停利/追蹤停損的裸 ORB 策略。經 1,088 組全參數掃描，確認勝率與盈虧比存在結構性取捨，無法同時達標。

## Key Evidence
- 全參數掃描 1,088 組（2023-2025）
- 最佳組合：勝率 44.9%、PF 1.02、期望值 +1.0 pts/筆
- Pareto 前緣顯示勝率與盈虧比為結構性取捨，非參數問題

## Why Rejected
裸 ORB 的 edge 不足。問題出在策略結構本身（無訊號品質過濾），不是參數最佳化能解決的。需要加入過濾器（OR%、weekday 等）才有機會產生正期望值。

## Derived Hypotheses
- H023：ORB + 過濾器（OR% 濾網等訊號品質改善）
- H024：ORB Phase 2 全參數回測
- H025：ORB Phase 4 Hybrid 策略
- H026：ORB Long-only 方向
- H027：ORB Exit Crossover 出場改良
- H028：Breakout Timing 突破時機研究
- H029：Weekday Effect 星期效應

## Links
- Proposal：research/active/H022-orb/proposal.md
- Spec：research/active/H022-orb/spec.md
- Tasks：research/active/H022-orb/tasks.md
