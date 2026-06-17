"""
H125 Climax Bar Reclaim — Phase 1 分佈探索

事件（causal，無 lookahead，量能爆衝錨定）：
  1. 賣壓 climax bar = 成交量爆衝（vol >= MULT × 近 W 根均量）且當根創近 W 根新低（破底的下殺）。
  2. 出現 climax 即武裝；武裝期間若再出現更大量且續創低的 climax，錨點上移到新的最大量 K
     （對應「持續放量下殺取最大量那根」）。
  3. 當後續某根 K 的 close > climax bar 的 high（且在 climax 之後）→ 觸發做多事件，於該 K 收盤進場。
  4. 觸發後 disarm；逾 EXPIRE 根未收復則作廢；之後可被新的 climax 重新武裝。

度量：forward 報酬 +15/+30/+60 分鐘、到日盤收盤(13:45)。長方向。
虛無對照：同日「隨機進場分鐘」的同 horizon 報酬分佈（控制當日 drift / 趨勢日）。
切片：進場時段、leg 跌幅、climax 量比、事前 60 分壓縮度。

與 H062 區隔：H062 凸量 K 雙向突破；本假設限定「破新低的賣壓 climax + 只做多收復其高點」。

用法：
  uv run python research/active/H125-climax-bar-reclaim/explore.py
  uv run python research/active/H125-climax-bar-reclaim/explore.py --debug-date 2026-06-17
  uv run python research/active/H125-climax-bar-reclaim/explore.py --mult 4 --window 20
"""
import argparse
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

DB_PATH = "data/futures.duckdb"
OUT = Path(__file__).parent / "results"
SESSION_START = "08:45:00"
SESSION_END = "13:45:00"
SUST_WIN = 3           # 持續放量窗（近 N 根）
BASE_WIN = 10          # 基準均量窗（再往前 N 根，即「10 分鐘前」）
SUST_MULT = 2.5        # 持續放量門檻：mean(近3根) >= MULT × mean(再前10根)
EXPIRE = 30            # climax 武裝後逾 N 根未收復則作廢
RECENT_HIGH_WIN = 30   # leg 跌幅 = 近 N 根 high - climax low
FWD_MINS = [15, 30, 60]
COST_PTS = 2.0         # 參考用：來回成本（分佈階段僅標示，不扣）


def load_days():
    with duckdb.connect(DB_PATH, read_only=True) as conn:
        df = conn.execute(f"""
            SELECT timestamp, open AS o, high AS h, low AS l, close AS c, volume AS v
            FROM ohlcv_1m
            WHERE symbol='TX'
              AND CAST(timestamp AS TIME) BETWEEN TIME '{SESSION_START}' AND TIME '{SESSION_END}'
            ORDER BY timestamp
        """).df()
    df["date"] = df["timestamp"].dt.normalize()
    df["minute"] = df["timestamp"].dt.strftime("%H:%M")
    return df


def detect_events_one_day(day: pd.DataFrame, mult=SUST_MULT, sust=SUST_WIN,
                          base=BASE_WIN, expire=EXPIRE):
    """線上偵測一日內所有 climax-reclaim 多方事件（持續放量錨定）。回傳 list[dict]。

    持續放量資格：mean(近 sust 根量) >= mult × mean(再往前 base 根量)，且當根創近(sust+base)根新低。
    錨點：合格那段的「最大量單根」K 的 high（持續放量取最大量那根）。
    """
    h_ = day["h"].to_numpy(float)
    l_ = day["l"].to_numpy(float)
    c_ = day["c"].to_numpy(float)
    v_ = day["v"].to_numpy(float)
    n = len(c_)
    warm = sust + base
    if n < warm + 5:
        return []

    events = []
    armed = None  # dict(idx, high, vol, vr, low_so_far, start) 或 None

    for i in range(warm, n):
        sust_v = v_[i - sust + 1:i + 1].mean()             # 近 sust 根均量
        base_v = v_[i - sust + 1 - base:i - sust + 1].mean()  # 再往前 base 根均量
        vr = sust_v / base_v if base_v > 0 else 0.0
        is_local_low = l_[i] <= l_[i - warm:i + 1].min()   # 創近 (sust+base) 根新低（破底下殺）
        is_climax = (vr >= mult) and is_local_low

        # --- 武裝 / 更新錨點（錨到該段最大量單根）---
        if is_climax:
            # 合格段內最大量單根 = 近 sust 根中量最大者
            seg = slice(i - sust + 1, i + 1)
            mj = i - sust + 1 + int(np.argmax(v_[seg]))
            if armed is None:
                armed = dict(idx=mj, high=h_[mj], vol=v_[mj], vr=vr,
                             low_so_far=l_[i], start=i)
            elif v_[mj] > armed["vol"]:
                # 持續放量下殺 → 錨到更大量那根
                armed.update(idx=mj, high=h_[mj], vol=v_[mj], vr=vr)

        if armed is not None:
            if l_[i] < armed["low_so_far"]:
                armed["low_so_far"] = l_[i]

            # --- 收復偵測：close 站上 climax bar high ---
            if i > armed["idx"] and c_[i] > armed["high"]:
                recent_high = h_[max(0, armed["start"] - RECENT_HIGH_WIN):armed["start"] + 1].max()
                events.append(dict(
                    entry_idx=i,
                    entry_min=day["minute"].iloc[i],
                    entry_price=c_[i],
                    climax_idx=armed["idx"],
                    climax_min=day["minute"].iloc[armed["idx"]],
                    climax_high=armed["high"],
                    climax_vol=armed["vol"],
                    climax_vr=armed["vr"],
                    leg_low=armed["low_so_far"],
                    leg_drop=recent_high - armed["low_so_far"],
                ))
                armed = None  # disarm；之後可被新 climax 重新武裝
            # --- 逾期作廢 ---
            elif i - armed["idx"] >= expire:
                armed = None

    return events


