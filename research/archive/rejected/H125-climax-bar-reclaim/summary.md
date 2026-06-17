# Archive: Climax Bar Reclaim 反轉做多

## Status
Rejected（Phase 1 GATE）

## Summary
源自 2026-06-17 盤中觀察：悶盤後一段持續放量下殺破底、收盤站上該段最大量 K（climax bar）高點後反轉上攻。假設「下跌 leg 的 climax bar 高點被收盤收復 → 做多有正期望值」。Phase 1 用持續放量定義（近3根≥2.5×前10根+創新低）撈出 N=1,847 事件（2021–2026），結果整體超額邊際、扣成本 ≈ breakeven，且核心的「壓縮前提」被數據反向否定、edge 與高波 regime 共線並逐年衰減。

## Key Evidence
- 整體 N=1,847：fwd30 中位數 +1 點、勝率 51.2%、**excess vs 同日隨機進場僅 +1.8 點、pctile ~50**（≈無時點優勢），扣 2 點來回成本即歸零。
- **壓縮前提反向**：事前最悶盤（comp<0.25）fwd30 excess **−4.8**、勝率 48.5%；事前已大動（>0.6）excess **+10.2**、勝率 60%。edge 來源是「已成形下殺被收復」而非「壓縮釋放」。
- **大跌幅集中**：leg 跌幅 >200 點 fwd30 excess +34、勝率 63%，但 N=70 且與高波共線。
- **年度衰減 + regime confound**：fwd30 excess 2021 +3.4 → 2023 −0.7 → 2025 −0.1 → 2026 +12.5；2023–25 勝率掉到 40–43%。正向幾乎全來自 2021 與 2026（高波 regime，見 memory `project_oos_equals_highvol_regime`）。

## Why Rejected
與已 Rejected 的 H062（凸量突破）/ H063（大單無方向力）/ H061（morning dip）落在同一結構陷阱：**反轉/出量現象真實存在，但機械化後超額 ≈ 長期 drift + 高波雜訊**。「破底失敗收復」本身無穩定 alpha，超額 pctile ~50；唯一強切片（大跌幅/事前大動/2026）彼此共線，等同「高波行情反彈幅度大」的副產品，平靜年份（2023–25）失效。使用者裁示 Reject。

## Derived Hypotheses
- **大跌幅 climax reclaim（高波限定）**：放棄壓縮前提，只在 leg 跌幅 ≥~1.5×ATR / 事前已大動時做多，明確定位高波 regime 訊號，需獨立 OOS 避開 2026-only。
- **錨點定義敏感度**：單根爆量(3×均量) vs 持續放量(3根/10根) 抓到的 climax 不同，比較哪個 reclaim 價位後續分佈較佳。
- **空方對稱**：上漲噴出量 climax 被跌破做空，檢驗是否對稱（排除單純 long drift）。

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md（含完整切片表）
- 圖：results/distribution.png
- 探索腳本：explore.py
- 事件明細：results/events.csv
