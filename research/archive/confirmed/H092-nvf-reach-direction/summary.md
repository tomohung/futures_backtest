# Archive: NVF Reach Multiples & Direction Asymmetry

## Status
Confirmed(描述性發現)

## Summary
延伸 H070(夜盤波動 → 日盤 EstRange 觸及率)兩個未被回答的問題:0.75× 中段補完 + 方向 bias 拆解。1,264 天 (2021-01-04 ~ 2026-05-14) 樣本,深入研究發現:**「Strong GO lower bias」在 production EstHL 視角下大幅萎縮(−8.6pp → −2.5pp)**,原來是 fixed EmaHL 在高 vol 日的副作用,非真實方向偏空。Production SatZone reach 機率被 EstHL 自動「跨 tier normalize」,均落在 40-46% either-side。最佳 ladder exit m 跨年穩定:**B-sat(S001 SatZone) m=0.60 全 tier 通用**;A 定義(EmaHL ladder) m=0.30-0.45,**0.618 為次優**。

## Key Evidence

### 1. 4-bucket NVF 切分(cutoffs 0.8 / 1.0 / 1.2)
- Tier 樣本:deep STOP N=430、mid STOP N=299、mid GO N=221、strong GO N=314
- Signed return:strong GO mean −0.056% / median +0.078% / std 1.045%(其他 tier 1.5×)
- 結論:strong GO 是「tail risk」而非「方向偏空」

### 2. 三種 reach 定義對比(2h 窗 08:45-10:45)

| 定義 | strong GO upper 0.618 reach | 對 ladder 含義 |
|---|---|---|
| A (open-anchored, EmaHL) | 26.4% | 可預掛單,tier-dependent |
| B-est (running, EstHL no buffer) | 53.8% | 動態,EstHL 量大日拉高 target |
| B-sat (running, S001 production) | 73.6% | 含 /8 buffer,**跨 tier 均勻 40-46%** |

### 3. EstHL/EmaHL ratio by tier
- deep STOP: 0.79 → 0.86(量縮 → 縮小 target)
- strong GO: 1.05 → 1.13(量大 → 拉高 target)
- **這個自動 normalize 把 fixed-EmaHL 視角下的 tier-dependent reach 拉平**

### 4. 最佳 m scan(0.10-1.50,step 0.05)

| 定義 | 跨 tier opt_m 範圍 | 跨年穩定性 |
|---|---|---|
| A | 0.30-0.60 | **不穩**(年範圍 0.20-0.35) |
| B-sat | 0.55-0.70 | **穩定**(年範圍 0.15-0.40,多數 0.55-0.70) |

### 5. IS / OOS 穩健性(2021-2024 vs 2025-2026)
- 4 個 B-sat cell 達成 **IS=OOS opt_m 完全一致**:
  - mid STOP short(m=0.55)
  - mid GO long(m=0.60)
  - strong GO long(m=0.60)
  - strong GO short(m=0.55)
- A 定義有 2 個明顯 overfit(mid GO up: IS 0.35 → OOS 0.60;strong GO dn: IS 0.60 → OOS 0.45)

### 6. 5-unit front-heavy E[R] at optimum

| 環境 | A (5 × opt m) | B-sat (5 × m=0.60) |
|---|---|---|
| strong GO long | 1.02 R | **1.97 R** ⭐ |
| mid GO long | 1.00 R | 1.78 R |
| strong GO short | 0.96 R | 1.86 R |
| mid GO short | 0.78 R | 1.70 R |
| deep STOP short | 0.75 R | 1.48 R |

→ B-sat 比 A 高近 2 倍 E[R],但需要看盤。

## Why Confirmed
- **描述性發現有 standalone 價值**:重新詮釋了 NVF tier 對日盤的影響本質
- **跨年穩定**:B-sat 在 IS/OOS 多個 cell 達成完全一致 opt_m,沒有 overfit
- **可立即落地的應用**:
  1. Ladder exit 統一改用 m=0.60(B-sat)取代 0.618
  2. Morning briefing NVF 多階顯示升級(已在 memory 記下)
- **澄清了 Phase 1 的誤解**:「Strong GO lower bias」在 production 視角下大幅縮減,**不需要進入策略 backtest** 階段(原 Phase 2 plan)

## Phase 1 vs Phase 2 主要 reinterpretation

| Phase 1 結論(B-old 視角) | Phase 2 修正(B-sat 視角) |
|---|---|
| Strong GO −8.6pp lower bias at 1.0× | 縮減為 −2.5pp |
| Strong GO 適合 short(lower 機率高) | **Strong GO long 略優**(E[R/unit] 0.40 vs 0.37) |
| 0.618 是 sweet spot | A 定義最佳 m≈0.40;B-sat≈0.60(0.618 OK) |
| 2025 是 regime 反例 | 跨年掃描看 2025 不極端,OOS 表現大多優於 IS |
| Bipolar GO 結構強 | 結構縮減,主要為 mid GO upper bias +5pp 仍清晰 |

## Derived Hypotheses

1. **H093 候選 — Mid-GO long-bias 策略應用驗證**
   - Mid GO upper bias 跨 3 種 reach 定義都成立(+5 to +9pp at 0.618)
   - IS/OOS B-sat 完全一致(m=0.60),最穩定 cell
   - 是否能 boost S001 / ORB long-only 策略 PF?

2. **H094 候選 — Tail-risk-aware position sizing**
   - Strong GO std 1.5×、p10 −1.12%(最差)
   - 進場前已知 tier → 動態調整單筆部位大小
   - 對比 fixed sizing 的 max drawdown 改善

3. **H095 候選 — Production EstHL ratio 預測效用**
   - EstHL/EmaHL ratio first valid(09:00-09:15)是否有預測力?
   - 例如 ratio > 1.1 早盤是否預測高機率 0.618 reach?

4. **H096 候選 — 2h 窗口外的 trend 連續性**
   - 60% 的天高/低在 2h 內就鎖定
   - 那剩下 40% late-extreme 是否有條件可預測?
   - 連結 path shape(L-then-H / H-then-L)分析

## Live 落地建議

### A. Morning briefing NVF 多階顯示(已 pending,在 memory)

- 替換 `src/analysis/key_prices.py:_compute_night_vol_filter` 為多階 label
- 替換 `src/analysis/daily_range.py:get_night_vol_alert` 同理
- 4 tier 用 cutoffs 0.8 / 1.0 / 1.2(與本研究一致)

### B. S001 SatZone 出場參數可考慮統一 m=0.60

- 目前 S001 SatZone Upper = `session_low + EmaHL − EmaHL/8`(相當於 m=1.0)
- 改為 `session_low + 0.60 × EstHL − EmaHL/8`(m=0.60)可能提升 reach 機率與 E[R]
- 需 backtest 驗證(本研究只算理論 E[R],未驗收 PF / Sharpe / drawdown)

## Links
- Proposal: `proposal.md`
- Phase 1 distribution: `results/distribution.md`
- Phase 2 main: `results/market_structure.md`
- Scripts: `explore.py`、`explore_4bucket.py`、`explore_cutoff_sensitivity.py`、`phase2_market_structure.py`、`phase2_reach_2h.py`、`phase2_reach_4tier.py`、`phase2_reach_definitions.py`、`phase2_satzone_reach.py`、`phase2_reach_production_esthl.py`、`phase2_ladder_bsat.py`、`phase2_optimal_m_scan.py`、`phase2_optimal_m_yearly.py`
- Plots: `results/h092_*.png`(10+ 張)
- CSVs: `results/*.csv`(20+ 個)