def day_forward_stats(day: pd.DataFrame, entry_idx: int):
    """事件的 forward 報酬（點 & %），及同日隨機進場虛無對照。"""
    c_ = day["c"].to_numpy(float)
    n = len(c_)
    ep = c_[entry_idx]
    out = {}
    for m in FWD_MINS:
        j = entry_idx + m
        if j < n:
            ret_pt = c_[j] - ep
            out[f"fwd{m}_pt"] = ret_pt
            out[f"fwd{m}_pct"] = ret_pt / ep * 100
            # 同日隨機進場 null（固定 horizon m）
            base = c_[m:] - c_[:-m]            # 每個起點的 m 分鐘位移（點）
            out[f"fwd{m}_null_mean_pt"] = base.mean()
            out[f"fwd{m}_excess_pt"] = ret_pt - base.mean()
            # 事件報酬在當日隨機分佈的 percentile
            out[f"fwd{m}_pctile"] = (base < ret_pt).mean() * 100
        else:
            for k in (f"fwd{m}_pt", f"fwd{m}_pct", f"fwd{m}_null_mean_pt",
                      f"fwd{m}_excess_pt", f"fwd{m}_pctile"):
                out[k] = np.nan
    # 到收盤
    ret_close = c_[-1] - ep
    out["fwd_close_pt"] = ret_close
    out["fwd_close_pct"] = ret_close / ep * 100
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--debug-date", default=None)
    ap.add_argument("--mult", type=float, default=SUST_MULT)
    ap.add_argument("--sust", type=int, default=SUST_WIN)
    ap.add_argument("--base", type=int, default=BASE_WIN)
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)

    df = load_days()
    dates = sorted(df["date"].unique())

    rows = []
    for d in dates:
        day = df[df["date"] == d].reset_index(drop=True)
        evs = detect_events_one_day(day, mult=args.mult, sust=args.sust, base=args.base)
        for k, e in enumerate(evs):
            fs = day_forward_stats(day, e["entry_idx"])
            # 事前 60 分壓縮度：climax 起算前 60 根的 range / 同日盤全程 range（越小越壓縮）
            cidx = e["climax_idx"]
            pre = day.iloc[max(0, cidx - 60):cidx]
            day_rng = day["h"].max() - day["l"].min()
            pre_range = (pre["h"].max() - pre["l"].min()) if len(pre) >= 20 else np.nan
            comp_ratio = pre_range / day_rng if (np.isfinite(pre_range) and day_rng > 0) else np.nan
            rows.append(dict(date=d, ev_k=k, first_of_day=(k == 0),
                             pre_range=pre_range, comp_ratio=comp_ratio, **e, **fs))

    res = pd.DataFrame(rows)
    res.to_csv(OUT / "events.csv", index=False)

    if args.debug_date:
        dd = pd.Timestamp(args.debug_date).normalize()
        sub = res[res["date"] == dd]
        print(f"\n=== DEBUG {args.debug_date}：偵測到 {len(sub)} 事件 ===")
        cols = ["entry_min", "entry_price", "climax_min", "climax_high", "climax_vol",
                "climax_vr", "leg_low", "leg_drop", "fwd30_pt", "fwd60_pt", "fwd_close_pt"]
        print(sub[cols].to_string(index=False) if len(sub) else "（無）")

    summarize(res)


def _agg(g):
    out = {"N": len(g)}
    for m in FWD_MINS:
        s = g[f"fwd{m}_pt"].dropna()
        ex = g[f"fwd{m}_excess_pt"].dropna()
        pc = g[f"fwd{m}_pctile"].dropna()
        out[f"fwd{m}_med"] = s.median()
        out[f"fwd{m}_mean"] = s.mean()
        out[f"fwd{m}_win%"] = (s > 0).mean() * 100
        out[f"fwd{m}_excess"] = ex.mean()
        out[f"fwd{m}_pctile"] = pc.mean()
    cl = g["fwd_close_pt"].dropna()
    out["close_med"] = cl.median()
    out["close_win%"] = (cl > 0).mean() * 100
    return pd.Series(out)


