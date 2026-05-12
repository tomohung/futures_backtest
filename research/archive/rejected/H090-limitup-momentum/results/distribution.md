# H090 Distribution Research Results

## Date
2026-05-12

## Conditions Tested

對 `lu_value_ratio_ma7` 取 4 × 3 = 12 個 (top_q, consec) 組合作為 trigger：
- top_q: 5%, 10%, 15%, 20%
- consecutive: 1, 3, 5 天

每個 trigger 量測：cluster 數、Jaccard vs H085、+60/120/250d 0050 含息 forward return median，
+ macro_tier breakdown + 非 bull regime 子樣本。

## Sample

- 時間範圍：2010-01-04 ~ 2026-05-08（N=3987 trading days）
- DCA baseline (monthly)：+60d med +3.26%、+120d +5.59%、+250d +11.38%
- H085 panic days: 210 dates, 7 clusters

## Key Findings

### 1. 短期 +60d 有訊號，但長期 +120d/+250d 大幅反轉

| Top q | consec | clusters | +60d lift | +120d lift | +250d lift |
|---|---|---:|---:|---:|---:|
| 5% | 1 | 20 | +0.46% | **−1.63%** | **−16.33%** |
| 5% | 3 | 19 | −0.04% | −1.62% | **−18.53%** |
| 5% | 5 | 16 | −0.40% | −1.34% | **−19.03%** |
| 10% | 1 | 35 | **+2.34%** | −0.06% | −9.25% |
| 10% | 3 | 35 | +1.93% | −0.71% | −11.86% |
| 10% | 5 | 27 | +2.02% | −0.86% | −12.89% |
| 15% | 1 | 61 | **+2.72%** | +0.65% | −3.41% |
| 15% | 3 | 46 | +2.72% | +0.38% | −7.18% |
| 15% | 5 | 36 | +2.36% | −0.22% | −11.23% |
| **20% | 1** | **77** | **+2.10%** | **+1.31%** | **+1.10%** |
| 20% | 3 | 64 | +2.36% | +0.69% | −2.43% |
| 20% | 5 | 48 | +2.34% | +0.35% | −4.85% |

**Pattern**：
- **+60d**：top 10-20% 大部分 lift +2~3%（短期動量訊號存在）
- **+120d**：lift 衰退到 0 ~ +1.31%（中期消失）
- **+250d**：嚴重負數（除了 top 20% c=1 +1.10%）

最佳 variant `top 20% c=1` 在 250d 才剛勉強回到 baseline，但 77 個 cluster = 一年 4-5 次觸發，
**不像「訊號」，比較像「日常 chasing 信號」**。

### 2. 非 bull regime 完全沒 edge

| Top q | consec | non-bull +60d lift | non-bull +120d lift | non-bull +250d lift |
|---|---|---:|---:|---:|
| 5% | 1 | −0.35% | −2.13% | −15.55% |
| 10% | 1 | +1.48% | −1.35% | −11.86% |
| 15% | 1 | +1.28% | −0.57% | −6.27% |
| 20% | 1 | +1.24% | **+0.08%** | **+4.51%** |

`top 20% c=1` 是唯一在非 bull regime 仍勉強 +120d ≥ 0、+250d +4.51% 的 variant。
但 +120d lift +0.08% 遠低於 GATE 的 +1%。

**重大發現**：拿掉牛市定義之後，**+60d 短期訊號雖仍存在（+1.2~1.5%）但 +120d 蒸發**。
代表「漲停熱絡 → 動量延續」這個觀察基本上是「市場本來就在牛市，跑啥都會漲」的 tautology。

### 3. macro_tier 分佈：bull regime 主導

`top 20% c=1` 的 797 觸發日 tier 分佈：
- bull: 311 (39%)
- B: 156 (20%)
- C: 156 (20%)
- D: 103 (13%)
- A: 71 (9%)

bull regime 佔 ~40%，加上 D、B 等 sideways/up-correction tier 共 70%+。
**漲停熱絡 ma7 top 20% 基本上就是「市場目前處於 up regime」的 proxy**。

### 4. Jaccard vs H085：完全互補（如預期）

