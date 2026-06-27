# Tasks: 電子/金融 leadership 方向作為日線 directional risk-on/off 訊號

> 資料 `results/sector_index.csv` 由 H131 沿用（已驗證）。Phase 1 不需重抓。
> 基礎方向效應 H131 已建立；H132 Phase 1 聚焦「穩定性 + 增量 + 對稱性」三個晉升門檻。

## Phase 1: Distribution Research（穩健性驗證）

- [x] 重建基礎效應：重現 H131（dir t=2.4~2.9 @K≥10）✓
- [x] **子期間穩定性**：逐年 spread>0 僅 11/17（6 年反號含 2024/2026）；pre/post 2019 雙雙不顯著（pre spread 為負）✗
- [x] **regime 分層**：效應只活在中波/中VIX 桶，低高兩端≈0/負 ✗（非單調風險偏好）
- [x] **增量對照**：控制 mom+rvol dir t=2.30；2016+ 加 VIX 後 dir t 降至 1.96（破2）；rvol 才是最強 t=3.49 ⚠
- [x] **多空對稱性**：電子側超額僅 Δ+0.17%（大半是 drift）；剔除 2025 後 spread 腰斬至 +0.18% ✗
- [x] 視覺化：`h132_stability.png`（逐年 spread bar + 每日 long-short 累積，Sharpe≈0.72 gross）
- 註：fg-composite comp_z 全控制未做（VIX 已覆蓋快變主成分；(B)/穩定性已否決故略）

---
### GATE
**問題：方向效應是否穩健到值得進入可交易化回測？**

- 樣本數是否足夠？（門檻：非重疊子樣本各 K **N≥150**；H131 已達）
- 子期間 / regime 分層中符號是否**一致為正、無反號**？（核心：排除單一 regime confound）
- 控制 VIX / fg-composite 後是否仍有**增量**？（排除恐懼貪婪換句話說）
- 是否僅由少數極端時段驅動？
- data snooping：W/K 多重比較是否已用一致性（非挑單一最佳）把關？

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest（可交易化）

- [ ] 定義進出場規則：dir 翻正進場（偏多/加碼）、翻負出場或防禦；持有期 K
- [ ] 設定回測參數（手續費、滑價）
- [ ] in-sample 回測 + 連敗/drawdown 評估（[[feedback_filter_eval_includes_streaks]]）
- [ ] out-of-sample / walk-forward（注意 OOS≡高波 confound，分層看而非單切點）
- [ ] 與既有 risk 工具疊加增量：作為 EstHL 順勢族的 regime 加碼條件（[[project_dci_is_extension_signal]] 類比）
- [ ] 參數敏感度（W/K）+ 多空對稱性實盤化
