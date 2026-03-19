"""EstRange Credit Spread — Weekday × Exit Time Optimization

Runs a grid of (weekday, exit_time) combinations and summarizes results.
Also tests weekday combination portfolios (Step 3).
"""

import sys
from itertools import combinations

import pandas as pd

from src.backtest.backtest_estrange_options import run_backtest

# Grid parameters
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
EXIT_TIMES = ["10:30", "11:00", "11:30", "12:00", "12:30", "13:00", "13:30", "13:44"]

# Backtest defaults (matching current best config)
BT_DEFAULTS = dict(
    start="2025-07-01",
    end="2026-03-18",
    fraction=0.70,
    spread_pct=0.50,
    skip_settlement=True,
    min_gap=50,
    min_dte=0,
)


def compute_stats(df: pd.DataFrame) -> dict:
    """Compute summary stats from a trades DataFrame."""
    if df.empty:
        return {"n": 0, "wins": 0, "wr": 0.0, "pnl": 0.0, "pf": 0.0, "avg": 0.0}
    n = len(df)
    wins = (df["result"] == "Win").sum()
    win_pnl = df.loc[df["result"] == "Win", "pnl"].sum()
    loss_pnl = abs(df.loc[df["result"] == "Loss", "pnl"].sum())
    pf = win_pnl / loss_pnl if loss_pnl > 0 else float("inf")
    return {
        "n": n,
        "wins": int(wins),
        "wr": round(wins / n * 100, 1),
        "pnl": round(df["pnl"].sum(), 1),
        "pf": round(pf, 2),
        "avg": round(df["pnl"].mean(), 1),
    }


def step1_weekday_exit_grid():
    """Step 1: Run weekday × exit_time grid."""
    print("=" * 70)
    print("  Step 1: Weekday × Exit Time Grid")
    print("=" * 70)

    # Load 1-min data once (shared across all runs)
    # run_backtest loads it internally; we rely on its caching
    results = []

    for wd in WEEKDAYS:
        for et in EXIT_TIMES:
            print(f"  Running {wd} × exit={et}...", end=" ", flush=True)
            df = run_backtest(**BT_DEFAULTS, exit_time_str=et, weekdays=[wd])
            stats = compute_stats(df)
            stats["weekday"] = wd
            stats["exit_time"] = et
            results.append(stats)
            print(f"n={stats['n']}, WR={stats['wr']}%, PnL={stats['pnl']:+.1f}, PF={stats['pf']}")

    # Build summary table
    df_results = pd.DataFrame(results)

    # Pivot: rows=weekday, cols=exit_time, values=pnl
    print(f"\n{'--- PnL by Weekday × Exit Time ---':^70}")
    pivot_pnl = df_results.pivot(index="weekday", columns="exit_time", values="pnl")
    pivot_pnl = pivot_pnl.reindex(WEEKDAYS)
    pivot_pnl = pivot_pnl[EXIT_TIMES]
    print(pivot_pnl.to_string())

    print(f"\n{'--- WR% by Weekday × Exit Time ---':^70}")
    pivot_wr = df_results.pivot(index="weekday", columns="exit_time", values="wr")
    pivot_wr = pivot_wr.reindex(WEEKDAYS)
    pivot_wr = pivot_wr[EXIT_TIMES]
    print(pivot_wr.to_string())

    print(f"\n{'--- PF by Weekday × Exit Time ---':^70}")
    pivot_pf = df_results.pivot(index="weekday", columns="exit_time", values="pf")
    pivot_pf = pivot_pf.reindex(WEEKDAYS)
    pivot_pf = pivot_pf[EXIT_TIMES]
    print(pivot_pf.to_string())

    print(f"\n{'--- Trade Count by Weekday × Exit Time ---':^70}")
    pivot_n = df_results.pivot(index="weekday", columns="exit_time", values="n")
    pivot_n = pivot_n.reindex(WEEKDAYS)
    pivot_n = pivot_n[EXIT_TIMES]
    print(pivot_n.to_string())

    # Best exit time per weekday
    print(f"\n{'--- Best Exit Time per Weekday (by PnL) ---':^70}")
    for wd in WEEKDAYS:
        wd_rows = df_results[df_results["weekday"] == wd]
        if wd_rows.empty:
            continue
        best = wd_rows.loc[wd_rows["pnl"].idxmax()]
        print(f"  {wd}: exit={best['exit_time']}, PnL={best['pnl']:+.1f}, WR={best['wr']}%, PF={best['pf']}, n={best['n']}")

    # Save raw results
    df_results.to_csv("output/estrange_weekday_exit_grid.csv", index=False)
    print("\nGrid saved → output/estrange_weekday_exit_grid.csv")

    return df_results


