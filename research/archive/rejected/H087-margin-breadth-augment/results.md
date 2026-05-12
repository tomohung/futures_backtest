# H087 Results: 廣度指標補強 H085 — REJECT

## Verdict

**Reject**。雖然有 4 個廣度指標通過「trough 命中率 ≥60% + max |r| <0.6 vs H084 4 軸」
的非冗餘性 GATE，但**加進 H085 composite 後 forward-return 顯著下降**。

## Phase 0: ETL 與指標建置 ✅

### Data backfill
- TWSE/TPEX market_breadth + stock_day 2010-01-04 ~ 2026-05-11
- 修正 TWSE API canned-data 污染（共 24 個日期的 echoed responses）
- 最終 coverage：market_breadth TWSE=3989 / TPEX=3990，stock_day=6,511,875 列

### 7 個候選廣度指標（`results/breadth_indicators.csv`）

| 指標 | 描述 |
|---|---|
| `breadth_adv_dec` | 漲家/跌家比 |
| `breadth_adv_dec_cum` | 累積（漲家-跌家）— McClellan-style |
| `new_highs_52w` | 個股 close ≥ 252日最高 家數 |
| `new_lows_52w` | 個股 close ≤ 252日最低 家數 |
| `new_high_low_diff` | new_highs - new_lows |
| `value_concentration_top20` | top 20 成交額占比 |
| `value_per_stock` | 全市場成交額 / 有成交家數 |

## Phase 1.1+1.2: Hit rate + 相關性

對 21 個 Tier B/C trough 事件（其中 16 個有廣度資料；早期 2008-2010 無）：

| 指標 | Hit rate (16 events) | non-A | A | max \|r\| vs H084 4 軸 | 通過 GATE? |
|---|---|---|---|---|---|
| new lows 52w | 88% | 100% | 71% | 0.40 vs z 125MA | ✓ |
| high-low diff | 88% | 100% | 71% | 0.55 vs z 125MA | ✓ |
| adv/dec | 81% | 78% | 86% | 0.17 vs margin drop 60d | ✓ |
| new highs 52w | 75% | 56% | 100% | 0.59 vs z 125MA (邊緣) | ✓ |
| adv-dec cum | 38% | 44% | 29% | 0.41 vs econ_score | ✗ hit rate |
| top20 concen | 38% | 56% | 14% | 0.37 vs econ_score | ✗ hit rate |
| value/stock | 25% | 44% | 0% | 0.59 vs econ_score | ✗ hit rate |

**4 個指標通過 GATE 1+2**：adv/dec、new lows 52w、high-low diff、new highs 52w。

最獨立的是 **adv/dec**（與 H084 所有軸 max |r| = 0.17）。

## Phase 1.3: 加入 H085 composite 後 forward-return

對 H085 原版 (`comp_z_4` = VIX_pct + -z125MA + -margin_drop_60d + -econ_score) 逐步加廣度指標。
取 top 10% 觸發，比較 60/120/250 日 0050 含息 forward return。

**Sample**: 2017-08-31 ~ 2026-04-30，N=2094 交易日。

### Forward-return 對比

| Composite | 軸數 | +60d median | +120d median | +250d median | +250d win | 250d lift |
|---|---|---|---|---|---|---|
| **comp_z_4** | 4 | **+12.49%** | **+14.91%** | **+32.74%** | **75%** | **+10.79%** |
| comp_z_4 + adv/dec | 5 | +9.08% | +14.40% | +27.71% | 67% | +5.75% |
| ++ new lows 52w | 6 | +2.82% | +8.56% | +25.13% | 60% | +3.18% |
| +++ high-low diff | 7 | +2.29% | +8.22% | +24.50% | 57% | +2.55% |

**每加一個廣度軸，forward-return 跨所有 horizon 都下降**。

### Cluster 數對比（top 10% threshold, gap >5 日）

| Composite | Threshold | Triggers | Clusters |
|---|---|---|---|
| comp_z_4 | +3.58 | 210 | **9** |
| + adv/dec | +2.96 | 210 | 19 |
| ++ new lows | +4.33 | 210 | 41 |
| +++ high-low diff | +5.36 | 210 | **48** |

加廣度後 cluster 數從 9 暴增到 48 — 把太多假底事件納入了。

## 為何 hit rate 高但 forward-return 差？

**Hit rate vs forward-return 衡量不同東西**：
- Hit rate：事件已知 trough 上指標達極值的比例（**已知底部後驗算**）
- Forward-return：每個觸發日後實際 +N 天的市場走勢

廣度指標的問題：
1. **極值延伸**：trough 前後幾週都有「廣度爆量」，但只有那一天是真底
2. **假底干擾**：廣度經常在半底（後續還會再跌）就達極值
3. **訊號 lag**：等廣度新低家數爆量時，VIX/margin/z125MA 通常已經提供等價訊號
4. **稀釋 H084 4 軸的訊噪比**：H084 4 軸已經高度優化（IS 拼出 75% win），加任何指標都是稀釋

## 結論

> **H084 4 軸 composite 已經 sufficient for panic detection.**
> 廣度指標雖然在 trough 達極值且與現有指標統計獨立，
> 但 trough 命中率高 ≠ 預測力高 — 廣度極值經常出現在非底部，加入後 dilute 訊號。

## Derived Hypotheses

- **H088 (proposal)**: H085 不涵蓋 Tier C 標準回檔（2021-05、2024-08、2026-03 都沒命中）。
  廣度指標在這些 Tier C 事件 hit rate 100%（看 `percentile_table_with_breadth.csv`），
  也許可以做**「Tier C 專用」的廣度合成 score**（不和 VIX/margin 混合），補 H085 漏接的場景。
  - 條件：要先確認 Tier C 進場有正期望（H085 spec 推測 H088 待做）
  - 核心改變：把廣度當「**獨立 alternative trigger**」而非 H085 的擴展

- **「廣度極值卻非底部」的案例研究**：把廣度觸發但 fwd_120d < 0 的 case 找出來，
  看是否能找到 second filter 排除假底。

## Files

| File | Description |
|---|---|
| `build_breadth_indicators.py` | Phase 0.2 建 7 個廣度指標 |
| `percentile_correlation_with_breadth.py` | Phase 1.1+1.2 hit rate + correlation |
| `extend_composite.py` | Phase 1.3 加廣度到 H085 composite |
| `results/breadth_indicators.csv` | 7 個指標 × 3990 個交易日 |
| `results/percentile_table_with_breadth.csv` | 21 events × 16 個指標的百分位 |
| `results/hit_rates_with_breadth.csv` | 命中率（含 H084 9 軸 + H087 7 軸） |
| `results/correlation_matrix_with_breadth.csv` | 16 個指標的 Pearson 矩陣 |
| `results/correlation_heatmap_with_breadth.png` | heatmap |
| `results/composite_comparison.csv` | comp_z_4 → comp_z_4p3 forward-return |
