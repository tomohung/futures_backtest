# Archive: 電子/金融 leadership 方向作為日線 directional risk-on/off 訊號

## Status
Rejected

## Summary
承接 H131 (A) 效應，測試電子/金融 leadership 方向（`dir=sign(ln(TSE23/TSE28)−SMA_W)`）能否
預測 forward TAIEX 報酬。基礎效應重現 H131（池化 t=2.4~2.9 @K≥10），但**穩定性電池全面拆穿**：
這是池化假象，非可交易 edge。連使用者原始的「站上均線+持續走高 / 跌破均線下緩衝」緩衝構造也
同樣失敗，且近兩年（2024/2026）關係**反轉**。

## Key Evidence
- N=3924（2010-01-04~2026-06-26），非重疊 stride=K 顯著性。
- 基礎：dir t=2.4~2.9 @K≥10（重現 H131）。
- **逐年符號**：spread>0 僅 10~11/17 年，6~7 年反號（2011,2012,2015,2017,2018,2024,2026）。
- **pre/post 2019 雙雙不顯著**（t≈0.95），pre 期 spread 為負 → 全樣本 t 是池化假象。
- **僅中段桶有效**：realized-vol 三分位 spread 低/中/高 = +0.06/**+1.30**/+0.14；
  VIX 三分位 = −0.19/**+1.09**/−0.07。非單調 → 不是真風險偏好訊號。
- **增量薄弱**：控制 mom+rvol dir t=2.30，但 2016+ 加 VIX 後 dir t **降至 1.96**；rvol t=3.49 最強。
- **對稱性/尾段**：電子側超額僅 Δ+0.17%（大半 equity drift）；剔除 2025 後 spread 腰斬至 +0.18%。
- **使用者原始構造（緩衝+持續走高）**：池化 t 2.3~2.6 仍漂亮但逐年僅 9~11/17；2024 spread −1.32、
  2026 −4.24（金融領先 forward 報酬反而更高）→ 訊號隨 regime 翻號、近兩年正在翻號。

## Why Rejected
「電子強=Risk On」直覺合理但資料不支持：方向→forward 報酬的關係 **regime-dependent 且會翻號**，
靜態訊號抓不住。H131 的強 headline t 是把翻來覆去的年份平均在一起的池化假象 —— 逐年/子期間/
regime 三分位三關正是為此而設，全數擋下。緩衝/持續性精修無助穩定。

## Derived Hypotheses
- 無新增（H133 半導體/金融細切面優先級已下調：問題在「方向→報酬」關係本身不穩，換分子未必救回）。
- **方法論備忘（重要）**：任何「池化 t 顯著」的訊號，晉升前必過 ①逐年符號一致 ②子期間
  ③regime 三分位 三關，否則池化假象會偽裝成 edge。本鏈（H131 t=2.6 → H132 拆穿）即範例。

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- 圖：results/h132_stability.png
- 腳本：explore.py（穩定性電池）、explore_buffer.py（使用者原始構造）
- 資料：results/sector_index.csv（H131 Phase 0 沿用，TWSE MI_INDEX type=IND）
- 上游：[[H131]] archive/rejected/H131-elec-fin-ratio-regime