def step3_weekday_combos(best_exits: dict[str, str] | None = None):
    """Step 3: Compare weekday combinations.

    Parameters
    ----------
    best_exits : dict mapping weekday → best exit_time.
        If None, uses 13:44 for all.
    """
    print("\n" + "=" * 70)
    print("  Step 3: Weekday Combination Comparison")
    print("=" * 70)

    combos = {
        "A: All (Mon~Fri)": ["Mon", "Tue", "Wed", "Thu", "Fri"],
        "B: Tue+Fri": ["Tue", "Fri"],
        "C: Tue+Wed+Fri": ["Tue", "Wed", "Fri"],
        "D: Mon+Tue+Wed+Fri (no Thu)": ["Mon", "Tue", "Wed", "Fri"],
        "E: Tue+Wed+Thu+Fri (no Mon)": ["Tue", "Wed", "Thu", "Fri"],
    }

    if best_exits is None:
        best_exits = {wd: "13:44" for wd in WEEKDAYS}

    results = []
    for label, days in combos.items():
        # Run each weekday with its best exit time, then combine
        all_trades = []
        for wd in days:
            et = best_exits.get(wd, "13:44")
            df = run_backtest(**BT_DEFAULTS, exit_time_str=et, weekdays=[wd])
            all_trades.append(df)

        combined = pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame()
        stats = compute_stats(combined)
        stats["combo"] = label
        stats["days"] = ",".join(days)
        stats["exits"] = ",".join(best_exits.get(d, "13:44") for d in days)
        results.append(stats)
        print(f"  {label}: n={stats['n']}, WR={stats['wr']}%, PnL={stats['pnl']:+.1f}, PF={stats['pf']}")

    df_combos = pd.DataFrame(results)
    df_combos.to_csv("output/estrange_weekday_combos.csv", index=False)
    print("\nCombos saved → output/estrange_weekday_combos.csv")
    return df_combos


def step4_spread_pct_grid(best_exits: dict[str, str], combo_days: list[str]):
    """Step 4: Weekday × spread_pct grid, using each weekday's best exit time.

    Parameters
    ----------
    best_exits : dict mapping weekday → best exit_time
    combo_days : list of weekdays to test (e.g. D combo = Mon,Tue,Wed,Fri)
    """
    SPREAD_PCTS = [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.70, 0.80]

    print("\n" + "=" * 70)
    print("  Step 4: Weekday × Spread Pct Grid (D combo)")
    print("=" * 70)

    results = []
    for wd in combo_days:
        et = best_exits.get(wd, "13:44")
        for sp in SPREAD_PCTS:
            print(f"  {wd} exit={et} spread_pct={sp:.2f}...", end=" ", flush=True)
            bt_args = {**BT_DEFAULTS, "spread_pct": sp}
            df = run_backtest(**bt_args, exit_time_str=et, weekdays=[wd])
            stats = compute_stats(df)
            stats["weekday"] = wd
            stats["exit_time"] = et
            stats["spread_pct"] = sp
            # Avg credit and avg spread_width
            if not df.empty:
                stats["avg_credit"] = round(df["credit"].mean(), 1)
                stats["avg_spread"] = round(df["spread_width"].mean(), 0)
                stats["avg_cr_pct"] = round(df["cr_pct"].mean(), 1)
            else:
                stats["avg_credit"] = 0
                stats["avg_spread"] = 0
                stats["avg_cr_pct"] = 0
            results.append(stats)
            print(f"n={stats['n']}, WR={stats['wr']}%, PnL={stats['pnl']:+.1f}, PF={stats['pf']}, CR%={stats['avg_cr_pct']}%")

    df_results = pd.DataFrame(results)

    # Pivot tables
    print(f"\n{'--- PnL by Weekday × Spread Pct ---':^70}")
    pivot = df_results.pivot(index="weekday", columns="spread_pct", values="pnl")
    pivot = pivot.reindex(combo_days)
    print(pivot.to_string())

    print(f"\n{'--- PF by Weekday × Spread Pct ---':^70}")
    pivot_pf = df_results.pivot(index="weekday", columns="spread_pct", values="pf")
    pivot_pf = pivot_pf.reindex(combo_days)
    print(pivot_pf.to_string())

    print(f"\n{'--- CR% by Weekday × Spread Pct ---':^70}")
    pivot_cr = df_results.pivot(index="weekday", columns="spread_pct", values="avg_cr_pct")
    pivot_cr = pivot_cr.reindex(combo_days)
    print(pivot_cr.to_string())

    # Best spread_pct per weekday
    print(f"\n{'--- Best Spread Pct per Weekday (by PnL) ---':^70}")
    for wd in combo_days:
        wd_rows = df_results[df_results["weekday"] == wd]
        if wd_rows.empty:
            continue
        best = wd_rows.loc[wd_rows["pnl"].idxmax()]
        print(f"  {wd}: spread_pct={best['spread_pct']:.2f}, PnL={best['pnl']:+.1f}, PF={best['pf']}, CR%={best['avg_cr_pct']}%")

    # D combo total with each spread_pct (uniform)
    print(f"\n{'--- D Combo Total by Spread Pct ---':^70}")
    combo_totals = []
    for sp in SPREAD_PCTS:
        sp_rows = df_results[df_results["spread_pct"] == sp]
        total_pnl = sp_rows["pnl"].sum()
        total_n = sp_rows["n"].sum()
        total_wins = sp_rows["wins"].sum()
        wr = round(total_wins / total_n * 100, 1) if total_n > 0 else 0
        combo_totals.append({"spread_pct": sp, "n": total_n, "wr": wr, "pnl": round(total_pnl, 1)})
        print(f"  spread_pct={sp:.2f}: n={total_n}, WR={wr}%, PnL={total_pnl:+.1f}")

    df_results.to_csv("output/estrange_spread_pct_grid.csv", index=False)
    print(f"\nGrid saved → output/estrange_spread_pct_grid.csv")
    return df_results


