# Archive: 序數 vs 前置延伸 — L2 拉回續攻 edge 的真正 driver

## Status
Rejected

## Summary
H126 發現「同向第 2 次（含以上）L2 拉回續攻」在 09:30–11:30 的深目標 reach 約為第一次的 2 倍。
H127 檢驗這個 edge 的真正 driver 是「序數（第幾次）」還是「進場時已實現的同向延伸（趨勢成熟度）」——
兩者在多次日近乎共線。結論：**driver 是序數本身，前置延伸不是**。H127 假設（前置延伸是 driver）被否證，
反而乾淨地確認了 H126。

## Key Evidence
（edge 窗 entry∈[09:30,11:30]，N=1086；reach = L4/L5 %）
- **控制前置延伸後序數完全 survive**：prior_swing <L3 與 ≥L3 兩層，2nd+ 的 L4 都 ~40% ≈ 2× 同層 1st。
- **反向控制**：1st 不論 prior L2–L3 / L3–1.0 / ≥1.0，L4 都卡 ~25% → 延伸給不出 edge。
- **極端桶 prior≥1.0 拆序數**：高 reach（68/45/34%）全由 55% 的 2nd+ 成員撐起；同桶 1st 仍只有 25% L4。
- **2nd+ 內前置延伸幾無影響**：prior<L3（40.4% L4）≈ prior≥L3（39.7% L4）。
- logistic 唯一保留意見：`entry_min` 是最強負向因子（比序數更會殺 edge），與 H126 ≥11:30 死區一致。

## Why Rejected
H127 主張「前置延伸（趨勢成熟）才是 driver、序數只是代理」。三組獨立檢驗一致反證：序數效應在固定
prior 分層內完全保留，而 prior 在固定序數內幾無主效果；單變量上「延伸越深 reach 越高」的假象來自極端桶
內 2nd+ 成員的集中。因此前置延伸非 driver，假設不成立。

## Implication（對 H126 Phase 2）
- 進場條件**直接用離散「2nd+ 同向 L2 拉回」**即可，無需加前置延伸門檻（已證無增量、且會誤收 1st-已延伸的無效樣本）。
- 保留 **entry∈[09:30,11:30]** 時間閘（最強因子）。
- sizing 線索（待 Phase 2 驗、N 薄）：2nd+ 且 prior_swing≥1.0 的深 reach 子集（L4 62% / L5 45%，N=29）。

## Derived Hypotheses
- **H128**：2nd+ 的 MAE 偏大 → 測「更寬停損 + L4/L5 目標」是否比沿用 l2_pullback 緊停損更適配續攻。
- **H129**：序數「資訊」是否隨次數遞增（3rd > 2nd）？以「同向 reclaim 次數」為連續 dose 測 dose-response（N 薄）。
- 「2nd+ 訊號的時間半衰期」：10:00 vs 11:00 進場的 reach 衰減曲線（entry_min 為最強負向因子）。

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- Script：explore.py　Data：results/entries_prior.csv　Fig：results/ordinal_vs_prior.png
