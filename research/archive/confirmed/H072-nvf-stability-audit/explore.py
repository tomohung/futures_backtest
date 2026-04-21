#!/usr/bin/env python3
"""H072 Phase 1: NVF Stability Audit by Weekday × Strategy × Period.

對 H066/H067 confirmed 的 NVF (night_norm >= 0.85) 做 sub-cell 健康度檢查：
  T1  重建 baseline & 重現 H066/H067 aggregate 結論
  T2  (strategy × weekday × year) cell 矩陣
  T3  Rolling 2-year window
  T4  IS (2021-23) vs OOS (2024-26)
  T5  反向 cell 的 threshold sweep (0.70/0.85/1.00/1.15)
  T6  Exhaustion (control, 不用 NVF) 對照

Usage:
    uv run python research/active/H072-nvf-stability-audit/explore.py
"""

import bisect
from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import TwoSlopeNorm

from backtesting import Backtest

from src.backtest.runner import (
    load_data_for_orb_est_hl,
    load_data_for_reversal,
    load_data_for_exhaustion,
)
from src.strategies.orb_est_hl_exit import ORBWithEstHLExitStrategy
from src.strategies.reversal import ReversalStrategy
from src.strategies.exhaustion import ExhaustionStrategy

DB_PATH = "data/futures.duckdb"
OUT_DIR = Path("research/active/H072-nvf-stability-audit/results")
OUT_DIR.mkdir(parents=True, exist_ok=True)

plt.rcParams["font.size"] = 10

# 解掉所有 weekday filter（公平比較 5 個 weekday）
ESTHL_PARAMS = dict(sl_ema_fraction=0.25, adx_min=0.0, long_only=True, vwap_days=2,
                    skip_thursday=False, skip_friday=False)
REVERSAL_PARAMS = dict(vol_ratio=1.2, sl_ema_fraction=0.25, exhaust_fraction=0.5,
                       signal_skip=0, sat_pullback_fraction=0.5)
EXHAUSTION_PARAMS = dict(skip_wed=False, skip_thu=False)

WD_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri"]
NVF_THRESH = 0.85
THRESHOLDS = [0.70, 0.85, 1.00, 1.15]
IS_END = "2023-12-31"
OOS_START = "2024-01-01"
MIN_N_CELL = 5  # 樣本門檻


# ─────────────────────────── helpers ───────────────────────────

def calc(t: pd.DataFrame) -> dict:
    n = len(t)
    if n == 0:
        return {"N": 0, "WR": 0.0, "PF": np.nan, "avg": 0.0, "total": 0.0}
    w = t[t["PnL"] > 0]["PnL"].sum()
    l = abs(t[t["PnL"] <= 0]["PnL"].sum())
    return {
        "N": n,
        "WR": (t["PnL"] > 0).sum() / n,
        "PF": w / l if l > 0 else float("inf"),
        "avg": t["PnL"].mean(),
        "total": t["PnL"].sum(),
    }


def run_strategy(name: str, runner_fn, strategy_cls, params: dict) -> pd.DataFrame:
    print(f"[{name}] loading + running backtest...")
    df = runner_fn()
    bt = Backtest(df, strategy_cls, cash=200_000, commission=0.0, trade_on_close=True)
    stats = bt.run(**params)
    trades = stats["_trades"].copy()
    trades["EntryTime"] = pd.to_datetime(trades["EntryTime"])
    trades["trade_date"] = trades["EntryTime"].dt.normalize()
    trades["weekday"] = trades["EntryTime"].dt.dayofweek
    trades["year"] = trades["EntryTime"].dt.year
    print(f"[{name}] trades: {len(trades)}")
    return trades


