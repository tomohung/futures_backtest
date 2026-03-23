# Archive: ORB Phase 2 全參數掃描（含 Trend MA Filter）

## Status
Confirmed

## Summary
固定 Trend MA(10)，對 5 個基礎參數進行 896 組全掃描。找到最佳組合累計 +4,632 pts（2021-2026），但發現固定 % TP 的結構性問題：2021/2022 強制出場率僅 27%，TP 幾乎沒被打到。

## Key Evidence
- 896 組參數掃描，最佳組合：PF 1.22（2024）、勝率 56.8%（2025）
- 累計 +4,632 pts（2021-2026）
- 強制出場率僅 27%（2021/2022），暴露固定 TP 的結構問題

## Why Confirmed
確認了 ORB + Trend MA 的參數空間，找到穩定正期望值組合。同時發現固定 TP 的瓶頸，推動 Phase 4 自適應 TP 改良。

## Derived Hypotheses
- H025：Phase 4 自適應 TP（OR 寬度 TP）

## Links
- Proposal：research/active/H024-orb-phase2/proposal.md
- Spec：research/active/H024-orb-phase2/spec.md
- Tasks：research/active/H024-orb-phase2/tasks.md
