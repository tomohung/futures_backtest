# Tasks: 淨空開盤裸突破（Clear-Runway Breakout）

## Phase 1: Distribution Research

- [x] 建每日資料集（explore.py → results/h102_daily.csv，N=1312）
- [x] VWAP 成本對齊 `key_prices.py`、ladder 距離對齊 H095（EMA20）
- [x] 分佈 1：reach 達標按 clear_norm 分層 → finite 區單調成立 ✅
- [x] 分佈 2：反咬率對比（淨空降 5–9pp，但絕對仍高 56–68%）
- [x] 分佈 3：開盤三態 → 發現 gap-up fade / gap-down run 不對稱 ⚠️
- [ ] 旁路：NVF 分佈（延後，併入 Phase 2）
- [ ] 視覺化：clear_norm × reach 圖（延後，數字表已足夠 GATE 決策）

---
### GATE
**問題：分佈結果是否支持進入回測？**

- 樣本數是否足夠？（最低門檻：**每個淨空分層 ≥ 30 個交易日**，總淨空日 ≥ 100）
- clear_norm 與 reach 達標率是否呈單調關係、且淨空日 L3 達標明顯優於 baseline？
- 反咬率是否未惡化？
- 是否有明顯 data snooping 疑慮（門檻 L4/L5 是先驗選的，非事後挑）？

**決定：** [x] **修改假設 → 衍生 H103（gap-down 折價回補做多）**　[ ] 繼續 Phase 2　[ ] 直接 Archive
（原「裸突破」框架未被支持；唯一穩健訊號為 mean-reversion 多單，已轉 H103。H102 待歸檔 inconclusive/rejected。）

---

## Phase 2: Backtest（需先過 GATE）

- [ ] 定義進出場：只做淨空那一邊（上方淨空→上破多 / 下方淨空→下破空），出場沿用 reach ladder / EstHL exit
- [ ] 設定回測參數（手續費、滑價）
- [ ] in-sample 回測：淨空裸突破 vs (a) EstHL 全濾網 baseline (b) 全日無濾網突破 baseline
- [ ] out-of-sample 驗證
- [ ] Walk-forward 測試
- [ ] 門檻（L4/L5）敏感度分析
- [ ] 連敗長度 / drawdown 檢視（依 feedback_filter_eval_includes_streaks）
