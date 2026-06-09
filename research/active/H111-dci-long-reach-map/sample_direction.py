"""H111 樣本特性：TX 181 天日盤漲跌天數 + 日 % 報酬分群（檢視多頭偏度）。"""
from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
DB = str(HERE.parents[2] / "data" / "futures.duckdb")
LO, HI = date(2025, 6, 2), date(2026, 2, 26)

with duckdb.connect(DB, read_only=True) as c:
    d = c.execute(
        "SELECT CAST(timestamp AS DATE) d, "
        "arg_min(open, CAST(timestamp AS TIME)) o, "
        "arg_max(close, CAST(timestamp AS TIME)) cl "
        "FROM ohlcv_1m WHERE symbol='TX' "
        "AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' "
        "AND CAST(timestamp AS DATE) BETWEEN ? AND ? GROUP BY 1 ORDER BY 1", [LO, HI]).df()

d["o"] = d["o"].astype(float); d["cl"] = d["cl"].astype(float)
d["ret"] = (d["cl"] - d["o"]) / d["o"] * 100
N = len(d)
up, dn, fl = (d["ret"] > 0).sum(), (d["ret"] < 0).sum(), (d["ret"] == 0).sum()
L = [f"TX 日盤(close vs open) N={N}：漲 {up} ({up/N:.0%})  跌 {dn} ({dn/N:.0%})  平 {fl}",
     f"  日%報酬：均={d['ret'].mean():+.2f}%  中位={d['ret'].median():+.2f}%  std={d['ret'].std():.2f}%  "
     f"min={d['ret'].min():+.1f}%  max={d['ret'].max():+.1f}%",
     "", "用日%分群（close vs open，每格天數）："]
bins = [-99, -1.5, -1, -0.5, 0, 0.5, 1, 1.5, 99]
labs = ["< -1.5", "-1.5~-1", "-1~-0.5", "-0.5~0", "0~0.5", "0.5~1", "1~1.5", "> 1.5"]
g = pd.cut(d["ret"], bins=bins, labels=labs)
for l in labs:
    n = int((g == l).sum())
    L.append(f"  {l:>9}%  {n:>3}  " + "█" * n)

# open-anchor 哪邊擺更遠（與 reach 研究同尺）
p = pd.read_csv(HERE / "results" / "reach_map_panel.csv")
big_up = (p["up_full"] >= p["dn_full"]).sum() if "dn_full" in p else None
L.append("")
if "dn_full" in p:
    L.append(f"open-anchor 上行擺更遠的天數：{big_up}/{len(p)} ({big_up/len(p):.0%})")
else:
    L.append("（panel 無 dn_full 欄；up_full 中位 = %.0f 點）" % p["up_full"].median())

txt = "\n".join(L)
print(txt)
(HERE / "results" / "sample_direction.txt").write_text(txt + "\n")
