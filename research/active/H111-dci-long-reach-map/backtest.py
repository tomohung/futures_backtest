"""H111 Phase 2 — 穩定性 + 可用門檻 + 正式 OOS 複驗（strategy-agnostic，非損益回測）。

讀 results/reach_map_panel.csv（explore.py 全窗產出）。聚焦 W-50 @09:30、目標 L4（Phase 1 甜蜜點），
W-20 @09:15 為對照。
  0. **正式 OOS 複驗**：門檻在 IS(≤2026-02-26, 181日) 校準凍結 → 套 OOS(≥2026-03-01, 69日) 評估。
     誠實 OOS = 參數只看 IS、凍結、再評 OOS；比較 IS lift vs OOS lift / base / 召回。
  1. 絕對門檻掃描（全窗）：P(forward 達 L4 | dci_long ≥ x) vs base（門檻穩健性參考）。
  2. 穩定性：用全窗定的門檻，拆 2025-H2 vs 2026、月別（附 N，誠實標小樣本）。
  3. 下游接口：輸出「強 dci_long → forward 達 L4 機率」條件，供順勢族策略引用。

樣本：全窗 250 日（IS 181 + OOS 69），上市-only、偏多頭。所有數字附 N。
用法：uv run python research/active/H111-dci-long-reach-map/backtest.py
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
PANEL = HERE / "results" / "reach_map_panel.csv"
LVL = {"L3": 0.711, "L4": 0.977, "L5": 1.225}
IS_END = date(2026, 2, 26)        # IS 末日；OOS = 2026-03-01 起


def load():
    df = pd.read_csv(PANEL)
    df["d"] = pd.to_datetime(df.iloc[:, 0]).dt.date
    df["ym"] = pd.to_datetime(df["d"]).dt.to_period("M").astype(str)
    return df


def reach_fwd(df, k, name):
    lvl = LVL[name] * df["ema20"]
    return ((df[f"upsw_{k}"] < lvl) & (df["up_full"] >= lvl)).astype(int)


def oos_verify(df, L):
    """門檻只用 IS 校準凍結 → 套 OOS 評估。比較 IS/OOS lift。"""
    is_m = df["d"] <= IS_END
    L.append("\n" + "=" * 90)
    L.append("⓪ 正式 OOS 複驗（門檻在 IS 校準凍結 → 套 OOS 評估）")
    L.append(f"   IS={int(is_m.sum())}日(≤{IS_END}) / OOS={int((~is_m).sum())}日(≥2026-03-01)")
    for U, K in [("W50", "09:30"), ("W20", "09:15")]:
        col = df[f"{U}_{K}"]; y = reach_fwd(df, K, "L4")
        L.append("\n" + "─" * 90)
        L.append(f"【{U} @{K}】目標 forward-L4")
        for qx in [0.70, 0.80]:
            x = col[is_m].quantile(qx)          # 門檻只看 IS
            for lab, mask in [("IS", is_m), ("OOS", ~is_m)]:
                sub = mask & (col >= x)
                base = y[mask].mean(); rate = y[sub].mean() if sub.sum() else np.nan
                L.append(f"   q{qx:.2f}→x≥{x:+.3f}  {lab:<3} base={base:.0%}(N={int(mask.sum())})  "
                         f"門檻內={rate:.0%}(N={int(sub.sum())})  lift={rate-base:+.0%}")
    return L


def main():
    df = load()
    N = len(df)
    PRIM_U, PRIM_K = "W50", "09:30"          # 主：W-50 @09:30
    ALT_U, ALT_K = "W20", "09:15"            # 對照：W-20 @09:15
    L = ["=" * 90,
         f"H111 Phase 2 — 穩定性 + 可用門檻 + OOS 複驗  N={N}（{df['d'].min()}~{df['d'].max()}）",
         "strategy-agnostic；主 W-50@09:30 目標 L4；上市-only、IS 181 + OOS 69"]

    oos_verify(df, L)

    L.append("\n" + "=" * 90)
    L.append("① 全窗門檻穩健性 + 穩定性（參考；非 OOS）")
    for U, K in [(PRIM_U, PRIM_K), (ALT_U, ALT_K)]:
        col = df[f"{U}_{K}"]; y = reach_fwd(df, K, "L4"); base = y.mean()
        L.append("\n" + "─" * 90)
        L.append(f"【{U} @{K}】目標 forward-L4　base 達成率={base:.1%}（N={N}）")
        # 1. 絕對門檻掃描
        L.append("  ① 門檻掃描 P(forward L4 | dci≥x)：")
        L.append(f"    {'門檻x':>8}{'N(≥x)':>7}{'達成率':>8}{'lift vs base':>13}")
        best = None
        for qx in [0.5, 0.6, 0.7, 0.75, 0.8, 0.9]:
            x = col.quantile(qx); m = col >= x
            n = int(m.sum()); rate = y[m].mean() if n else np.nan
            lift = rate - base
            L.append(f"    ≥{x:>+6.3f}{n:>7}{rate:>8.0%}{lift:>+12.0%}  (q{qx:.2f})")
            if n >= 20 and (best is None or lift > best[3]):
                best = (x, n, rate, lift, qx)
        if best:
            L.append(f"  → 建議門檻 x≥{best[0]:+.3f}(q{best[4]:.2f})：N={best[1]}　"
                     f"達成率={best[2]:.0%} vs base {base:.0%}（lift {best[3]:+.0%}）")
        # 2. 穩定性（用建議門檻拆期）
        if best:
            x = best[0]; m = col >= x
            L.append("  ② 穩定性（建議門檻；附 N，小樣本誠實標）：")
            df2 = df.assign(_hit=y, _sel=m)
            # 2025-H2 vs 2026
            seg = {"2025-H2": df2[df2["ym"] <= "2025-12"], "2026": df2[df2["ym"] >= "2026-01"]}
            for lab, g in seg.items():
                gs = g[g["_sel"]]
                b = g["_hit"].mean()
                r = gs["_hit"].mean() if len(gs) else np.nan
                L.append(f"     {lab:<8} 全段 base={b:.0%}(N={len(g)})　門檻內={r:.0%}(N={len(gs)})  lift={r-b:+.0%}")
            # 月別
            L.append("     月別（門檻內達成率, N）：")
            mo = []
            for ym, g in df2.groupby("ym"):
                gs = g[g["_sel"]]
                if len(gs):
                    mo.append(f"{ym}:{gs['_hit'].mean():.0%}(n{len(gs)})")
            L.append("       " + "  ".join(mo))

    # 3. L3/L5 對照（主 U/K）
    L.append("\n" + "─" * 90)
    L.append(f"③ L3/L5 對照（{PRIM_U}@{PRIM_K}，q0.8 門檻）：")
    col = df[f"{PRIM_U}_{PRIM_K}"]; x = col.quantile(0.8); m = col >= x
    for name in ("L3", "L4", "L5"):
        yy = reach_fwd(df, PRIM_K, name)
        L.append(f"   {name}: base={yy.mean():.0%}　門檻內={yy[m].mean():.0%}(N={int(m.sum())})  lift={yy[m].mean()-yy.mean():+.0%}")

    # 4. 下游接口
    L.append("\n" + "─" * 90)
    col = df[f"{PRIM_U}_{PRIM_K}"]; x = col.quantile(0.8); m = col >= x
    y = reach_fwd(df, PRIM_K, "L4")
    L.append("④ 下游接口（供順勢族策略引用）：")
    L.append(f"   條件：dci_long(W-50, 09:30) ≥ {x:+.3f}（約全窗前 20%）")
    L.append(f"   → 當日 forward 達 L4 機率 ≈ {y[m].mean():.0%}（base {y.mean():.0%}，N={int(m.sum())}/{N}）")
    L.append("   注意：純條件機率，非損益；接策略需另立假設驗證 P&L（[[project_dci_is_extension_signal]] 順勢族）。")

    L.append("\n  ⚠ 全窗 250 日（IS 181 + OOS 69）、偏多頭、上市-only。OOS 複驗見 ⓪ 段。")
    L.append("    結論：W50@09:30 OOS lift 崩(+19%→+2%)；W20@09:15 OOS 守住(+11%)、全窗分段亦穩(+21/+18%)。")
    txt = "\n".join(L)
    print(txt)
    (HERE / "results" / "backtest_raw.txt").write_text(txt + "\n")
    print(f"\n存：{HERE/'results'/'backtest_raw.txt'}")


if __name__ == "__main__":
    main()
