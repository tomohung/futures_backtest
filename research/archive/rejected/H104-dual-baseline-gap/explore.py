"""
H104 雙基準跳空 — Phase 1 分佈探索（純現象）

比較兩種開盤跳空基準對「開盤後當日日盤 excursion」的預測力：
  基準 A（對夜盤收）：日盤開(08:45) − 前一段夜盤收
  基準 B（對昨日盤收）：日盤開(08:45) − 昨日日盤收(13:45)

關鍵處理：
  - 跨日跳空用 adj_close（Panama 調整）剔除換倉假跳空
  - 夜盤錨點用 datetime 窗法（前一日盤開盤之後、本日盤開盤之前的最後一段夜盤），
    自動處理週末/假日，不靠日曆日對齊
  - 夜盤收兩種取法：05:00 整點根 vs 夜盤實際末筆
  - excursion 在當日盤內，offset 抵銷，用 raw 即可
  - 跳空向上日 / 向下日各自獨立統計（不互相推論）
輸出：results/distribution.md 用的數字 + results/*.png 圖
"""
import duckdb
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

OUT = Path(__file__).parent / "results"
OUT.mkdir(exist_ok=True)

# ---------------------------------------------------------------- load
con = duckdb.connect("data/futures.duckdb", read_only=True)
df = con.sql("""
    select timestamp, open, high, low, close, adjustment, adj_close, is_rollover
    from ohlcv_1m
    order by timestamp
""").df()
con.close()
df["date"] = df["timestamp"].dt.normalize()
df["t"] = df["timestamp"].dt.time
df["adj_open"] = df["open"] + df["adjustment"]   # Panama-adjusted open

import datetime as dt
T_OPEN, T_CLOSE = dt.time(8, 45), dt.time(13, 45)

# ---------------------------------------------------------------- day-session table
day = df[(df.t >= T_OPEN) & (df.t <= T_CLOSE)].copy()
g = day.groupby("date")
# open bar = 08:45 ; close bar = 13:45 (last)
day_open  = g.apply(lambda x: x.loc[x.t == T_OPEN, "open"].iloc[0], include_groups=False)
day_aopen = g.apply(lambda x: x.loc[x.t == T_OPEN, "adj_open"].iloc[0], include_groups=False)
day_close = g.apply(lambda x: x.loc[x.t == T_CLOSE, "close"].iloc[-1], include_groups=False)
day_aclose= g.apply(lambda x: x.loc[x.t == T_CLOSE, "adj_close"].iloc[-1], include_groups=False)
day_high  = g["high"].max()
day_low   = g["low"].min()
is_roll   = g["is_rollover"].max().astype(bool)
D = pd.DataFrame({
    "open": day_open, "adj_open": day_aopen,
    "close": day_close, "adj_close": day_aclose,
    "high": day_high, "low": day_low, "is_rollover": is_roll,
}).sort_index()
D["range"] = D["high"] - D["low"]
trading_days = D.index.to_numpy()
open_dt = (D.index + pd.Timedelta(hours=8, minutes=45)).to_numpy()  # 08:45 datetime per trading day

# prior 10-day avg range (ATR-ish, shifted so no lookahead)
D["atr10"] = D["range"].rolling(10).mean().shift(1)
# previous trading day's close (adjusted)
D["prev_aclose"] = D["adj_close"].shift(1)

# ---------------------------------------------------------------- night anchors
# night bars: time >= 15:00 OR time <= 05:00
night = df[(df.t >= dt.time(15, 0)) | (df.t <= dt.time(5, 0))].copy()
# owning trading day = first trading-day 08:45 open strictly AFTER this night bar
idx = np.searchsorted(open_dt, night["timestamp"].to_numpy(), side="left")
night = night[idx < len(trading_days)].copy()
night["own"] = trading_days[idx[idx < len(trading_days)]]

ng = night.groupby("own")
# last actual night bar before open
night_last = ng.apply(lambda x: x.loc[x.timestamp.idxmax(), "adj_close"], include_groups=False)
# 05:00 bar (canonical close); fallback to last if absent
def get_0500(x):
    s = x.loc[x.t == dt.time(5, 0), "adj_close"]
    return s.iloc[-1] if len(s) else x.loc[x.timestamp.idxmax(), "adj_close"]
night_0500 = ng.apply(get_0500, include_groups=False)
D["night_last_aclose"] = night_last
D["night_0500_aclose"] = night_0500

# ---------------------------------------------------------------- gaps (points, on adjusted prices)
D["gap_A_0500"] = D["adj_open"] - D["night_0500_aclose"]   # 基準A: 對夜盤收(05:00)
D["gap_A_last"] = D["adj_open"] - D["night_last_aclose"]   # 基準A: 對夜盤末筆
D["gap_B"]      = D["adj_open"] - D["prev_aclose"]         # 基準B: 對昨日盤收
# normalized by prior 10-day range
for c in ["gap_A_0500", "gap_A_last", "gap_B"]:
    D[c + "_n"] = D[c] / D["atr10"]

