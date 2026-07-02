#!/usr/bin/env python3
"""
H133 Phase 1 — 盤前多空計分表有效性審計

共用 harness：對每個「盤前訊號」逐日算出 causal 讀數（long/short/neutral），
再以三個早盤時段窗口衡量兩種 outcome：
  1) 方向命中率 vs base rate（含 same-mix 虛無：控制訊號自身多空傾斜）
  2) 機械交易 P&L（窗口起點進、終點出、投票方向、成本可調）

三道關卡：逐年拆 + regime 拆（VIX 中位）+ 方向與 P&L 並列。

審計對象：現行 key_prices.py 四訊號 + 合計投票。
所有訊號嚴格 causal（只用 D 日 08:45 前可得資料）。

用法：
    uv run python research/active/H133-preopen-scorecard-audit/explore.py
"""
import duckdb
import numpy as np
import pandas as pd
from pathlib import Path

DB = Path(__file__).parents[3] / "data" / "futures.duckdb"
SYMBOL = "TX"

# 成本：3 點/邊（round-trip 6）— 沿用 brainstorming 設計；同時報 gross 供成本敏感度參考
COST_PER_SIDE = 3.0
COST_RT = COST_PER_SIDE * 2

WINDOWS = {
    "08:45-09:30": ("08:45:00", "09:30:00"),
    "09:00-10:30": ("09:00:00", "10:30:00"),
    "08:45-11:30": ("08:45:00", "11:30:00"),
}


# ══════════════════════════════════════════════════════════════════
# 1. 載入原始資料
# ══════════════════════════════════════════════════════════════════
def load_data():
    con = duckdb.connect(str(DB), read_only=True)

    # 全部 TX 1 分 K（日盤 + 夜盤）
    bars = con.execute("""
        SELECT timestamp, open, high, low, close, volume
        FROM ohlcv_1m WHERE symbol = ?
        ORDER BY timestamp
    """, [SYMBOL]).df()
    bars["timestamp"] = pd.to_datetime(bars["timestamp"])
    for c in ("open", "high", "low", "close"):
        bars[c] = bars[c].astype(float)

    # 換倉日（排除，避免 gap 污染 P&L）
    roll = con.execute(
        "SELECT rollover_date FROM rollover_log WHERE symbol = ?", [SYMBOL]
    ).df()
    roll_dates = set(pd.to_datetime(roll["rollover_date"]).dt.date)

    # 昨日 VIX（regime 分層用）— 用 D 日「前一日」的 VIX
    try:
        vix = con.execute(
            "SELECT trade_date, close FROM vixtwn ORDER BY trade_date").df()
        vix["trade_date"] = pd.to_datetime(vix["trade_date"]).dt.date
        vix_map = dict(zip(vix["trade_date"], vix["close"].astype(float)))
    except Exception:
        vix_map = {}

    con.close()
    return bars, roll_dates, vix_map


