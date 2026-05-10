"""
H084 Step 0.8：保險絲層驗證 — Mode 1 / Mode 2 切換條件的歷史一致性。

雙條件設計（依 proposal v2）：
  條件A: TAIEX close < 250MA（即 dist_250ma_pct < 0）
  條件B: econ_blue_streak ≥ 3（連續 3 個月藍/黃藍燈）

兩種組合方式各跑一次：
  - mode2_AND = A AND B（保守：兩個都成立才切到 Mode 2）
  - mode2_OR  = A OR B  （敏感：任一成立就切）

驗證問題：
  1. 在 Tier A regime 期間（2008-2014、2022-2024），Mode 2 觸發比例多高？目標：高
  2. 在 Tier B/C regime 期間，Mode 2 觸發比例多低？目標：低
  3. 在事件以外的「正常多頭」期，Mode 2 應該幾乎不觸發
  4. 2015-08-24（hindsight Tier B macro，但 LIVE 指標可能 Mode 2）這種邊界事件如何

輸出：
  - results/fuse_state.csv     每日 mode 狀態（AND + OR 兩版）
  - results/fuse_chart.png     TAIEX + mode 切換時間軸
  - 終端：混淆矩陣 + 邊界事件清單
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd

RESULTS_DIR = Path(__file__).parent / "results"

BLUE_STREAK_THRESHOLD = 3


def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    indicators = pd.read_csv(RESULTS_DIR / "indicators.csv", parse_dates=["trade_date"])
    indicators["trade_date"] = indicators["trade_date"].dt.date
    events = pd.read_csv(RESULTS_DIR / "tiers.csv",
                         parse_dates=["peak_date", "trough_date", "recovery_date"])
    for col in ("peak_date", "trough_date", "recovery_date"):
        events[col] = pd.to_datetime(events[col]).dt.date
    return indicators, events


def compute_modes(indicators: pd.DataFrame) -> pd.DataFrame:
    df = indicators.copy()
    df["cond_A_below_250ma"] = df["taiex_dist_250ma_pct"] < 0
    df["cond_B_blue_streak"] = df["econ_blue_streak"] >= BLUE_STREAK_THRESHOLD
    df["mode2_AND"] = df["cond_A_below_250ma"] & df["cond_B_blue_streak"]
    df["mode2_OR"] = df["cond_A_below_250ma"] | df["cond_B_blue_streak"]
    return df


def assign_macro_tier_per_day(modes: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """每天標記它屬於哪一個 macro 事件期（None = 正常多頭）"""
    df = modes.copy()
    df["macro_tier"] = "bull"  # 預設值

    # 只用 macro 事件（parent_macro_idx is NaN 表示是 macro 自己）
    macros = events[events["parent_macro_idx"].isna()].copy()

    for _, ev in macros.iterrows():
        end_date = ev["recovery_date"] if pd.notna(ev["recovery_date"]) else df["trade_date"].max()
        mask = (df["trade_date"] >= ev["peak_date"]) & (df["trade_date"] <= end_date)
        df.loc[mask, "macro_tier"] = ev["tier"]
    return df


def confusion_summary(df: pd.DataFrame, mode_col: str) -> pd.DataFrame:
    """每個 macro_tier 內 Mode 2 觸發比例"""
    rows = []
    for tier in ["A", "B", "C", "D", "bull"]:
        sub = df[df["macro_tier"] == tier]
        if len(sub) == 0:
            continue
        n_total = len(sub)
        n_mode2 = sub[mode_col].sum()
        rows.append({
            "macro_tier": tier,
            "days": n_total,
            f"mode2_days": int(n_mode2),
            f"mode2_pct": round(n_mode2 / n_total * 100, 1),
        })
    return pd.DataFrame(rows)


def trough_mode_check(df: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """每個事件 trough day 的 mode 狀態"""
    main_events = events[events["tier"].isin({"A", "A-sub", "B", "B-sub", "C", "C-sub"})]
    rows = []
    for _, ev in main_events.iterrows():
        match = df[df["trade_date"] == ev["trough_date"]]
        if match.empty:
            continue
        r = match.iloc[0]
        rows.append({
            "trough_date": ev["trough_date"],
            "tier": ev["tier"],
            "parent_tier": ev["parent_macro_tier"],
            "dist_250ma": round(r["taiex_dist_250ma_pct"], 1) if pd.notna(r["taiex_dist_250ma_pct"]) else None,
            "blue_streak": int(r["econ_blue_streak"]) if pd.notna(r["econ_blue_streak"]) else None,
            "cond_A": bool(r["cond_A_below_250ma"]),
            "cond_B": bool(r["cond_B_blue_streak"]),
            "mode2_AND": bool(r["mode2_AND"]),
            "mode2_OR": bool(r["mode2_OR"]),
        })
    return pd.DataFrame(rows).sort_values("trough_date").reset_index(drop=True)


def plot_fuse_timeline(df: pd.DataFrame, events: pd.DataFrame, out_path: Path) -> None:
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 9), sharex=True,
                                    gridspec_kw={"height_ratios": [3, 1]})

    # Top: TAIEX with macro tier bands + mode2 shading
    ax1.plot(df["trade_date"], df["close"], color="#333", linewidth=0.7, zorder=2)

    tier_colors = {"A": "#c8102e", "B": "#e97132", "C": "#f4b400", "D": "#cccccc"}
    macros = events[events["parent_macro_idx"].isna()].copy()
    for _, ev in macros.iterrows():
        if ev["tier"] not in tier_colors:
            continue
        end = ev["recovery_date"] if pd.notna(ev["recovery_date"]) else df["trade_date"].max()
        ax1.axvspan(ev["peak_date"], end, color=tier_colors[ev["tier"]],
                    alpha=0.12, zorder=0)

    # 標記 trough 點
    main_ev = events[events["tier"].isin({"A", "B", "C", "A-sub", "B-sub", "C-sub"})]
    for _, ev in main_ev.iterrows():
        m = df[df["trade_date"] == ev["trough_date"]]
        if m.empty:
            continue
        is_sub = ev["tier"].endswith("-sub")
        col = tier_colors.get(ev["tier"][0], "#888")
        ax1.scatter([ev["trough_date"]], [m.iloc[0]["close"]],
                    color=col, s=20 if is_sub else 40,
                    marker="v" if is_sub else "o",
                    zorder=4, edgecolor="white", linewidth=0.8)

    ax1.set_title("TAIEX with macro Tier bands (Tier A=red / B=orange / C=yellow)", fontsize=11)
    ax1.set_ylabel("TAIEX Close")
    ax1.grid(True, alpha=0.3)

    # Bottom: mode state strip
    df_indexed = df.set_index("trade_date")
    dates = df_indexed.index
    # Plot mode2_AND as filled bars at y=2, mode2_OR at y=1 (showing only OR-not-AND extra triggers)
    ax2.fill_between(dates,
                     0, df_indexed["mode2_AND"].astype(int),
                     color="#c8102e", alpha=0.7, step="post", label="Mode 2 (AND)")
    or_extra = df_indexed["mode2_OR"].astype(int) - df_indexed["mode2_AND"].astype(int)
    ax2.fill_between(dates,
                     1.1, 1.1 + or_extra,
                     color="#f4a460", alpha=0.5, step="post", label="Mode 2 only-OR (extra)")
    ax2.set_ylim(-0.1, 2.3)
    ax2.set_yticks([0.5, 1.6])
    ax2.set_yticklabels(["AND", "OR-extra"])
    ax2.set_ylabel("Mode 2 active")
    ax2.set_xlabel("Date")
    ax2.legend(loc="upper right", fontsize=9)
    ax2.grid(True, alpha=0.3)
    ax2.xaxis.set_major_locator(mdates.YearLocator(2))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    fig.suptitle("Fuse layer validation: Mode 2 trigger timeline vs hindsight Tier macros (H084)", fontsize=13)
    fig.tight_layout()
    fig.savefig(out_path, dpi=110, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    indicators, events = load_data()
    print(f"Loaded indicators={indicators.shape}, events={len(events)}")

    modes = compute_modes(indicators)
    daily = assign_macro_tier_per_day(modes, events)

    out_csv = RESULTS_DIR / "fuse_state.csv"
    daily.to_csv(out_csv, index=False)
    print(f"Daily mode state → {out_csv}")

    # Confusion summaries
    print("\n=== Mode 2 trigger rate by macro tier (AND) ===")
    print(confusion_summary(daily, "mode2_AND").to_string(index=False))

    print("\n=== Mode 2 trigger rate by macro tier (OR) ===")
    print(confusion_summary(daily, "mode2_OR").to_string(index=False))

    # Trough day mode state
    trough_states = trough_mode_check(daily, events)
    out_trough = RESULTS_DIR / "trough_mode_state.csv"
    trough_states.to_csv(out_trough, index=False)
    print(f"\nTrough mode state → {out_trough}")
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", None)
    print("\n=== Mode state at each trough ===")
    print(trough_states.to_string(index=False))

    # Boundary cases: hindsight tier vs live mode
    print("\n=== Boundary cases: hindsight tier ≠ live mode ===")
    bc_and = trough_states[
        ((trough_states["parent_tier"] == "A") & ~trough_states["mode2_AND"])
        | ((trough_states["parent_tier"].isin(["B", "C"])) & trough_states["mode2_AND"])
    ]
    print("(AND mode):")
    print(bc_and[["trough_date", "tier", "parent_tier", "dist_250ma",
                  "blue_streak", "cond_A", "cond_B", "mode2_AND"]].to_string(index=False))

    out_chart = RESULTS_DIR / "fuse_chart.png"
    plot_fuse_timeline(daily, events, out_chart)
    print(f"\nChart → {out_chart}")


if __name__ == "__main__":
    main()