def step5_fraction_grid(best_exits: dict[str, str], combo_days: list[str]):
    """Step 5: Weekday × fraction grid, with max_spread=200.

    Parameters
    ----------
    best_exits : dict mapping weekday → best exit_time
    combo_days : list of weekdays to test
    """
    FRACTIONS = [0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90]

    print("\n" + "=" * 70)
    print("  Step 5: Weekday × Fraction Grid (D combo, max_spread=200)")
    print("=" * 70)

    results = []
    for wd in combo_days:
        et = best_exits.get(wd, "13:44")
        for frac in FRACTIONS:
            print(f"  {wd} exit={et} fraction={frac:.2f}...", end=" ", flush=True)
            bt_args = {**BT_DEFAULTS, "fraction": frac, "max_spread": 200}
            df = run_backtest(**bt_args, exit_time_str=et, weekdays=[wd])
            stats = compute_stats(df)
            stats["weekday"] = wd
            stats["exit_time"] = et
            stats["fraction"] = frac
            results.append(stats)
            print(f"n={stats['n']}, WR={stats['wr']}%, PnL={stats['pnl']:+.1f}, PF={stats['pf']}")

    df_results = pd.DataFrame(results)

    # Pivot tables
    print(f"\n{'--- PnL by Weekday × Fraction ---':^70}")
    pivot_pnl = df_results.pivot(index="weekday", columns="fraction", values="pnl")
    pivot_pnl = pivot_pnl.reindex(combo_days)
    print(pivot_pnl.to_string())

    print(f"\n{'--- WR% by Weekday × Fraction ---':^70}")
    pivot_wr = df_results.pivot(index="weekday", columns="fraction", values="wr")
    pivot_wr = pivot_wr.reindex(combo_days)
    print(pivot_wr.to_string())

    print(f"\n{'--- PF by Weekday × Fraction ---':^70}")
    pivot_pf = df_results.pivot(index="weekday", columns="fraction", values="pf")
    pivot_pf = pivot_pf.reindex(combo_days)
    print(pivot_pf.to_string())

    print(f"\n{'--- Trade Count by Weekday × Fraction ---':^70}")
    pivot_n = df_results.pivot(index="weekday", columns="fraction", values="n")
    pivot_n = pivot_n.reindex(combo_days)
    print(pivot_n.to_string())

    # Best fraction per weekday
    print(f"\n{'--- Best Fraction per Weekday (by PnL) ---':^70}")
    for wd in combo_days:
        wd_rows = df_results[df_results["weekday"] == wd]
        if wd_rows.empty:
            continue
        best = wd_rows.loc[wd_rows["pnl"].idxmax()]
        print(f"  {wd}: fraction={best['fraction']:.2f}, PnL={best['pnl']:+.1f}, WR={best['wr']}%, PF={best['pf']}, n={best['n']}")

    # D combo total with each fraction (uniform)
    print(f"\n{'--- D Combo Total by Fraction ---':^70}")
    for frac in FRACTIONS:
        f_rows = df_results[df_results["fraction"] == frac]
        total_pnl = f_rows["pnl"].sum()
        total_n = f_rows["n"].sum()
        total_wins = f_rows["wins"].sum()
        wr = round(total_wins / total_n * 100, 1) if total_n > 0 else 0
        print(f"  fraction={frac:.2f}: n={total_n}, WR={wr}%, PnL={total_pnl:+.1f}")

    df_results.to_csv("output/estrange_fraction_grid.csv", index=False)
    print(f"\nGrid saved → output/estrange_fraction_grid.csv")
    return df_results


def main():
    import sys

    mode = sys.argv[1] if len(sys.argv) > 1 else "all"

    # Step 1 best exits (from previous run, or re-run)
    BEST_EXITS = {"Mon": "11:30", "Tue": "11:30", "Wed": "10:30", "Thu": "11:30", "Fri": "12:00"}
    D_COMBO = ["Mon", "Tue", "Wed", "Fri"]

    if mode in ("all", "step1"):
        df_grid = step1_weekday_exit_grid()
        # Update best exits from fresh results
        for wd in WEEKDAYS:
            wd_rows = df_grid[df_grid["weekday"] == wd]
            if not wd_rows.empty:
                best_row = wd_rows.loc[wd_rows["pnl"].idxmax()]
                BEST_EXITS[wd] = best_row["exit_time"]
        print(f"\nBest exits: {BEST_EXITS}")

    if mode in ("all", "step3"):
        step3_weekday_combos(BEST_EXITS)

    if mode in ("all", "step4", "spread"):
        step4_spread_pct_grid(BEST_EXITS, D_COMBO)

    if mode in ("all", "step5", "fraction"):
        step5_fraction_grid(BEST_EXITS, D_COMBO)


if __name__ == "__main__":
    main()
