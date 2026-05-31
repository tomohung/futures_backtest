"""H095 — 驗證「靜態 L3 最佳是否長尾效應」+ 事後檢視漲跌家數關聯。

(1) 靜態 L3 vs Dow trail 的逐筆 P&L：優勢是否集中在少數大單？砍掉 top-K 後還贏嗎？
(2) 事後（hindsight，非可交易）：大贏單是否落在「當日漲跌家數淨值」極端的日子？
    註：market_breadth 為每日收盤值，盤中不可得 → 僅作機制驗證，不能當盤中規則。
"""

from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd
from phase2_path_backtest import build_entries, simulate
from src.backtest.runner import load_data_for_orb_est_hl


def per_trade(entries, tt, sp):
    rows = []
    for e in entries:
        px, reason, l3 = simulate(e["day"], e["ei"], e["base"], e["emahl"], e["ema20"], tt, sp)
        rows.append({"date": e["date"], "pnl": px - e["entry"], "l3": l3, "reason": reason})
    return pd.DataFrame(rows)


def main():
    df = load_data_for_orb_est_hl()
    entries = build_entries(df)
    static = per_trade(entries, "fixed", "be").rename(columns={"pnl": "static"})
    dow = per_trade(entries, "dow", "be").rename(columns={"pnl": "dow"})
    m = static.merge(dow[["date", "dow"]], on="date")
    print(f"N={len(m)}  靜態總={m.static.sum():.0f}  Dow總={m.dow.sum():.0f}  差={m.static.sum()-m.dow.sum():.0f}\n")

    # (1) 長尾：砍掉靜態最大的 K 筆後還贏 Dow 嗎？
    s_sorted = m.static.sort_values(ascending=False).to_numpy()
    print("=== 長尾檢驗：砍掉靜態 top-K 大單 ===")
    print(f"{'K':>4}{'靜態(去top-K)':>14}{'top-K佔總':>12}")
    for k in [0, 3, 5, 10, 20]:
        rest = s_sorted[k:].sum()
        share = s_sorted[:k].sum() / m.static.sum() if k else 0
        print(f"{k:>4}{rest:>14.0f}{share:>12.0%}")
    print(f"  （對照 Dow 總 = {m.dow.sum():.0f}）")
    print(f"  靜態 P&L 分佈：中位 {m.static.median():.0f}, p90 {m.static.quantile(.9):.0f}, "
          f"max {m.static.max():.0f}；勝率 {(m.static>0).mean():.0%}")

    # 靜態 vs Dow 的逐筆差，差距來自哪些單
    m["diff"] = m.static - m.dow
    big = m.nlargest(10, "diff")[["date", "static", "dow", "diff", "l3"]]
    print(f"\n  靜態勝過 Dow 最多的 10 筆（多半是靜態抱到 L3、Dow 早洗）：")
    print(big.to_string(index=False))

    # (2) 漲跌家數（事後）：大贏單是否落在廣度極端日
    with duckdb.connect("data/futures.duckdb", read_only=True) as c:
        b = c.execute("SELECT trade_date, up_count, down_count, listed_count, "
                      "up_limit_count, down_limit_count FROM market_breadth WHERE market='TWSE'").df()
    b["date"] = pd.to_datetime(b["trade_date"]).dt.date
    b["net_adv"] = (b.up_count - b.down_count) / b.listed_count   # 淨上漲家數比
    m2 = m.merge(b[["date", "net_adv"]], on="date", how="left")
    print(f"\n=== (2) 事後：當日漲跌家數淨值 vs 出場結果（{m2.net_adv.notna().sum()} 筆有 breadth）===")
    m2 = m2.dropna(subset=["net_adv"])
    m2["adv_q"] = pd.qcut(m2.net_adv, 4, labels=["極弱", "弱", "強", "極強"])
    g = m2.groupby("adv_q", observed=True).agg(
        n=("static", "size"), 靜態均=("static", "mean"), Dow均=("dow", "mean"),
        到L3率=("l3", "mean"), 靜態勝Dow差=("diff", "mean"))
    print(g.round(2).to_string())
    print("\n→ 若『極強/極弱』分位的『到L3率』與『靜態勝Dow差』明顯更高 = 趨勢日(廣度極端)正是長尾來源。")


if __name__ == "__main__":
    main()
