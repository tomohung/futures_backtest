"""H116 Phase 1（全歷史多 regime 版）— 累積淨多空力道當 ladder 續攻早碰層修正。

★ 關鍵：本案訊號(累積淨力)+事件(L3碰觸/續攻L4)全部只用 TX ohlcv_1m,不需 stock_min
→ 可拉全 TX 歷史(2021~2026,含 2022 熊市),解掉 H114/H115「OOS≡單一高波 regime」的 confound。

每碰 L3 日於 t_k 取：累積淨力比例 cum_frac=Σ(漲K量−跌K量)/Σ總量(當日累積,界−1~1)、碰觸時點 tod。
結果 cont = t_k 後續攻 L4。Regime = 全史 ema20(前日EMA20振幅) 三分位(低/中/高波)。

驗：
  A. base P(L4|L3) + 時點 gap by regime（時點主軸是否跨 regime 穩）
  B. 累積淨力分帶 P(L4|L3) by regime（方向是否 regime-stable）
  C. ★ 早碰層 累積淨力增量 by regime（Invalidation #1：是否同向、不翻、含 2022 熊）
用法：uv run python research/active/H116-net-force-modifier/explore.py
"""
from __future__ import annotations

from datetime import date, time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
DB = str(HERE.parents[2] / "data" / "futures.duckdb")
WARM = date(2021, 2, 1)      # EMA20 暖機後起算
L3, L4 = 0.711, 0.977


def build():
    with duckdb.connect(DB, read_only=True) as c:
        rng = c.execute(
            "SELECT CAST(timestamp AS DATE) d, MAX(high)-MIN(low) r FROM ohlcv_1m WHERE symbol='TX' "
            "AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' GROUP BY 1 ORDER BY 1").df()
        rng["ema20"] = rng["r"].astype(float).shift(1).ewm(span=20, adjust=False).mean()
        ema = rng.set_index("d")["ema20"]
        bars = c.execute(
            "SELECT CAST(timestamp AS DATE) d, CAST(timestamp AS TIME) t, open, high, low, close, volume FROM ohlcv_1m "
            "WHERE symbol='TX' AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' ORDER BY d,t").df()
    for col in ("open", "high", "low", "close", "volume"):
        bars[col] = bars[col].astype(float)
    rows = []
    for d, g in bars.groupby("d"):
        dd = pd.Timestamp(d).date()
        e = float(ema.get(d, np.nan))
        if dd < WARM or not (e > 0):
            continue
        g = g.sort_values("t")
        hi, lo, op, cl, vol = g["high"].values, g["low"].values, g["open"].values, g["close"].values, g["volume"].values
        up = np.maximum.accumulate(hi - np.minimum.accumulate(lo))
        ci = np.argmax(up >= L3 * e) if (up >= L3 * e).any() else -1
        if ci < 0:
            continue
        ts = list(g["t"])
        bull = np.where(cl > op, vol, 0.0); bear = np.where(cl < op, vol, 0.0)
        cn = np.cumsum(bull - bear); ct = np.cumsum(bull + bear)
        cum_frac = np.divide(cn, ct, out=np.zeros_like(cn), where=ct > 0)
        tk = ts[ci]
        cont = int((up[ci:] >= L4 * e).any())
        rows.append({"d": dd, "yr": dd.year, "ema20": e,
                     "tod": tk.hour * 60 + tk.minute, "cum_frac": float(cum_frac[ci]), "cont": cont})
    return pd.DataFrame(rows)


def gap_split(g, col, invert=False):
    """中位數切強弱,回傳 (強rate, 弱rate, n強, n弱)。invert: 小值=強。"""
    m = g[col].median()
    strong = g[col] <= m if invert else g[col] >= m
    return g[strong]["cont"].mean(), g[~strong]["cont"].mean(), int(strong.sum()), int((~strong).sum())


