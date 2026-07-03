"""
H136 Phase 1: 開盤相對均線位置 → 早盤時間窗方向

條件: 當日 08:45 開盤價 vs 日線均線 (5/10/20/60/120/240)，均在 adj 空間比較，MA 用前一日資料
結果: 三窗窗內漲跌 (窗收 - 窗開)，用原始價
  窗 A: 08:45 -> 09:45  (open@08:45, close@09:44)
  窗 B: 09:00 -> 10:00
  窗 C: 09:15 -> 10:15
"""
import duckdb
import numpy as np
import pandas as pd
from scipy.stats import norm

DB = "data/futures.duckdb"
MAS = [5, 10, 20, 60, 120, 240]
WINDOWS = {
    "A_0845_0945": ("08:45", "09:44"),
    "B_0900_1000": ("09:00", "09:59"),
    "C_0915_1015": ("09:15", "10:14"),
}

con = duckdb.connect(DB, read_only=True)

# ---- 1. 日盤 1 分 K (raw + adj) ----
df = con.execute("""
    SELECT CAST(timestamp AS DATE) AS d,
           CAST(timestamp AS TIME) AS t,
           open, close, adj_close
    FROM ohlcv_1m
    WHERE symbol='TX'
      AND CAST(timestamp AS TIME) BETWEEN '08:45' AND '13:45'
    ORDER BY timestamp
""").df()
con.close()
df["open"] = df["open"].astype(float)
df["close"] = df["close"].astype(float)
df["adj_close"] = df["adj_close"].astype(float)
df["t"] = df["t"].astype(str).str.slice(0, 5)

# ---- 2. daily close (adj) for MA: 每日最後一根 (<=13:45) 的 adj_close ----
daily = df.groupby("d").agg(daily_adj_close=("adj_close", "last")).reset_index()
daily = daily.sort_values("d").reset_index(drop=True)
for n in MAS:
    # shift(1): 用前一交易日為止的 n 日均，當日開盤時可得
    daily[f"ma{n}"] = daily["daily_adj_close"].rolling(n).mean().shift(1)

# ---- 3. 08:45 開盤 adj = raw_open + (adj_close - close) 同日調整量 ----
o0845 = df[df["t"] == "08:45"].copy()
o0845["adj_open_0845"] = o0845["open"] + (o0845["adj_close"] - o0845["close"])
o0845 = o0845[["d", "open", "adj_open_0845"]].rename(columns={"open": "raw_open_0845"})

# ---- 4. 三窗窗內報酬 (raw) ----
rows = []
g = df.groupby("d")
for d, sub in g:
    sub = sub.set_index("t")
    rec = {"d": d}
    for wname, (t0, t1) in WINDOWS.items():
        if t0 in sub.index and t1 in sub.index:
            wo = sub.loc[t0, "open"]
            wc = sub.loc[t1, "close"]
            ret = wc - wo
            rec[f"{wname}_ret"] = ret
            rec[f"{wname}_pct"] = ret / wo * 100.0
        else:
            rec[f"{wname}_ret"] = np.nan
            rec[f"{wname}_pct"] = np.nan
    rows.append(rec)
wins = pd.DataFrame(rows)

# ---- 5. merge ----
m = daily.merge(o0845, on="d").merge(wins, on="d")
m["year"] = pd.to_datetime(m["d"]).dt.year
m = m.dropna(subset=[f"ma{max(MAS)}"]).reset_index(drop=True)  # 需最長均線可算
print(f"總樣本(240MA可算後) N={len(m)}, 範圍 {m['d'].min()} ~ {m['d'].max()}")


def binom_ci(k, n, z=1.96):
    if n == 0:
        return (np.nan, np.nan)
    p = k / n
    se = np.sqrt(p * (1 - p) / n)
    return (p - z * se, p + z * se)


