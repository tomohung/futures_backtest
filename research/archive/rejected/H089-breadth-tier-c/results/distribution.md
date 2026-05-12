# H089 Distribution Research Results

## Date
2026-05-12

## Conditions Tested

對 4 個廣度指標（H087 篩出的 hit-rate ≥75% 候選）各取 top 5% / top 10% threshold 作為單一 trigger：

| 指標 | 方向 | top 5% threshold | top 10% threshold |
|---|---|---|---|
| breadth_adv_dec | low | — | — |
| new_lows_52w | high | — | — |
| new_high_low_diff | low | — | — |
| new_highs_52w | low | — | — |

每個變體量測：
- cluster 數（gap >5 日）
- 與 H085 panic days (comp_z_4 top 10%) Jaccard
- +60/120/250d 0050 含息 forward return median
- 對比 monthly DCA baseline
- 「H085-excluded」變體（只看廣度極值但 H085 未觸發的日子）
- 命中事件 macro_tier 分布

## Sample

- 時間範圍：2009-01-05 ~ 2026-05-08（N=4235 個 0050 交易日）
- 廣度資料：2010-01-04 ~ 2026-05-11
- DCA baseline：monthly last-trading-day +120d med = +5.70%、+250d med = +11.38%
- H085 panic days：210 dates, 7 clusters

## Key Findings

### 全部 8 個變體都未通過 GATE

| Indicator | Q | n_trig | clusters | jaccard | +120d med | +120d lift | +250d med | +250d lift |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| adv/dec | 5% | 200 | 137 | 0.07 | +7.07% | +1.37% | +11.93% | +0.55% |
| **adv/dec** | **10%** | **399** | **231** | **0.06** | **+7.31%** | **+1.61%** | **+12.85%** | **+1.47%** |
| new lows 52w | 5% | 201 | 61 | 0.11 | +3.04% | **−2.65%** | +12.63% | +1.25% |
| new lows 52w | 10% | 403 | 90 | 0.10 | +4.94% | −0.76% | +12.64% | +1.26% |
| high-low diff | 5% | 202 | 59 | 0.11 | +3.51% | −2.19% | +12.76% | +1.38% |
| high-low diff | 10% | 403 | 95 | 0.10 | +4.57% | −1.13% | +10.91% | −0.46% |
| new highs 52w | 5% | 221 | 14 | 0.01 | +6.33% | +0.64% | +11.26% | −0.12% |
| new highs 52w | 10% | 435 | 46 | 0.09 | +5.87% | +0.17% | +11.98% | +0.60% |

最好的 +120d lift 是 **adv/dec top 10% = +1.61%**，遠低於 GATE 的 +5% 標準。

### H085-excluded（純「只有廣度極值」事件）— 全部更差

| Indicator | Q | excl N | excl +120d lift | excl +250d lift |
|---|---|---:|---:|---:|
| adv/dec | 5% | 167 | +0.47% | −1.53% |
| adv/dec | 10% | 350 | **+1.15%** | −0.60% |
| new lows 52w | 5% | 148 | **−5.12%** | −1.98% |
| new lows 52w | 10% | 317 | −2.18% | −1.70% |
| high-low diff | 5% | 153 | −4.51% | −1.73% |
| high-low diff | 10% | 327 | −2.50% | −2.94% |
| new highs 52w | 5% | 216 | +0.52% | −0.51% |
| new highs 52w | 10% | 379 | −1.05% | −1.33% |

排除 H085 重疊後，**沒有任何變體在 +120d 或 +250d 達到 DCA + 5%**。

### 重要發現：new_lows_52w / high-low diff 是 CONTINUATION 訊號，不是 REVERSAL

- `new_lows_52w` top 5% 的 +120d median = **+3.04%** （跑輸 DCA 2.65%）
- H085-excluded 變體下：**−5.12%**（pure breadth-only event 接下來 120 天市場繼續弱）
- 廣度新低極值 ≠ 已到底，反而代表「**個股新低家數還在擴大、後續再跌**」

H087 觀察到的「廣度在 trough 上 hit rate 88%」是**後驗框架**（已知 trough 後回看指標）。
向前看時，廣度極值的 timing 太早 — 在 trough 前數週至數月就達極值，但中間還會繼續跌。

### Cluster 數 — 廣度極值缺乏「事件感」

| Indicator | top 10% clusters |
|---|---:|
| adv/dec | 231 |
| new lows 52w | 90 |
| high-low diff | 95 |
| new highs 52w | 46 |
| H085 (comp_z_4) | 7 |

H085 7 個 cluster 在 17 年 = 真稀有事件。廣度單獨 top 10% 是 50-230 cluster = 每年 3-14 次，
不符合「panic 底部」的 event 定義。

### Macro tier 命中分佈

adv/dec top 10% 觸發 399 次的 macro_tier 分佈：
- A (主結構熊): 177 (44%) — 落在「猜底失敗」期
- B (急速回檔): 94 (24%)
- C (標準回檔): 63 (16%)
- bull / D: 65 (16%)

廣度極值在「A 結構熊」期最常見（市場整體弱），不是 Tier C-specific。

## Vs. Expected

- **預期**：廣度單獨 trigger 對 Tier C 有 +5% 以上 edge → ❌ 完全不符合
- **預期**：「H085-excluded」變體還能有 edge → ❌ 反而更差
- **預期**：cluster 6-50 的合理事件感 → ❌ 普遍 50-230

但 proposal 也預設「失敗機率高」，正是要關掉這個 open question。

## Gate Decision

- [ ] 進入 Phase 2
- [x] Archive (reject)
- [ ] 修改假設

### Invalidation 條件觸發狀況

| # | 條件 | 結果 |
|---|---|---|
| 1 | 3 個廣度指標 +120d/+250d median 都不超過 DCA + 5% | **✓ 觸發** — 最佳 lift +1.61% |
| 2 | top 5% 下 cluster < 6 | ✗ 不觸發 |
| 3 | top 5% 下 cluster > 50 | **✓ 觸發** — 多個變體 100+ cluster |
| 4 | 與 H085 Jaccard > 0.5 | ✗ 不觸發（最高 0.11）|
| 5 | 廣度單獨也 underperform DCA → 確認結構性無 edge | **✓ 觸發** |

3 個 invalidation 同時觸發 → **強 reject**。

### Combined finding (H088 + H089)

> **Tier C 標準回檔結構性無 timing edge over DCA**。
> 傳統 fear signals (H088) 與廣度 signals (H089) 都試過了，都打不過 monthly DCA。
> H085（panic specialist）抓的是不同類型的市場狀態，不能擴展到 Tier C。

## Derived Hypotheses

- **HXXX-tier-c-exit-condition**：Tier C 訊號用「條件出場」（z125 回 0 / SMA60 突破）而非 250d hold，
  可能改變結論。H088 limitation 已記錄這方向，仍未測。
- **HXXX-breadth-mean-reversion**：把廣度極值反向用 — 廣度新低 = continuation 訊號代表
  「廣度未達極值但接近極值」可能是 fade signal。但這是 fade strategy 不是 entry。
  跟 H085 panic specialist 是不同 dimension。
- **不建議**繼續挖 Tier C entry。H088 + H089 兩個失敗已強化「結構性無 edge」結論。

## Files

| File | Description |
|---|---|
| `explore.py` | Phase 1 探索腳本 |
| `results/single_triggers.csv` | 8 個變體的完整 metrics |
| `results/distribution.md` | 本檔案 |
