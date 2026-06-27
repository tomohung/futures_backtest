# Tasks: 電子/金融比率趨勢強度作為 trend-vs-chop regime 偵測器

## Phase 0: 資料取得（前置，本假設特有）

- [x] 取得 TSE23（電子工業類，2019H1 前名電子類）/ TSE28（金融保險類）日指數（TWSE MI_INDEX type=IND），2010 起
- [x] 落地 `results/sector_index.csv`（N=3924，2010-01-04~2026-06-26）；驗證 0 污染/0 重複/缺漏 114 日均勻

## Phase 1: Distribution Research

- [x] 計算 `r = ln(TSE23/TSE28)`、`ratioER`（W=10/20）、方向 `sign(r − SMA_W)`
- [x] 計算 TAIEX `fwdER(K)`（K=5/10/20）與 trailing `taiexER(W)`（baseline）
- [x] **主關係（B）**：ratioER 分位 × fwdER 中位數 → 6/6 組合非單調、相關≈0 ✗
- [x] **增量（核心 GATE）**：非重疊 OLS，ratioER t=0.25~0.79 全不顯著、ΔR²≈0 ✗
- [~] **冗餘對照**：VIX 共線 spearman −0.02（無關）。concentration_index 表未建，(B) 已死故略
- [x] **(A) 附帶**：方向分組 + 動能對照 → dir t=2.4~2.9（K≥10）、獨立於動能 ✓（亮點）
- [x] 視覺化：`ratioER_vs_fwdER.png`（五分位非單調，支持 B reject）

---
### GATE
**問題：分佈結果是否支持進入回測/正式化？**

- 樣本數是否足夠？（最低門檻：**> 800 交易日有效樣本**，約 3+ 年；2010 起應遠超過）
- 比率-ER 對 forward TAIEX-ER 是否**單調遞增**？
- **是否有增量**？控制 TAIEX-ER 後 partial 預測力是否仍為正？（這是最可能擋下的關卡）
- 是否只是 concentration_index / VIX regime 換句話說？
- 是否有 data snooping 疑慮（W/K 多重比較）？

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest / 應用驗證

> 注意：本假設是 regime 偵測器而非交易訊號。Phase 2 不是獨立策略回測，而是
> **regime 條件化應用**：在「比率-ER 高（趨勢環境）」的日子，順勢族（如 EstHL）
> 是否表現較佳；在「比率-ER 低（盤整環境）」是否該收手或偏 fade。

- [ ] 定義 regime 分類規則（高/低趨勢環境門檻）
- [ ] 條件化既有順勢策略（EstHL）績效：高趨勢 regime vs 低趨勢 regime
- [ ] 與既有 regime 濾網（VIX regime）疊加，檢查增量
- [ ] out-of-sample 驗證（注意 OOS≡高波 regime 的 confound，記憶 project_oos_equals_highvol_regime）
- [ ] 穩健性：W/K 敏感度
