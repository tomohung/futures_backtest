# Futures Backtest Project Memory

## Research scope preference
- [feedback_research_scope.md](feedback_research_scope.md) — Phase 2 偏好現象描述性研究，非綁特定策略 filter 測試

## Phase 2 best params (baseline)
range_end=90, entry_end=120, sl_pct=0.005, tp_multiplier=1.5, trail=45, trend_ma=10
6-year total: +4,632 pts

## Phase 4 Hybrid best params
tp_or_multiplier=1.5, sl_pct=0.004, or_min_width=20.0, tp_multiplier=1.5
range_end=90, entry_end=120, trail=45, trend_ma=10
6-year total: +5,653 pts (longs: +4,509 / shorts: +1,144)
2021: +10   2022: +96   2023: +351   2024: +1,527   2025: +1,845   2026: +1,824

## ORBLongStrategy current best params (2021–2026)
sl_pct=0.004, tp_or_multiplier=1.5, or_min_width=20.0, trend_ma_days=10
or_pct_min=0.3, or_pct_max=1.0, force_exit_minute=300 (13:00)
skip_thursday=0, thu_or_pct_min=0.7
Results: trades=232, win=58.6%, Sharpe=3.96, total=+5,649
2021:-51  2022:+351  2023:+490  2024:+672  2025:+2,290  2026:+1,897

## Filter sweep results (ORBLong, 2021–2026)
- force_exit: 13:00 best (Sharpe 3.23), 13:45 highest pts but worst Sharpe
- OR% filter 0.3–1.0: Sharpe 1.36→1.54, total +4,615→+5,262, 2021 -499→-123
- skip_thursday=1: Sharpe 3.23→4.05, total +5,368→+5,580
- thu_or_pct_min=0.7 (skip Thu OR%<0.7 only): Sharpe 3.96, total +5,649 (best)
- Thursday win rate only 43%; 0.7–1.0% bucket is 55.6% win rate (+69 total)

## Key structural insights
- OR high SL for shorts is too wide → shorts fail in Phase 3A/3B/C
- Phase 4 OR-width TP improves longs; shorts kept on Phase 2 TP (Hybrid design)
- 2021 longs are structurally broken (win%=39%, exp=-6.6): mean-reverting bull market
- 2021 is NOT filterable via ATR%, ADX, or realized vol — indicators overlap with good years
- All approaches to fix 2021 cost more than they save — accept as regime outlier

## Long-only findings
- Removing shorts costs -1,144 pts total (shorts contribute positively overall)
- Long-only best: tp=1.5, sl=0.004 → +4,509 (same params as bilateral)
- Long-only 2021-safe: tp=1.0, sl=0.005 → +3,618 (2021=-28, but 2024 halved)
- ADX filter on longs: doesn't help, costs -500~-1,400 pts

## TradingView indicator
- Output file: `indicators/tradingview/orb_long_tx.pine`
- Always use `//@version=6`, script type: `indicator` (not `strategy`)
- OR% label: teal ✓ = pass, gray ✗ = OR% filtered, orange 週四✗ = Thursday filtered

## Pine Script v6 syntax rules (CRITICAL)
- Multiline expressions MUST be wrapped in parentheses — no implicit line continuation
- `plot()` arguments `linewidth` and `style` must be constants — cannot use series/conditional values
  - ✅ vary `color` with `color.new(c, in_pos ? 0 : 60)`
  - ❌ `linewidth = in_pos ? 2 : 1`

## 回測結果顯示規範
跑回測顯示結果時，除完整 metrics 外，必須附上：
1. **逐年分析** — 每年損益、筆數、勝率
2. **逐月分析** — 每月損益分布
3. **Weekday 分析** — 按星期幾分組的損益與勝率
4. **結算日分析** — 台指期結算日（每月第三個週三，遇非交易日延後）單獨分析

## Rejected vs Inconclusive 判定標準
- 研究過但沒有交易價值 = **rejected**（無 edge）
- **inconclusive** 僅用於結果真正不明確、未來可能重新探索的情況（如樣本不足、資料品質問題）
- 統計顯著但效應不足以產生 actionable edge → rejected

## NVF 4-tier 顯示（已實作於 H092 confirmed 之後,2026-05-17）
H092 confirmed cutoffs 0.8 / 1.0 / 1.2 — 4 tier 標籤:deep STOP / mid STOP / mid GO / strong GO。

實作:
- `src/analysis/key_prices.py`:`_classify_nvf_tier()` + `_NVF_TIER_CUTS` + `_compute_night_vol_filter` 加 `tier` 欄位
- morning_briefing 顯示拆 2 行:H092 tier(視覺+提示)+ H075 binary STOP/GO(策略濾網)
- `src/analysis/daily_range.py`:`get_night_vol_alert` 加 `tier`,4 tier 對應 4 種 bar color
- Binary STOP/GO 邏輯不變(H075 production behavior),tier 是 orthogonal 顯示