# ---------------------------------------------------------------- excursions (raw, within-day; points)
D["ret_co"]   = D["close"] - D["open"]   # signed open->close
D["up_exc"]   = D["high"] - D["open"]    # >=0 : best long move from open
D["down_exc"] = D["open"] - D["low"]     # >=0 : best short move from open

# usable sample: need both gap bases + atr + excursion
base = D.dropna(subset=["gap_A_0500", "gap_B", "atr10"]).copy()
# drop rollover days (artificial contract jump would still show in raw, adj removes it but be safe & report both)
base_noroll = base[~base["is_rollover"]].copy()

print("=== SAMPLE ===")
print("all day sessions:", len(D))
print("usable (gapA+gapB+atr10):", len(base))
print("  of which rollover days:", int(base["is_rollover"].sum()))
print("date range:", base.index.min().date(), "->", base.index.max().date())

# ---------------------------------------------------------------- (1) two-basis divergence
def divergence(b):
    a, bb = b["gap_A_0500_n"], b["gap_B_n"]
    corr = np.corrcoef(a, bb)[0, 1]
    diff_sign = (np.sign(a) != np.sign(bb)).mean()
    # quintile bins on each, share landing in different bin
    qa = pd.qcut(a, 5, labels=False, duplicates="drop")
    qb = pd.qcut(bb, 5, labels=False, duplicates="drop")
    diff_bin = (qa != qb).mean()
    return corr, diff_sign, diff_bin

for name, b in [("all", base), ("no-rollover", base_noroll)]:
    corr, ds, db = divergence(b)
    print(f"\n=== (1) DIVERGENCE A(0500) vs B  [{name}, N={len(b)}] ===")
    print(f"corr(gapA_n, gapB_n) = {corr:.3f}")
    print(f"P(different sign)    = {ds:.1%}")
    print(f"P(different quintile bin) = {db:.1%}")
    print(f"night-move (A-B) median |pts| = {(b['gap_A_0500']-b['gap_B']).abs().median():.1f}")

# 05:00 vs last robustness
print("\n=== 05:00 vs night-last robustness ===")
dd = (base["gap_A_0500"] - base["gap_A_last"])
print(f"corr(0500, last) = {np.corrcoef(base['gap_A_0500'], base['gap_A_last'])[0,1]:.4f}")
print(f"|0500-last| median = {dd.abs().median():.2f} pts ; >5pts in {(dd.abs()>5).mean():.1%}")

# ---------------------------------------------------------------- (2) excursion conditioned on gap, per basis, per direction
def bin_table(b, gapcol, direction):
    """direction: 'up' keep gap>0, 'down' keep gap<0. Bin by |gap_n| quintiles."""
    sub = b[b[gapcol] > 0].copy() if direction == "up" else b[b[gapcol] < 0].copy()
    sub["mag"] = sub[gapcol + "_n"].abs()
    sub["q"] = pd.qcut(sub["mag"], 5, labels=False, duplicates="drop")
    rows = []
    for q, grp in sub.groupby("q"):
        rows.append({
            "q": int(q), "N": len(grp),
            "mag_md": grp["mag"].median(),
            "ret_co_md": grp["ret_co"].median(),
            "P(ret<0)": (grp["ret_co"] < 0).mean(),
            "up_exc_md": grp["up_exc"].median(),
            "down_exc_md": grp["down_exc"].median(),
        })
    t = pd.DataFrame(rows)
    # monotonic strength: spearman of mag vs ret_co
    from scipy.stats import spearmanr
    rho, p = spearmanr(sub["mag"], sub["ret_co"])
    return t, rho, p, len(sub)

print("\n\n###### (2) EXCURSION vs GAP MAGNITUDE (quintiles), no-rollover ######")
for gapcol, label in [("gap_A_0500", "BASIS A (vs night 05:00)"),
                      ("gap_B", "BASIS B (vs prev-day close)")]:
    for direction in ["up", "down"]:
        t, rho, p, n = bin_table(base_noroll, gapcol, direction)
        print(f"\n--- {label} | GAP-{direction.upper()} (N={n}) | spearman(mag, ret_co)={rho:+.3f} (p={p:.1e}) ---")
        print(t.to_string(index=False,
              formatters={"mag_md": "{:.2f}".format, "ret_co_md": "{:+.1f}".format,
                          "P(ret<0)": "{:.0%}".format, "up_exc_md": "{:.1f}".format,
                          "down_exc_md": "{:.1f}".format}))

