# futures-backtest

A research toolchain for Taiwan index futures (TX) intraday strategies — raw TAIFEX
tick archives → DuckDB → backtests, plus a daily automated ETL and a pre-market
briefing email.

**But the system is not the interesting part. The research log is.**

> 139 hypotheses. 126 have a verdict: **71 rejected**, 4 inconclusive, 51 confirmed.
> The other 13 are still open. Every one of them is in this repository, including the
> ones that failed.

*繁體中文完整說明（含安裝與操作手冊）→ [README.zh-TW.md](README.zh-TW.md)*

---

## Why the rejections are the point

Working with an LLM makes producing a plausible-looking result nearly free. Write a
prompt, get a chart, get a number that supports what you already believed. The
bottleneck in research stops being *generation* and becomes *rejection* — and
rejection is the part that has no dopamine attached to it.

So the workflow in this repo is built around one rule, which has to be satisfied
before any code runs:

> **Step 1.4 — Invalidation criteria: what result would mean this hypothesis is wrong?**
> *(must be defined before starting)*
> — [`.claude/skills/new-hypothesis/SKILL.md`](.claude/skills/new-hypothesis/SKILL.md)

You write down what would falsify the idea *first*. Then exploration runs. Then a
GATE decision, recorded in `distribution.md`, which the backtest skill is instructed
to read and refuse to proceed without. That is a constraint on the agent, not a
compiler error — it holds because the state lives in a file that can be checked, not
because anything enforces it at runtime. The result is `research/archive/rejected/`:
71 directories of ideas that looked good in my head and did not survive contact with
the data.

Three of them, to show what one actually looks like:

- [**H041** — rejected](research/archive/rejected/H041-reversal-skip-after-breakout/summary.md).
  I was confident these were the days producing bad trades, and wanted to filter them
  out. They turned out to be the *better* days (50% win rate versus 43%). The
  hypothesis was not refined, it was inverted.
- [**H083** — rejected before the formal study ran](research/archive/rejected/H083-lagged-concentration-vol-prediction/summary.md).
  Two exploration scripts were decisive enough that Phase 1 was never started. The
  gate exists to stop work early, not only to grade it afterwards.
- [**H008** — confirmed](research/archive/confirmed/H008-estrange-options/summary.md),
  and the write-up records that correcting how exits were priced cut the profit factor
  from 23.3 to 1.70. A confirmation is not a rubber stamp.

## The research loop

Five [Claude Code skills](.claude/skills/) implement the lifecycle. Each one writes to
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
        ├─ research/archive/confirmed/      (51)  ──by hand──→  strategies/live/ (3)
        ├─ research/archive/rejected/       (71)                       │
        └─ research/archive/inconclusive/    (4)                       ↓
                                                     indicators/tradingview/*.pine (14)
  /status  →  overview of everything in flight
```

Rules written into the skills, so they apply to every hypothesis rather than the ones
I remember to apply them to:

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
| [`tests/test_orb_long_rules.py`](tests/test_orb_long_rules.py) | Entry/exit rules driven through the real engine on synthetic days. Checked by hand-mutating each strategy parameter and confirming a test broke — done once while writing them, not wired into CI. |
| [`tests/test_runner_pure.py`](tests/test_runner_pure.py) | Settlement-date arithmetic, Wilder smoothing, volume adjustment. |

Two tests are marked `xfail(strict=True)`. They assert the *correct* behaviour for
known defects (see below); when a defect is fixed they turn into `XPASS` and fail the
build, which is the reminder to remove the marker.

The backtest engine itself is [backtesting.py](https://github.com/kernc/backtesting.py) —
a third-party library. What is tested here is the layer this repo owns: the features
fed into it, and the strategy rules built on top.

## Known gaps

Writing the tests above found a bug that had been shaping results for months.

**`trend_ma_days` does not mean days.** The trend moving average is computed as
`trend_ma_days * 301` bars, where 301 is the length of a *day session*
([`runner.py:189`](src/backtest/runner.py#L189), and hardcoded again at
[`runner.py:348`](src/backtest/runner.py#L348)). Both apply it to the continuous
series, which includes the night session at 1142 bars per trading day. So
`trend_ma_days=10` — described in [`orb.py:214`](src/strategies/orb.py#L214) as "the
10-day trend moving average" — actually looks back about 2.6 trading days. The same
constant is *correct* at `orb.py:51` and `orb.py:324`, where the series really is
day-session only. One parameter, two meanings, decided by which loader ran.

The consequence is not that the backtests are invalid — the average is still trailing,
with no look-ahead. It is that `trend_ma_days=10` was selected by optimisation *against
the 2.6-day version*. Fixing the constant does not fix the parameter; the search has to
be re-run.

There is also a latent one: `_compute_daily_adx` is never shifted, so day D's ADX is
computed from day D's own high and low. `adx_period` defaults to `0`, so the filter has
always been off and no strategy has ever read it.

Neither is fixed, because the first one invalidates the backtests that chose the
current parameters. Both are pinned by `xfail(strict=True)` tests asserting the
*correct* behaviour: when someone fixes one, the test starts passing, strict mode fails
the build, and that is the reminder to redo everything downstream. Write-ups are in
[`tests/test_lookahead.py`](tests/test_lookahead.py).

The largest untested surface is somewhere else entirely. Confirmed strategies are
reimplemented as TradingView Pine Script — the language they actually trade in, and one
that cannot run this backtest. Nothing checks that the two implementations agree.

## Repository layout

```
src/etl/            TAIFEX / TWSE / TPEX / FinMind ingestion → DuckDB
                    (download → parse → 1-min bars → Panama continuous contract → validate)
src/backtest/       data loading, feature computation, EstRange, optimisation
src/strategies/     strategy classes for backtesting.py
src/analysis/       pre-market briefing, key price levels, VIX regime, breadth thermometer
src/chart_ui/       FastAPI + lightweight-charts market browser

research/           139 hypotheses — active/ and archive/{confirmed,rejected,inconclusive}
strategies/live/    3 live strategies (5 were promoted; 2 are in strategies/retired/)
indicators/         14 TradingView Pine Script indicators (the execution surface)
tests/              197 tests, synthetic fixtures only
.claude/skills/     five research-lifecycle skills, plus /ship (a git helper)
```

## Stack

Python 3.14 (free-threaded) · uv · DuckDB · backtesting.py · pandas / numpy ·
FastAPI + lightweight-charts · matplotlib · Resend · launchd

Data sources: TAIFEX (futures and options tick archives), TWSE / TPEX (market breadth,
daily equity bars), FinMind (index and per-symbol minute bars), NDC (business cycle
indicator). Nothing is redistributed here — everything is fetched at run time.

## A note on language

Code identifiers, test names, directory names and the API surface are English. Most of
the prose — docstrings, comments, and the research write-ups — is Traditional Chinese,
because that is the language I think in while doing this research and translating it
would have slowed the research down. Commit subjects are mixed: of 580 commits, 255
have Chinese somewhere in the message.

If you are evaluating this repository and do not read Chinese, the test suite is the
most readable entry point: test names state the property being asserted, and the
assertions themselves are language-neutral.

## Scope

Nothing here is investment advice, and backtested numbers are simulated results that
exclude costs and slippage. See [LICENSE](LICENSE).

MIT.
