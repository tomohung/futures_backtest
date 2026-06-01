# Tasks: Regime 對 L1-L4 觸及率的影響與轉換偵測

## Phase 1: Distribution Research

### 資料 & 定義
- [x] 沿用 H097 的 EMA-only 階梯係數（L1=0.385 / L2=0.497 / L3=0.711 / L4=0.977）
      與 causal prior-day EMA20(日盤振幅) 距離計算
- [x] 算每日「上方 L1-L4」「下方 L1-L4」觸及（high/low vs session_open ± 距離_n）
- [x] 定義 causal 日線趨勢分類器（baseline：MA±std；另 alt MA-slope、%-dev band
      各 1 備敏感度；ADX+DI 略，三個價格分類器已足證穩定）

### 分佈探索
- [x] 依 regime 分桶，算各方向各 level 觸及率 + Wilson CI + 樣本數
- [x] 計算「不對稱度」= 上方觸及率 − 下方觸及率（逐 level），分 regime 看分佈
- [x] regime 間差異檢定（遠端 L3/L4 為重點）：CI 是否分離、不對稱度是否離 0
- [x] **轉換窗口分析**：標記分類器 flip 日，取 flip 前後 ±7 日 event-study 軌跡
- [x] 分類器敏感度：3 個 causal 分類器，主結論（空方 asym 顯著負）穩定
- [x] 視覺化：touch_rates.png / asymmetry.png / event_study.png（皆在 results/）

> 結果見 `results/distribution.md`。一句話：**regime 鑑別力只在空方成立**
> （空頭日下方 L3/L4 觸及率顯著高、CI 分離、三分類器穩定），多方≈盤整（不成立）；
> 轉換領先僅 ~1 日且機械性。

---
### GATE
**問題：分佈結果是否支持進入回測？**

- 每個 regime 桶樣本數是否足夠？（最低門檻：**每桶 ≥ 100 交易日**）
- 主假設：三 regime 的上/下方遠端（L3/L4）觸及率 CI 是否分離、不對稱度方向是否符合預期？
- 延伸假設：轉換窗口的觸及率/不對稱度是否**領先或同步**於 flip（非 lag-only）？
- 結論是否在不同分類器下穩定（無明顯 data snooping）？

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest / 應用驗證
> 本假設偏結構觀測；Phase 2 的具體形式待 GATE 後依結果擇一定案：
> (A) regime-conditioned 階梯：依 regime 調 L1-L4 係數或出場模式選擇（回灌 H095）
> (B) 不對稱度當轉換偵測訊號：驗證其領先性是否可轉成可交易的 regime 切換時點

- [ ] 依 GATE 結論確定 Phase 2 形式（A / B / 兩者）
- [ ] 定義規則與評估指標（A：出場路徑回測對比 H095 全期係數；B：轉換偵測的領先天數 / 命中率）
- [ ] in-sample 驗證
- [ ] out-of-sample 驗證
- [ ] 分類器與門檻敏感度分析
