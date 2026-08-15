# futures-backtest

A research toolchain for Taiwan index futures (TX) intraday strategies — raw TAIFEX
tick archives → DuckDB → backtests, plus a daily automated ETL and a pre-market
briefing email.

**But the system is not the interesting part. The research log is.**

> 140 hypotheses tested. **71 rejected.** 4 inconclusive. 52 confirmed.
> Every one of them is still in this repository, including the ones that failed.

*繁體中文完整說明（含安裝與操作手冊）→ [README.zh-TW.md](README.zh-TW.md)*

---

## Why the rejections are the point

Working with an LLM makes producing a plausible-looking result nearly free. Write a
prompt, get a chart, get a number that supports what you already believed. The
bottleneck in research stops being *generation* and becomes *rejection* — and
rejection is the part that has no dopamine attached to it.

So the workflow in this repo is built around one rule, enforced before any code runs:

> **Step 1.4 — Invalidation criteria: what result would mean this hypothesis is wrong?**
> *(must be defined before starting)*
> — [`.claude/skills/new-hypothesis/SKILL.md`](.claude/skills/new-hypothesis/SKILL.md)

You write down what would falsify the idea *first*. Then exploration runs. Then a
GATE decision — and the backtest skill refuses to run on a hypothesis that has not
passed its GATE. The result is `research/archive/rejected/`: 71 directories of ideas
that looked good in my head and did not survive contact with the data.

That ratio — 71 rejected to 52 confirmed — is the number I would want a reviewer to
look at. A research log with no failures in it is not a research log.

## The research loop

Six [Claude Code skills](.claude/skills/) implement the lifecycle. Each one writes to
the filesystem, so the state of every hypothesis is a directory you can read, diff and
review — not conversation history.

```
  /new-hypothesis   →  research/active/HXXX-name/
                       proposal.md  ← intuition, testable claim, INVALIDATION CRITERIA
                       tasks.md
                              │
  /explore          →  Phase 1: distribution study on historical data
                       distribution.md + GATE verdict
                              │
                       ┌──────┴──────┐
                    GATE fail     GATE pass
                       │              │
                       │       /backtest  →  Phase 2: walk-forward, parameter
                       │                     sensitivity, drawdown, losing streaks
                       │                     backtest.md + Verdict
                       │              │
  /archive          ←──┴──────────────┘
        │
        ├─ research/archive/confirmed/      (52)  ──/ship──→  strategies/live/  (4)
        ├─ research/archive/rejected/       (71)                     │
        └─ research/archive/inconclusive/    (4)                     ↓
                                                     indicators/tradingview/*.pine (14)
  /status  →  overview of everything in flight
```

Rules the skills enforce, not just suggest:

- Invalidation criteria must exist before Phase 1 starts.
- No backtest without a passing GATE.
- Every numeric conclusion must carry its sample size.
- Parameter optimisation requires out-of-sample validation before `Confirmed`.
- Exploration and backtest scripts are committed alongside the write-up — a result
  you cannot re-run is not a result.

## What you can run right now

Market data is not in this repository (it is ~27 GB and belongs to the exchanges).
The test suite deliberately does not need any of it:

```bash
asdf install        # Python 3.14.3t + uv, pinned in .tool-versions
uv sync
uv run pytest       # 197 tests, no market data required
```

All fixtures are synthesised in [`tests/synthetic.py`](tests/synthetic.py). The tests
worth reading first:

| File | What it pins down |
|---|---|
| [`tests/test_lookahead.py`](tests/test_lookahead.py) | **Look-ahead detection.** Perturbs every bar *after* a decision point and asserts the feature value at that point does not move. Also checks feature *semantics* — whether a "10-day moving average" is really 10 days. |
| [`tests/test_pipeline_invariants.py`](tests/test_pipeline_invariants.py) | Contracts that are otherwise only comments: indicators must be computed on full history *before* date filtering; warm-up must be `NaN` and never `0`; OHLC columns must not be positionally swapped. |
| [`tests/test_orb_long_rules.py`](tests/test_orb_long_rules.py) | Entry/exit rules driven through the real engine on synthetic days. Verified by mutation testing — eight strategy parameters were perturbed and every mutation was caught. |
| [`tests/test_runner_pure.py`](tests/test_runner_pure.py) | Settlement-date arithmetic, Wilder smoothing, volume adjustment. |

