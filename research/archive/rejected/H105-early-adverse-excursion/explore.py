"""
H105 早期套牢 → 結局 — Phase 1 分佈探索（零策略現象）

每交易日 08:45 開盤進場，多/空各自獨立測：
  早期窗 X∈{5,10,15,30}分；早期 MAE（最大逆走）÷ 前10日日盤range均值(ATR) = 套牢深度 Y
報兩種：
  (A) 描述性：最終報酬(進場→13:45) vs Y         —— 會單調但可能是路徑自相關廢話
  (B) 前瞻性：剩餘報酬(第X分→13:45) vs Y         —— tautology guard，判斷依據
      + 控制第X分當下水位 mark_X，看 MAE 深度是否帶額外資訊
報酬一律 % of 進場價（跨年可比）。多/空為同一路徑鏡像，但市場不對稱故分開看。
"""
import duckdb
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
from scipy.stats import spearmanr

OUT = Path(__file__).parent / "results"
OUT.mkdir(exist_ok=True)
XS = [5, 10, 15, 30]
ATR_N = 10

# ---------------------------------------------------------------- load day-session bars
con = duckdb.connect("data/futures.duckdb", read_only=True)
df = con.sql("""
    SELECT timestamp, open, high, low, close
    FROM ohlcv_1m
    WHERE symbol='TX' AND timestamp::time BETWEEN TIME '08:45' AND TIME '13:45'
    ORDER BY timestamp
""").df()
con.close()
df["date"] = df["timestamp"].dt.normalize()
df["mins"] = (df["timestamp"].dt.hour * 60 + df["timestamp"].dt.minute) - (8 * 60 + 45)

rows = []
for d, g in df.groupby("date"):
    g = g.sort_values("mins")
    o = float(g["open"].iloc[0])
    c = float(g["close"].iloc[-1])
    hi_day, lo_day = float(g["high"].max()), float(g["low"].min())
    rec = {"date": d, "open": o, "close": c, "range": hi_day - lo_day}
    for X in XS:
        w = g[g["mins"] <= X]
        rec[f"elow{X}"] = float(w["low"].min())
        rec[f"ehigh{X}"] = float(w["high"].max())
        rec[f"markpx{X}"] = float(w["close"].iloc[-1])   # 第X分收盤價
    rows.append(rec)
D = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
D["atr"] = D["range"].rolling(ATR_N).mean().shift(1)
D["yr"] = D["date"].dt.year
D = D.dropna(subset=["atr"]).reset_index(drop=True)
print(f"=== SAMPLE === N={len(D)}  {D.date.min().date()} → {D.date.max().date()}")


def analyze(side):
    """side='long' or 'short'. 回傳每個 X 的 (描述性桶表, 前瞻性桶表, 相關)。"""
    s = 1 if side == "long" else -1
    print(f"\n{'='*92}\n###### {side.upper()}（08:45 進場）######")
    for X in XS:
        d = D.copy()
        # 早期 MAE（逆走，正值）÷ ATR
        if side == "long":
            mae = d["open"] - d[f"elow{X}"]
        else:
            mae = d[f"ehigh{X}"] - d["open"]
        d["Y"] = mae / d["atr"]
        d["markX"] = s * (d[f"markpx{X}"] - d["open"]) / d["open"] * 100     # 第X分浮盈% (進場方向)
        d["final"] = s * (d["close"] - d["open"]) / d["open"] * 100          # 最終報酬%
        d["fwd"]   = s * (d["close"] - d[f"markpx{X}"]) / d["open"] * 100    # 剩餘報酬%(X→收)
        d["q"] = pd.qcut(d["Y"], 5, labels=False, duplicates="drop")
        rho_f = spearmanr(d["Y"], d["final"])[0]
        rho_w = spearmanr(d["Y"], d["fwd"])[0]
        print(f"\n--- X={X}分  spearman(Y,最終)={rho_f:+.3f}  spearman(Y,剩餘X→收)={rho_w:+.3f} ---")
        print("  Y桶  N   Y中位  最終%中位  最終勝率  | 剩餘%(X→收)均  剩餘勝率  當下水位%中位")
        for q, gg in d.groupby("q"):
            print(f"  q{int(q)}  {len(gg):4d}  {gg.Y.median():4.2f}  "
                  f"{gg['final'].median():+7.3f}   {(gg['final']>0).mean():5.0%}    | "
                  f"{gg['fwd'].mean():+7.3f}      {(gg['fwd']>0).mean():5.0%}    {gg['markX'].median():+6.3f}")
    return


analyze("long")
analyze("short")

# ---------------------------------------------------------------- tautology guard: 控制 markX 後 MAE 是否帶額外資訊
print(f"\n{'='*92}\n###### Tautology guard：控制『第X分當下水位』後，套牢深度Y是否仍預測剩餘報酬 (X=10) ######")
for side in ["long", "short"]:
    s = 1 if side == "long" else -1
    d = D.copy()
    mae = (d["open"] - d["elow10"]) if side == "long" else (d["ehigh10"] - d["open"])
    d["Y"] = mae / d["atr"]
    d["markX"] = s * (d["markpx10"] - d["open"]) / d["open"] * 100
    d["fwd"] = s * (d["close"] - d["markpx10"]) / d["open"] * 100
    # 只取「第X分仍浮虧」的單（markX<0），這些是真正『套牢中』；看深MAE vs 淺MAE 剩餘差
    under = d[d["markX"] < 0].copy()
    under["yhi"] = under["Y"] > under["Y"].median()
    lo = under[~under["yhi"]]; hi = under[under["yhi"]]
    print(f"\n  {side.upper()} 第10分仍浮虧者 N={len(under)}：")
    print(f"    淺套牢(Y小) N={len(lo)} 當下水位中位={lo.markX.median():+.3f}% → 剩餘均={lo.fwd.mean():+.3f}% 剩餘勝率={(lo.fwd>0).mean():.0%}")
    print(f"    深套牢(Y大) N={len(hi)} 當下水位中位={hi.markX.median():+.3f}% → 剩餘均={hi.fwd.mean():+.3f}% 剩餘勝率={(hi.fwd>0).mean():.0%}")

# ---------------------------------------------------------------- plot (X=10)
fig, axes = plt.subplots(1, 2, figsize=(13, 5))
for ax, side in zip(axes, ["long", "short"]):
    s = 1 if side == "long" else -1
    d = D.copy()
    mae = (d["open"] - d["elow10"]) if side == "long" else (d["ehigh10"] - d["open"])
    d["Y"] = mae / d["atr"]
    d["final"] = s * (d["close"] - d["open"]) / d["open"] * 100
    d["fwd"] = s * (d["close"] - d["markpx10"]) / d["open"] * 100
    d["q"] = pd.qcut(d["Y"], 10, labels=False, duplicates="drop")
    mf = d.groupby("q")["final"].median()
    mw = d.groupby("q")["fwd"].mean()
    ax.plot(mf.index, mf.values, "o-", label="最終%中位 (描述性)", color="#7f8c8d")
    ax.plot(mw.index, mw.values, "s-", label="剩餘%均 X→收 (前瞻/判斷依據)", color="#c0392b")
    ax.axhline(0, color="k", lw=.6)
    ax.set_title(f"{side.upper()}：套牢深度Y(十分位) vs 報酬 (X=10)")
    ax.set_xlabel("早期套牢深度 Y 十分位 (低→高)"); ax.set_ylabel("報酬 %"); ax.legend(fontsize=8)
plt.tight_layout()
plt.savefig(OUT / "h105_distribution.png", dpi=110)
print(f"\nsaved {OUT/'h105_distribution.png'}")
