#!/usr/bin/env python3
"""H045: Compare EstHL live trades vs backtest trades.

Matches by date and direction, categorizes differences.
"""
import pandas as pd
from pathlib import Path

LIVE_CSV = Path("research/archive/confirmed/H044-reversal-live-vs-backtest/data/live_parsed.csv")
# Default spec backtest (long+short, skip Thu/Fri)
BT_CSV = Path("output/orb_est_hl_2024-11-01_2026-03-19.csv")
# Full universe backtest (all directions, all weekdays)
BT_FULL_CSV = Path("output/orb_est_hl_full_2024-11-01_2026-03-19.csv")


def load_live():
    df = pd.read_csv(LIVE_CSV)
    # Keep only esthl and esthl_costline
    df = df[df["strategy"].isin(["esthl", "esthl_costline"])].copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["pnl"] = pd.to_numeric(df["pnl"], errors="coerce")
    # Direction normalization
    df["dir"] = df["direction"].map({"B": "long", "S": "short"})
    return df


def load_bt(path):
    df = pd.read_csv(path)
    df["EntryTime"] = pd.to_datetime(df["EntryTime"])
    df["ExitTime"] = pd.to_datetime(df["ExitTime"])
    df["date"] = df["EntryTime"].dt.date
    df["dir"] = df["Size"].apply(lambda s: "long" if s > 0 else "short")
    df["entry_time_str"] = df["EntryTime"].dt.strftime("%H:%M")
    df["exit_time_str"] = df["ExitTime"].dt.strftime("%H:%M")
    return df


