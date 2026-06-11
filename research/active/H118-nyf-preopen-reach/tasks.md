# Tasks: 0050期(NYF)盤前延伸對 TX ladder L3/L4 達成的預測力

## Phase 1: Distribution Research（三方對照 A=NYF / B=CDF / C=cash W10）

- [ ] **匯入 CDF（台積電）全史** → aux_futures_1m（NYF 已在）✅ 進行中
- [ ] **建 panel**：逐日算
  - A=NYF、B=CDF open-anchor 延伸 `tanh((F(t)−F(08:45open))/EMA20_range)` 於
    T = {08:45, 08:50, 08:55, 09:00, 09:05, 09:10, 09:15, 09:20, 09:25, 09:30}
    （各標的用自身 causal EMA20 日振幅當分母）
  - C=cash ext_long(W10) 於同時點（09:00 起）
  - TX forward 上行 reach：**t 之後** session high 相對當日 open，÷ causal EMA20 範圍；
    標記達 L3(0.711)/L4(0.977)/L5(1.30)
  - 每日標 regime（VIX/已實現），供長歷史分段
- [ ] **盤前流動性 gate**：每日每標的標記盤前 08:45–08:59 tick 數；低於門檻的日子
      （NYF 多在 2025-12 前）標為無效、不計入該標的統計
- [ ] **forward-tautology guard**：forward reach 嚴格取「t 之後」的 high；
      建立虛無分佈（IID 洗牌 / 前瞻條件期望），確認 corr 非自我關聯產物
- [ ] **corr 曲線**：corr(各標的延伸 @ t, forward L3/L4 reach) 隨 t；特別標盤前 08:45–09:00
- [ ] **分位 lift**：各標的讀數五分位 → forward L4 達成率 vs base
- [ ] **三方 head-to-head**：每時點 A vs B vs C 的 corr / lift 並排（重疊期）
- [ ] **B 長歷史跨 regime**：CDF 2021牛/2022熊/2024牛/2025-26高波 分段穩定度
- [ ] **每格實測**：多/空對稱、各 reach level、各時點都出數字（附 N）
- [ ] 視覺化關鍵圖（corr-by-time、lift-by-quantile、三方疊圖、regime 分段）

---
### GATE
**問題：分佈結果是否支持進入回測？**

- 樣本數：~103 日（2026-01 起，**單一高波 regime**）。最低門檻 **≥ 90 交易日**有效。
- 盤前 08:45–09:00 NYF 讀數對 forward L3/L4 **corr 顯著 > 0**（且通過 forward guard）。
- Head-to-head：NYF 鑑別力**不劣於** cash ext_long(W10)。
- 無明顯 data snooping / forward tautology。
- **regime 警示**：所有結論明示「僅高波 regime、外推受限」。

**決定：** [x] **繼續 Phase 2**（2026-06-11；H1+guard+跨regime+同日7/7勝）　[ ] Archive　[ ] 修改

---

## Phase 2: Backtest
（過 GATE 後定義；初步方向）

- [ ] 進場規則：NYF 盤前讀數 ≥ 門檻 → 偏多 / 順勢族放行
- [ ] in-sample 回測（含手續費、滑價）
- [ ] out-of-sample（注意 OOS≡高波 regime confound，[[project_oos_equals_highvol_regime]]）
- [ ] 參數敏感度（門檻、時點）
