# Tasks: Reversal Exit Leakage

## Phase 1: Distribution Research

- [ ] 修改回測以記錄每筆交易的出場原因（SL / SatZone / Trail / Force）
- [ ] 各出場類型的交易次數、勝率、平均 PnL 分佈
- [ ] SL 出場交易的「假性止損」分析：止損後 N 根 bar 內，價格是否回到原方向？
- [ ] Trailing stop 出場交易的「殘餘空間」分析：出場後 MFE 還有多少？
- [ ] SL 距離（sl_ema_fraction）敏感度：0.2, 0.25, 0.3, 0.35 的影響

---
### GATE
**問題：出場邏輯是否是 edge leakage 的主要來源？**

- 是否有出場類型的勝率顯著低於整體？
- SL 假性止損比例是否 > 15%？
- 調整出場參數是否能改善 in-sample 績效 > 10%？

**決定：** [ ] 繼續 Phase 2（出場優化回測）　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest

- [ ] 調整 SL 距離的 ablation 回測
- [ ] Trailing stop 參數調整（pivot window、啟動時間）
- [ ] Out-of-sample 驗證
- [ ] Walk-forward 測試
