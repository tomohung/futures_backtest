# Tasks: Reversal BB Touch + Structural Support Confluence

## Phase 1: Distribution Research

- [x] ~~(v1) 歷史 30 日 S/R confluence — 無效，見 results/distribution_v1.md~~
- [ ] 定義 intraday level retest：BB touch 前，同價位 ± tolerance 被測試的次數
- [ ] 測試 tolerance 敏感度（10pt, 20pt, 30pt）
- [ ] 測試 retest 次數閾值（N >= 2, 3, 5）
- [ ] 比較有/無 retest 兩組的：勝率、MFE、報酬分佈
- [ ] 分析 retest 次數與成功率的相關性

---
### GATE
**問題：intraday level retest 是否能有效區分 BB touch 訊號品質？**

- 兩組差異是否明確？（勝率差 > 5% 或期望值差 > 20%）
- Retest 組樣本數是否 >= 30？
- 結果對 tolerance / N 參數是否穩健？（至少 2 組參數方向一致）

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest

- [ ] 定義進出場規則（在 Reversal 框架下，用 confluence 作為 CCD bypass 或獨立濾網）
- [ ] 設定回測參數（手續費、滑價）
- [ ] 執行 in-sample 回測
- [ ] 執行 out-of-sample 驗證
- [ ] Walk-forward 測試
- [ ] 參數敏感度分析