def compute_night_norm() -> pd.DataFrame:
    """Same as H066/H067/H071."""
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        day_dates_df = conn.execute("""
            SELECT DISTINCT timestamp::DATE AS trade_date
            FROM ohlcv_1m WHERE symbol = 'TX'
              AND timestamp::TIME >= '08:45' AND timestamp::TIME < '13:45'
            ORDER BY trade_date
        """).df()
        day_dates_list = sorted(pd.to_datetime(day_dates_df["trade_date"]).tolist())

        night_raw = conn.execute("""
            SELECT timestamp, high, low FROM ohlcv_1m WHERE symbol = 'TX'
              AND (timestamp::TIME >= '15:00' OR timestamp::TIME < '05:00')
            ORDER BY timestamp
        """).df()

    night_raw["timestamp"] = pd.to_datetime(night_raw["timestamp"])

    def find_next(ts):
        cal_time = ts.time()
        if cal_time >= pd.Timestamp("15:00").time():
            search_date = (ts + pd.Timedelta(days=1)).normalize()
        else:
            search_date = ts.normalize()
        idx = bisect.bisect_left(day_dates_list, search_date)
        return day_dates_list[idx] if idx < len(day_dates_list) else None

    night_raw["trade_date"] = night_raw["timestamp"].apply(find_next)
    night_raw = night_raw.dropna(subset=["trade_date"])

    night = night_raw.groupby("trade_date").agg(
        night_high=("high", "max"), night_low=("low", "min"),
        night_bars=("high", "count"),
    )
    night["night_range"] = night["night_high"] - night["night_low"]
    night = night[night["night_bars"] >= 100].copy()
    night["sma20"] = night["night_range"].rolling(20).mean()
    night["night_norm"] = night["night_range"] / night["sma20"]
    return night


def merge_nvf(trades: pd.DataFrame, night: pd.DataFrame) -> pd.DataFrame:
    return trades.merge(night[["night_norm"]], left_on="trade_date",
                        right_index=True, how="left")


# ─────────────────────────── analyses ───────────────────────────

def task1_baseline(strats: dict) -> None:
    """重現 H066/H067 aggregate 結論。"""
    print("\n" + "=" * 78)
    print("T1: aggregate baseline (重現 H066/H067)")
    print("=" * 78)
    for name, m in strats.items():
        b = calc(m)
        h = calc(m[m["night_norm"] >= NVF_THRESH])
        l = calc(m[m["night_norm"] < NVF_THRESH])
        diff_pct = (h["PF"] - l["PF"]) / l["PF"] * 100 if l["PF"] > 0 else np.nan
        print(f"\n  {name}:")
        print(f"    Baseline (all):     N={b['N']:4d}  PF={b['PF']:.2f}  WR={b['WR']:.1%}")
        print(f"    NVF HIGH (>={NVF_THRESH}):  N={h['N']:4d}  PF={h['PF']:.2f}  WR={h['WR']:.1%}")
        print(f"    NVF LOW (< {NVF_THRESH}):   N={l['N']:4d}  PF={l['PF']:.2f}  WR={l['WR']:.1%}")
        print(f"    HIGH vs LOW PF diff: {diff_pct:+.1f}%")


