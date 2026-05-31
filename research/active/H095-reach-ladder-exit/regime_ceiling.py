"""H095 — regime 條件式出場的「事後廣度」上限估計（oracle ceiling）。

用當日漲跌家數淨值(net_adv，事後不可交易)決定每筆用哪種出場：
  強廣度 → 靜態抱 L3；其餘 → Dow trail；(選配) 極弱 → 不做(0)。
比較：最佳單一出場 vs regime oracle vs 逐筆完美 oracle(絕對上限)。
並檢查 regime 結構在 train(≤2024)/test(≥2025) 是否一致 → 天花板是否真實。
"""

from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd
from phase2_path_backtest import build_entries, simulate
from src.backtest.runner import load_data_for_orb_est_hl


def per_trade(entries, tt, sp):
    out = []
    for e in entries:
        px, _, l3 = simulate(e["day"], e["ei"], e["base"], e["emahl"], e["ema20"], tt, sp)
        out.append({"date": e["date"], "pnl": px - e["entry"], "l3": l3})
    return pd.DataFrame(out)


def main():
    df = load_data_for_orb_est_hl()
    entries = build_entries(df)
    s = per_trade(entries, "fixed", "be").rename(columns={"pnl": "static", "l3": "l3"})
    d = per_trade(entries, "dow", "be").rename(columns={"pnl": "dow"})
    m = s.merge(d[["date", "dow"]], on="date")

    with duckdb.connect("data/futures.duckdb", read_only=True) as c:
        b = c.execute("SELECT trade_date, up_count, down_count, listed_count "
                      "FROM market_breadth WHERE market='TWSE'").df()
    b["date"] = pd.to_datetime(b["trade_date"]).dt.date
    b["net_adv"] = (b.up_count - b.down_count) / b.listed_count
    m = m.merge(b[["date", "net_adv"]], on="date", how="inner")
    m["year"] = pd.to_datetime(m["date"]).dt.year
    n = len(m)
    print(f"有 breadth 的交易：{n} 筆\n")

    thr = m.net_adv.quantile(0.75)   # 「強廣度」門檻 = 淨上漲家數比 top 25%
    q25 = m.net_adv.quantile(0.25)
    print(f"強廣度門檻 net_adv≥{thr:.2f}（top25%）；極弱門檻 ≤{q25:.2f}\n")

    def totals(sub):
        strong = sub.net_adv >= thr
        weak = sub.net_adv <= q25
        return {
            "靜態全抱": sub.static.sum(),
            "Dow全trail": sub.dow.sum(),
            "regime(強→靜態,其餘→Dow)": np.where(strong, sub.static, sub.dow).sum(),
            "regime+極弱不做": np.where(strong, sub.static, np.where(weak, 0.0, sub.dow)).sum(),
            "逐筆完美oracle(上限)": np.maximum(sub.static, sub.dow).sum(),
        }

    def show(name, sub):
        t = totals(sub)
        base = t["靜態全抱"]
        print(f"=== {name}（n={len(sub)}）===")
        for k, v in t.items():
            up = f"  (vs 靜態 {v-base:+.0f}, {(v/base-1)*100:+.0f}%)" if k != "靜態全抱" else ""
            print(f"  {k:<26} {v:>7.0f}{up}")
        print()

    show("全期", m)
    show("train ≤2024", m[m.year <= 2024])
    show("test ≥2025", m[m.year >= 2025])

    # regime 結構穩定性：各期『強廣度日』靜態 vs Dow 的均值
    print("=== regime 穩定性：強廣度日 靜態均 vs Dow均（該抱嗎？）===")
    for lab, sub in [("全期", m), ("train≤2024", m[m.year <= 2024]), ("test≥2025", m[m.year >= 2025])]:
        st = sub[sub.net_adv >= thr]
        mid = sub[(sub.net_adv < thr) & (sub.net_adv > q25)]
        print(f"  {lab:<10} 強日(n={len(st):>3}) 靜態{st.static.mean():>6.1f} vs Dow{st.dow.mean():>6.1f}"
              f"  | 中間日(n={len(mid):>3}) 靜態{mid.static.mean():>6.1f} vs Dow{mid.dow.mean():>6.1f}")
    print("\n→ 若每期『強日 靜態>Dow』且『中間日 Dow≥靜態』都成立 = regime 結構穩定、天花板真實。")


if __name__ == "__main__":
    main()
