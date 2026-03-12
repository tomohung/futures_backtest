"""
分析 EstHL 策略在各星期幾的表現
用法: uv run python src/backtest/analyze_weekday_esthl.py
"""
import pandas as pd
import glob
import os

WEEKDAY_NAMES = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"}

def load_all_trades():
    # 載入 2021-2024 + 2025 + 2026
    files = [
        "output/orb_est_hl_2021-01-01_2024-12-31.csv",
        "output/orb_est_hl_2025-01-01_2025-12-31.csv",
        "output/orb_est_hl_2026-01-01_2026-03-12.csv",
    ]
    dfs = []
    for f in files:
        if os.path.exists(f):
            df = pd.read_csv(f)
            dfs.append(df)
        else:
            print(f"[WARN] 找不到 {f}")
    return pd.concat(dfs, ignore_index=True)

def analyze(df: pd.DataFrame, label: str):
    df = df.copy()
    df["EntryTime"] = pd.to_datetime(df["EntryTime"])
    df["weekday"] = df["EntryTime"].dt.weekday  # 0=Mon, 4=Fri
    df["weekday_name"] = df["weekday"].map(WEEKDAY_NAMES)
    df["entry_price"] = df["EntryPrice"]
    df["pnl_pct"] = df["PnL"] / df["entry_price"] * 100

    print(f"\n{'='*60}")
    print(f"  {label}  (共 {len(df)} 筆)")
    print(f"{'='*60}")
    print(f"{'星期':<6} {'筆數':>5} {'勝率':>7} {'平均損益':>10} {'總損益':>9} {'Avg損益%':>9}")
    print(f"{'-'*60}")

    totals = []
    for wd in range(5):
        name = WEEKDAY_NAMES[wd]
        sub = df[df["weekday"] == wd]
        if len(sub) == 0:
            continue
        wins = (sub["PnL"] > 0).sum()
        wr = wins / len(sub) * 100
        avg_pnl = sub["PnL"].mean()
        total_pnl = sub["PnL"].sum()
        avg_pct = sub["pnl_pct"].mean()
        totals.append((name, len(sub), wr, avg_pnl, total_pnl, avg_pct))
        print(f"{name:<6} {len(sub):>5} {wr:>6.1f}% {avg_pnl:>+10.1f} {total_pnl:>+9.0f} {avg_pct:>+8.3f}%")

    print(f"{'-'*60}")
    print(f"{'Total':<6} {len(df):>5} {(df['PnL']>0).mean()*100:>6.1f}% "
          f"{df['PnL'].mean():>+10.1f} {df['PnL'].sum():>+9.0f} {df['pnl_pct'].mean():>+8.3f}%")

    # 年度 × 星期幾
    print(f"\n  各年度 × 星期幾 總損益")
    print(f"{'年份':<6}", end="")
    for wd in range(5):
        print(f"  {WEEKDAY_NAMES[wd]:>7}", end="")
    print(f"  {'Total':>7}")
    print(f"{'-'*55}")

    df["year"] = df["EntryTime"].dt.year
    for year, ydf in df.groupby("year"):
        print(f"{year:<6}", end="")
        for wd in range(5):
            sub = ydf[ydf["weekday"] == wd]
            total = sub["PnL"].sum() if len(sub) > 0 else 0
            print(f"  {total:>+7.0f}", end="")
        print(f"  {ydf['PnL'].sum():>+7.0f}")

    return df


if __name__ == "__main__":
    df = load_all_trades()
    analyze(df, "EstHL 策略  2021–2026")