def task2_cell_matrix(strats: dict) -> tuple[dict, list[dict]]:
    """(strategy × weekday × year) cell matrix。"""
    print("\n" + "=" * 78)
    print("T2: Cell matrix (strategy × weekday × year)")
    print("=" * 78)
    years = sorted({y for m in strats.values() for y in m["year"].unique()})
    matrices = {}  # name -> {weekday → {year → ΔPF}}
    reverse_cells = []  # list of dicts: {strategy, weekday, year, base, nvf, delta, n}

    for name, m in strats.items():
        print(f"\n── {name} ──  (cells: NVF_PF / baseline_PF, ΔPF)")
        header = "  Day  " + "  ".join(f"{y:>15}" for y in years)
        print(header)
        mat = {wd: {y: np.nan for y in years} for wd in range(5)}
        for wd in range(5):
            cells = []
            for y in years:
                sub = m[(m["weekday"] == wd) & (m["year"] == y)]
                base = calc(sub)
                nvf = calc(sub[sub["night_norm"] >= NVF_THRESH])
                if base["N"] == 0 or nvf["N"] == 0:
                    cells.append(f"{'—':>15}")
                    continue
                bp = base["PF"] if np.isfinite(base["PF"]) else np.nan
                np_ = nvf["PF"] if np.isfinite(nvf["PF"]) else np.nan
                delta = np_ - bp if not (np.isnan(np_) or np.isnan(bp)) else np.nan
                mat[wd][y] = delta
                cells.append(f"{np_:>5.2f}/{bp:>4.2f} ({nvf['N']:>2})")
                if not np.isnan(delta) and delta < 0 and nvf["N"] >= MIN_N_CELL:
                    reverse_cells.append({
                        "strategy": name, "weekday": WD_NAMES[wd], "wd_idx": wd,
                        "year": y, "base_N": base["N"], "base_PF": bp,
                        "nvf_N": nvf["N"], "nvf_PF": np_, "delta": delta,
                    })
            print(f"  {WD_NAMES[wd]:>3}  " + "  ".join(cells))
        matrices[name] = mat

    print(f"\n── Reverse cells (ΔPF < 0 且 NVF N ≥ {MIN_N_CELL}) ──")
    print(f"  total: {len(reverse_cells)}")
    for r in reverse_cells:
        print(f"    {r['strategy']:>10} {r['weekday']} {r['year']}  "
              f"base PF={r['base_PF']:.2f}(N={r['base_N']})  "
              f"NVF PF={r['nvf_PF']:.2f}(N={r['nvf_N']})  Δ={r['delta']:+.2f}")
    return matrices, reverse_cells


def task3_rolling(strats: dict) -> dict:
    """Rolling 2-year window。"""
    print("\n" + "=" * 78)
    print("T3: Rolling 2-year window (ΔPF per weekday)")
    print("=" * 78)
    windows = [(2021, 2022), (2022, 2023), (2023, 2024), (2024, 2025), (2025, 2026)]
    rolling = {}  # name -> {weekday -> [ΔPF per window]}
    for name, m in strats.items():
        print(f"\n── {name} ──")
        header = "  Day  " + "  ".join(f"{a}-{b}".rjust(11) for a, b in windows)
        print(header)
        wd_data = {wd: [] for wd in range(5)}
        for wd in range(5):
            cells = []
            for a, b in windows:
                sub = m[(m["weekday"] == wd) & (m["year"].between(a, b))]
                base = calc(sub)
                nvf = calc(sub[sub["night_norm"] >= NVF_THRESH])
                if nvf["N"] < MIN_N_CELL or not np.isfinite(base["PF"]):
                    wd_data[wd].append(np.nan)
                    cells.append(f"{'—':>11}")
                    continue
                np_ = nvf["PF"] if np.isfinite(nvf["PF"]) else np.nan
                delta = np_ - base["PF"]
                wd_data[wd].append(delta)
                cells.append(f"{delta:>+5.2f}({nvf['N']:>2})")
            print(f"  {WD_NAMES[wd]:>3}  " + "  ".join(cells))
        rolling[name] = wd_data
    return rolling