# ══════════════════════════════════════════════════════════════════
# 2. 日盤 / 夜盤 per-day 聚合
# ══════════════════════════════════════════════════════════════════
def build_sessions(bars):
    t = bars["timestamp"].dt.time
    tstr = bars["timestamp"].dt.strftime("%H:%M:%S")
    date = bars["timestamp"].dt.date

    is_day = (tstr >= "08:45:00") & (tstr <= "13:45:00")
    day = bars[is_day].copy()
    day["d"] = date[is_day]

    # 日盤 per-day：open/close/high/low/vwap + 三窗口 close-open
    def _first(s):
        return s.iloc[0]

    def _last(s):
        return s.iloc[-1]

    grp = day.groupby("d")
    ds = grp.agg(
        day_open=("open", _first),
        day_close=("close", _last),
        day_high=("high", "max"),
        day_low=("low", "min"),
    )
    # VWAP
    day["_pv"] = day["close"] * day["volume"]
    vw = day.groupby("d").apply(
        lambda g: g["_pv"].sum() / g["volume"].sum() if g["volume"].sum() else np.nan
    )
    ds["vwap"] = vw

    # 三窗口 open(first)/close(last)
    dts = day["timestamp"].dt.strftime("%H:%M:%S")
    for name, (t0, t1) in WINDOWS.items():
        m = (dts >= t0) & (dts <= t1)
        sub = day[m]
        g = sub.groupby("d")
        o = g["open"].apply(_first)
        c = g["close"].apply(_last)
        ds[f"win_{name}_ret"] = c - o
    ds = ds.reset_index()

    # 夜盤 per-trading-day P：night 收盤/高/低（P 15:00 → 次一 05:00）
    # 以「夜盤起始日 P」為 key。凌晨 (<05:00) 段歸屬前一日的夜盤。
    is_night = (tstr >= "15:00:00") | (tstr < "05:00:00")
    night = bars[is_night].copy()
    nt = night["timestamp"]
    # 夜盤起始日：>=15:00 用當日；<05:00 用前一日
    start_day = np.where(nt.dt.strftime("%H:%M:%S") >= "15:00:00",
                         nt.dt.date, (nt - pd.Timedelta(days=1)).dt.date)
    night["P"] = start_day
    ng = night.sort_values("timestamp").groupby("P")
    ns = ng.agg(
        night_close=("close", _last),
        night_high=("high", "max"),
        night_low=("low", "min"),
        n_night=("close", "count"),
    ).reset_index()
    ns = ns[ns["n_night"] >= 100]  # 需足夠夜盤 bar

    return ds, ns, day


