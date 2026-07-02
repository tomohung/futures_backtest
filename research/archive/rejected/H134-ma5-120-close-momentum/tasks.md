# Tasks: 5分K 120MA vs 收盤價 對後續 30 分鐘的預測力

## Phase 1: Distribution Research

- [x] 從 ohlcv_1m 建日盤 5 分 bar 連續序列，計算 120MA 值與扣抵值
- [x] 定義四個檢查時點 9:00/9:15/9:30/9:45 的訊號（均線值法 & 扣抵法，各含多/空/無訊號）
- [x] 計算 outcome：sign(price(T+30) − price(T)) 方向、以及順訊號帶符號報酬（點數 & %）
- [x] 統計方向命中率（4 時點 × 2 訊號定義）與樣本數
- [x] **虛無分佈對照**：分離度（drift-immune）+ 2000 次 IID 洗牌 null p 值
- [x] 順訊號報酬分佈基本統計（EV pts / EV% / median）
- [x] **穩健性切分**：逐年 + 波動 tertile（事後 vs 盤前可知）→ 揭露 look-ahead 假象
- [x] 視覺化：以表格呈現（分離度 / 命中 / EV / p）

---
### GATE
**問題：分佈結果是否支持進入回測？**

- 每個時點 × 訊號定義的樣本數 ≥ 500 筆？
- 命中率相對 base rate 淨提升是否顯著（且非池化假象）？
- 順訊號報酬 EV 是否 > 0？
- 是否有明顯 data snooping / regime confound 疑慮？

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest

- [ ] 定義進出場規則（訊號時點進場、+30 分鐘或觸價出場）
- [ ] 設定回測參數（手續費、滑價）
- [ ] 執行 in-sample 回測
- [ ] 執行 out-of-sample 驗證
- [ ] Walk-forward 測試
- [ ] 參數敏感度分析（檢查時點、持有時長、訊號定義）