所有 variants 的 Jaccard vs H085 panic days 都 ≤ 0.04 — 確認 H090 與 H085 是完全不同維度
（greed 動量 vs fear panic），這部分符合假設。

### 5. 起初 +2.29% lift 是怎麼回事？

最初快速 correlation 分析時觀察到 `lu_value_ratio_ma7` top 10% 的 +120d lift +2.29%。
本探索的 top 10% c=1 變體實際 +120d lift 是 **−0.06%**。差異原因：
- 最初快速分析用了「rolling future return」 (`p['ret_120d']`) 而非「forward return from trigger day」
- 本探索用 `df.merge(p)` 後計算 forward — 兩種 lookup 路徑不同（前者多了 weekday alignment 影響）

修正後的數字是正確的：**top 10% c=1 +120d 沒有 lift**。

## Vs. Expected

- **預期**：lift > +2% on +60d or +120d → ❌ 只在 +60d 有，+120d 衰退到 ≤ +1.31%
- **預期**：cluster 8-30 合理事件感 → ❌ 通過 lift 門檻的變體 cluster 36-77（太密）
- **預期**：非 bull regime 仍 robust → ❌ 完全失敗
- **預期**：與 H085 互補 → ✓ Jaccard ≤ 0.04

## Gate Decision

- [ ] 進入 Phase 2
- [x] **Archive (reject)**
- [ ] 修改假設

### Invalidation 條件觸發狀況

| # | 條件 | 結果 |
|---|---|---|
| 1 | 全部組合 +60d/+120d 都 ≤ DCA + 2% | ✗（+60d 多個 ≥ 2%） |
| 2 | top 10% c=1 cluster > 50 | ✗（35 個）|
| 3 | lift 為負 | **✓ 觸發** — +250d 全面負（−3% to −19%）|
| 4 | 非 bull 子樣本 +120d lift < +1% | **✓ 觸發** — 全部 variants 失敗 |
| 5 | Jaccard vs H085 > 0.3 | ✗（max 0.04） |

**Invalidation #3 + #4 觸發** → reject。

## 為什麼結論與初始 quick analysis 不同？

初始 raw quantile 分析顯示 +120d lift +2.29% 看起來有 edge，但深入後發現：
1. 該 lift 主要被 bull regime 撐起來
2. 拿掉 bull regime 後 lift 蒸發
3. +250d horizon 嚴重負數 — momentum chase 經典陷阱
4. 觸發頻率太高（cluster 35-77）不像稀有事件

**結論**：「漲停熱絡持續」**不是獨立動量訊號，而是 bull regime 的同步指標**。
與 H085 panic 不同 — H085 抓的是稀有 panic-to-rally 結構，而 H090 抓的是普通牛市日子。

## Combined finding with prior research

H079 (confirmed) + H089 (rejected) + H090 (rejected) 結合：
- 漲停**萎縮**（H079）= 真實 leading sell signal（panic 之前資金結構崩壞）
- 漲停**熱絡**（H090）= bull regime co-incident，無獨立預測力
- 廣度**新低/極值**（H089）= continuation 訊號，無 entry edge

**asymmetric finding**：漲停萎縮對下跌有預測力，但熱絡對上漲無預測力。
這是市場結構的常見現象 — fear 訊號比 greed 訊號可靠。

## Derived Hypotheses

- **不建議**繼續挖漲停 momentum 方向。三個失敗（H089、H090 本身）已強化「漲停爆量這個 dimension 沒 entry edge」。
- **可能的方向**：在 H085 panic 進場後，把 lu_value_ratio_ma7 上升突破 50 分位當「動量確認 → 加碼」訊號（不是進場 trigger，是 H085 內部的 sizing helper）。但這需要先確定 H085 加碼有沒有 benefit，可能 derive 為 HXXX-h085-momentum-add-on。
- **跌停爆量**：原始 correlation 分析中 `ld_value_ratio` top 5% 在 +120d 有 lift +1.82%（弱 mean-reversion）。Edge 太弱不建議做策略，已記錄不繼續。

## Files

- `explore.py` — Phase 1 grid 探索腳本
- `results/trigger_grid.csv` — 12 個變體的完整 metrics
- `results/distribution.md` — 本檔案
