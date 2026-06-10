"""台指 VIX regime 標籤（因果、實時可判）+ ladder 達成期望查表。

動機（research/archive…H114 線 + VIX 疊圖）：ladder L3/L4/L5 達成頻率**重度 regime-dependent**——
VIX 升壓段的深關卡(L4/L5) reach ~2× 於降壓段。把升降段平均會洗掉這個 2× 差異
→ 不同 regime 該給不同期望（出場積極度 / 博長尾 EV）。

★ 因果鐵律（盤前只有昨日 VIX）：台指 VIX 收盤後才用當日選擇權算出,**盤前只有 D−1 的 VIX**。
  regime(D) 一律用 **VIX(≤D−1)** 計（嚴格早於 D）。歷史 join 與 live readout 皆遵此。
  ⚠ 偷看 VIX(D) 會出現「升→偏空/降→偏多」的方向假象（VIX(D) 與當日跌幅同期耦合）;
  **lag 後方向偏移消失（多−空L4 +0~+3%）→ 不可用 VIX 偏多空,只能判「深 reach 機率」。**

★ 實時偵測器（皆當日即可算,非 ZigZag 事後）：
  - 壓力 lvl = VIX vs 20 日均線（升壓 VIX≥MA20 / 降壓 <）= 主 regime
  - 方向 dir = VIX 近 20 日變化正負（升/降);水位 = VIX 絕對帶

達成期望查表（2021-02~2026-06,N=1296,zero-strategy 全日 reach,**VIX lag 1 因果版**）：
  升壓：多 L4≈30% L5≈16%、空 L4≈30% L5≈17%（深 reach ~2×;**方向中性**）
  降壓：多 L4≈19% L5≈7% 、空 L4≈19% L5≈10%（深 reach 稀;方向中性）
★ 反直覺(H117 回撤拆解)：抱滿尾的回撤風險在**升壓**(maxDD −9)不在降壓(−3.6)→ 要控回撤/多 trim 的是升壓;
  降壓低波吐回小、抱尾/blend Sharpe 最佳,反可放手。EV 上抱尾兩 regime 皆微幅最佳(賠付不對稱),差別在變異。

用法：
  uv run python src/analysis/vix_regime.py            # 印當前 regime + 近況 + 期望
  uv run python src/analysis/vix_regime.py --csv out/vix_regime.csv   # 落地每日標籤表
  from src.analysis.vix_regime import get_regime, regime_table
"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

DB = str(Path(__file__).resolve().parents[2] / "data" / "futures.duckdb")

# 達成期望查表（升壓 / 降壓;源 2021-2026 ladder × VIX>MA20 疊圖,VIX lag 1 因果版 + H117 回撤拆解）
# note = 看盤動作（含回撤紀律;反直覺重點：要控回撤的是升壓不是降壓）
REACH_EXPECT = {
    "升壓": {"多L4": 0.30, "多L5": 0.16, "空L4": 0.30, "空L5": 0.17,
            "note": "機會多但凶｜深關卡~2×(別太早砍贏單);高波吐回兇(抱滿尾回撤大)→L4多trim/用blend控回撤｜方向中性,勿用VIX偏多空"},
    "降壓": {"多L4": 0.19, "多L5": 0.07, "空L4": 0.19, "空L5": 0.10,
            "note": "機會少但溫和｜深尾稀(別硬等L5,多在L3/L4滿足);低波吐回小→可舒服抱尾/blend(Sharpe最佳)｜方向中性"},
}


def regime_table(db: str = DB) -> pd.DataFrame:
    """每日 VIX + 因果 regime 標籤（升壓/降壓、升/降 方向、水位帶）。"""
    with duckdb.connect(db, read_only=True) as c:
        df = c.execute("SELECT date, vix FROM vixtwn ORDER BY date").df()
    df["date"] = pd.to_datetime(df["date"])
    df["ma20"] = df["vix"].rolling(20).mean()
    df["chg20"] = df["vix"] - df["vix"].shift(20)
    df["regime"] = df.apply(
        lambda r: ("升壓" if r["vix"] >= r["ma20"] else "降壓") if pd.notna(r["ma20"]) else None, axis=1)
    df["dir"] = df["chg20"].apply(lambda x: ("升" if x > 0 else "降") if pd.notna(x) else None)
    df["level"] = df["vix"].apply(lambda v: "極高>24" if v > 24 else ("高 18-24" if v >= 18 else "低<18"))
    return df


def get_regime(as_of: date | None = None, db: str = DB) -> dict:
    """回傳指定日（預設最新）的 regime dict（因果,當日即可判）。"""
    df = regime_table(db).dropna(subset=["regime"])
    if as_of is not None:
        df = df[df["date"].dt.date <= as_of]
    row = df.iloc[-1]
    return {"date": row["date"].date(), "vix": round(row["vix"], 1), "ma20": round(row["ma20"], 1),
            "regime": row["regime"], "dir": row["dir"], "level": row["level"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", help="落地每日標籤表到此路徑")
    ap.add_argument("--date", help="指定日 YYYY-MM-DD（預設最新）")
    args = ap.parse_args()

    if args.csv:
        tab = regime_table()[["date", "vix", "ma20", "regime", "dir", "level"]].dropna(subset=["regime"])
        Path(args.csv).parent.mkdir(parents=True, exist_ok=True)
        tab.to_csv(args.csv, index=False)
        print(f"已落地 {len(tab)} 日標籤 → {args.csv}")
        return

    as_of = date.fromisoformat(args.date) if args.date else None
    r = get_regime(as_of)
    e = REACH_EXPECT[r["regime"]]
    print(f"=== 台指 VIX regime（最後 VIX={r['date']}，套用於下一個交易日;因果）===")
    print(f"  VIX={r['vix']}  MA20={r['ma20']}  → 主 regime: 【{r['regime']}】  方向:{r['dir']}  水位:{r['level']}")
    print(f"\n  下一交易日 ladder 達成期望（{r['regime']},2021-2026 實證 VIX lag 1）:")
    print(f"    多方  L4≈{e['多L4']:.0%}  L5≈{e['多L5']:.0%}　空方  L4≈{e['空L4']:.0%}  L5≈{e['空L5']:.0%}")
    print(f"    → {e['note']}")
    # 近 20 個交易日 regime 軌跡
    tab = regime_table().dropna(subset=["regime"])
    if as_of:
        tab = tab[tab["date"].dt.date <= as_of]
    recent = tab.tail(20)
    print("\n  近 20 日 regime 軌跡（VIX / 標籤）:")
    print("    " + " ".join(f"{int(v)}{'▲' if g=='升壓' else '▽'}" for v, g in zip(recent["vix"], recent["regime"])))


if __name__ == "__main__":
    main()
