# Tasks: Reversal 方向濾網替換（納入夜盤）

## Phase 1: Distribution Research（方向判定差異與覆蓋率）

- [x] 在 runner 載入新濾網欄位：MA5m_240 / MA5m_240_Prev（連續日+夜盤 5m），MACD_1h / Signal_1h（1H 12/26/9，連續日+夜盤），皆 shift 避免未來函數
- [x] 對每個交易日，計算 base / A / B / C 在進場時間窗（09:10–10:05）內各自的方向判定（bullish/bearish/無方向）
- [x] 統計四者的方向一致率、歧異率；A 與 B 的同向比例（情境 C 的覆蓋率）
- [x] 統計各濾網會「允許交易」的交易日數（樣本量預估）

---
### GATE
**問題：方向判定差異是否值得進入回測？**

- 新濾網與 base 的方向歧異率是否夠高（> 15%）→ 有實質差異才值得測
- 情境 C（A∩B 同向）允許交易的天數是否 ≥ 80（避免樣本不足）
- 是否有明顯 data snooping 疑慮？（本實驗只換濾網、不調其他參數 → 低）

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest（四變體並排）

- [x] 進出場規則維持 base 不變，唯一變數為方向濾網（base / A / B / C）
- [x] 設定回測參數（手續費、滑價）與 base 回測一致
- [x] in-sample 回測：四變體並排輸出 損益% / Sharpe / PF / 勝率 / 最大連敗 / 最大回撤 / 交易筆數
- [x] out-of-sample 驗證（時間分割，例如前 70% / 後 30%）
- [x] Walk-forward / 年度分段穩健度檢查
- [x] Verdict：對照 Invalidation Condition 判定各情境是否優於 base

---

## 變體定義（唯一變數＝方向濾網）

| 變體 | 方向濾網 | 資料 |
|------|----------|------|
| base | 5m 120MA 斜率 | 只日盤 |
| A | 5m 240MA 斜率（=1H 20MA） | 連續日+夜盤 |
| B | 1H MACD：MACD 線 vs Signal 線（12/26/9） | 連續日+夜盤 |
| C | A 且 B 同向 | 連續日+夜盤 |
