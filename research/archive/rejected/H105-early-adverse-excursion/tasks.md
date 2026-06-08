# Tasks: 早期套牢 → 結局（Early Adverse Excursion）

## Phase 1: Distribution Research（零策略現象）

### 資料準備
- [x] 取每交易日 08:45 進場價、各分鐘 high/low、13:45 收盤（N=1305）
- [x] 前 10 日日盤 range 均值（ATR，shift）波動正規化
- [x] 早期窗 X∈{5,10,15,30}；早期 MAE÷ATR = Y

### 描述性：最終結局 vs 早期套牢
- [x] **多單**：Y 越深最終越差，X=30 spearman −0.36、q4 勝率 30%
- [x] **空單**：獨立實測，幾乎一樣（spearman −0.34、q4 勝率 28%）
- [x] 早期套牢 vs 早期浮盈最終對比 → 強單調（但見前瞻）

### 前瞻性：剩餘報酬 vs 早期套牢（tautology guard，判斷依據）
- [x] X→收盤剩餘報酬按 Y 分桶 → **spearman(Y,剩餘)≈0（±0.03），完全平坦**
- [x] 前瞻剩餘期望非負、不低於浮盈組 → **無效條件成立**
- [x] 控制當下水位後 MAE 額外資訊 ~0.04%（1 SE）且多空矛盾 → 無

### 視覺化
- [x] results/h105_distribution.png（Y 十分位 × 最終 vs 剩餘，多/空並列）

---
### GATE
**問題：分佈結果是否支持進入回測？**

- 樣本數是否足夠？（08:45 進場每日一筆，~1300 日；分桶後每桶 ≥ 100）
- 描述性是否單調？**前瞻剩餘期望**是否在早期套牢組為負/顯著較低？（後者為硬門檻）
- 多空是否至少一側穩健？是否有 data snooping（X、N、分桶數選擇）？
- tautology guard 是否通過（MAE 深度帶額外資訊，非僅路徑自相關）？

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest（GATE 通過才做）

- [ ] 定義「早期套牢就認賠 / 時間停損」規則（X 分鐘、Y 門檻）
- [ ] 移植到 EstHL / Reversal 真實 trade log：加此出場濾網前後對比
- [ ] 評估含連敗長度 / drawdown（依 `[[feedback_filter_eval_includes_streaks]]`，非只看 PF）
- [ ] in-sample / out-of-sample / walk-forward
- [ ] 參數敏感度（X、Y 門檻）