def match_trades(live, bt):
    """Match live trades to backtest trades by date."""
    results = []

    all_dates = set(live["date"].tolist()) | set(bt["date"].tolist())

    for d in sorted(all_dates):
        live_rows = live[live["date"] == d]
        bt_rows = bt[bt["date"] == d]

        if len(live_rows) == 0 and len(bt_rows) > 0:
            for _, br in bt_rows.iterrows():
                results.append({
                    "date": d,
                    "weekday": pd.Timestamp(d).day_name()[:3],
                    "match": "bt_only",
                    "live_strategy": "",
                    "live_dir": "",
                    "bt_dir": br["dir"],
                    "live_entry_time": "",
                    "bt_entry_time": br["entry_time_str"],
                    "live_entry_price": "",
                    "bt_entry_price": br["EntryPrice"],
                    "live_pnl": "",
                    "bt_pnl": br["PnL"],
                    "pnl_diff": "",
                    "price_diff": "",
                    "category": "漏接 (live missed)",
                })
        elif len(bt_rows) == 0 and len(live_rows) > 0:
            for _, lr in live_rows.iterrows():
                results.append({
                    "date": d,
                    "weekday": pd.Timestamp(d).day_name()[:3],
                    "match": "live_only",
                    "live_strategy": lr["strategy"],
                    "live_dir": lr["dir"],
                    "bt_dir": "",
                    "live_entry_time": lr.get("entry_time", ""),
                    "bt_entry_time": "",
                    "live_entry_price": lr.get("entry_price", ""),
                    "bt_entry_price": "",
                    "live_pnl": lr["pnl"] if pd.notna(lr["pnl"]) else "",
                    "bt_pnl": "",
                    "pnl_diff": "",
                    "price_diff": "",
                    "category": "多做 (extra live trade)",
                })
        else:
            # Both have trades - match them
            for _, lr in live_rows.iterrows():
                # Try to find matching bt trade (same direction)
                matched = bt_rows[bt_rows["dir"] == lr["dir"]]
                if len(matched) == 0:
                    # Direction mismatch - find any bt trade
                    matched = bt_rows
                    if len(matched) > 0:
                        br = matched.iloc[0]
                        results.append({
                            "date": d,
                            "weekday": pd.Timestamp(d).day_name()[:3],
                            "match": "dir_mismatch",
                            "live_strategy": lr["strategy"],
                            "live_dir": lr["dir"],
                            "bt_dir": br["dir"],
                            "live_entry_time": lr.get("entry_time", ""),
                            "bt_entry_time": br["entry_time_str"],
                            "live_entry_price": lr.get("entry_price", ""),
                            "bt_entry_price": br["EntryPrice"],
                            "live_pnl": lr["pnl"] if pd.notna(lr["pnl"]) else "",
                            "bt_pnl": br["PnL"],
                            "pnl_diff": "",
                            "price_diff": "",
                            "category": "方向不一致",
                        })
                    else:
                        results.append({
                            "date": d,
                            "weekday": pd.Timestamp(d).day_name()[:3],
                            "match": "live_only",
                            "live_strategy": lr["strategy"],
                            "live_dir": lr["dir"],
                            "bt_dir": "",
                            "live_entry_time": lr.get("entry_time", ""),
                            "bt_entry_time": "",
                            "live_entry_price": lr.get("entry_price", ""),
                            "bt_entry_price": "",
                            "live_pnl": lr["pnl"] if pd.notna(lr["pnl"]) else "",
                            "bt_pnl": "",
                            "pnl_diff": "",
                            "price_diff": "",
                            "category": "多做",
                        })
                else:
                    br = matched.iloc[0]
                    live_pnl = lr["pnl"] if pd.notna(lr["pnl"]) else None
                    bt_pnl = br["PnL"]
                    pnl_diff = (live_pnl - bt_pnl) if live_pnl is not None else None

                    live_ep = lr.get("entry_price", "")
                    bt_ep = br["EntryPrice"]
                    try:
                        price_diff = float(live_ep) - bt_ep if live_ep else None
                    except (ValueError, TypeError):
                        price_diff = None

                    # Categorize
                    if live_pnl is not None and pnl_diff is not None:
                        if abs(pnl_diff) <= 20:
                            cat = "一致 (≤20pt)"
                        elif abs(pnl_diff) <= 50:
                            cat = "小差異 (21-50pt)"
                        elif abs(pnl_diff) <= 100:
                            cat = "中差異 (51-100pt)"
                        else:
                            cat = "大差異 (>100pt)"
                    else:
                        cat = "無法比較 (missing pnl)"

                    results.append({
                        "date": d,
                        "weekday": pd.Timestamp(d).day_name()[:3],
                        "match": "matched",
                        "live_strategy": lr["strategy"],
                        "live_dir": lr["dir"],
                        "bt_dir": br["dir"],
                        "live_entry_time": lr.get("entry_time", ""),
                        "bt_entry_time": br["entry_time_str"],
                        "live_entry_price": live_ep,
                        "bt_entry_price": bt_ep,
                        "live_pnl": live_pnl if live_pnl is not None else "",
                        "bt_pnl": bt_pnl,
                        "pnl_diff": pnl_diff if pnl_diff is not None else "",
                        "price_diff": price_diff if price_diff is not None else "",
                        "category": cat,
                    })

    return pd.DataFrame(results)


