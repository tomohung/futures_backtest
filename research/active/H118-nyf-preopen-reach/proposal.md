# Proposal: 0050期(NYF)盤前延伸對 TX ladder L3/L4 達成的預測力

## ID
H118

## Derived From
Origin（原創；資料源來自本次新建的 `aux_futures_1m` NYF pipeline）。
方法承襲 H111-dci-long-reach-map / H114-live-ext-at-ladder 的 reach-map 框架。

## Trading Intuition
元大台灣50 ETF 期貨（NYF＝0050 期，台灣50 指數本體）**日盤 08:45 開盤**，
而現貨與 cash 版 ext_long(W10) 要 **09:00** 才有值。盤前 15 分鐘 NYF 已在做價格發現。

直接觀察到的背離（已驗證，2026-05-18）：

| 指標 | 08:45 | 09:00 | 09:15 | 09:30 | 全日 |
|------|------|------|------|------|------|
| **NYF 0050期延伸** | +0.137 | +0.482 | +0.164 | +0.369 | min +0.11 / max +0.79（**全日不破 0**）|
| cash ext_long(W10) | —（未開）| +0.055 | **−0.272** | **−0.124** | 早盤翻負誤導 |

結果：當日 TX 上行 reach=(high−open)/EMA20 = **1.061 ≥ L4(0.977)**，**確實走到多 L4**。
→ NYF 盤前即站對方向並維持，cash ext_long 早盤翻負誤導。

## Hypothesis（三方對照）

以「錨 08:45 期貨 open」的 open-anchor 延伸 `tanh((F(t)−F(08:45open))/EMA20_range)`，
對三種標的各算一條，對打 TX forward 上行 L3/L4 達成：

- **A｜NYF（0050 期）**：台灣50 指數本體（指數預定義，無 which-N 選擇）。盤前流動性
  僅 2025-12+ 夠密。
- **B｜CDF（台積電單檔）**：2330 個股期（無 which-N 問題，2330 即指數最大權值~40%+）。
  盤前流動性回溯 ~2021、跨多 regime。
- **C｜cash ext_long(W10)**：現有基準（動態 top-10 by 20日均成交值、value-weighted；
  含 which-10 + 權重的人為選擇）。

**H1（領先）**：A/B 的 **盤前 08:45–09:00** 讀數對 TX forward 上行 L3/L4 達成有正的、
顯著鑑別力（corr > 0、強分位 lift > base）——這是 cash 版做不到的盤前窗。

**H2（不劣於 cash）**：A/B 早盤（≤09:30）鑑別力 **≥ C** 在同時點的鑑別力
（H111 基準 ext_long@09:30 對 L4 corr≈+0.35）。

**H3（指數 vs 動態 W10）**：定義好的指數代理（A/B，無 which-N 選擇）的鑑別力是否
**≥ 動態 W10（C）**——若是，則 cash 版的 which-10/權重人為選擇並未換得更高預測力。

對照設計：
- **重疊期**（NYF 盤前夠密、且 cash 有 stock_min，≈2025-12～2026-06）三方並排比。
- **長歷史跨 regime**：B（CDF）回溯 ~2021，做 2021牛/2022熊/2024牛/2025-26高波 的
  regime 穩定度（A 受盤前流動性限制只能 2025-12+）。

## Expected Distribution
- corr(NYF 延伸 @ t, forward 上行 reach) 隨 t 上升而增強；**盤前 08:45–09:00 即 > 0**。
- 高 NYF 盤前讀數分位 → forward L4 達成率明顯高於 base（lift）。
- Head-to-head：NYF 在多數時點 corr ≥ cash ext_long。

## Invalidation Condition
任一成立即視為**不支持**：
- NYF 盤前（08:45–09:00）讀數對 forward L3/L4 達成 **corr ≈ 0 或負**（無領先）。
- NYF 鑑別力**明顯劣於** cash ext_long（非「≥」）。
- 表面 edge 來自 **forward tautology**：forward reach 未嚴格定義在「時點 t 之後」，
  使「t 時已上漲」與「之後達標」自我關聯（必設前瞻 guard，對比正確虛無分佈）。

## Notes
- **資料限制**：`aux_futures_1m` NYF 僅 2026-01-02 起（~103 交易日），**全部落在
  2026 高波 regime**（見 memory [[project_oos_equals_highvol_regime]]）→ 結論的
  regime 外推性受限，需明示。
- **forward-tautology guard 為硬要求**（見 [[feedback_excursion_needs_forward_tautology_guard]]）：
  forward reach 取「t 之後的 session high」相對 open；並對比 IID/前瞻條件期望虛無。
- **每個對稱情境都實測**（多/空、各 reach level、各時點），不推論帶過
  （[[feedback_isolate_phenomenon_and_test_each_cell]]）。
- 所有結論附樣本數。
- NYF 是「**指數延伸**」（單一標的），與 cash ext_long「W10 廣度延伸」同質不同標的；
  對照時須註明這是不同 construct，不是同一指標的兩種算法。
