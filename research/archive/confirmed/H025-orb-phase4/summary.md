# Archive: ORB Phase 4 自適應 TP 優化

## Status
Confirmed

## Summary
以 OR 寬度（OR_high - OR_low）乘以倍數作為動態 TP，取代固定百分比 TP。Phase 4 Hybrid 策略 2021-2026 累計 +5,653 pts，優於 Phase 2 的 +4,632 pts。ORBPhase4HybridStrategy 成為後續迭代基礎。

## Key Evidence
- OR 寬度與日盤波動相關性最強，是最佳 TP 代理
- Phase 4 Hybrid 累計 +5,653 pts > Phase 2 +4,632 pts（+22%）
- 自適應 TP 解決了固定 TP 在低波動日幾乎不被觸發的問題

## Why Confirmed
動態 TP 顯著改善策略表現，ORBPhase4HybridStrategy 成為 ORBLong 系列的核心實作。

## Derived Hypotheses
- H026：Long-only + ADX 濾網
- H011：Phase 6 機制濾網（已 rejected）

## Links
- Proposal：research/active/H025-orb-phase4/proposal.md
- Spec：research/active/H025-orb-phase4/spec.md
- Tasks：research/active/H025-orb-phase4/tasks.md
