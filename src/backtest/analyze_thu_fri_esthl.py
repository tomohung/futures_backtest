"""
分析 EstHL 策略週四/五交易，探索是否有條件可以保留部份交易。

分析維度：
  1. OR%      = ORWidth / 開盤價 × 100
  2. SatZone 距離 = (SatZoneUpper - entry_price) / EmaHL  （entry 距滿足區幾個 EmaHL）

用法: uv run python src/backtest/analyze_thu_fri_esthl.py
"""

import os
import pandas as pd
import numpy as np

from src.backtest.runner import load_data_for_orb_est_hl

TRADE_FILES = [
    "output/orb_est_hl_2021-01-01_2024-12-31.csv",
    "output/orb_est_hl_2025-01-01_2025-12-31.csv",
    "output/orb_est_hl_2026-01-01_2026-03-12.csv",
]
WD = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"}


def load_trades() -> pd.DataFrame:
    dfs = []
    for f in TRADE_FILES:
        if os.path.exists(f):
            dfs.append(pd.read_csv(f))
        else:
            print(f"[WARN] 找不到 {f}")
    df = pd.concat(dfs, ignore_index=True)
    df["EntryTime"] = pd.to_datetime(df["EntryTime"])
    df["weekday"] = df["EntryTime"].dt.weekday
    df["date"] = df["EntryTime"].dt.normalize()
    return df


def enrich_with_bar_data(trades: pd.DataFrame, bar_df: pd.DataFrame) -> pd.DataFrame:
    """對每筆交易，查找進場 bar 的 ORWidth / RollingOR / SatZoneUpper / EmaHL。"""
    bar_df = bar_df.copy()
    bar_df.index = pd.to_datetime(bar_df.index)

    rows = []
    for _, t in trades.iterrows():
        entry_ts = t["EntryTime"]
        entry_price = t["EntryPrice"]

        # 找最接近進場時間的 bar（取 entry_ts 當分鐘 bar）
        if entry_ts in bar_df.index:
            bar = bar_df.loc[entry_ts]
        else:
            # fallback: 找當天 09:00 bar
            day_start = entry_ts.normalize() + pd.Timedelta(hours=9)
            if day_start in bar_df.index:
                bar = bar_df.loc[day_start]
            else:
                rows.append({**t, "or_pct": np.nan, "sat_dist_emaHL": np.nan, "or_width": np.nan})
                continue

        or_width   = bar["ORWidth"]
        rolling_or = bar["RollingOR"]
        sat_upper  = bar["SatZoneUpper"]
        ema_hl     = bar["EmaHL"]

        # 當日開盤（08:45 bar 的 Open）
        day_open_ts = entry_ts.normalize() + pd.Timedelta(hours=8, minutes=45)
        day_open = bar_df.loc[day_open_ts, "Open"] if day_open_ts in bar_df.index else entry_price

        or_pct = or_width / day_open * 100 if (not np.isnan(or_width) and day_open > 0) else np.nan

        # 進場距滿足區距離（以 EmaHL 為單位）
        sat_dist = (sat_upper - entry_price) / ema_hl if (
            not np.isnan(sat_upper) and not np.isnan(ema_hl) and ema_hl > 0
        ) else np.nan

        rows.append({**t,
                     "or_pct": or_pct,
                     "or_width": or_width,
                     "rolling_or": rolling_or,
                     "sat_upper": sat_upper,
                     "ema_hl": ema_hl,
                     "sat_dist_emaHL": sat_dist})

    return pd.DataFrame(rows)


def bucket_analysis(df: pd.DataFrame, col: str, bins, labels, title: str):
    df = df.copy()
    df[f"{col}_bin"] = pd.cut(df[col], bins=bins, labels=labels, right=False)
    grouped = df.groupby(f"{col}_bin", observed=True)

    print(f"\n  [{title}]")
    print(f"  {'區間':<14} {'筆數':>5} {'勝率':>7} {'平均損益':>10} {'總損益':>8}")
    for label, g in grouped:
        if len(g) == 0:
            continue
        wr = (g["PnL"] > 0).mean() * 100
        avg = g["PnL"].mean()
        total = g["PnL"].sum()
        marker = " ◀ good" if (wr >= 55 and avg > 0) else (" ◀ bad" if wr < 40 else "")
        print(f"  {str(label):<14} {len(g):>5} {wr:>6.1f}% {avg:>+10.1f} {total:>+8.0f}{marker}")


