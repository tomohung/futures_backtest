# Archive: H089 廣度指標單獨作為 Tier C 進場 trigger

## Status
**Rejected** — 廣度單獨 trigger 對 Tier C 無 forward-return edge over DCA；
new_lows_52w / high-low diff 反而是 BEAR continuation 訊號。

## Date Closed
2026-05-12

## Summary

H088 (rejected) 試用傳統 fear signals 補 H085 漏抓的 Tier C 標準回檔，
結論「Tier C 結構性無 timing edge」。H088 limitation 留下 open question：「未測廣度指標」。
H087 又證實廣度指標在 Tier B/C trough hit rate 75-88% 但加進 H085 composite 反而稀釋訊號。
H089 把兩者的正交補集測掉 — 廣度**單獨**作 trigger（不和 VIX/margin 混合）對 Tier C 是否有 edge？

對 4 個廣度指標各取 top 5/10% 共 8 個變體測試。**沒有任何變體 +120d/+250d 達 DCA + 5%**，
甚至 new_lows_52w / high-low diff 是 BEAR continuation 訊號（觸發後 120d 跑輸 DCA）。

→ **確認 H088 結構性結論**：Tier C 標準回檔結構性無 timing edge over DCA。

## Key Evidence

### 8 個變體 forward-return lift vs DCA baseline

| Indicator | Q | clusters | jaccard | +120d lift | +250d lift |
|---|---|---:|---:|---:|---:|
| **adv/dec** | **10%** | **231** | **0.06** | **+1.61%** | **+1.47%** |
| adv/dec | 5% | 137 | 0.07 | +1.37% | +0.55% |
| new lows 52w | 5% | 61 | 0.11 | **−2.65%** | +1.25% |
| new lows 52w | 10% | 90 | 0.10 | −0.76% | +1.26% |
| high-low diff | 5% | 59 | 0.11 | −2.19% | +1.38% |
| high-low diff | 10% | 95 | 0.10 | −1.13% | −0.46% |
| new highs 52w | 5% | 14 | 0.01 | +0.64% | −0.12% |
| new highs 52w | 10% | 46 | 0.09 | +0.17% | +0.60% |

最佳 variant `adv/dec top 10%`：+120d lift +1.61%（GATE 要 ≥ +5%）✗、cluster 231 太密 ✗

### 重要 finding：new_lows_52w 是 continuation 訊號

- top 5% +120d lift = **−2.65%**（跑輸 DCA 2.65%）
- H085-excluded 變體下：**−5.12%**（pure breadth-only event 後 120d 市場繼續弱）
- 廣度新低 ≠ 已到底，**反而代表「個股新低家數還擴大、後續再跌」**

H087 觀察的「廣度 trough hit rate 88%」是**後驗框架**（已知 trough 後回看），
向前看時廣度極值的 timing 太早 — 在 trough 前數週至數月就達極值，中間還會繼續跌。

### Invalidation 觸發

| # | 條件 | 結果 |
|---|---|---|
| 1 | 全部 +120d/+250d 都不超過 DCA + 5% | ✓ 觸發 — 最佳 lift +1.61% |
| 3 | top 5% 下 cluster > 50 | ✓ 觸發 — 多個變體 100+ cluster |
| 5 | 廣度單獨也 underperform DCA → 結構性無 edge | ✓ 觸發 |

3 個 invalidation 同時觸發 → **強 reject**。

## Why Rejected

H088 (rejected) + H089 (rejected) 聯合證據：
> **Tier C 標準回檔結構性無 timing edge over DCA**。
> 傳統 fear signals (H088) 與廣度 signals (H089) 都試過了，
> 都打不過 monthly DCA。H085 panic specialist 抓的是不同類型市場狀態，無法擴展到 Tier C。

可能原因：
1. Tier C 不是「行情底部」，只是「次級拉回」
2. 廣度極值是 continuation 而非 reversal（個股廣泛新低時下殺仍在進行）
3. Tier C 13 個事件中 7 個 parent_tier=A（結構熊內部），這些 dip 是「猜底失敗」

## Impact on Other Strategies

**不影響 S004-fg-composite（H085）confirmed 狀態**。
反而強化了 H085「panic specialist 限定 Tier B 急速恐慌」的定位。

寫進 H085 spec.md 的建議：
> Tier C 標準回檔已通過 H088 (傳統 signals) + H089 (廣度 signals) 雙重驗證為結構性無 edge over DCA，
> 不建議擴展 S004 涵蓋 Tier C。

## Derived Hypotheses

- **HXXX-tier-c-exit-condition**：原 H088 limitation 已記錄 — Tier C 訊號用「條件出場」
  （z125 回 0 / SMA60 突破）而非 250d hold 可能改變結論。但 H088+H089 結構性結論強，
  不建議優先做。
- **HXXX-breadth-bear-continuation**：把 new_lows_52w / high-low diff 反向用作空方訊號
  （continuation 訊號代表跌勢未終結）。是 fade strategy 不是 entry。

## Files

- `proposal.md` — 假設陳述（含預設失敗機率高）
- `tasks.md` — Phase 1 任務追蹤
- `explore.py` — Phase 1 探索腳本
- `results/distribution.md` — 完整分佈分析
- `results/single_triggers.csv` — 8 個變體 metrics
