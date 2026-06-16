# Tasks: Bull-Trap OR Break

## Phase 1: Distribution Research

- [x] 計算每日 session_open、昨日/前日日盤 VWAP，標記「成本之上(AND)」日
- [x] 計算每日 OR(08:45–08:57) high/low、EmaHL(EMA20 日盤振幅)
- [x] 偵測 08:58–09:15 內首次「close < OR low」事件，標記事件日 + 事件時間
- [x] 計算事件日自當日最高點往下的 L1–L5 達成 flag（running-high anchored，H092 定義）+ 首次達成時間
- [x] 建立對照組：(a) 全體向下日無條件 reach；(b) 早盤破 OR low 但開盤不在成本之上
- [x] 對比正確虛無分佈（IID 洗牌 / 前瞻條件期望），檢定 L3/4/5 達成率增量
- [x] 統計事件日年度/regime 分佈（標註高波 confound）
- [x] 視覺化 L1–L5 達成率長條（事件 vs 兩組對照）

---
### GATE
**問題：分佈結果是否支持進入回測？**

- 事件日樣本數是否 ≥ 30？（最低門檻；< 30 → Inconclusive）
- 事件日 L3/L4/L5 達成率是否顯著高於虛無分佈？
- 「站穩成本」相較「不站穩成本」破底日是否有增量（VWAP 條件有無貢獻）？
- 事件是否過度集中單一 regime（高波 confound）？

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest

- [ ] 定義進出場規則（破 OR low 進空、ladder 階梯出場）
- [ ] 設定回測參數（手續費、滑價）
- [ ] 執行 in-sample 回測
- [ ] 執行 out-of-sample 驗證
- [ ] Walk-forward 測試
- [ ] 參數敏感度分析（m 倍數、進場窗、VWAP 天數）