def task4_is_oos(strats: dict) -> list[dict]:
    """IS (2021-23) vs OOS (2024-26)。"""
    print("\n" + "=" * 78)
    print(f"T4: IS ({IS_END.split('-')[0][:4]}-2023) vs OOS (2024-2026) NVF effect")
    print("=" * 78)
    drift_cells = []
    for name, m in strats.items():
        print(f"\n── {name} ──")
        is_m = m[m["trade_date"] <= IS_END]
        oos_m = m[m["trade_date"] >= OOS_START]
        print(f"  {'Day':>4}  {'IS_base':>7} {'IS_NVF':>7} {'IS_Δ':>7} {'IS_N':>5}   "
              f"{'OOS_base':>8} {'OOS_NVF':>8} {'OOS_Δ':>7} {'OOS_N':>6}  drift?")
        for wd in range(5):
            is_sub = is_m[is_m["weekday"] == wd]
            oos_sub = oos_m[oos_m["weekday"] == wd]
            is_base = calc(is_sub); is_nvf = calc(is_sub[is_sub["night_norm"] >= NVF_THRESH])
            oos_base = calc(oos_sub); oos_nvf = calc(oos_sub[oos_sub["night_norm"] >= NVF_THRESH])
            is_d = (is_nvf["PF"] - is_base["PF"]) if (np.isfinite(is_nvf["PF"]) and np.isfinite(is_base["PF"])) else np.nan
            oos_d = (oos_nvf["PF"] - oos_base["PF"]) if (np.isfinite(oos_nvf["PF"]) and np.isfinite(oos_base["PF"])) else np.nan
            drifted = (
                is_nvf["N"] >= MIN_N_CELL and oos_nvf["N"] >= MIN_N_CELL
                and not np.isnan(is_d) and not np.isnan(oos_d)
                and is_d > 0 and oos_d < 0
            )
            tag = " ⚠ DRIFT" if drifted else ""
            print(f"  {WD_NAMES[wd]:>4}  "
                  f"{is_base['PF']:>7.2f} {is_nvf['PF']:>7.2f} {is_d:>+7.2f} {is_nvf['N']:>5}   "
                  f"{oos_base['PF']:>8.2f} {oos_nvf['PF']:>8.2f} {oos_d:>+7.2f} {oos_nvf['N']:>6}{tag}")
            if drifted:
                drift_cells.append({
                    "strategy": name, "weekday": WD_NAMES[wd], "wd_idx": wd,
                    "is_PF_NVF": is_nvf["PF"], "is_PF_base": is_base["PF"], "is_delta": is_d,
                    "oos_PF_NVF": oos_nvf["PF"], "oos_PF_base": oos_base["PF"], "oos_delta": oos_d,
                    "is_N": is_nvf["N"], "oos_N": oos_nvf["N"],
                })
    print(f"\n── DRIFT cells (IS NVF positive, OOS NVF negative) ──")
    print(f"  total: {len(drift_cells)}")
    for d in drift_cells:
        print(f"    {d['strategy']:>10} {d['weekday']}  IS Δ={d['is_delta']:+.2f}(N={d['is_N']})  "
              f"→ OOS Δ={d['oos_delta']:+.2f}(N={d['oos_N']})")
    return drift_cells


def task5_threshold_sweep(strats: dict, reverse_cells: list[dict],
                          drift_cells: list[dict]) -> pd.DataFrame:
    """Threshold sweep on reverse + drift cells."""
    print("\n" + "=" * 78)
    print("T5: Threshold sweep (0.70/0.85/1.00/1.15) on suspect cells")
    print("=" * 78)
    # Build candidate cell set: drift cells (full strategy×weekday) + reverse cells (with year)
    cands = set()
    for d in drift_cells:
        cands.add((d["strategy"], d["wd_idx"], None))  # None = all years OOS
    # Group reverse cells by (strategy, wd) when there are >=2 reverse years for same cell
    rev_by_cell = {}
    for r in reverse_cells:
        k = (r["strategy"], r["wd_idx"])
        rev_by_cell.setdefault(k, []).append(r["year"])
    for (s, wd), years in rev_by_cell.items():
        if len(years) >= 2:
            cands.add((s, wd, "recent"))  # 2024-2026 only

    rows = []
    for (s_name, wd, period) in sorted(cands, key=lambda x: (x[0], x[1])):
        m = strats[s_name]
        if period == "recent":
            sub = m[(m["weekday"] == wd) & (m["year"] >= 2024)]
            label = f"{s_name} {WD_NAMES[wd]} 2024-26"
        else:  # OOS
            sub = m[(m["weekday"] == wd) & (m["trade_date"] >= OOS_START)]
            label = f"{s_name} {WD_NAMES[wd]} OOS"
        base = calc(sub)
        print(f"\n  {label}  baseline N={base['N']}  PF={base['PF']:.2f}")
        for thr in THRESHOLDS:
            nvf = calc(sub[sub["night_norm"] >= thr])
            if nvf["N"] == 0:
                print(f"    NVF≥{thr}:  N=0  (empty)")
                continue
            delta = nvf["PF"] - base["PF"] if np.isfinite(nvf["PF"]) else np.nan
            tag = " ✓ recovers" if delta > 0 else " ✗"
            print(f"    NVF≥{thr}:  N={nvf['N']:3d}  PF={nvf['PF']:.2f}  WR={nvf['WR']:.1%}  Δ={delta:+.2f}{tag}")
            rows.append({
                "label": label, "threshold": thr,
                "base_N": base["N"], "base_PF": base["PF"],
                "nvf_N": nvf["N"], "nvf_PF": nvf["PF"],
                "delta": delta, "WR": nvf["WR"],
            })
    return pd.DataFrame(rows)


