# Archive: H090 漲停熱絡持續作為動量延續訊號

## Status
**Rejected** — 訊號是 bull regime 同步指標，無獨立預測力；長期 (+250d) 為負 lift。

## Date Closed
2026-05-12

## Summary

H079 (confirmed) 確認「漲停萎縮」是 leading sell signal，H090 對稱測試「漲停熱絡」是否能當動量延續買訊。
對 `lu_value_ratio_ma7` 取 12 個 (top_q × consec) 組合，發現 +60d 短期 lift +2-3% 看似可觀，
但 **+120d 衰退到 ≤+1.3%、+250d 全面負（−3% 到 −19%）、非 bull regime 完全沒 edge**。

最初快速分析觀察的 +2.29% lift 不 robust — Phase 1 完整探索後修正為 −0.06%。

→ **漲停熱絡是 bull regime 的同步指標，不是動量訊號**。

## Key Evidence

### 12 個 (top_q × consec) 變體 forward-return lift vs DCA baseline

| Top q | consec | clusters | +60d lift | +120d lift | +250d lift | non-bull +120d |
|---|---|---:|---:|---:|---:|---:|
| 5% | 1 | 20 | +0.46% | **−1.63%** | **−16.33%** | −2.13% |
| 10% | 1 | 35 | +2.34% | −0.06% | −9.25% | −1.35% |
| 15% | 1 | 61 | +2.72% | +0.65% | −3.41% | −0.57% |
| **20% | 1** | **77** | **+2.10%** | **+1.31%** | **+1.10%** | **+0.08%** |

最佳 variant `top 20% c=1`：
- +60d lift +2.10% ✓（但 77 cluster 太密）
- +120d lift +1.31%（< +2% GATE 門檻）
- +250d lift +1.10%（剛好打平 baseline）
- **非 bull regime +120d lift +0.08%（GATE 要 +1%）✗**

### 觸發日 macro_tier 分佈

`top 20% c=1` 797 觸發中：bull 39% + B 20% + C 20% + D 13% + A 9%
→ 漲停熱絡 ma7 top 20% **基本上就是「market is up」的 proxy**

### Invalidation 觸發

| # | 條件 | 結果 |
|---|---|---|
| 3 | +250d lift 為負 | ✓ 觸發 — 全 12 variants 中 8 個 +250d 嚴重負數 |
| 4 | 非 bull 子樣本 +120d lift < +1% | ✓ 觸發 — 所有 variants 都失敗 |

## Why Rejected

1. **+250d 全面負 lift**：典型 momentum-chase 陷阱，短期延續但長期均值回歸
2. **Bull regime tautology**：拿掉牛市子樣本後 edge 蒸發
3. **訊號太密**：通過短期 lift 門檻的變體 cluster 35-77 不像稀有事件
4. **與 H085 / H079 對照下顯不對稱**：fear 訊號（H079 萎縮、H085 panic）有預測力，
   greed 訊號（H090 熱絡）只是同步指標 — 市場結構常見的不對稱

## Combined finding with prior research

| 假設 | 訊號 | 結果 |
|---|---|---|
| H079 (confirmed) | 漲停萎縮 ma7 < 15 percentile 連 3 天 | leading sell signal |
| H087 (rejected) | 廣度指標加進 H085 composite | 稀釋 H085 訊號 |
| H088 (rejected) | 傳統 fear signals on Tier C | 無 edge over DCA |
| H089 (rejected) | 廣度指標單獨作 Tier C trigger | 無 edge over DCA + 5% |
| **H090 (rejected)** | **漲停熱絡持續作 momentum trigger** | **+250d 為負、非 bull 無 edge** |

**結構性結論**：漲停/廣度指標**對下跌防守有效**（H079），對**上漲動量擇時無效**（H090）；
**Tier C 結構性無 timing edge**（H088+H089）；H085 panic specialist 是稀缺結構，無法擴展。

## Derived Hypotheses

- **HXXX-h085-momentum-add-on**：H085 panic 進場後若 lu_value_ratio_ma7 突破 50 分位
  → 加碼訊號（不是進場 trigger，是 sizing helper）。先決條件：確認 H085 加碼有 benefit。
- **不建議**繼續挖漲停 momentum 方向。

## Links

- Proposal：proposal.md
- Phase 1 探索結果：results/distribution.md
- 探索腳本：explore.py
- 變體 grid：results/trigger_grid.csv