def print_summary(result_df, live_df, bt_df):
    print("=" * 70)
    print("  H045: EstHL 實盤 vs 回測比對")
    print("=" * 70)

    # Basic counts
    n_live = len(live_df)
    n_live_esthl = len(live_df[live_df["strategy"] == "esthl"])
    n_live_costline = len(live_df[live_df["strategy"] == "esthl_costline"])
    n_bt = len(bt_df)

    print(f"\n實盤交易數：{n_live}（esthl: {n_live_esthl}, costline: {n_live_costline}）")
    print(f"回測交易數：{n_bt}")
    print(f"時間範圍：{live_df['date'].min()} ~ {live_df['date'].max()}")

    # Match categories
    print(f"\n{'─' * 50}")
    print("比對結果分類：")
    cats = result_df["category"].value_counts()
    for cat, cnt in cats.items():
        print(f"  {cat:<25} {cnt:>3} 筆")

    # Direction match rate
    matched = result_df[result_df["match"] == "matched"]
    dir_matched = matched[matched["live_dir"] == matched["bt_dir"]]
    if len(matched) > 0:
        print(f"\n方向一致率：{len(dir_matched)}/{len(matched)} = {len(dir_matched)/len(matched)*100:.1f}%")

    # PnL comparison for matched trades
    pnl_matched = matched[matched["pnl_diff"] != ""].copy()
    if len(pnl_matched) > 0:
        pnl_matched["pnl_diff"] = pnl_matched["pnl_diff"].astype(float)
        pnl_matched["live_pnl"] = pnl_matched["live_pnl"].astype(float)
        pnl_matched["bt_pnl"] = pnl_matched["bt_pnl"].astype(float)

        print(f"\n{'─' * 50}")
        print("配對交易損益比較（N={n}）：".format(n=len(pnl_matched)))
        print(f"  實盤總損益：{pnl_matched['live_pnl'].sum():+.0f} 點")
        print(f"  回測總損益：{pnl_matched['bt_pnl'].sum():+.0f} 點")
        print(f"  損益差異均值：{pnl_matched['pnl_diff'].mean():+.1f} 點")
        print(f"  損益差異中位：{pnl_matched['pnl_diff'].median():+.1f} 點")
        print(f"  損益差異 std：{pnl_matched['pnl_diff'].std():.1f} 點")

        # Win rate comparison
        live_wins = (pnl_matched["live_pnl"] > 0).sum()
        bt_wins = (pnl_matched["bt_pnl"] > 0).sum()
        print(f"\n  實盤勝率：{live_wins}/{len(pnl_matched)} = {live_wins/len(pnl_matched)*100:.1f}%")
        print(f"  回測勝率：{bt_wins}/{len(pnl_matched)} = {bt_wins/len(pnl_matched)*100:.1f}%")

    # Live-only analysis
    live_only = result_df[result_df["match"] == "live_only"]
    if len(live_only) > 0:
        print(f"\n{'─' * 50}")
        print(f"實盤有 / 回測無（多做）：{len(live_only)} 筆")
        for _, row in live_only.iterrows():
            pnl_str = f"{row['live_pnl']:+.0f}" if row["live_pnl"] != "" and pd.notna(row["live_pnl"]) else "N/A"
            print(f"  {row['date']} ({row['weekday']}) {row['live_dir']:<5} {row['live_strategy']:<18} pnl={pnl_str}")

    # BT-only analysis
    bt_only = result_df[result_df["match"] == "bt_only"]
    if len(bt_only) > 0:
        print(f"\n{'─' * 50}")
        print(f"回測有 / 實盤無（漏接）：{len(bt_only)} 筆")
        for _, row in bt_only.iterrows():
            print(f"  {row['date']} ({row['weekday']}) {row['bt_dir']:<5} entry={row['bt_entry_time']} pnl={row['bt_pnl']:+.0f}")

    # Direction mismatch
    dir_mm = result_df[result_df["match"] == "dir_mismatch"]
    if len(dir_mm) > 0:
        print(f"\n{'─' * 50}")
        print(f"方向不一致：{len(dir_mm)} 筆")
        for _, row in dir_mm.iterrows():
            print(f"  {row['date']} ({row['weekday']}) live={row['live_dir']} bt={row['bt_dir']}")

    # Large PnL differences
    if len(pnl_matched) > 0:
        large_diff = pnl_matched[pnl_matched["pnl_diff"].abs() > 50].sort_values("pnl_diff")
        if len(large_diff) > 0:
            print(f"\n{'─' * 50}")
            print(f"損益差異 >50 點的交易（{len(large_diff)} 筆）：")
            for _, row in large_diff.iterrows():
                print(f"  {row['date']} ({row['weekday']}) {row['live_dir']:<5} "
                      f"live={row['live_pnl']:+.0f} bt={row['bt_pnl']:+.0f} "
                      f"diff={row['pnl_diff']:+.0f} "
                      f"entry: live={row['live_entry_time']} bt={row['bt_entry_time']}")

    # Price slippage analysis
    if len(pnl_matched) > 0:
        price_diff = pnl_matched[pnl_matched["price_diff"] != ""].copy()
        if len(price_diff) > 0:
            price_diff["price_diff"] = price_diff["price_diff"].astype(float)
            print(f"\n{'─' * 50}")
            print(f"進場價差（滑價）分析（N={len(price_diff)}）：")
            print(f"  均值：{price_diff['price_diff'].mean():+.1f} 點")
            print(f"  中位：{price_diff['price_diff'].median():+.1f} 點")
            print(f"  std：{price_diff['price_diff'].std():.1f} 點")
            print(f"  max：{price_diff['price_diff'].max():+.0f} 點")
            print(f"  min：{price_diff['price_diff'].min():+.0f} 點")

    # esthl_costline separate analysis
    costline = live_df[live_df["strategy"] == "esthl_costline"].copy()
    if len(costline) > 0:
        print(f"\n{'─' * 50}")
        print(f"EstHL Costline 獨立分析（{len(costline)} 筆）：")
        costline_pnl = costline[costline["pnl"].notna()]
        if len(costline_pnl) > 0:
            wins = (costline_pnl["pnl"] > 0).sum()
            print(f"  勝率：{wins}/{len(costline_pnl)} = {wins/len(costline_pnl)*100:.1f}%")
            print(f"  總損益：{costline_pnl['pnl'].sum():+.0f} 點")
            print(f"  平均損益：{costline_pnl['pnl'].mean():+.1f} 點")
        # These trades are NOT in backtest (different entry logic)
        print("  ※ Costline 為未回測的變體，回測中無對應信號")


