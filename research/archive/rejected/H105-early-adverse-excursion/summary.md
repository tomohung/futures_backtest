# Archive: H105 — 早期套牢 → 結局（Early Adverse Excursion）

## Status
Rejected（描述性為真但不可行動；Phase 1 即否，未進 Phase 2）

## Summary
源自 backlog DH-03（Angell 心法「逆向交易後幾乎不會變好」）。零策略：08:45 開盤進場、多/空各自，
量「進場後 X 分鐘內套牢深度 Y（早期 MAE÷ATR）是否預測結局」。描述性強單調（早期套牢深→最終差），
但 proposal 預設的 tautology guard 顯示**前瞻剩餘期望平坦（≈0）**——訊號是路徑自相關廢話，砍早期套牢
無可行動 edge。GATE 直接 Archive。

## Key Evidence（N=1305 交易日，2021–2026）
- **描述性**（最終報酬 vs Y）：強單調。LONG X=30 spearman −0.36、q0 勝率 72% → q4 勝率 30%；SHORT 幾乎同（−0.34、28%）。
- **前瞻性**（剩餘報酬 第X分→收 vs Y）：**spearman ≈ 0**（LONG −0.02、SHORT +0.00，各 X 皆然），各 Y 桶剩餘均 ~0（±0.07%）。
- **Tautology guard**（控制第10分當下水位）：深 vs 淺套牢的剩餘差僅 ~0.04%（≈1 SE）**且多空方向相反**（long 深略差、short 深略好）→ 無一致額外資訊。

## Why Rejected
Angell「逆向後不變好」在台指日盤**描述性成立但不可行動**：第 X 分已套牢者最終確實差，但那是因為
「已經」浮虧（markX 已負），不是「接下來」更糟——剩餘期望 ~0。砍掉只鎖定當下虧損、不改變期望，
無正 edge；連「深套牢後反彈」的均值回歸也沒有（剩餘 ~0）。正中 proposal 無效條件。

## Derived Hypotheses
- **盤中無記憶（附帶確立）**：第 X 分到收盤的剩餘走勢對「之前早期 excursion 路徑」幾乎零記憶（剩餘期望平坦）。
  可當**所有日內擇時假設的 efficient-walk baseline 對照**——若某擇時宣稱用早期走勢預測剩餘，須先勝過此零記憶基準。
- **方法論示範（重要）**：描述性 spearman −0.36 看似強訊號、前瞻 ≈0——**excursion 類研究必做前瞻/tautology guard**，
  否則路徑自相關會被誤當 edge 帶進 Phase 2 才爆。此為 H104 之外的另一過擬合來源範例。

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md（GATE：Archive Rejected）
- 腳本：explore.py；圖 results/h105_distribution.png