# correlation summary: |gap| vs signed/abs excursion, both bases
print("\n=== (2b) corr summary [no-rollover] ===")
from scipy.stats import spearmanr
for gapcol, label in [("gap_A_0500_n", "A_0500"), ("gap_B_n", "B")]:
    x = base_noroll[gapcol]
    print(f"{label}: spearman(gap, ret_co)={spearmanr(x, base_noroll['ret_co'])[0]:+.3f} | "
          f"spearman(|gap|, up_exc)={spearmanr(x.abs(), base_noroll['up_exc'])[0]:+.3f} | "
          f"spearman(|gap|, down_exc)={spearmanr(x.abs(), base_noroll['down_exc'])[0]:+.3f}")

# ---------------------------------------------------------------- plots
fig, axes = plt.subplots(2, 2, figsize=(13, 9))
for ax, (gapcol, label) in zip(axes.flat[:2],
        [("gap_A_0500", "Basis A (vs night 05:00)"), ("gap_B", "Basis B (vs prev-day close)")]):
    sub = base_noroll.copy()
    sub["q"] = pd.qcut(sub[gapcol + "_n"], 10, labels=False, duplicates="drop")
    m = sub.groupby("q")["ret_co"].median()
    ax.bar(m.index, m.values, color=["#c0392b" if v >= 0 else "#27ae60" for v in m.values])
    ax.axhline(0, color="k", lw=.6)
    ax.set_title(f"{label}\nmedian open→close ret by gap decile")
    ax.set_xlabel("gap decile (low→high)"); ax.set_ylabel("median ret_co (pts)")

# scatter divergence
axes[1, 0].scatter(base_noroll["gap_B_n"], base_noroll["gap_A_0500_n"], s=4, alpha=.3)
lim = 3
axes[1, 0].plot([-lim, lim], [-lim, lim], "r--", lw=.8)
axes[1, 0].set_xlim(-lim, lim); axes[1, 0].set_ylim(-lim, lim)
axes[1, 0].set_title("gap divergence: A vs B (normalized)")
axes[1, 0].set_xlabel("gap_B_n (vs prev close)"); axes[1, 0].set_ylabel("gap_A_n (vs night)")

# hist of night move A-B
axes[1, 1].hist((base_noroll["gap_A_0500"] - base_noroll["gap_B"]), bins=60, color="#7f8c8d")
axes[1, 1].set_title("night-session move (gapA - gapB), pts")
axes[1, 1].set_xlabel("pts")
plt.tight_layout()
plt.savefig(OUT / "h104_distribution.png", dpi=110)
print(f"\nsaved {OUT/'h104_distribution.png'}")

# ---------------------------------------------------------------- (3) GAP FILL (% of open, scale-invariant)
# 回補 = 盤中價格碰回參考價位：gap-up 補=low觸及參考(down_exc>=gap)；gap-down 補=high觸及參考(up_exc>=|gap|)
print("\n\n###### (3) GAP FILL — 回補率（以 % of 開盤價，可跨年比）######")
b = base_noroll.copy()
b["gap_A_0500_pct"] = b["gap_A_0500"] / b["open"] * 100
b["gap_B_pct"]      = b["gap_B"]      / b["open"] * 100
b["ret_pct"]        = b["ret_co"]     / b["open"] * 100

def fill_table_pct(gapcol):
    up = b[b[gapcol] > 0].copy(); dn = b[b[gapcol] < 0].copy()
    up["filled"] = up["down_exc"] >= up[gapcol]
    dn["filled"] = dn["up_exc"]   >= -dn[gapcol]
    for name, s in [("gap-UP  ", up), ("gap-DOWN", dn)]:
        print(f"  {name}: 整體回補率={s['filled'].mean():.0%}  N={len(s)}")
        s = s.copy(); s["q"] = pd.qcut(s[gapcol + "_pct"].abs(), 5, labels=False, duplicates="drop")
        for q, grp in s.groupby("q"):
            print(f"     q{int(q)}: |gap|={grp[gapcol+'_pct'].abs().median():.3f}%  "
                  f"回補={grp['filled'].mean():.0%}  收-開中位={grp['ret_pct'].median():+.3f}%  N={len(grp)}")

print("\n--- BASIS A (對夜盤 05:00) ---"); fill_table_pct("gap_A_0500")
print("\n--- BASIS B (對昨日盤收) ---"); fill_table_pct("gap_B")

# 跨年穩定性（證明 % 標準化後結構不隨指數水準漂移）
print("\n--- 跨年穩定性 (BASIS A) ---")
b["yr"] = b.index.year
print("  年度  中位|gapA|%  gap-up回補  gap-down回補   N")
for yr, g in b.groupby("yr"):
    up = g[g.gap_A_0500 > 0]; dn = g[g.gap_A_0500 < 0]
    upf = (up["down_exc"] >= up["gap_A_0500"]).mean()
    dnf = (dn["up_exc"] >= -dn["gap_A_0500"]).mean()
    print(f"  {yr}    {g['gap_A_0500_pct'].abs().median():.3f}%       {upf:.0%}         {dnf:.0%}        {len(g)}")