def task6_exhaustion_control(esth_m: pd.DataFrame, drift_cells: list[dict]) -> None:
    """Check if Exhaustion shows same NVF pattern in drift cells."""
    print("\n" + "=" * 78)
    print("T6: Exhaustion control — same cells (是市場結構還是策略特性？)")
    print("=" * 78)
    if not drift_cells:
        print("  No drift cells from T4 — skip control comparison.")
        return
    print(f"  {'Cell':>30}  {'OOS_base':>9} {'OOS_NVF':>9} {'OOS_Δ':>7} {'OOS_N':>6}  verdict")
    for d in drift_cells:
        # Run same OOS NVF cut on Exhaustion for this weekday
        oos = esth_m[(esth_m["trade_date"] >= OOS_START) & (esth_m["weekday"] == d["wd_idx"])]
        base = calc(oos); nvf = calc(oos[oos["night_norm"] >= NVF_THRESH])
        delta = (nvf["PF"] - base["PF"]) if (np.isfinite(nvf["PF"]) and np.isfinite(base["PF"])) else np.nan
        verdict = "MARKET (also negative)" if (not np.isnan(delta) and delta < 0) else \
                  ("STRATEGY (Exhaustion OK)" if not np.isnan(delta) else "—small N")
        cell = f"{d['strategy']} {d['weekday']}"
        print(f"  {cell:>30}  {base['PF']:>9.2f} {nvf['PF']:>9.2f} {delta:>+7.2f} {nvf['N']:>6}  {verdict}")


# ─────────────────────────── plotting ────────────────────────────────────

def plot_cell_heatmaps(matrices: dict, years: list):
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    fig.suptitle("H072 (T2): NVF ΔPF Heatmap by Weekday × Year", fontsize=13)
    for ax, (name, mat) in zip(axes, matrices.items()):
        arr = np.array([[mat[wd].get(y, np.nan) for y in years] for wd in range(5)])
        norm = TwoSlopeNorm(vmin=-2.0, vcenter=0.0, vmax=2.0)
        im = ax.imshow(arr, cmap="RdYlGn", aspect="auto", norm=norm)
        ax.set_xticks(range(len(years))); ax.set_xticklabels(years)
        ax.set_yticks(range(5)); ax.set_yticklabels(WD_NAMES)
        ax.set_title(f"{name}  (NVF_PF − baseline_PF)")
        for i in range(5):
            for j in range(len(years)):
                v = arr[i, j]
                if np.isnan(v):
                    ax.text(j, i, "—", ha="center", va="center", fontsize=9, color="gray")
                else:
                    ax.text(j, i, f"{v:+.1f}", ha="center", va="center", fontsize=9,
                            color="white" if abs(v) > 1.0 else "black")
        fig.colorbar(im, ax=ax, fraction=0.04)
    plt.tight_layout()
    p = OUT_DIR / "h072_t2_heatmap.png"
    plt.savefig(p, dpi=150, bbox_inches="tight"); plt.close()
    print(f"\nSaved → {p}")


