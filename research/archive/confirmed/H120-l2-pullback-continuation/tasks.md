# Tasks: L2 趨勢確立後拉回續攻

## Phase 1: Distribution Research

- [x] 實作 L2 門檻 ZigZag setup 偵測（重用 `swing_legs.zigzag_legs`，門檻=L2_COEF×EMA20）
- [x] 定義 setup：開盤後第一個 ≥L2 方向段確立趨勢 + 隨後拉回（<L2）；記前波極值、拉回極值、起點 pivot
- [x] 標出三種 trigger 觸發時點（A 5MA站回 / B 突破前波極值+buffer / C 5MA站回+確認）+ N(null 確立即進)
- [x] 計算 base rate：50% 無條件 + 達 L2→L3 條件 baseline（tautology guard：N 對照組）
- [x] 統計各 trigger 的條件續攻 L3 勝率、L4/L5 延伸率、勝率/EV/avgR
- [x] 從真實 trigger 點重算 MAE 分佈（含結構停損兩版：拉回極值 / 起點 pivot）
- [x] 分層：進場時間 9:30前 / 9:30–11:30 / 11:30後
- [x] 視覺化：拉回深度 + MAE 分佈（dist_pb_mae.png）

> 結果見 `results/distribution.md`。核心：A(5MA站回) ≫ N(確立即進) ≫ B(突破)；雙停損皆正 EV；早盤勝率最高。

---
### GATE
**問題：分佈結果是否支持進入回測？**

- 樣本數是否足夠？（最低門檻：**150 筆**合格 setup，可分層）
- 條件續攻 L3 機率是否**顯著高於 50% 無條件 base rate**（差距 ≥ 5pp 且超出抽樣噪音）？
- 至少一種 trigger 在保住多數贏家的結構停損下 R:R 期望 > 0？
- 是否有 data snooping / regime confound 疑慮？

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest

- [x] 選定最佳 trigger（A 5MA站回）+ 結構停損版本（alpha=0.75 寬停）
- [x] 定義進出場規則（出場：L3 固定 + trail 0.5 抱尾變體）
- [x] 設定回測參數（成本 3pt round-trip）
- [x] 執行 in-sample 回測
- [x] 執行 out-of-sample 驗證（OOS 不衰退，Sharpe 0.235→0.331）
- [x] Walk-forward 測試（逐年全正，alpha* 收斂 0.75）
- [x] 參數敏感度分析（停損 alpha、成本、時間窗、出場模式）
- [x] 評估連敗長度 / drawdown（maxDD −2%、最大連敗 ≤5）

> 結果見 `results/backtest.md`。Verdict: **Confirmed**（待使用者最終確認）。