def summarize(res: pd.DataFrame):
    print("\n" + "=" * 70)
    print(f"H125 Climax Bar Reclaim — Phase 1 分佈（全樣本 N={len(res)}）")
    print(f"時間範圍：{res['date'].min().date()} ~ {res['date'].max().date()}，"
          f"涵蓋 {res['date'].nunique()} 個交易日")
    print("=" * 70)

    print("\n[整體 forward 報酬]")
    print(_agg(res).to_string())

    print("\n[只取每日第一個事件]")
    print(_agg(res[res["first_of_day"]]).to_string())

    # 切片：進場時段
    def tbucket(m):
        hh, mm = int(m[:2]), int(m[3:])
        t = hh * 60 + mm
        if t < 10 * 60: return "0845-1000"
        if t < 11 * 60 + 30: return "1000-1130"
        if t < 13 * 60: return "1130-1300"
        return "1300-1345"
    res = res.copy()
    res["tbucket"] = res["entry_min"].map(tbucket)
    print("\n[切片：進場時段]")
    print(res.groupby("tbucket").apply(_agg, include_groups=False).to_string())

    # 切片：leg 跌幅（點）
    res["leg_bin"] = pd.cut(res["leg_drop"], [0, 60, 120, 200, 1e9],
                            labels=["<60", "60-120", "120-200", ">200"])
    print("\n[切片：leg 跌幅(點)]")
    print(res.groupby("leg_bin", observed=True).apply(_agg, include_groups=False).to_string())

    # 切片：持續放量量比（近3根 / 前10根）
    res["vr_bin"] = pd.cut(res["climax_vr"], [0, 3, 4, 6, 1e9],
                           labels=["2.5-3x", "3-4x", "4-6x", ">6x"])
    print("\n[切片：持續放量量比 (近3/前10)]")
    print(res.groupby("vr_bin", observed=True).apply(_agg, include_groups=False).to_string())

    # 切片：事前 60 分壓縮度（comp_ratio = 前60分range / 當日全程range；越小越壓縮）
    res["comp_bin"] = pd.cut(res["comp_ratio"], [0, 0.25, 0.4, 0.6, 1e9],
                             labels=["<0.25壓縮", "0.25-0.4", "0.4-0.6", ">0.6寬"])
    print("\n[切片：事前60分壓縮度 comp_ratio]")
    print(res.groupby("comp_bin", observed=True).apply(_agg, include_groups=False).to_string())

    # 年度穩定度（用 +30 分）
    res["year"] = res["date"].dt.year
    print("\n[年度穩定度 fwd30]")
    yr = res.groupby("year").apply(
        lambda g: pd.Series({
            "N": len(g),
            "fwd30_med": g["fwd30_pt"].median(),
            "fwd30_win%": (g["fwd30_pt"] > 0).mean() * 100,
            "fwd30_excess": g["fwd30_excess_pt"].mean(),
        }), include_groups=False)
    print(yr.to_string())

    _plot(res, yr)
    print("\n→ events.csv + distribution.png 已輸出，結論寫入 distribution.md")


def _plot(res, yr):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(2, 2, figsize=(13, 9))

    # (a) fwd30/fwd60 報酬分佈
    ax[0, 0].hist(res["fwd30_pt"].dropna().clip(-80, 80), bins=60, alpha=0.6, label="fwd30")
    ax[0, 0].hist(res["fwd60_pt"].dropna().clip(-80, 80), bins=60, alpha=0.5, label="fwd60")
    ax[0, 0].axvline(0, color="k", lw=0.8)
    ax[0, 0].set_title(f"Forward 報酬分佈 (點)  N={len(res)}")
    ax[0, 0].legend()

    # (b) leg 跌幅 → fwd30 excess
    g = res.groupby("leg_bin", observed=True)["fwd30_excess_pt"].mean()
    nb = res.groupby("leg_bin", observed=True).size()
    ax[0, 1].bar([f"{k}\nN={nb[k]}" for k in g.index], g.values, color="tab:orange")
    ax[0, 1].axhline(0, color="k", lw=0.8)
    ax[0, 1].set_title("fwd30 excess vs null — by leg 跌幅(點)")

    # (c) 事前壓縮度 → fwd30 excess
    g = res.groupby("comp_bin", observed=True)["fwd30_excess_pt"].mean()
    nb = res.groupby("comp_bin", observed=True).size()
    ax[1, 0].bar([f"{k}\nN={nb[k]}" for k in g.index], g.values, color="tab:green")
    ax[1, 0].axhline(0, color="k", lw=0.8)
    ax[1, 0].set_title("fwd30 excess — by 事前60分壓縮度 (越左越壓縮)")

    # (d) 年度 excess
    ax[1, 1].bar([str(int(y)) for y in yr.index], yr["fwd30_excess"].values, color="tab:blue")
    ax[1, 1].axhline(0, color="k", lw=0.8)
    ax[1, 1].set_title("fwd30 excess — by year")

    fig.suptitle("H125 Climax Bar Reclaim — Phase 1 分佈", fontsize=13)
    fig.tight_layout()
    fig.savefig(OUT / "distribution.png", dpi=110)
    plt.close(fig)


if __name__ == "__main__":
    main()