def plot_rolling(rolling: dict):
    windows = ["21-22", "22-23", "23-24", "24-25", "25-26"]
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    fig.suptitle("H072 (T3): Rolling 2-year ΔPF by Weekday", fontsize=13)
    for ax, (name, wd_data) in zip(axes, rolling.items()):
        for wd in range(5):
            ax.plot(windows, wd_data[wd], marker="o", label=WD_NAMES[wd])
        ax.axhline(0, color="black", linewidth=0.7, linestyle="--")
        ax.set_title(name); ax.set_ylabel("ΔPF (NVF − baseline)")
        ax.legend(fontsize=8); ax.grid(alpha=0.3)
    plt.tight_layout()
    p = OUT_DIR / "h072_t3_rolling.png"
    plt.savefig(p, dpi=150, bbox_inches="tight"); plt.close()
    print(f"Saved → {p}")


def plot_threshold_sweep(sweep_df: pd.DataFrame):
    if sweep_df.empty:
        return
    labels = sorted(sweep_df["label"].unique())
    fig, ax = plt.subplots(figsize=(12, 5))
    for lbl in labels:
        sub = sweep_df[sweep_df["label"] == lbl].sort_values("threshold")
        ax.plot(sub["threshold"], sub["delta"], marker="o", label=lbl)
    ax.axhline(0, color="black", linewidth=0.7, linestyle="--")
    ax.set_xlabel("NVF threshold")
    ax.set_ylabel("ΔPF (NVF − baseline)")
    ax.set_title("H072 (T5): Threshold sweep on suspect cells")
    ax.legend(fontsize=8, loc="best")
    ax.grid(alpha=0.3)
    plt.tight_layout()
    p = OUT_DIR / "h072_t5_threshold_sweep.png"
    plt.savefig(p, dpi=150, bbox_inches="tight"); plt.close()
    print(f"Saved → {p}")


# ─────────────────────────── main ────────────────────────────────────────

def main():
    print("=" * 78)
    print("H072: NVF Stability Audit — Phase 1")
    print("=" * 78)

    # 1) Run all 3 strategies (no weekday filter)
    raw = {}
    raw["EstHL"]      = run_strategy("EstHL", load_data_for_orb_est_hl,
                                     ORBWithEstHLExitStrategy, ESTHL_PARAMS)
    raw["Reversal"]   = run_strategy("Reversal", load_data_for_reversal,
                                     ReversalStrategy, REVERSAL_PARAMS)
    raw["Exhaustion"] = run_strategy("Exhaustion", load_data_for_exhaustion,
                                     ExhaustionStrategy, EXHAUSTION_PARAMS)

    # 2) Compute night_norm + merge
    print("\nComputing night_norm...")
    night = compute_night_norm()
    merged = {name: merge_nvf(t, night) for name, t in raw.items()}
    for name, m in merged.items():
        m_clean = m.dropna(subset=["night_norm"])
        print(f"  {name}: total={len(m)}  with NVF={len(m_clean)}")
        merged[name] = m_clean

    # 3) Save merged trades
    for name, m in merged.items():
        m.to_csv(OUT_DIR / f"trades_{name.lower()}_with_nvf.csv", index=False)

    # 4) Tasks
    task1_baseline(merged)
    matrices, reverse_cells = task2_cell_matrix(merged)
    rolling = task3_rolling(merged)
    drift_cells = task4_is_oos(merged)
    sweep_df = task5_threshold_sweep(merged, reverse_cells, drift_cells)
    task6_exhaustion_control(merged["Exhaustion"], drift_cells)

    # 5) Save intermediate CSVs
    pd.DataFrame(reverse_cells).to_csv(OUT_DIR / "reverse_cells.csv", index=False)
    pd.DataFrame(drift_cells).to_csv(OUT_DIR / "drift_cells.csv", index=False)
    sweep_df.to_csv(OUT_DIR / "threshold_sweep.csv", index=False)

    # 6) Plots
    years = sorted({y for m in merged.values() for y in m["year"].unique()})
    plot_cell_heatmaps(matrices, years)
    plot_rolling(rolling)
    plot_threshold_sweep(sweep_df)

    print("\nDone.")


if __name__ == "__main__":
    main()