def main():
    df = build()
    df["reg"] = pd.qcut(df["ema20"], 3, labels=["低波", "中波", "高波"])
    REG = ["低波", "中波", "高波"]
    L = ["=" * 96,
         f"H116 Phase 1（全 TX 歷史,多 regime）— 累積淨力 早碰層修正  L3 事件 N={len(df)}",
         f"  窗 {df['d'].min()}~{df['d'].max()}；regime=ema20 三分位"]
    L.append(f"  base P(L4|L3) 全體={df['cont'].mean():.0%}")
    L.append("  各 regime ema20 中位 / base：" + " ｜ ".join(
        f"{r}: ema20={df[df.reg==r]['ema20'].median():.0f}/base={df[df.reg==r]['cont'].mean():.0%}(n{len(df[df.reg==r])})" for r in REG))
    L.append("  各年事件數 / base：" + " ｜ ".join(
        f"{y}:{df[df.yr==y]['cont'].mean():.0%}(n{len(df[df.yr==y])})" for y in sorted(df['yr'].unique())))

    # A. 時點 gap by regime（主軸 robustness）
    L.append("\n" + "═" * 96)
    L.append("A) 碰觸時點 gap（早碰−晚碰,各 regime 內中位切;主軸是否跨 regime 穩）")
    tmed_all = df["tod"].median()
    for r in REG:
        g = df[df.reg == r]
        s, w, ns, nw = gap_split(g, "tod", invert=True)
        L.append(f"   {r}: 早碰={s:.0%}(n{ns}) 晚碰={w:.0%}(n{nw})  gap={s-w:+.0%}")

    # B. 累積淨力分帶 P(L4|L3) by regime（方向 regime-stable?）
    L.append("\n" + "═" * 96)
    L.append("B) 累積淨力 gap（買壓−賣壓,各 regime 內中位切;方向是否 regime-stable）")
    for r in REG:
        g = df[df.reg == r]
        s, w, ns, nw = gap_split(g, "cum_frac")
        L.append(f"   {r}: 買壓={s:.0%}(n{ns}) 賣壓={w:.0%}(n{nw})  gap={s-w:+.0%}")
    L.append("   各年累積淨力 gap：" + " ｜ ".join(
        f"{y}:{(lambda s,w,a,b:f'{s-w:+.0%}(n{a+b})')(*gap_split(df[df.yr==y],'cum_frac'))}" for y in sorted(df['yr'].unique())))

    # C. ★ 早碰層 累積淨力增量 by regime（Invalidation #1）
    L.append("\n" + "═" * 96)
    L.append("C) ★ 早碰層 累積淨力增量 by regime（控時點後;早碰=各 regime 內時點<中位）")
    for r in REG:
        g = df[df.reg == r]
        tmed = g["tod"].median()
        early = g[g.tod <= tmed]
        if len(early) < 8:
            L.append(f"   {r} 早碰層: n={len(early)} 太少"); continue
        s, w, ns, nw = gap_split(early, "cum_frac")
        L.append(f"   {r} 早碰層: 買壓={s:.0%}(n{ns}) 賣壓={w:.0%}(n{nw})  增量gap={s-w:+.0%}")
    # 2022 熊單列
    g22 = df[df.yr == 2022]
    if len(g22):
        tmed = g22["tod"].median(); e22 = g22[g22.tod <= tmed]
        s, w, ns, nw = gap_split(e22, "cum_frac")
        L.append(f"   〔2022 熊市單列〕早碰層: 買壓={s:.0%}(n{ns}) 賣壓={w:.0%}(n{nw})  增量gap={s-w:+.0%}")

    L.append("\n  ⚠ TX-only(無 stock_min 依賴),全史多 regime;GATE 看 C 是否跨 regime（含 2022 熊）同向不翻。")
    txt = "\n".join(L)
    print(txt)
    out = HERE / "results"; out.mkdir(exist_ok=True)
    (out / "distribution_raw.txt").write_text(txt + "\n")
    df.to_csv(out / "h116_fullhist_panel.csv", index=False)
    print(f"\n存：{out/'distribution_raw.txt'}")


if __name__ == "__main__":
    main()
