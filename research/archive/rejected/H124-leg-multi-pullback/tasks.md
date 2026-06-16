# Tasks: 同 leg 多次拉回進場（被濾掉的淺拉回不佔名額）

## Phase 1: Distribution Research

- [x] 複用 **causal** detect 邏輯（非 leg-bounded），實作 A(baseline) / B(淺不燒名額) / C(同相位全取)
- [x] 全窗跑出三組進場清單，標記「新增筆」（B/C 相對 A extra）
- [x] 統計：A=1262 / B=1566 / C=4997；B extra N=304 分布 293 天
- [x] 用 simulate() 算每筆 R，比較 extra avgR/勝率 vs baseline（B extra avgR −0.03 < A 0.02）
- [x] 確認非單日 snooping（extra 跨 293 天）；2026-06-11 sanity：causal A 該日 3 筆全贏，無漏單

---
### GATE
**問題：分佈結果是否支持進入回測？**

- B 新增訊號樣本數 ≥ 30？
- 新增筆 avgR > 0 且勝率不顯著低於 baseline？
- 改善跨多日分佈，無單日 data snooping？

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest

- [ ] 以 B（必要時含 C）跑完整回測，沿用 H120 的 IS/OOS 切分
- [ ] 比較 A vs B 的 PF、期望 R、勝率、最大連敗、maxDD（含心理資本面）
- [ ] Out-of-sample 驗證（注意 OOS≡高波 regime confound）
- [ ] 敏感度：MIN_DEPTH_FRAC 不變下，「繼續找下一拉回」是否對 PB_FLOOR / 是否含 overshoot guard 穩健
- [ ] 結論：是否值得改動 h120.py 真相源（Confirmed 才同步 chart-ui + backtest 兩處）
