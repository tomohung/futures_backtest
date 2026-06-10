# Proposal: vol_ratio（量比）vs DCI 當「還有沒有空間」調節器

## ID
H115

## Derived From
H114（live-ext-at-ladder）的 backtest 階段 + 收尾設計討論（2026-06-10）。
背景：[[project_dci_verify_handoff]]、[[project_dci_is_extension_signal]]。

## Trading Intuition
S001 / journal_checklist 目前用 **DCI（dci_long）強弱**當「目標積極度」的調節器
（dci≥0.2 強→瞄遠/多抱、<0.2 弱→靜態收 L3）。但 H111/H114 OOS 已證明 **dci_long 對「碰 L3 後還有沒有空間到 L4」的預測會垮**
（IS 強分位 +30% → OOS +7%;各形式水平/斜率/自峰回落/早盤增幅 OOS 全脆）。

同時 H114 發現「碰觸時點」這個耗竭訊號 OOS 穩,且與 SatZone 的判定 **68% 同向**。
而 SatZone 的核心參數 **vol_ratio（今日累計量 / 該時段預期量,est_range = EMA20 × vol_ratio）**
是生產已驗證、且與「時點耗竭」同邏輯的訊號。關鍵對齊：**滿足關卡係數 ≈ vol_ratio**
（vol_ratio=1.0 → 滿足落 L4=0.977;0.71 → 只到 L3;1.22 → 拉到 L5）。

→ 直覺：**「今天放不放量」(vol_ratio) 比 DCI 更能、更穩地分辨「碰 L3 後還有沒有空間」**,
因為它直接量「今日的振幅預算還剩多少」,而非依賴 OOS 易碎的龍頭推力訊號。

## Hypothesis
**在碰到 L3 的當下,當日 vol_ratio（量加權,causal）對 P(L4|L3) 的分辨力，
OOS 上優於且更穩於 dci_long；放量(vol_ratio 高)→續攻機率高、縮量→低。**
主測 L3→L4（樣本足）;L4→L5 探索性。

對照三個 causal 調節器（皆碰 L3 當下可得）：
  (a) **vol_ratio**（提議）　(b) **dci_long**（現行 checklist 軸,用 t_k 可得的盤中/09:15 讀數）
  (c) **碰觸時點**（H114 OOS 穩基準）

## Expected Distribution
- vol_ratio 分帶（放量/中/縮量）對 P(L4|L3) 呈單調分辨,且 **IS/OOS gap 一致**（不像 dci_long OOS 崩）。
- dci_long 分帶 OOS gap 顯著小於 IS（重現 H114 的崩）。
- 開放問題：vol_ratio 與「時點」是否冗餘（兩者皆耗竭邏輯,可能 ~同一件事）——記錄,非否證。

## Invalidation Condition
任一成立即**否證 / 降級**：
1. vol_ratio 分帶的 OOS 分辨 gap **不大於 dci_long 的 OOS gap**（沒贏現行軸 → 不值得換）。
2. vol_ratio 分帶 OOS **也崩**（IS 有、OOS 塌 <~10% 或符號翻轉）→ 跟 DCI 一樣不穩。
3. vol_ratio 對 P(L4|L3) 的分辨,控制「碰觸時點」後**完全消失**（純粹是時點代理,無獨立量資訊）
   → 此時時點已足夠,不需 vol_ratio（仍可結論「DCI 該換掉」,但換成時點而非量）。
4. 樣本不足以判定（見 GATE）。

## Notes
- **因果鐵律**：vol_ratio 用 1-slot(5分)延遲版（生產 `compute_vol_estimated_range`,causal）;
  dci_long 用 t_k 當下可得的讀數（盤中 W10 ext_long 或 09:15 凍結），**禁用收盤版 dci_daily（look-ahead）**。
- 這是 strategy-agnostic 條件機率研究（Phase 1）;Phase 2 才轉成收割積極度規則 + 對撞既有 DCI 軸 + 必要時改 S001 checklist。
- 資料窗：stock_min/TX 2025-06~2026-06;IS=≤2026-02-26、OOS=≥2026-03-01（沿用複驗切分）。
- 若 Confirmed：把 journal_checklist 的「DCI 目標積極度軸」換成 vol_ratio 分帶（見 H114 backtest.md 設計）。
</content>
