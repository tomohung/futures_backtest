# Tasks: close vs 當日 VWAP 對後續 30 分鐘的預測力

## Phase 1: Distribution Research

- [x] 從 ohlcv_1m 建每日日盤累積 VWAP（typical price 加權、08:45 重置）
- [x] 定義四時點 9:00/9:15/9:30/9:45 訊號 sign(close − VWAP)（含多/空/無訊號）
- [x] 計算 outcome：sign(price(T+H)−price(T)) 方向、順訊號帶符號報酬（點數 & %），H=30 主、15 敏感度
- [x] 統計走多機率 / 分離度 / 命中率 / EV（4 時點）與樣本數
- [x] **虛無分佈對照**：drift-immune 分離度 + 2000 次 IID 洗牌 null p 值
- [x] **穩健性切分**：逐年 + 盤前可知波動 tertile（禁用當日事後波動）
- [x] 與 H134（MA 版）對照

---
### GATE
**問題：分佈結果是否支持進入回測？**

- 每時點樣本數 ≥ 500？
- 分離度顯著為正且 EV>0？
- 是否過逐年 / 盤前可知 regime 三關？（避免 H134 的 look-ahead 假象）

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest

- [ ] 定義進出場規則（VWAP 上/下進場、+H 分鐘或觸價出場）
- [ ] 設定回測參數（手續費、滑價）
- [ ] in-sample / out-of-sample / walk-forward
- [ ] 參數敏感度（時點、horizon）
