# Tasks: 實現波動「溫度計」預判深reach延續

## Phase 1: Distribution Research  ✅ 完成（explore.py，2026-07-16）

### A. 建 zero-strategy 事實表（每個交易日一列，全 TX 史）
- [x] 逐日算 open-anchor 深 reach 旗標：`up_L4/up_L5/dn_L4/dn_L5`（全日）與 `_1130`/`_1030` 變體
- [x] 逐日算 deep-STOP 旗標（沿用 key_prices NVF：night_norm < 0.8）
- [x] 併 vix_regime 每日標籤（升壓/降壓、level、extreme；因果）

### B. 建溫度計（trailing，因果）
- [x] temp_ladder(W) = trailing W 日 any-L4 / any-L5 頻率，W∈{5,10,20}，全日與 11:30 變體
- [x] temp_night(W) = trailing W 夜 deep-STOP 頻率
- [x] early-fireworks 次要旗標：trailing「10:30 前碰 L4」頻率（僅記錄）

### C. 目標與虛無基準比較
- [x] 目標 future_reach(H) = 未來 H 個 session any-L4/any-L5 頻率，H∈{1,3,5,10}
- [x] **虛無①persistence**：IID 洗牌 forward → 真實 spread 落 null 75–89 分位（未過 p95）
- [x] **極端桶分析**：trailing L4 count=0 極冷桶 → 未來 5 日 revert 回基準（24.5% vs 24.8%）
- [x] **虛無②VIX-regime**：regime 分層內高−低溫增量 ≈0/負（−0%~−4%，N 充足）→ 資訊被吸收
- [x] **虛無③共線性**：corr −0.39、2×2 forward 全 23–27% → deep-STOP 非 additive

### D. 穩健性
- [x] daily anyL4 ACF ≈0（lag3 起）→ clustering 極弱，溫度計上限本就低
- [x] 視覺化：results/temp_forecast.png（溫度時序+L5事件、溫度→forward散點、regime分層）

---
### 桶界 / 門檻 = 數據決定（snooping 防線）
順序鐵律：**先只看預測變數與基準率，定好桶界與門檻，再揭露 forward 目標。**
- [ ] 步驟1：只看 trailing L4 次數分佈 → 用自然質量 / quantile 定桶界（不看 forward）
- [ ] 步驟2：只看無條件基準率 + 溫度計自相關（trailing 視窗重疊→daily 觀測不獨立）→ 用
      **effective sample size**（或非重疊視窗）定「桶內幾個觀測才算穩」的門檻；門檻理由寫進 distribution.md
- [ ] 步驟3：才揭露 forward 目標分桶比較（含正確 IID/洗牌虛無）

### GATE
**問題：分佈結果是否支持進入回測 / 接預測訊號？**

- 樣本數門檻：**由步驟 2 的 effective-N 分析決定**（非事先寫死），最冷/最熱桶須達該門檻且非單一 regime 期間獨撐。
- 對比 persistence 虛無後仍 **顯著且單調**（極端桶偏離無條件基準，非只有線性 clustering 重述）。
- 在 VIX-regime 分層內 **仍能拉開** future reach 差距（＝資訊未被 regime 完全吸收）。
- 無明顯 data-snooping（(W,H) 網格多重比較須留意；用單調性 + 跨期間穩定當防線）。

**決定：** [ ] 繼續 Phase 2（接預測訊號）　[ ] 直接 Archive（僅保留觀測 tile）　[ ] 修改假設後重跑

---

## Phase 2: Backtest（僅在 GATE 過才執行）
- [ ] 定義預測訊號用法（如：極冷桶 → 降深關卡期望 / 縮停損；極熱桶 → 放深關卡）
- [ ] 套到既有策略（EstHL / Reversal）當 regime modulator，比有無溫度濾網的績效
- [ ] out-of-sample / walk-forward / 跨 regime 驗證
- [ ] 參數敏感度（W, H, 桶界）

---

## 平行交付（無論 GATE，描述性工具）✅ 已上線（2026-07-16）
- [x] `key_prices.py` 新增「市場溫度（現狀）」段：近 5/10/20 日 anyL4(多/空)/anyL5/deep-STOP vs 全史基準、
      溫度方向箭頭（振幅 EMA5 vs EMA20）、與 ladder regime 並列對照（一致/背離）。
      實作：`_compute_market_temperature()` + print_report 渲染；只進盤前簡報 clipboard（不進 chart-ui）。
      明確標註「現狀、非預測」，深 reach 期望仍以 ladder regime tile 為準。
