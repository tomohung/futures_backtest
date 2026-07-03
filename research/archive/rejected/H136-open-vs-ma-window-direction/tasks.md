# Tasks: 開盤相對均線位置 → 早盤時間窗方向

## Phase 1: Distribution Research

- [x] 建 daily MA 序列（5/10/20/60/120/240 日，adj_close，shift 1 日避前瞻）
- [x] 取每日 08:45 開盤價 + 三窗（A/B/C）的窗開盤、窗收盤，算窗內報酬（點數 & %）
- [x] 計算**無條件基準**：三窗各自收紅機率、平均/中位報酬（含 N）
- [x] 逐條 MA × 逐窗：開盤在 MA 上/下 的收紅機率、EV，附二項信賴區間與 N
- [x] 淨效果：扣除當期無條件漂移後，條件 EV 是否仍偏離 0
- [x] 池化穩健性抽查：挑分辨力最強的 MA×窗，看逐年方向是否一致（不翻號）→ 翻號，rejected
- [x] 視覺化：MA×窗 的收紅機率熱力圖（vs baseline 差值）→ results/heatmap_dred.png

---
### GATE
**問題：分佈結果是否支持進入回測？**

- 樣本數是否足夠？（最低門檻：每個 MA×窗×方向 cell ≥ 200 筆交易日）
- 是否有任一 MA×窗 的條件收紅機率穩定超出 baseline ≥ 3pp，且逐年不翻號？
- 淨效果（扣漂移後）是否仍在？EV 是否為正？
- 是否有明顯 data snooping（測 6 MA × 3 窗 = 18 組，需控制多重比較）？

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest
（通過 GATE 後再展開）

- [ ] 定義進出場規則（依最強 cell：開盤相對某 MA → 該窗方向持有）
- [ ] 設定回測參數（手續費、滑價）
- [ ] in-sample 回測
- [ ] out-of-sample 驗證
- [ ] Walk-forward + 逐年 / regime 分層
- [ ] 參數敏感度（換 MA 週期、換窗）
