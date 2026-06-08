"""產生兩種模式的 chart-ui 清單（open / anywhere），每個交易日一組 valid two-leg。
item：time=P0、exit_time=P3、side=leg1方向、levels=P0..P3+等幅目標(水平線)、legPoints=斜線overlay用。"""
import sys
import duckdb
import numpy as np
import pandas as pd
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))
from prep2_legs import find_two_legs
from src.chart_ui.list_writer import write_chart_list

con = duckdb.connect(str(ROOT / "data" / "futures.duckdb"), read_only=True)
df = con.sql("""SELECT timestamp, close, high, low FROM ohlcv_1m
               WHERE symbol='TX' AND timestamp::time BETWEEN TIME '08:45' AND TIME '13:45'
               ORDER BY timestamp""").df()
con.close()
df["date"] = df["timestamp"].dt.normalize()
df["mins"] = (df["timestamp"].dt.hour * 60 + df["timestamp"].dt.minute) - 525
rng = df.groupby("date").apply(lambda x: x["high"].max() - x["low"].min(), include_groups=False)
atr = rng.rolling(10).mean().shift(1)
days = {d: g.sort_values("mins") for d, g in df.groupby("date")}


def tstr(d, idx):
    m = 525 + int(idx)
    return f"{d.date()} {m//60:02d}:{m % 60:02d}:00"


def build(mode):
    items = []
    for d in sorted(days.keys(), reverse=True):   # 倒序：最新日期在最上
        a = atr.get(d, np.nan)
        if not np.isfinite(a):
            continue
        tl = find_two_legs(days[d]["close"].to_numpy(), a, anchor=mode)
        if not tl:
            continue
        t = tl[0]
        P = [t["P0"], t["P1"], t["P2"], t["P3"]]
        target = t["P2"][1] + t["dir"] * abs(t["P1"][1] - t["P0"][1])   # 等幅投射目標
        items.append({
            "time": tstr(d, P[0][0]),
            "exit_time": tstr(d, P[3][0]),
            "side": "long" if t["dir"] > 0 else "short",
            "result": "Win" if t["success"] else "Loss",
            "pnl_pts": round(t["P3"][1] - t["P0"][1] if t["dir"] > 0 else t["P0"][1] - t["P3"][1], 1),
            "note": (f"leg1={t['leg1']:.2f}A 回撤{t['retr_ratio']:.0%} leg2={t['leg2']:.2f}A "
                     f"(L2/L1={t['leg2_over_leg1']:.2f}) {'✅成功腳' if t['success'] else '❌失敗腳'}"),
            "levels": [
                {"price": round(P[0][1]), "label": "P0開"},
                {"price": round(P[1][1]), "label": "P1(leg1極值)"},
                {"price": round(P[2][1]), "label": "P2(回撤/均衡)"},
                {"price": round(P[3][1]), "label": "P3(leg2終)"},
                {"price": round(target), "label": "等幅目標"},
            ],
            "legPoints": [[tstr(d, idx), round(pr, 1)] for idx, pr in P],   # 斜線 overlay 用
        })
    n_succ = sum(1 for it in items if it["result"] == "Win")
    summary = {"trades": len(items), "win_rate": round(n_succ / len(items), 3) if items else None,
               "pnl_pts": round(sum(it["pnl_pts"] for it in items), 1), "pf": None}
    label = {"open": "開盤衝勢型", "intraday": "盤中兩腳型"}.get(mode, mode)
    path = write_chart_list(f"prep2-twoleg-{mode}", items,
                            name=f"PREP-2 兩腳·{label}({mode})", summary=summary,
                            entry_marker=True)
    print(f"  [{mode:8}] {len(items)} 日（成功腳 {n_succ}, {n_succ/len(items):.0%}）→ {path}")


print("=== 產生 chart-ui 清單 ===")
for m in ("open", "intraday"):
    build(m)
print("啟動 chart-ui 後 dropdown 可見；點日期跳到 P0。")
