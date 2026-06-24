# Tasks: 同向第二次 L2 拉回續攻

## Phase 1: Distribution Research

- [x] 重用 `services/l2_pullback.detect_day` 逐日掃出所有 causal L2 拉回進場（2021–2026 全樣本）
- [x] 對每筆進場標記同方向序數 k（當日同 side 第幾次）→ 分組 `1st` vs `2nd+`
- [x] 統計：具 ≥2 次同向 setup 的交易日數、多/空各別 N、序數分佈
- [x] 零策略 forward excursion：每筆進場到收盤的 MFE/MAE（以 anchor±L_n 距離標準化），
      比較 `2nd+` vs `1st` 碰 L3/L4/L5 的比率
- [x] **虛無對照**：建立正確虛無分佈（同為趨勢日但只取第一次 / 條件期望 / IID 洗牌），
      檢驗 `2nd+` 增益是否為 selection artifact（趨勢日延伸 tautology）
- [x] 附帶欄位：新做盤中 VWAP，記錄每筆 `2nd+` 前「是否曾站上成本線又跌破」（僅描述）
- [x] 附帶欄位：DCI 在 `1st` vs `2nd+` 的表態強度差異
- [x] 視覺化關鍵分佈圖（序數 × 碰階比率、MFE/MAE 分佈、虛無對照）

---
### GATE
**問題：分佈結果是否支持進入回測？**

- 具 ≥2 次同向 setup 的樣本數是否足夠？（**門檻待 Phase 1 給出實際 N 後再定**）
- `2nd+` 碰 L3/L4/L5 比率 / 賠率是否顯著優於 `1st`？
- 對照正確虛無分佈後，增益是否仍存在（非純 selection / 趨勢日延伸）？
- 是否有明顯 data snooping 疑慮？

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest

- [x] 進場規則：`2nd+` 同向 L2 拉回站回 5MA（沿用 detect_day 進場相位）
- [x] 停損：沿用 `l2_pullback`（pb_ext 往 anchor STOP_ALPHA）
- [x] 目標敏感度：測 L3 vs L4 vs L5（驗證「第二次可瞄更遠」）
- [x] 對照組：同規則但只取 `1st`（baseline），量化序數條件的增量
- [x] 設定回測參數（手續費、滑價）
- [x] 執行 in-sample 回測
- [x] 執行 out-of-sample 驗證（留意 OOS≡高波 regime confound）
- [x] Walk-forward 測試
- [x] 參數敏感度分析（PF + 連敗長度 + drawdown，非只看 PF）
