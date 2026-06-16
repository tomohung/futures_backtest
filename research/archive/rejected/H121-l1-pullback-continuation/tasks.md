# Tasks: L1 拉回續攻 — 確立門檻從 L2 放寬到 L1

## Phase 1: Distribution Research

- [ ] Fork H120 `validate_causal.py` → `explore.py`，把確立門檻參數化（level ∈ {L1, L2}），
      cross-check：level=L2 重現 H120 causal 數字（防 `em` 前視復發）
- [ ] 定義篩選條件：causal 偵測下「leg 確立於 L1 + 拉回 ≥ 0.05×EMA20 且 < 確立距離 + 站回 5MA」
- [ ] 探索 L1 確立 leg 的樣本數與分佈（vs L2 版的訊號量差異）
- [ ] **條件續攻率**：P(後續摸到 L3 | L1 確立 + 拉回站回 5MA)，逐年 + 多空分開
- [ ] **虛無對照 1（無條件基準）**：P(摸到 L3 | L1 確立)，不論是否拉回站回 → 比較條件機率有無增量
- [ ] **虛無對照 3（IID 洗牌）**：leg 內 bar 洗牌後續攻率，確認非隨機漂移
- [ ] RR / avgR / 負偏態：L1 版 vs L2 版的 per-trade 報酬分佈（重點看負偏態是否收斂）
- [ ] 確立門檻連續掃描 L1→L2，畫 EV/Sharpe/avgR vs 門檻 曲線
- [ ] 視覺化關鍵分佈圖（續攻率、報酬分佈、門檻掃描）

---
### GATE
**問題：分佈結果是否支持進入回測？**

- 樣本數是否足夠？（最低門檻：causal L1 版 ≥ 300 筆，逐年 ≥ 30 筆）
- 條件續攻率是否**顯著高於無條件基準**？（站回訊號要有增量資訊，否則 tautology）
- RR 幾何改善是否真的吃得到？avgR 上升 / 負偏態收斂 / per-trade EV 為正
- 是否有明顯 data snooping 疑慮？（門檻掃描勿挑單點最佳）

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest

- [ ] 定義進出場規則（沿用 H120 規格：站回 5MA 收盤進、stop alpha=0.75、目標 L3、≤12:00、cost 3pt）
- [ ] 設定回測參數（手續費、滑價；對 ≤6pt 成本穩健性）
- [ ] 執行 in-sample 回測（<2025）
- [ ] 執行 out-of-sample 驗證（≥2025；注意 OOS≡高波 regime confound）
- [ ] Walk-forward 測試（確立門檻 + stop alpha）
- [ ] 參數敏感度分析（確立門檻、最小拉回深度、進場時間上限）
- [ ] 與 H120 causal baseline（Sharpe 0.04）並排對照，確認 edge 來自幾何而非勝率