# ---- 6. 無條件 baseline ----
print("\n" + "=" * 70)
print("無條件 BASELINE (三窗)")
print("=" * 70)
base = {}
for w in WINDOWS:
    r = m[f"{w}_ret"].dropna()
    pct = m[f"{w}_pct"].dropna()
    red = (r > 0).sum()
    n = len(r)
    lo, hi = binom_ci(red, n)
    base[w] = {"red_p": red / n, "mean_ret": r.mean(), "mean_pct": pct.mean(), "n": n}
    print(f"{w:14s} N={n:4d}  收紅%={red/n*100:5.1f}% [{lo*100:.1f},{hi*100:.1f}]  "
          f"meanRet={r.mean():+6.2f}pt  meanPct={pct.mean():+.4f}%  medRet={r.median():+.1f}")

# ---- 7. 逐 MA x 逐窗 x 上/下 ----
print("\n" + "=" * 70)
print("條件: 開盤 adj vs MA (above/below)  |  三窗收紅% 與 EV")
print("=" * 70)
results = []
for n in MAS:
    m[f"pos{n}"] = np.where(m["adj_open_0845"] > m[f"ma{n}"], "above", "below")
    for w in WINDOWS:
        for side in ["above", "below"]:
            sub = m[m[f"pos{n}"] == side]
            r = sub[f"{w}_ret"].dropna()
            pct = sub[f"{w}_pct"].dropna()
            nn = len(r)
            if nn == 0:
                continue
            red = (r > 0).sum()
            lo, hi = binom_ci(red, nn)
            d_red = red / nn - base[w]["red_p"]  # vs baseline
            d_pct = pct.mean() - base[w]["mean_pct"]  # 扣漂移淨效果
            results.append({
                "ma": n, "window": w, "side": side, "n": nn,
                "red_p": red / nn, "ci_lo": lo, "ci_hi": hi,
                "d_red_pp": d_red * 100, "mean_ret": r.mean(),
                "mean_pct": pct.mean(), "net_pct": d_pct,
            })
res = pd.DataFrame(results)

# 熱力圖式印出: 每 MA 一塊
for n in MAS:
    print(f"\n--- MA{n} ---")
    for w in WINDOWS:
        for side in ["above", "below"]:
            row = res[(res.ma == n) & (res.window == w) & (res.side == side)]
            if row.empty:
                continue
            row = row.iloc[0]
            flag = ""
            # 顯著: CI 不含 baseline 且 |d_red|>=3pp
            if abs(row.d_red_pp) >= 3 and (base[w]["red_p"] < row.ci_lo or base[w]["red_p"] > row.ci_hi):
                flag = " *"
            print(f"  {w:14s} {side:5s} N={int(row.n):4d}  收紅%={row.red_p*100:5.1f}%  "
                  f"Δ={row.d_red_pp:+5.1f}pp  meanRet={row.mean_ret:+6.2f}  "
                  f"淨Pct={row.net_pct:+.4f}%{flag}")

# ---- 8. 找最強 cell 做逐年穩健性 ----
print("\n" + "=" * 70)
print("最強 cell (|Δred_pp| 最大, N>=200) 的逐年收紅%")
print("=" * 70)
strong = res[res.n >= 200].copy()
strong["absd"] = strong.d_red_pp.abs()
top = strong.sort_values("absd", ascending=False).head(6)
for _, row in top.iterrows():
    n, w, side = int(row.ma), row.window, row.side
    sub = m[m[f"pos{n}"] == side]
    print(f"\nMA{n} {w} {side}: 全期收紅%={row.red_p*100:.1f}% (Δ{row.d_red_pp:+.1f}pp, N={int(row.n)})  淨Pct={row.net_pct:+.4f}%")
    for yr in sorted(m.year.unique()):
        ys = sub[sub.year == yr]
        r = ys[f"{w}_ret"].dropna()
        if len(r) == 0:
            continue
        red = (r > 0).sum()
        print(f"    {yr}: N={len(r):3d}  收紅%={red/len(r)*100:5.1f}%  meanRet={r.mean():+6.2f}")

res.to_csv("research/active/H136-open-vs-ma-window-direction/results/cells.csv", index=False)
print("\n已存 cells.csv")