Two tests are marked `xfail(strict=True)`. They assert the *correct* behaviour for
known defects (see below); when a defect is fixed they turn into `XPASS` and fail the
build, which is the reminder to remove the marker.

The backtest engine itself is [backtesting.py](https://github.com/kernc/backtesting.py) —
a third-party library. What is tested here is the layer this repo owns: the features
fed into it, and the strategy rules built on top.

## Known gaps

Listed because a repository that claims to be about honest research should be honest
about itself.

1. **`_compute_daily_adx` has look-ahead.** Day *D*'s ADX is computed from day *D*'s
   full-session high/low, but the strategy reads it at 09:30 while the session is
   still running. The ADX filter is disabled by default (`adx_period=0`), so no live
   strategy is affected. Pinned by an `xfail` test; the fix is a one-line `.shift(1)`.
   Notably, an earlier study found ADX had no predictive value here — a filter that
   could see the future still found no edge, which strengthens that conclusion.
2. **`trend_ma_days` does not mean days.** `runner.py` uses
   `n_bars = trend_ma_days * 301`, where 301 is the *day-session* bar count — but it
   applies that window to a series that also contains the night session (1,142 bars
   per trading day). So `trend_ma_days=10` looks back roughly 2.6 trading days. The
   fallback path inside the strategy uses the same constant *correctly*, so the same
   parameter means different things depending on how data was loaded. The moving
   average is still trailing, so no result is invalidated — but the label is wrong.
3. **The Python ↔ Pine Script translation is unverified.** Confirmed strategies are
   reimplemented as TradingView indicators for actual execution, in a language that
   cannot run this backtest. Nothing checks that the two agree. Gap 2 is exactly the
   kind of thing that breaks in translation.
4. **The first day of any backtest never trades** — the opening-range indicator is
   `NaN` before 09:30, and the engine skips leading bars until all indicators are
   valid. On a short backtest window this silently removes a meaningful share of the
   sample.
5. **`end="YYYY-MM-DD"` excludes that whole day**, because it parses to midnight and
   the session starts at 08:45.
6. **Test coverage is targeted, not broad.** The feature layer and one strategy's
   rules are covered. The remaining strategies, the options backtest and the
   exploration scripts are not.

Gaps 4 and 5 are pinned by tests so they cannot regress silently.

## Repository layout

```
src/etl/            TAIFEX / TWSE / TPEX / FinMind ingestion → DuckDB
                    (download → parse → 1-min bars → Panama continuous contract → validate)
src/backtest/       data loading, feature computation, EstRange, optimisation
src/strategies/     strategy classes for backtesting.py
src/analysis/       pre-market briefing, key price levels, VIX regime, breadth thermometer
src/chart_ui/       FastAPI + lightweight-charts market browser

research/           140 hypotheses — active/ and archive/{confirmed,rejected,inconclusive}
strategies/live/    4 strategies promoted from confirmed hypotheses
indicators/         14 TradingView Pine Script indicators (the execution surface)
tests/              197 tests, synthetic fixtures only
.claude/skills/     the six research-lifecycle skills
```

## Stack

Python 3.14 (free-threaded) · uv · DuckDB · backtesting.py · pandas / numpy ·
FastAPI + lightweight-charts · matplotlib · Resend · launchd

Data sources: TAIFEX (futures and options tick archives), TWSE / TPEX (market breadth,
daily equity bars), FinMind (index and per-symbol minute bars), NDC (business cycle
indicator). Nothing is redistributed here — everything is fetched at run time.

## A note on language

Code identifiers, test names, directory names and the API surface are English. Prose —
docstrings, comments, the 140 research write-ups and 576 commit messages — is
Traditional Chinese, because that is the language I think in while doing this research
and translating it would have slowed the research down.

If you are evaluating this repository and do not read Chinese, the test suite is the
most readable entry point: test names state the property being asserted, and the
assertions themselves are language-neutral.

## Scope

Nothing here is investment advice, and backtested numbers are simulated results that
exclude costs and slippage. See [LICENSE](LICENSE).

MIT.