def main():
    live = load_live()
    bt_default = load_bt(BT_CSV)
    bt_full = load_bt(BT_FULL_CSV)

    # Filter live to only trades with entry price (exclude empty entries)
    live_valid = live[live["entry_price"].notna() & (live["entry_price"] != "")].copy()
    # Separate esthl vs costline
    live_esthl = live_valid[live_valid["strategy"] == "esthl"].copy()
    live_costline = live_valid[live_valid["strategy"] == "esthl_costline"].copy()

    print("\n" + "=" * 70)
    print("  [A] EstHL vs 預設回測（long+short, skip Thu/Fri）")
    print("=" * 70)
    result_default = match_trades(live_esthl, bt_default)
    print_summary(result_default, live_esthl, bt_default)

    print("\n\n" + "=" * 70)
    print("  [B] EstHL vs 全開回測（all directions, all weekdays）")
    print("=" * 70)
    result_full = match_trades(live_esthl, bt_full)
    print_summary(result_full, live_esthl, bt_full)

    # Save detailed results
    out_dir = Path("research/active/H045-esthl-live-vs-backtest/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    result_default.to_csv(out_dir / "compare_default.csv", index=False)
    result_full.to_csv(out_dir / "compare_full.csv", index=False)
    print(f"\n\n詳細比對結果已存入：{out_dir}/")

    # Overall live performance (all esthl + costline)
    print("\n" + "=" * 70)
    print("  [C] 實盤整體績效")
    print("=" * 70)
    all_pnl = live_valid[live_valid["pnl"].notna()].copy()
    if len(all_pnl) > 0:
        wins = (all_pnl["pnl"] > 0).sum()
        losses = (all_pnl["pnl"] < 0).sum()
        breakeven = (all_pnl["pnl"] == 0).sum()
        avg_win = all_pnl[all_pnl["pnl"] > 0]["pnl"].mean() if wins > 0 else 0
        avg_loss = all_pnl[all_pnl["pnl"] < 0]["pnl"].mean() if losses > 0 else 0
        print(f"  總筆數：{len(all_pnl)}")
        print(f"  勝/敗/平：{wins}/{losses}/{breakeven}")
        print(f"  勝率：{wins/len(all_pnl)*100:.1f}%")
        print(f"  總損益：{all_pnl['pnl'].sum():+.0f} 點")
        print(f"  平均獲利：{avg_win:+.0f} 點")
        print(f"  平均虧損：{avg_loss:+.0f} 點")
        if avg_loss != 0:
            print(f"  獲利因子：{abs(all_pnl[all_pnl['pnl']>0]['pnl'].sum() / all_pnl[all_pnl['pnl']<0]['pnl'].sum()):.2f}")


if __name__ == "__main__":
    main()
