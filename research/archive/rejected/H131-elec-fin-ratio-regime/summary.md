# Archive: 電子/金融比率趨勢強度作為 trend-vs-chop regime 偵測器

## Status
Rejected（主假設 B）。次效應 A 衍生為 H132。

## Summary
測試電子(TSE23)/金融(TSE28) 對數比率的「趨勢強度」（trailing Efficiency Ratio）能否偵測
TAIEX 的「趨勢 vs 盤整」環境（forward ER）。結論：**不能**。比率趨勢強度對 forward TAIEX-ER
零相關、非單調、控制 TAIEX 自身 ER 後零增量。但附帶檢驗的「方向」效應（電子領先 vs 金融領先）
意外強且穩健，獨立另開 H132 接手。

## Key Evidence
- 樣本 N=3,924 交易日（2010-01-04~2026-06-26，TWSE MI_INDEX type=IND，資料驗證 0 污染）。
- **(B) 死因**：spearman(ratioER, forward TAIEX-ER) = −0.02~+0.05；五分位 **6/6 (W,K) 組合非單調**；
  非重疊 OLS 中 ratioER t=0.25~0.79 全不顯著、ΔR²≈0.0005。命中 proposal 自列的「最可能死法」。
- 旁證：TAIEX 趨勢度本身在 5–20 日尺度**均值回歸**（taiexER t −2.1~−2.7），與「trend regime 很黏」
  的先驗相反 —— TAIEX 自身性質，與本假設正交。
- **(A) 亮點**：電子領先 → forward TAIEX 報酬顯著高（dir t=2.4~2.9 @ K≥10），且**通過動能對照**
  （控制 TAIEX trailing return 後 t 幾乎不變；TAIEX 動能自身 t<1.2 已死）。

## Why Rejected
比率的核心機制假設「果斷 leadership = 市場在 trend」在資料上不存在：比率的趨勢性與 TAIEX 的
趨勢性幾乎無關（共線 spearman 僅 +0.12~0.15），且對未來趨勢度毫無預測/增量。與記憶
[[project_dci_is_extension_signal]] 一致 —— leadership/breadth 類屬「方向/延伸」訊號，
不是「趨勢度 regime」預測器。

## Derived Hypotheses
- **H132**：電子/金融 leadership 方向作為日線 directional risk-on/off 訊號，預測 forward TAIEX 報酬。
  Phase 1 已顯示穩健（t>2.4 @ K≥10、獨立於動能）。需補子期間穩定性（含 OOS≡高波 confound）、
  與 VIX/fg-composite 增量、多空對稱性、可交易化。
- H133（選配）：半導體類 vs 金融（更細切面，去電子工業類雜訊）。

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- 圖：results/ratioER_vs_fwdER.png
- 腳本：fetch_sector_index.py（Phase 0 抓取）、explore.py（Phase 1 分析）