# ══════════════════════════════════════════════════════════════════
# 3. 30m 日盤 bar（扣底用）與 1H 連續 bar（MACD 用）
# ══════════════════════════════════════════════════════════════════
def build_30m_day(day):
    """日盤 30m bar（bucket 對齊 08:45；13:45 併入 13:15），全歷史連續。"""
    dd = day.copy()
    base = pd.Timestamp("2000-01-01 08:45:00")
    # 對齊 08:45 的 30 分 bucket
    delta = (dd["timestamp"] - base)
    bucket = base + (delta // pd.Timedelta("30min")) * pd.Timedelta("30min")
    # 13:45 這根併入前一個 bucket
    is_1345 = bucket.dt.strftime("%H:%M:%S") == "13:45:00"
    bucket = bucket.mask(is_1345, bucket - pd.Timedelta("30min"))
    dd["bucket"] = bucket
    g = dd.sort_values("timestamp").groupby("bucket")
    b30 = g.agg(close=("close", lambda s: s.iloc[-1])).reset_index()
    b30["d"] = b30["bucket"].dt.date
    b30 = b30.sort_values("bucket").reset_index(drop=True)
    return b30


def _ema(arr, period):
    arr = np.asarray(arr, dtype=float)
    out = np.full_like(arr, np.nan)
    if len(arr) == 0:
        return out
    a = 2.0 / (period + 1)
    out[0] = arr[0]
    for i in range(1, len(arr)):
        out[i] = arr[i] * a + out[i - 1] * (1 - a)
    return out


def build_1h_macd(bars):
    """全歷史 1H bar（日盤+夜盤，floor 到小時）→ MACD(12,26,9) hist 序列。"""
    b = bars.copy()
    b["h"] = b["timestamp"].dt.floor("h")
    g = b.sort_values("timestamp").groupby("h")
    h1 = g.agg(close=("close", lambda s: s.iloc[-1])).reset_index()
    h1 = h1.sort_values("h").reset_index(drop=True)
    closes = h1["close"].values
    macd = _ema(closes, 12) - _ema(closes, 26)
    signal = _ema(macd, 9)
    h1["hist"] = macd - signal
    return h1  # columns: h (hour ts), close, hist


# ══════════════════════════════════════════════════════════════════
# 4. 逐日組裝訊號 + outcomes
# ══════════════════════════════════════════════════════════════════
def assemble(ds, ns, b30, h1, roll_dates, vix_map):
    ds = ds.sort_values("d").reset_index(drop=True)
    trading_days = ds["d"].tolist()
    day_arr = np.array([pd.Timestamp(d) for d in trading_days], dtype="datetime64[ns]")

    night_close = dict(zip(ns["P"], ns["night_close"]))
    night_high = dict(zip(ns["P"], ns["night_high"]))
    night_low = dict(zip(ns["P"], ns["night_low"]))
    ds_idx = ds.set_index("d")

    # 30m 陣列（for 扣底）
    b30_close = b30["close"].values
    b30_ts = b30["bucket"].values.astype("datetime64[ns]")

    # 1H hist 陣列
    h1_ts = h1["h"].values.astype("datetime64[ns]")
    h1_hist = h1["hist"].values

    rows = []
    for i in range(1, len(trading_days)):
        D = trading_days[i]
        P = trading_days[i - 1]          # 前一交易日
        if D in roll_dates:
            continue
        if P not in night_close:
            continue
        ref = night_close[P]             # 盤前基準 = 夜盤(P)收
        if ref is None or np.isnan(ref):
            continue

        rec = {"D": D, "P": P, "wd": pd.Timestamp(D).weekday(), "ref": ref}

        # --- 訊號 1：1H MACD 方向（hist>=0 多）---
        # 取 D 08:00 前最後一根 1H bar 的 hist
        cut = np.datetime64(pd.Timestamp(D) + pd.Timedelta(hours=8))
        j = np.searchsorted(h1_ts, cut, side="left") - 1
        if j >= 26:                      # 需足夠 warmup
            hist = h1_hist[j]
            rec["s_macd"] = "long" if hist >= 0 else "short"
        else:
            rec["s_macd"] = None

        # --- 訊號 2：30m 20MA 方向（夜收 vs 扣底）---
        # P 日最後一根 30m bar 的 index k；扣底 = close[k-19]
        cutb = np.datetime64(pd.Timestamp(P) + pd.Timedelta(hours=14))  # <=P 13:xx
        k = np.searchsorted(b30_ts, cutb, side="right") - 1
        if k >= 19:
            deduct = b30_close[k - 19]
            rec["s_ma20"] = "long" if ref > deduct else "short"
        else:
            rec["s_ma20"] = None

        # --- 訊號 3：週幾早盤勝率（trailing 40 交易日，09:00-10:30）---
        wd = rec["wd"]
        lo = max(0, i - 40)
        hist_days = trading_days[lo:i]                    # 不含 D（causal）
        up = dn = 0
        col = "win_09:00-10:30_ret"
        for hd in hist_days:
            if pd.Timestamp(hd).weekday() != wd:
                continue
            if hd not in ds_idx.index:
                continue
            r = ds_idx.at[hd, col]
            if pd.isna(r):
                continue
            if r > 0:
                up += 1
            elif r < 0:
                dn += 1
        tot = up + dn
        if tot >= 3:
            pct = up / tot
            rec["s_weekday"] = "long" if pct > 0.5 else ("short" if pct < 0.5 else None)
        else:
            rec["s_weekday"] = None

        # --- 訊號 4：夜盤位置 vs 昨/前成本 ---
        pd_high = ds_idx.at[P, "day_high"]
        pd_low = ds_idx.at[P, "day_low"]
        pd_vwap = ds_idx.at[P, "vwap"]
        if ref > pd_high:
            rec["s_pos"] = "long"
        elif ref < pd_low:
            rec["s_pos"] = "short"
        elif not pd.isna(pd_vwap) and ref > pd_vwap:
            rec["s_pos"] = "long"
        elif not pd.isna(pd_vwap) and ref < pd_vwap:
            rec["s_pos"] = "short"
        else:
            rec["s_pos"] = None

        # --- 合計投票 ---
        sides = [rec["s_macd"], rec["s_ma20"], rec["s_weekday"], rec["s_pos"]]
        nl = sum(1 for s in sides if s == "long")
        nsh = sum(1 for s in sides if s == "short")
        rec["s_vote"] = "long" if nl > nsh else ("short" if nsh > nl else None)

        # --- outcomes：三窗口 close-open ---
        for name in WINDOWS:
            rec[f"ret_{name}"] = ds_idx.at[D, f"win_{name}_ret"]

        # regime：D 前一日 VIX
        rec["vix"] = vix_map.get(P, np.nan)
        rec["year"] = pd.Timestamp(D).year
        rows.append(rec)

    return pd.DataFrame(rows)


# ══════════════════════════════════════════════════════════════════
# 5. 評估指標
# ══════════════════════════════════════════════════════════════════
SIGNALS = {
    "s_macd": "1H MACD 方向",
    "s_ma20": "30m 20MA 方向",
    "s_weekday": "週幾早盤勝率",
    "s_pos": "夜盤位置 vs 成本",
    "s_vote": "合計投票",
}


def eval_signal(df, sig, win):
    """回傳單一 (訊號×窗口) 的評估 dict。"""
    ret_col = f"ret_{win}"
    d = df[[sig, ret_col, "year", "vix"]].dropna(subset=[sig, ret_col])
    d = d[d[sig] != None]
    d = d[d[sig].isin(["long", "short"])]
    if len(d) == 0:
        return None
    ret = d[ret_col].values
    side = np.where(d[sig].values == "long", 1.0, -1.0)

    # base rate（該窗口全體）
    base_up = (df[ret_col] > 0).mean()
    n_long = int((side > 0).sum())
    n_short = int((side < 0).sum())
    N = len(d)

    # 方向命中率
    hit = ((side > 0) & (ret > 0)) | ((side < 0) & (ret < 0))
    hit_rate = hit.mean()
    # same-mix 虛無：若隨機投票但維持同樣多空比例的期望命中
    exp_hit = (n_long / N) * base_up + (n_short / N) * (1 - base_up)
    lift_mix = hit_rate - exp_hit
    # vs always-majority accuracy
    base_acc = max(base_up, 1 - base_up)
    lift_maj = hit_rate - base_acc

    # P&L（net 3/邊 = round-trip 6）
    pnl_gross = side * ret
    pnl_net = pnl_gross - COST_RT
    wins = pnl_net > 0
    gross_pos = pnl_net[pnl_net > 0].sum()
    gross_neg = -pnl_net[pnl_net < 0].sum()
    pf = gross_pos / gross_neg if gross_neg > 0 else np.inf

    # 逐年 net mean
    yearly = {}
    for y in sorted(d["year"].unique()):
        m = d["year"] == y
        yearly[int(y)] = {
            "n": int(m.sum()),
            "mean_net": float(np.round((side[m.values] * ret[m.values] - COST_RT).mean(), 1)),
            "hit": float(np.round((((side[m.values] > 0) & (ret[m.values] > 0)) |
                                    ((side[m.values] < 0) & (ret[m.values] < 0))).mean(), 3)),
        }
    yrs_pos = sum(1 for v in yearly.values() if v["mean_net"] > 0)
    yrs_tot = len(yearly)

    # regime：VIX 中位拆
    reg = {}
    dv = d.dropna(subset=["vix"])
    if len(dv) > 20:
        med = dv["vix"].median()
        for lab, mask in [("低VIX", dv["vix"] <= med), ("高VIX", dv["vix"] > med)]:
            sub = dv[mask]
            sside = np.where(sub[sig].values == "long", 1.0, -1.0)
            sret = sub[ret_col].values
            reg[lab] = {
                "n": len(sub),
                "mean_net": float(np.round((sside * sret - COST_RT).mean(), 1)),
                "hit": float(np.round((((sside > 0) & (sret > 0)) |
                                        ((sside < 0) & (sret < 0))).mean(), 3)),
            }

    return {
        "N": N, "n_long": n_long, "n_short": n_short,
        "base_up": round(float(base_up), 3),
        "hit_rate": round(float(hit_rate), 3),
        "exp_hit_samemix": round(float(exp_hit), 3),
        "lift_mix": round(float(lift_mix), 3),
        "lift_maj": round(float(lift_maj), 3),
        "mean_gross": round(float(pnl_gross.mean()), 1),
        "mean_net": round(float(pnl_net.mean()), 1),
        "pf": round(float(pf), 2),
        "win_rate": round(float(wins.mean()), 3),
        "yrs_pos": yrs_pos, "yrs_tot": yrs_tot,
        "yearly": yearly,
        "regime": reg,
    }


def main():
    print("載入資料 …")
    bars, roll_dates, vix_map = load_data()
    ds, ns, day = build_sessions(bars)
    b30 = build_30m_day(day)
    h1 = build_1h_macd(bars)
    print(f"  日盤日數={len(ds)}  夜盤日數={len(ns)}  30m bars={len(b30)}  1H bars={len(h1)}")

    print("組裝逐日訊號 …")
    df = assemble(ds, ns, b30, h1, roll_dates, vix_map)
    print(f"  可評估日數 N={len(df)}（扣換倉/缺夜盤），{df['D'].min()} ~ {df['D'].max()}")

    # 存逐日表
    out_dir = Path(__file__).parent / "results"
    out_dir.mkdir(exist_ok=True)
    df.to_csv(out_dir / "h133_daily.csv", index=False)

    # base rate 概覽
    print("\n=== 窗口 base rate（全體當多比例 / 平均 close-open）===")
    for win in WINDOWS:
        rc = f"ret_{win}"
        print(f"  {win}: base_up={ (df[rc]>0).mean():.3f}  "
              f"mean={df[rc].mean():+.1f}  median={df[rc].median():+.1f}  N={df[rc].notna().sum()}")

    # 逐訊號 × 窗口
    results = {}
    for sig, label in SIGNALS.items():
        results[sig] = {}
        print(f"\n{'='*70}\n訊號：{label}  ({sig})\n{'='*70}")
        for win in WINDOWS:
            r = eval_signal(df, sig, win)
            results[sig][win] = r
            if r is None:
                print(f"  {win}: 無有效樣本")
                continue
            print(f"  ── {win} ──  N={r['N']} (多{r['n_long']}/空{r['n_short']})")
            print(f"     方向: hit={r['hit_rate']:.3f}  base_up={r['base_up']:.3f}  "
                  f"lift(samemix)={r['lift_mix']:+.3f}  lift(vs多數)={r['lift_maj']:+.3f}")
            print(f"     P&L : mean_net={r['mean_net']:+.1f} (gross {r['mean_gross']:+.1f})  "
                  f"PF={r['pf']}  win={r['win_rate']:.3f}  逐年正={r['yrs_pos']}/{r['yrs_tot']}")
            yr = "  ".join(f"{y}:{v['mean_net']:+.0f}" for y, v in r["yearly"].items())
            print(f"     逐年net: {yr}")
            if r["regime"]:
                rg = "  ".join(f"{k}:{v['mean_net']:+.0f}(hit{v['hit']:.2f},n{v['n']})"
                               for k, v in r["regime"].items())
                print(f"     regime : {rg}")

    # 合計 vs 最佳單一成分（用 09:00-10:30 為主窗口比較）
    print(f"\n{'='*70}\n合計投票 vs 最佳單一成分\n{'='*70}")
    for win in WINDOWS:
        comps = {s: results[s][win] for s in ["s_macd", "s_ma20", "s_weekday", "s_pos"]
                 if results[s][win]}
        vote = results["s_vote"][win]
        if not comps or not vote:
            continue
        best_sig = max(comps, key=lambda s: comps[s]["mean_net"])
        best = comps[best_sig]
        print(f"  {win}: 合計 mean_net={vote['mean_net']:+.1f} (PF{vote['pf']}, "
              f"逐年正{vote['yrs_pos']}/{vote['yrs_tot']}) | "
              f"最佳單一={SIGNALS[best_sig]} {best['mean_net']:+.1f} "
              f"→ 合計{'勝' if vote['mean_net']>best['mean_net'] else '未勝'}")

    # 存 JSON
    import json
    def _clean(o):
        if isinstance(o, dict):
            return {k: _clean(v) for k, v in o.items()}
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, (np.integer,)):
            return int(o)
        return o
    with open(out_dir / "h133_results.json", "w") as f:
        json.dump(_clean(results), f, ensure_ascii=False, indent=2)
    print(f"\n結果存至 {out_dir}/h133_results.json、h133_daily.csv")


if __name__ == "__main__":
    main()
