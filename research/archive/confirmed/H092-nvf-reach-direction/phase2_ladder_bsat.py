#!/usr/bin/env python3
"""H092 Phase 2 — 5-unit ladder E[R] under B-sat (S001 production EstHL).

回應 user 要求:在 production S001 視角下重算 5-unit ladder。

對每個 tier × direction:
    1. 計算每個 m 的 reach probability(B-sat,running anchor + dynamic EstHL + EmaHL/8 buffer)
    2. 計算每個 m 的 profit per unit(以 EmaHL 為單位)
    3. 計算每個 m 的 E[R per unit] = P(reach m) × profit
    4. 比較幾種 ladder 配置:
        - A. 5-unit front-heavy (all at m=0.618)
        - F. 3-2 split (3@0.618 + 2@0.75)
        - L. 1-2-1-1 mid-loaded (1@0.618, 2@0.75, 1@1.0, 1@1.2)
        - B. 1-1-1-1-1 full ladder

使用方式:
    uv run python research/active/H092-nvf-reach-direction/phase2_ladder_bsat.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

OUT_DIR = Path("research/active/H092-nvf-reach-direction/results")
OUT_DIR.mkdir(parents=True, exist_ok=True)

MULTIPLES = [0.618, 0.75, 0.875, 1.0, 1.2]
TIER_LABELS = ["deep STOP", "mid STOP", "mid GO", "strong GO"]
DIRECTIONS = ["upper (long)", "lower (short)"]

# Reach probabilities under B-sat (from phase2_reach_production_esthl.py output)
P_REACH = {
    ("deep STOP", "upper"): [0.765, 0.570, 0.393, 0.281, 0.142],
    ("deep STOP", "lower"): [0.800, 0.626, 0.409, 0.263, 0.133],
    ("mid STOP", "upper"):  [0.773, 0.589, 0.448, 0.264, 0.124],
    ("mid STOP", "lower"):  [0.709, 0.562, 0.411, 0.241, 0.144],
    ("mid GO", "upper"):    [0.765, 0.552, 0.403, 0.262, 0.122],
    ("mid GO", "lower"):    [0.747, 0.520, 0.348, 0.208, 0.086],
    ("strong GO", "upper"): [0.736, 0.519, 0.331, 0.217, 0.089],
    ("strong GO", "lower"): [0.666, 0.462, 0.325, 0.242, 0.121],
}

# EstHL / EmaHL median ratio at last valid bar (from phase2_reach_production_esthl output)
EST_HL_RATIO = {
    "deep STOP": 0.829,
    "mid STOP": 0.905,
    "mid GO": 0.966,
    "strong GO": 1.089,
}

# Ladder schemes: dict from m to # units at that level
SCHEMES = {
    "A. front-heavy (5@0.618)": {0.618: 5},
    "F. 3-2 split":              {0.618: 3, 0.75: 2},
    "G. 3-1-1 mix":              {0.618: 3, 0.75: 1, 1.0: 1},
    "L. 1-2-1-1 mid-loaded":     {0.618: 1, 0.75: 2, 1.0: 1, 1.2: 1},
    "B. 1-1-1-1-1 full ladder":  {0.618: 1, 0.75: 1, 0.875: 1, 1.0: 1, 1.2: 1},
    "T. 2-1-1-1 tail (less front)": {0.618: 2, 0.75: 1, 0.875: 1, 1.0: 1},
}


def profit_at(m, ratio):
    """profit per unit at multiple m, in EmaHL units (with /8 buffer)."""
    return m * ratio - 1 / 8


def conditional_state_probs(p_reach):
    """Convert P(reach m) array (sorted by m) into mutually exclusive bin probs.

    Returns list of (state_label, prob) for outcomes:
        ["none", "≥m1 not m2", "≥m2 not m3", ..., "≥mlast"]
    """
    states = []
    p_prev = 1.0  # P(reach < m[0]) base
    states.append(("no reach", 1 - p_reach[0]))
    for i in range(len(p_reach) - 1):
        states.append((f"reach m={MULTIPLES[i]} only", p_reach[i] - p_reach[i + 1]))
    states.append((f"reach m={MULTIPLES[-1]}", p_reach[-1]))
    return states


def evaluate_scheme(scheme, p_reach, profits):
    """Compute E[R total] and SD for a ladder scheme.

    scheme: dict m -> n_units
    p_reach: list of P(reach m) for each m in MULTIPLES
    profits: list of profit per unit at each m
    """
    # Get reach probabilities for the scheme's levels
    m_to_p = dict(zip(MULTIPLES, p_reach))
    m_to_profit = dict(zip(MULTIPLES, profits))

    # Construct mutually exclusive outcomes
    # State i: max m reached is MULTIPLES[i], or "none" before m[0]
    # P(state i) = P(reach m[i]) - P(reach m[i+1])
    # In state i, all units at levels ≤ m[i] fill, others don't
    outcomes = []  # list of (P, R)
    n_levels = len(MULTIPLES)

    # State 0: no reach
    p_none = 1 - p_reach[0]
    outcomes.append((p_none, 0.0))

    # States 1..n_levels: max reach is MULTIPLES[i]
    for i in range(n_levels):
        # State: reach m[i] but not m[i+1] (or fully reach if i is last)
        if i < n_levels - 1:
            p_state = p_reach[i] - p_reach[i + 1]
        else:
            p_state = p_reach[i]
        if p_state < 0:
            p_state = 0  # safety
        max_m_reached = MULTIPLES[i]
        # All units at levels ≤ max_m_reached fill
        r_total = sum(n_units * m_to_profit[m]
                      for m, n_units in scheme.items()
                      if m <= max_m_reached)
        outcomes.append((p_state, r_total))

    # Verify P sums to 1
    p_sum = sum(p for p, _ in outcomes)
    if abs(p_sum - 1.0) > 1e-6:
        print(f"  WARNING: P sum = {p_sum}")

    # Compute E[R] and Var
    e_r = sum(p * r for p, r in outcomes)
    e_r2 = sum(p * r ** 2 for p, r in outcomes)
    var = max(0, e_r2 - e_r ** 2)
    sd = np.sqrt(var)
    sharpe = e_r / sd if sd > 0 else np.nan

    # Probability of positive outcome
    p_positive = sum(p for p, r in outcomes if r > 0)
    # Worst case
    r_min = min(r for _, r in outcomes)
    # Best case
    r_max = max(r for _, r in outcomes)

    return {
        "E[R]": e_r,
        "SD": sd,
        "Sharpe-like": sharpe,
        "p_positive": p_positive,
        "r_min": r_min,
        "r_max": r_max,
    }


def main():
    print("=" * 100)
    print("H092 Phase 2 — 5-unit ladder under B-sat (S001 production EstHL)")
    print("=" * 100)
    print(f"\n{'Multiples:':<20} {MULTIPLES}")
    print(f"{'B-sat formula:':<20} target = running_low + m × EstHL − EmaHL/8")
    print(f"{'profit/unit:':<20} = m × (EstHL/EmaHL) − 0.125, in EmaHL units")

    print("\n" + "─" * 100)
    print("Profit per unit by tier × multiple (EmaHL units, with /8 buffer)")
    print("─" * 100)
    print(f"{'Tier':<12} {'ratio':>6} " + " ".join([f"  m={m}" for m in MULTIPLES]))
    profits_by_tier = {}
    for tier in TIER_LABELS:
        ratio = EST_HL_RATIO[tier]
        profits = [profit_at(m, ratio) for m in MULTIPLES]
        profits_by_tier[tier] = profits
        print(f"{tier:<12} {ratio:>6.3f} " +
              " ".join([f"  {p:>5.3f}" for p in profits]))

    print("\n" + "─" * 100)
    print("E[R per unit] = P(reach m) × profit(m) — sort by best m per tier × direction")
    print("─" * 100)
    for direction_key, direction_label in zip(["upper", "lower"], ["Long (upper)", "Short (lower)"]):
        print(f"\n  {direction_label}:")
        print(f"  {'Tier':<12} " + " ".join([f"  m={m}" for m in MULTIPLES]))
        for tier in TIER_LABELS:
            profits = profits_by_tier[tier]
            p_reach = P_REACH[(tier, direction_key)]
            er = [p * pr for p, pr in zip(p_reach, profits)]
            best_idx = int(np.argmax(er))
            line = f"  {tier:<12} "
            for i, val in enumerate(er):
                marker = "*" if i == best_idx else " "
                line += f"  {val:>5.3f}{marker}"
            print(line)

    # Evaluate schemes
    print("\n" + "=" * 100)
    print("Ladder scheme evaluation by tier × direction")
    print("=" * 100)
    print("All values in EmaHL units. E[R] is total expected return for 5 units.")
    print("Sharpe-like = E[R] / SD (per-trade,沒考慮多次交易).")

    all_results = []
    for tier in TIER_LABELS:
        for direction_key, direction_label in zip(["upper", "lower"], ["Long", "Short"]):
            print(f"\n──── {tier} × {direction_label} ────")
            p_reach = P_REACH[(tier, direction_key)]
            profits = profits_by_tier[tier]

            print(f"  P(reach m): {[f'{p*100:.1f}%' for p in p_reach]}")
            print(f"  Profits:    {[f'{p:.3f}' for p in profits]} EmaHL")
            print()
            print(f"  {'Scheme':<35} {'E[R]':>7} {'SD':>7} {'Sharpe':>7} {'P>0':>7} {'rmin':>7} {'rmax':>7}")
            print(f"  {'-'*35} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*7}")
            for name, scheme in SCHEMES.items():
                res = evaluate_scheme(scheme, p_reach, profits)
                print(f"  {name:<35} {res['E[R]']:>7.3f} {res['SD']:>7.3f} "
                      f"{res['Sharpe-like']:>7.3f} {res['p_positive']*100:>6.1f}% "
                      f"{res['r_min']:>7.3f} {res['r_max']:>7.3f}")
                all_results.append({
                    "tier": tier, "direction": direction_label, "scheme": name,
                    "E_R": res["E[R]"], "SD": res["SD"],
                    "Sharpe": res["Sharpe-like"],
                    "p_positive": res["p_positive"],
                    "r_min": res["r_min"], "r_max": res["r_max"],
                })

    # Save & summary
    results_df = pd.DataFrame(all_results)
    results_df.to_csv(OUT_DIR / "ladder_bsat_evaluation.csv", index=False)

    # ── Summary: best E[R] per tier × direction ──
    print("\n" + "=" * 100)
    print("SUMMARY: best scheme per tier × direction")
    print("=" * 100)
    print(f"{'Tier':<12} {'Dir':<8} {'Best by E[R]':<35} {'E[R]':>7} {'SD':>7} {'Sharpe':>7}")
    for tier in TIER_LABELS:
        for direction_label in ["Long", "Short"]:
            sub = results_df[(results_df["tier"] == tier) &
                             (results_df["direction"] == direction_label)]
            best = sub.loc[sub["E_R"].idxmax()]
            print(f"{tier:<12} {direction_label:<8} {best['scheme']:<35} "
                  f"{best['E_R']:>7.3f} {best['SD']:>7.3f} {best['Sharpe']:>7.3f}")

    print("\n" + "=" * 100)
    print("SUMMARY: best Sharpe per tier × direction")
    print("=" * 100)
    print(f"{'Tier':<12} {'Dir':<8} {'Best by Sharpe':<35} {'E[R]':>7} {'SD':>7} {'Sharpe':>7}")
    for tier in TIER_LABELS:
        for direction_label in ["Long", "Short"]:
            sub = results_df[(results_df["tier"] == tier) &
                             (results_df["direction"] == direction_label)]
            best = sub.loc[sub["Sharpe"].idxmax()]
            print(f"{tier:<12} {direction_label:<8} {best['scheme']:<35} "
                  f"{best['E_R']:>7.3f} {best['SD']:>7.3f} {best['Sharpe']:>7.3f}")

    print(f"\nResults CSV saved: {OUT_DIR / 'ladder_bsat_evaluation.csv'}")


if __name__ == "__main__":
    main()
