# Archive: EstHL BB Over-extension Filter

## Status
Rejected

## Summary
測試「30m BB%B(20, open, 2σ) > 1 時 EstHL 進場的假突破率（fixed SL hit）顯著偏高」假設。雙 pool 設計（Pool A = S001 filtered entries / Pool B = raw ORB long breakout）2021–2026 共 5.4 年資料。**核心結論：效果為零**，Pool A BB>1 桶 SL rate (29.5%) 與整體 (29.3%) 完全相同；Pool B 反而顯示 BB>1 SL rate 比整體**低** 5.5pp（方向相反）。

## Key Evidence

### Pool A — S001 filtered (N=167, overall SL=29.3%)
- (0.5, 1] 桶：N=105, SL=29.5%
- (1, +∞) 桶：N=61, SL=29.5%（Δ vs overall = **+0.2pp**）
- 跨年度方向：3 favorable / 2 against / 1 neutral（含邊際）— 不一致

### Pool B — Raw ORB (N=682, overall SL=64.1%)
- (-∞, 0] 桶：N=97, SL=64.9%
- **(0, 0.5] 桶：N=207, SL=74.4%（Δ=+10.3pp，全 pool 最差）**
- (0.5, 1] 桶：N=267, SL=58.1%
- **(1, +∞) 桶：N=111, SL=58.6%（Δ=−5.5pp，反向）**
- 跨年度方向：3 favorable / 3 against — 完全平手

### GATE：4 條 1/4 通過
| GATE 條件 | 達成? |
|---|:---:|
| Pool A BB>1 桶 ≥ 20 筆 | ✅ N=61 |
| Pool A SL rate 差距 ≥ 10pp | ❌ 僅 +0.2pp |
| 5 年方向一致 ≥ 3 | ❌ |
| Pool B 確認方向一致 | ❌ Pool B 反向 |

## Why Rejected

1. **核心效果為零**：S001 濾網下，BB%B > 1 與 (0.5, 1] 兩桶 SL hit rate 完全相同（29.5% vs 29.5%）
2. **Pool B 反向**：無濾網下 BB>1 SL rate 反而較低（58.6% vs 整體 64.1%）— 與「過度延伸 = 易假突破」直覺相反
3. **跨年度不一致**：兩 pool 都未達 3/5 年一致方向

**事後解讀**（非結論）：
- S003 Exhaustion 用 BB>1 反向做空是 confirmed 的，但 Exhaustion 額外要求 `ma_up + NightNewHigh + ORB 跌破`。**BB>1 單一條件不足以代表「力竭」**，需配合夜盤新高與日內反向破壞才成立
- ORB 突破做多的本質是「動能延續」。BB>1 可能反而是「強勢市況」訊號，與 ORB 突破訊號性質互補（而非互斥）
- S001 既有的 VWAP + 30m MA20 + OR-width 濾網已天然把 entries 集中在 BB%B > 0.5 區段（Pool A 中 (0, 0.5] 桶只有 1 筆、(-∞, 0] 桶為 0），這也解釋了為何在 S001 上再加 BB 濾網無增量價值

## Derived Hypotheses

1. **「弱多頭區段 ORB 突破」假突破熱區研究**
   - Pool B (0, 0.5] 桶 SL rate 74.4%，比整體高 10.3pp，N=207 充足
   - Pool A 該桶 N=1（S001 已天然濾掉），對 S001 不 actionable
   - 反向應用：「BB%B ∈ (0, 0.5] 時做空 ORB 突破」可能有效，需另立假設驗證

2. **S003 Exhaustion 的 BB>1 條件需配合 NightNewHigh 才有效**
   - Pool B 上若加 NightNewHigh 篩選後再分桶，可驗證 BB>1 是否單靠夜盤新高才產生 exhaustion 效應
   - 若 BB>1 ∧ NightNewHigh 桶 SL rate 顯著高於 BB>1 ∧ ¬NightNewHigh，則證實 S003 的兩條件交互作用

3. **BB%B middle-cross 動量檢驗**
   - Pool B 顯示 BB%B = 0.5 是分水嶺（下方 74.4% SL vs 上方 58.1% SL）
   - 「30m BB%B 從 < 0.5 上穿 > 0.5 時的 ORB 突破」是否為真正的高品質訊號？

## Links

- Proposal: `proposal.md`
- Distribution: `results/distribution.md`
- Explore script: `explore.py`
- Tasks: `tasks.md`
- Raw trades: `results/pool_a_trades.csv`, `results/pool_b_trades.csv`
- Plots: `results/bbpct_hist.png`, `results/sl_rate_bars.png`, `results/yearly_heatmap.png`
