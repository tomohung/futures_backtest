"""台指 ladder regime 標籤（因果、實時可判）+ 達成期望/動作查表。

動機（H114 線 + H117 VIX 疊圖）：ladder L3/L4/L5 達成頻率**重度 regime-dependent**——
升壓段深關卡(L4/L5) reach ~2× 降壓段。把升降平均會洗掉差異 → 不同 regime 給不同期望。

★ 主 regime = **組合方向規則**（H117，因果，盤前可判）：
  vix_dir = VIX vs MA20（VIX≥MA20 升 / <降;隱含波動方向）
  rv_dir  = TX 日振幅 EMA5 vs EMA20（已實現波動方向）
  **降壓 = vix_dir 降 AND rv_dir 降（兩者都收縮才算）;否則升壓/擴張。**
  為何組合：VIX-MA20 單獨在「高 VIX 高原」會誤判降壓（VIX 鈍化、MA20 追上,但已實現還在擴張,
  如 2026-06 深關卡狂中）。加 realized 方向確認後,全史分辨最好(anyL4 gap +19)、且修好高原誤判。

★ 額外旗標 extreme = VIX≥35（極端高波）：歷史通關率高(anyL4~62%/L5~36%),但**樣本集中近期(2026)、謹慎**。

★ 因果鐵律：台指 VIX 收盤後才算出 → 盤前只有 D−1;regime(D) 用 VIX/振幅(≤D−1)。
  ⚠ 同期 VIX(D) 會造「升偏空/降偏多」方向假象(與當日跌幅耦合),lag 後消失 → **只判通關率,不偏多空**。

達成期望（2021-02~2026-06,N=1296,組合規則,zero-strategy 全日 reach,因果）：
  升壓：多 L4≈30% L5≈15%、空 L4≈28% L5≈17%（深 reach ~2×;方向中性）
  降壓：多 L4≈17% L5≈6% 、空 L4≈18% L5≈8% （深 reach 稀;方向中性）
★ 反直覺(H117 回撤拆解)：抱滿尾的回撤風險在**升壓**(maxDD −9)不在降壓(−3.6)→ 控回撤/多 trim 的是升壓;
  降壓低波吐回小、抱尾/blend Sharpe 最佳,反可放手。EV 上抱尾兩 regime 皆微幅最佳(賠付不對稱),差別在變異。

用法：
  uv run python src/analysis/vix_regime.py            # 印當前 regime + 近況 + 期望
  uv run python src/analysis/vix_regime.py --csv out/vix_regime.csv   # 落地每日標籤表
  from src.analysis.vix_regime import get_regime, regime_note, regime_table
"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

DB = str(Path(__file__).resolve().parents[2] / "data" / "futures.duckdb")
EXTREME_VIX = 35.0

# 達成期望查表（組合規則 per-side,2021-2026 因果）
REACH_EXPECT = {
    "升壓": {"多L4": 0.30, "多L5": 0.15, "空L4": 0.28, "空L5": 0.17,
            "note": "機會多但凶｜深關卡~2×(別太早砍贏單);高波吐回兇(抱滿尾回撤大)→L4多trim/用blend控回撤｜方向中性,勿用VIX偏多空"},
    "降壓": {"多L4": 0.17, "多L5": 0.06, "空L4": 0.18, "空L5": 0.08,
            "note": "機會少但溫和｜深尾稀(別硬等L5,多在L3/L4滿足);低波吐回小→可舒服抱尾/blend(Sharpe最佳)｜方向中性"},
}


def regime_note(regime: str, level: str, extreme: bool = False) -> str:
    """看盤動作 note;降壓+極高水位追加警語、VIX≥35 加極端旗標（H117）。"""
    note = REACH_EXPECT[regime]["note"]
    if regime == "降壓" and str(level).startswith("極高"):
        note += "｜⚠高VIX但降壓(隱含+已實現皆收縮):關卡寬+收縮→通關率最低,格外別硬等深關卡"
    if extreme:
        note += "｜🔥VIX≥35極端高波:歷史通關率高(anyL4~62%),深關卡常見別過早收(惟樣本集中近期,謹慎)"
    return note


def regime_table(db: str = DB) -> pd.DataFrame:
    """每日 組合 regime（vix_dir + rv_dir → 升壓/降壓）+ 水位 + extreme（皆因果,套用次一交易日）。"""
    with duckdb.connect(db, read_only=True) as c:
        v = c.execute("SELECT date, vix FROM vixtwn ORDER BY date").df()
        rg = c.execute(
            "SELECT CAST(timestamp AS DATE) date, MAX(high)-MIN(low) rng FROM ohlcv_1m WHERE symbol='TX' "
            "AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' GROUP BY 1 ORDER BY 1").df()
    v["date"] = pd.to_datetime(v["date"])
    v["ma20"] = v["vix"].rolling(20).mean()
    rg["date"] = pd.to_datetime(rg["date"]); rg["rng"] = rg["rng"].astype(float)
    rg["ema20r"] = rg["rng"].ewm(span=20, adjust=False).mean()
    rg["ema5r"] = rg["rng"].ewm(span=5, adjust=False).mean()
    rg["rv_dir"] = (rg["ema5r"] >= rg["ema20r"]).map({True: "升", False: "降"})
    df = pd.merge_asof(v.sort_values("date"), rg[["date", "rv_dir"]].sort_values("date"),
                       on="date", direction="backward")
    df["vix_dir"] = df.apply(
        lambda r: ("升" if r["vix"] >= r["ma20"] else "降") if pd.notna(r["ma20"]) else None, axis=1)
    df["regime"] = df.apply(
        lambda r: None if (r["vix_dir"] is None or pd.isna(r["rv_dir"]))
        else ("降壓" if (r["vix_dir"] == "降" and r["rv_dir"] == "降") else "升壓"), axis=1)
    df["level"] = df["vix"].apply(lambda x: "極高>24" if x > 24 else ("高18-24" if x >= 18 else "低<18"))
    df["extreme"] = df["vix"] >= EXTREME_VIX
    return df


def get_regime(as_of: date | None = None, db: str = DB) -> dict | None:
    """指定日（預設最新）的組合 regime（因果,套用次一交易日）。"""
    df = regime_table(db).dropna(subset=["regime"])
    if as_of is not None:
        df = df[df["date"].dt.date <= as_of]
    if df.empty:
        return None
    r = df.iloc[-1]
    return {"date": r["date"].date(), "vix": round(r["vix"], 1), "ma20": round(r["ma20"], 1),
            "regime": r["regime"], "vix_dir": r["vix_dir"], "rv_dir": r["rv_dir"],
            "level": r["level"], "extreme": bool(r["extreme"])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", help="落地每日標籤表到此路徑")
    ap.add_argument("--date", help="指定日 YYYY-MM-DD（預設最新）")
    args = ap.parse_args()

    if args.csv:
        tab = regime_table()[["date", "vix", "ma20", "vix_dir", "rv_dir", "regime", "level", "extreme"]].dropna(subset=["regime"])
        Path(args.csv).parent.mkdir(parents=True, exist_ok=True)
        tab.to_csv(args.csv, index=False)
        print(f"已落地 {len(tab)} 日標籤 → {args.csv}")
        return

    as_of = date.fromisoformat(args.date) if args.date else None
    r = get_regime(as_of)
    if r is None:
        print("無資料"); return
    e = REACH_EXPECT[r["regime"]]
    ex = " 🔥VIX≥35極端" if r["extreme"] else ""
    print(f"=== 台指 ladder regime（最後資料={r['date']}，套用於下一個交易日;因果）===")
    print(f"  VIX={r['vix']} MA20={r['ma20']}（vix_dir {r['vix_dir']} / 已實現 rv_dir {r['rv_dir']}）"
          f" → 主 regime: 【{r['regime']}】 水位:{r['level']}{ex}")
    print(f"\n  下一交易日 ladder 達成期望（{r['regime']},組合規則 2021-2026）:")
    print(f"    多方  L4≈{e['多L4']:.0%}  L5≈{e['多L5']:.0%}　空方  L4≈{e['空L4']:.0%}  L5≈{e['空L5']:.0%}")
    print(f"    → {regime_note(r['regime'], r['level'], r['extreme'])}")
    tab = regime_table().dropna(subset=["regime"])
    if as_of:
        tab = tab[tab["date"].dt.date <= as_of]
    recent = tab.tail(20)
    print("\n  近 20 日 regime 軌跡（VIX / 標籤;🔥=VIX≥35）:")
    print("    " + " ".join(
        f"{int(v)}{'▲' if g=='升壓' else '▽'}{'🔥' if x else ''}"
        for v, g, x in zip(recent["vix"], recent["regime"], recent["extreme"])))


if __name__ == "__main__":
    main()
