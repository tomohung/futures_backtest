# Tasks: Weak-Open OR Break Short

## Phase 1: Distribution Research

- [x] 以嚴格弱勢定義（open < VWAP_t1 且 < VWAP_t2）重切事件日，計樣本數
- [x] 計算嚴格弱勢組的 L1–L5 下行 reach 達成率 + 條件續走 P(L_{k+1}|L_k)
- [x] 對照：全體 baseline、H122 寬鬆 B 組、H122 EVENT（成本上）並列比較
- [x] 虛無檢定（從破 OR low 池隨機抽同樣本數），確認顯著偏深
- [x] 進場可行性：破 OR low 首次觸發時點 vs 各 ladder 階首達成時點（是否來得及進場）
- [x] 年度/regime 分佈與跨年穩定性檢查

---
### GATE
**問題：分佈結果是否支持進入回測？**

- 事件樣本數是否 ≥ 50？
- 嚴格弱勢組 L3/L4/L5 是否顯著 > baseline / 虛無分佈，且 ≥ H122 寬鬆 B 組？
- 破 OR low 進場時點是否仍留有可捕捉的下行空間（非前瞻陷阱）？
- 是否過度集中單一 regime？

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest

- [x] 定義進出場：破 OR low 進空、停損（OR high / 成本帶 / EmaHL 倍數）、ladder 階梯出場
- [x] 設定回測參數（手續費、滑價）
- [x] in-sample 回測：比較 L2 / L3 / L4 不同出場階的淨 P&L / PF / 連敗 / maxDD
- [x] out-of-sample 驗證
- [x] Walk-forward 測試
- [x] 參數敏感度（m 倍數、進場窗、停損距離、VWAP 天數）
