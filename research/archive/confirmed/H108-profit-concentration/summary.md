# Archive: H108 — 利潤集中度（Profit Concentration / Pareto）

## Status
Confirmed（分佈診斷：報酬集中度真實且超 benchmark；非可交易策略，產出為行動意涵 + 衍生假設）

## Summary
源自 backlog DH-01（Angell「大行情日集中利潤、讓獲利奔跑」）。診斷 EstHL/Reversal 報酬集中度與對市場
大動日依賴。結論：年度淨利高度集中於少數大贏家、且超同 μ/σ 常態 benchmark（非機械效應）→ 集中論
成立。最大行動發現是 EstHL 為「波動日收割者」、靜日淨虧 → 衍生靜日濾網假設。

## Key Evidence（EstHL N=170 +27%、Reversal N=508 +10%，2021–2026）
- **集中度**：剔每年 top-5 獲利交易 → EstHL 剩 8%、Reversal 轉負（剔 top-3/年即負）；Gini(gross) EstHL 0.41 / Reversal 0.51。
- **benchmark 守門**：真實 top5 gross share 16%/12% 顯著超同 N/μ/σ 常態模擬 13%/6%，p=0.99/1.00 → 真實肥尾。
- **子假設反向**：Reversal 比 EstHL 更集中（低勝率 45% 靠少數大贏家）→ 集中度由勝率/賠率輪廓決定，非趨勢屬性。
- **市場依賴**：EstHL corr(|move|,PnL)=+0.566；Q3 大動日 +0.55%/勝率86%，Q0/Q1 靜日淨虧（−0.04%/44%）。剔極端 top-3/5 日仍保 94% → 依賴廣義高波動 regime 非少數極端日。
- 市場 buy-hold 自身超集中：日盤報酬和 −7.1%，剔每年 top-5 漲日 → −61.8%。

## Why Confirmed
集中度真實且超 benchmark（p≥0.99）、剔 top-5/年 edge 崩 → DH-01 集中論成立。診斷類，無需 Phase 2 即確認分佈事實；可交易產出在衍生假設。

## Derived Hypotheses
- **H109 EstHL 靜日濾網（已 rejected）**：測盤前波動預測子濾殘留靜日 → 否決。盤前能測振幅但測不準 EstHL 獲利（要趨勢性非振幅）、無增量於既有 NVF [[feedback_night_vol_as_hard_rule]]、撈不回淨負桶。H108「靜日=虧」是 ex-post，ex-ante 不可約。**正面確認既有 NVF 已良好調校。**
- **讓獲利奔跑（H108 Phase 2 未做，留待）**：top-5/年 carry 92% 淨利 → 量大贏家 MFE 捕捉率、測 Q3 放寬 trail（[[feedback_trail_giveback_is_scaleout_cost]]）。
- **Reversal 脆弱性警告**：剔 top-3/年即轉負、Gini 0.51 → 樂透型 edge、過擬合/部位風險須正視。
- **方法論**：評估策略脆弱性看 Gini/剔top-N 而非策略類型；benchmark 模擬區分真集中 vs 機械效應。

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md（GATE：進入 Phase 2 / 衍生）
- 腳本：explore.py；圖 results/h108_distribution.png；trade log：output/s001_esthl_2021-01-01.csv、s002_reversal_2021-01-01.csv
