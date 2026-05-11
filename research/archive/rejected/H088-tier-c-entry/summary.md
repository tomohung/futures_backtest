# Archive: Tier C 標準回檔進場訊號 (H088)

## Status
**Rejected** — 10 個訊號變體在 13 個 Tier C 事件上的 forward returns **全部不超過 DCA baseline + 1%**。Invalidation #1 觸發。

## Date Closed
2026-05-11

## Summary

H088 從 H085 confirmed 後的覆蓋盲點衍生：H085 抓 Tier B 急速 panic（4/8 事件命中率 50%），但 Tier C 標準回檔（13 個）幾乎全部漏抓。H088 要驗證能否用 z125MA / margin / econ 訊號補上 Tier C entry。

結果：核心矛盾 —
- 能標記事件的訊號（margin_drop60 ≤ −5%，hit rate 85%）**forward return 跑輸 DCA baseline −1.3%**
- forward return 略好的訊號（z125 + notA）**hit rate 僅 15-30%、必抓事件全漏**

→ **Tier C 並非「行情底部」，只是「次級拉回」，沒有 timing edge 可挖過 DCA**。

## Key Evidence

### 訊號矩陣（10 變體）

| Signal | hit_rate_C | 必抓 (2/2) | Jaccard H085 | +120d med | vs DCA baseline |
|---|---:|:---:|---:|---:|---:|
| margin_drop60≤−5+nonH085 | **85%** | **2/2** | **0** | +4.4% | **−1.3%** ❌ |
| S1+notA (parent_tier!=A) | 15% | 0/2 | 0.41 | +8.2% | +2.5% |
| S1+econ≥17 | 31% | 0/2 | 0.32 | +6.5% | +0.9% |
| S1+nonH085 | 31% | 0/2 | 0 | +3.5% | −2.2% |
| 其餘 6 個 | 15-31% | 0/2 | 0-0.32 | 接近 baseline | ≈ 0 |

**DCA monthly +120d baseline: +5.7%**

### 為何沒有 edge？

H085 抓「**深度恐慌底 + 大幅反彈**」每筆 +60-120% — 進場時恐慌極端、反彈空間大。

H088 抓的 Tier C 事件：
1. 進場時恐慌不夠深，反彈幅度有限
2. 13 個 C 中 **7 個 parent_tier=A**（結構熊內部），這些 dip 實際是「猜底失敗」
3. 1 年（250d）持有窗會吸收後續高點消化 → 中位數被拉平到接近 baseline

## Limitations / Caveats

1. **未測廣度指標**：H087 ETL 完成後（明天），用 ld_value_ratio 等廣度可能有不同結果。但即便如此，「Tier C 沒有 timing edge」的結構性結論可能仍成立。
2. **未測短 hold 期**：固定 250d 出場可能不適合 Tier C 短回檔節奏，60d/30d hold 沒測。
3. **未測 margin slope/timing filter**：用「margin 反轉」而非「margin 跌深」可能更貼近底部 timing。
4. **未測 conditional combos**：z125 AND margin 同時極端（不是 OR），樣本會少但 edge 可能浮現。

## Impact on Other Strategies

**不影響 S004-fg-composite（H085）confirmed 狀態**。

H088 的失敗強化了 H085 的定位：S004 抓「真正深恐慌」是有 edge 的，Tier C 標準回檔可能更適合單純 DCA。

## Derived Hypotheses（建議未來方向）

- **H08X-tier-c-conditional-exit**：Tier C 訊號 + 條件出場（z125 回 0 / 跌破 SMA60），不固定 250d
- **H08X-margin-slope**：margin_drop_60d 由負轉正（融資已止跌）作為 Tier C timing
- **H08X-breadth-tier-c**：H087 ETL 完成後加廣度（ld_value_ratio / adv_dec_ratio）重做

## Files

- `proposal.md` — 原始假設文件
- `tasks.md` — Phase 1 任務追蹤
- `explore.py` — 訊號 grid 分析腳本，可獨立重跑
- `results/distribution.md` — 完整結果
- `results/signal_grid.csv` — 10 訊號 metrics
- `results/signal_grid.png` — Hit rate vs Jaccard 散點 + forward returns bar