def main():
    print("Loading data...")
    bar_df = load_data_for_orb_est_hl(start="2021-01-01", end="2026-03-12")
    trades = load_trades()
    print(f"共 {len(trades)} 筆交易")

    trades = enrich_with_bar_data(trades, bar_df)

    # ── 全部星期表現（baseline）──────────────────────────────────────────
    print("\n" + "="*60)
    print("  全部交易（baseline）")
    print("="*60)
    print(f"  {'星期':<6} {'筆數':>5} {'勝率':>7} {'平均損益':>10} {'總損益':>8}")
    for wd, name in WD.items():
        sub = trades[trades["weekday"] == wd]
        if len(sub) == 0:
            continue
        wr = (sub["PnL"] > 0).mean() * 100
        print(f"  {name:<6} {len(sub):>5} {wr:>6.1f}%  {sub['PnL'].mean():>+9.1f}  {sub['PnL'].sum():>+8.0f}")

    # ── 週四/五深度分析 ──────────────────────────────────────────────────
    for wd, name in [(3, "週四"), (4, "週五")]:
        sub = trades[trades["weekday"] == wd].copy()
        print(f"\n{'='*60}")
        print(f"  {name}（{len(sub)} 筆）  勝率 {(sub['PnL']>0).mean()*100:.1f}%  "
              f"總損益 {sub['PnL'].sum():+.0f}")
        print(f"{'='*60}")

        # 1. OR% 分析
        bucket_analysis(
            sub, "or_pct",
            bins=[0, 0.3, 0.5, 0.7, 1.0, 1.5, 99],
            labels=["<0.3%", "0.3-0.5%", "0.5-0.7%", "0.7-1.0%", "1.0-1.5%", ">1.5%"],
            title=f"{name} × OR%"
        )

        # 2. SatZone 距離分析（以 EmaHL 倍數）
        bucket_analysis(
            sub, "sat_dist_emaHL",
            bins=[0, 0.5, 1.0, 1.5, 2.0, 3.0, 99],
            labels=["<0.5x", "0.5-1.0x", "1.0-1.5x", "1.5-2.0x", "2.0-3.0x", ">3.0x"],
            title=f"{name} × 進場距SatZone（EmaHL倍數）"
        )

        # 3. OR% × SatZone 距離 交叉表（勝率）
        sub2 = sub.dropna(subset=["or_pct", "sat_dist_emaHL"])
        sub2 = sub2.copy()
        sub2["or_bin"] = pd.cut(sub2["or_pct"],
                                bins=[0, 0.5, 0.7, 1.0, 99],
                                labels=["<0.5%", "0.5-0.7%", "0.7-1.0%", ">1.0%"])
        sub2["sat_bin"] = pd.cut(sub2["sat_dist_emaHL"],
                                 bins=[0, 0.75, 1.25, 2.0, 99],
                                 labels=["<0.75x", "0.75-1.25x", "1.25-2.0x", ">2.0x"])

        pivot_wr = sub2.pivot_table(
            values="PnL", index="or_bin", columns="sat_bin",
            aggfunc=lambda x: f"{(x>0).mean()*100:.0f}%({len(x)})"
        )
        pivot_pnl = sub2.pivot_table(
            values="PnL", index="or_bin", columns="sat_bin",
            aggfunc="sum"
        )

        print(f"\n  [{name} OR% × SatZone距離 勝率（筆數）]")
        print(pivot_wr.to_string())
        print(f"\n  [{name} OR% × SatZone距離 總損益]")
        print(pivot_pnl.to_string())


if __name__ == "__main__":
    main()
