# Futures Backtest Project Memory

## Project
Taiwan futures (TX) day-session ORB strategy backtest using backtesting.py + DuckDB.

## Key files
- `src/strategies/orb.py` — all strategy classes
- `src/backtest/runner.py` — load_data, load_data_with_night_ma (supports TrendMA, RollingOR, DailyADX)
- `src/backtest/optimize_phase4.py` — Phase 4 grid (tp_or_multiplier × sl_pct)
- `src/backtest/optimize_phase4_hybrid.py` — Phase 4 Hybrid grid
- `src/backtest/optimize_phase5.py` — Phase 5: rolling OR regime filter grid
- `src/backtest/explore_night_day.py` — Phase 4 Step 0: night vs day range correlation
- `src/backtest/explore_regime.py` — Phase 6 Step 0: ADX/ATR%/RealVol regime indicator exploration
- `src/backtest/optimize_longonly.py` — Long-only grid (tp_or × sl_pct) + ADX filter grid
- `src/backtest/summary_all.py` — comprehensive cross-strategy year-by-year summary

## Strategy classes in orb.py
- `ORBStrategy` — Phase 2 baseline (fixed sl_pct SL/TP + sl_pct trailing)
- `ORBPhase3AStrategy` — OR-based SL + OR-width TP + bar trailing
- `ORBPhase3BStrategy` — OR-based SL + Super Trend exit
- `ORBPhase3BHybridStrategy` — longs ST exit / shorts Phase 2 (or long_only=1)
- `ORBPlanCStrategy` — OR SL both sides + momentum stall exit
- `ORBPlanCHybridStrategy` — longs OR SL / shorts fixed sl_pct, momentum exit both
- `ORBPhase4Strategy` — adaptive TP = entry ± tp_or_multiplier × max(OR_width, or_min_width)
- `ORBPhase4HybridStrategy` — longs OR-width TP / shorts Phase 2 TP; supports:
    - min_rolling_or (Phase 5 regime filter)
    - long_only=1 (skip shorts)
    - long_adx_min (ADX entry filter for longs)

## Phase 2 best params (baseline)
range_end=90, entry_end=120, sl_pct=0.005, tp_multiplier=1.5, trail=45, trend_ma=10
6-year total: +4,632 pts

## Phase 4 Hybrid best params (current best)
tp_or_multiplier=1.5, sl_pct=0.004, or_min_width=20.0, tp_multiplier=1.5
range_end=90, entry_end=120, trail=45, trend_ma=10
6-year total: +5,653 pts (longs: +4,509 / shorts: +1,144)

## Year-by-year performance (Ph4 Hybrid, both directions)
2021: +10   2022: +96   2023: +351   2024: +1,527   2025: +1,845   2026: +1,824

## Key structural insights
- OR high SL for shorts is too wide → shorts fail in Phase 3A/3B/C
- Plan C Hybrid fixed shorts via sl_pct SL + momentum exit
- Phase 4 OR-width TP improves longs; shorts kept on Phase 2 TP (Hybrid design)
- 2021 longs are structurally broken (win%=39%, exp=-6.6): mean-reverting bull market
- 2021 is NOT filterable via ATR%, ADX, or realized vol — indicators overlap with good years
- Phase 5 rolling OR filter: best viable (w=20, min=60) only gets 2021 to -189, costs -351 total
- Long-only with tp=1.0 sl=0.005: 2021 near-zero (-28) but total drops -891 vs original

## Long-only findings
- Removing shorts costs -1,144 pts total (shorts contribute positively overall)
- But shorts win rate consistently 41-50% (psychologically challenging)
- Long-only best total: tp=1.5, sl=0.004 → +4,509 (same params as bilateral)
- Long-only 2021-safe: tp=1.0, sl=0.005 → +3,618 (2021=-28, but 2024 halved)
- ADX filter on longs: doesn't help, costs -500~-1,400 pts

## Conclusion: 2021 is unresolvable
All approaches to fix 2021 cost more than they save. 2021 is a statistical regime outlier
(mean-reverting bull, low vol, narrow OR) that cannot be prospectively identified.
Best recommendation: accept Ph4 Hybrid (+5,653 total) or Long-only (+4,509) as final.

## ORBLongStrategy current best params (2021–2026)
```python
sl_pct           = 0.004
tp_or_multiplier = 1.5
or_min_width     = 20.0
trend_ma_days    = 10
or_pct_min       = 0.3    # OR% filter sweet spot
or_pct_max       = 1.0
force_exit_minute = 300   # 13:00 (sweep best; 13:30 was baseline)
skip_thursday    = 0      # use thu_or_pct_min instead
thu_or_pct_min   = 0.7   # skip Thu only when OR%<0.7%
```
Results (2021–2026): trades=232, win=58.6%, Sharpe=3.96, total=+5,649
2021:-51  2022:+351  2023:+490  2024:+672  2025:+2,290  2026:+1,897

## Filter sweep results (ORBLong, 2021–2026)
- force_exit: 13:00 best (Sharpe 3.23), 13:45 highest pts but worst Sharpe
- OR% filter 0.3–1.0: Sharpe 1.36→1.54, total +4,615→+5,262, 2021 -499→-123
- skip_thursday=1: Sharpe 3.23→4.05, total +5,368→+5,580
- thu_or_pct_min=0.7 (skip Thu OR%<0.7 only): Sharpe 3.96, total +5,649 (best)
- Thursday win rate only 43%; 0.7–1.0% bucket is 55.6% win rate (+69 total)

## Data notes
- Train: 2025-01-01 ~ 2025-12-31
- OOS: 2026-01-01 ~ 2026-03-02 (~34 trading days)
- load_data_with_night_ma params: trend_ma_days, rolling_or_window, adx_period

## Known bugs fixed
- `_compute_supertrend`: NaN propagation when comparing against uninitialized bands
- `ORBPhase3AStrategy`: trail_bars float64 → int cast needed
- `optimize_phase4_hybrid.py`: strip tp_multiplier before passing to ORBPhase4Strategy
- `ORBPhase4HybridStrategy` entry block: signals must be inside `if _regime_ok:` scope

## TradingView indicator
- Output file: `indicators/tradingview/orb_long_tx.pine`
- Always use `//@version=6`
- Script type: `indicator` (not `strategy`) — tracks position state manually for reliable signal detection
- OR% filter: 0.3%–1.0%; live label during OR window (yellow, updates each bar)
- OR% label: teal ✓ = pass, gray ✗ = OR% filtered, orange 週四✗ = Thursday filtered
- Thursday filter: skip_thursday + thu_or_pct_min=0.7 (allow Thu when OR%≥0.7%)

## Pine Script v6 syntax rules (CRITICAL — violations cause compile errors)
- **Multiline expressions MUST be wrapped in parentheses** — no implicit line continuation
  - ✅ `x = (\n  a and\n  b)`
  - ❌ `x = a and\n  b`  ← "end of line without line continuation"
- This applies to: ternary chains, boolean `and`/`or`, arithmetic across lines
- Every multiline assignment needs `= (` to open and `)` to close
- **`plot()` arguments `linewidth` and `style` must be constants** — cannot use series/conditional values
  - ✅ vary `color` with `color.new(c, in_pos ? 0 : 60)` (series transparency is allowed)
  - ❌ `linewidth = in_pos ? 2 : 1`  ← "series int" not accepted

## Workflow rule (from CLAUDE.md)
Any new strategy or phase MUST have a spec in specs/strategies/ BEFORE writing code.
