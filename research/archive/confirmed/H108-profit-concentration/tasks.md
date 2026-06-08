# Tasks: 利潤集中度（Profit Concentration / Pareto）

## Phase 1: Distribution Research（分佈結構診斷）

### 資料準備
- [ ] 載入 EstHL/Reversal trade log（output/s001_esthl_2021-01-01.csv、s002_reversal_2021-01-01.csv），損益% + 點數
- [ ] 算台指日盤市場日報酬（open→close % / |move|）對齊交易日

### A. 策略自身報酬集中度
- [x] Pareto/Gini/top-K share/最大贏家比/skew → EstHL Gini 0.41、Reversal 0.51
- [x] 剔每年 top-N → 剔 top-5/年：EstHL 剩 8%、Reversal 轉負（剔 top-3 即負）
- [x] EstHL vs Reversal 對比 → 反向：Reversal 更集中（子假設錯）

### B. 對市場大動日的依賴
- [x] 策略 PnL vs 市場 |move| 相關 + 四分位 → EstHL corr +0.566、靜日(Q0/Q1)淨虧
- [x] 剔每年市場 |move| top-N 大動日 → EstHL 仍保 94%（依賴廣義高波動非極端日）
- [x] 高/低波動日期望對比 → EstHL Q3 +0.55%/86% vs Q0 −0.04%/44%

### benchmark 對照（防機械廢話）
- [x] 同 N/μ/σ 常態模擬 top5 share → 真實 16%/12% 超模擬 13%/6%，p=0.99/1.00 ✔
- [x] 市場 buy-hold 自身集中度 → 剔每年 top-5 漲日後 −7.1%→−61.8%（市場本身超集中）
- [x] 視覺化：results/h108_distribution.png（Pareto 曲線 + PnL vs 市場|move| 散點）

---
### GATE
**問題：分佈結果是否支持進入 Phase 2（出場效率研究）？**

- 集中度是否**顯著超 benchmark**（非機械效應）？剔 top-5/年是否使 EstHL 接近轉負？
- 趨勢型是否比均值回歸型更集中（方向符合）？對市場大動日依賴是否明確？
- 樣本：EstHL N=170、Reversal N=508，逐年 N 是否夠分（每年 top-N 剔除有意義）？
- 是否有 data snooping（N 選擇、波動分桶）？

**決定：** [ ] 繼續 Phase 2（出場效率 / 讓獲利奔跑）　[ ] 直接 Archive（含「edge 廣而穩健」之結論）　[ ] 修改假設

---

## Phase 2: Backtest（出場效率，GATE 通過才做）

- [ ] 重跑回測產每筆 MFE/MAE；算 big winner 的 MFE 捕捉率（realized / MFE）
- [ ] 測「趨勢日放寬 trail / 提高停利」是否提升大贏家捕捉、年度淨利（含 trail 回吐成本，[[feedback_trail_giveback_is_scaleout_cost]]）
- [ ] in-sample / out-of-sample / walk-forward；含連敗/DD
- [ ] 脆弱性評估：edge 對「少數事件」依賴度 → 部位/風險建議
