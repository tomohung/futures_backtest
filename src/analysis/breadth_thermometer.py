#!/usr/bin/env python3
"""H079 漲停萎縮溫度計 — 早盤觀察指標

每日輸出今日的「資金溫度計」狀態，作為觀察用 alert（不直接介入策略）。
排版仿 daily_range.py：圖表 PNG → output/breadth_thermometer.png + 剪貼簿，
終端輸出簡要文字。

訊號定義（H079-C 最佳參數）
-----------------------------
- ma = 7 日均
- pct = 0.15 分位門檻
- consec = 3 天連續
- skip_n = 10 天防禦窗
- logic = RATIO only（漲停成交額占比 ma7）

附加：H140 相對溫度（Phase 1 初步結果，尚未回測驗證）
-----------------------------------------------------
絕對門檻在不同年份的活躍度差異下會失準（2019 中位 1.32% vs 2026 中位 9.15%），
故另計 `pct1y` = ma7 在過去 250 交易日中的百分位（只比對過去，無前視）。
Phase 1（N=518 筆 S002 交易）顯示 S002 Reversal 的正期望值集中在 pct1y >= 0.80：
熱桶 +22.6 pts/筆、maxDD -777、最大連敗 5，對照全做 +1.5 / -2583 / 9。
**僅供參考，Phase 2 walk-forward 尚未完成，門檻 p80 為事後挑選。**

使用方式：
    uv run python src/analysis/breadth_thermometer.py
"""
from __future__ import annotations

import subprocess
from datetime import date, timedelta
from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.analysis.chart_style import (
    apply_style, style_axes,
    BG_FIG, BG_AXES, COLOR_UP, COLOR_DOWN,
    COLOR_ACCENT_ORANGE, COLOR_ACCENT_BLUE, COLOR_ACCENT_GOLD,
    COLOR_ACCENT_PURPLE,
    COLOR_TEXT, COLOR_TEXT_LIGHT, COLOR_GRID, BG_TABLE_HIGHLIGHT,
)

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "futures.duckdb"

# H079-C 最佳參數
MA_DAYS = 7
PCT_THRESHOLD = 0.15
CONSEC_DAYS = 3
DEFENSE_WINDOW = 10
DISPLAY_DAYS = 30  # 圖表顯示最近 30 天

# H140 相對溫度（Phase 1 初步，未經 Phase 2 驗證）
PCT_LOOKBACK = 250   # 回看窗（交易日）
HOT_PCT = 0.80       # 熱門檻


def load_breadth_history(end: date | None = None,
                         lookback_years: int = 8) -> pd.DataFrame:
    end = end or date.today()
    start = end - timedelta(days=int(lookback_years * 365.25))
    sql = """
    WITH b AS (
        SELECT trade_date,
               SUM(up_limit_count) AS up_limit_count,
               SUM(total_value)    AS total_value
        FROM market_breadth WHERE trade_date BETWEEN ? AND ?
        GROUP BY trade_date
    ),
    lv AS (
        SELECT trade_date,
               SUM(CASE WHEN is_limit_up THEN value ELSE 0 END) AS lu_value
        FROM stock_day WHERE trade_date BETWEEN ? AND ?
        GROUP BY trade_date
    )
    SELECT b.trade_date, b.up_limit_count, b.total_value, lv.lu_value
    FROM b LEFT JOIN lv USING (trade_date) ORDER BY b.trade_date
    """
    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        df = conn.execute(sql, [start, end, start, end]).fetchdf()
    df["lu_value_ratio"] = df["lu_value"] / df["total_value"]
    df["lu_ratio_ma"] = df["lu_value_ratio"].rolling(MA_DAYS).mean()
    # H140 相對溫度：ma7 在過去 PCT_LOOKBACK 日中的百分位（只比對過去，無前視）
    df["pct1y"] = df["lu_ratio_ma"].rolling(PCT_LOOKBACK, min_periods=120).apply(
        lambda a: (a[:-1] < a[-1]).mean(), raw=True)
    return df


def annotate(df: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    threshold = df["lu_ratio_ma"].quantile(PCT_THRESHOLD)
    df = df.copy()
    df["below"] = df["lu_ratio_ma"] < threshold
    df["event"] = (df["below"].rolling(CONSEC_DAYS).sum() >= CONSEC_DAYS).fillna(False)
    df["defense"] = df["event"].rolling(DEFENSE_WINDOW, min_periods=1).max().astype(bool)
    return df, threshold


def status_level(today: pd.Series, threshold: float, below_streak: int) -> str:
    if bool(today["event"]):
        return "🔴 RED 事件觸發"
    if bool(today["defense"]):
        return "🟠 ORANGE 防禦窗"
    if bool(today["below"]):
        return f"🟡 YELLOW 跌破門檻（連 {below_streak} 天）"
    distance_pct = (today["lu_ratio_ma"] - threshold) / threshold * 100
    if distance_pct < 50:
        return "🟡 YELLOW 接近門檻"
    return "🟢 GREEN 安全"


def relative_status(pct: float) -> str:
    """H140 相對溫度分級（觀察用）。"""
    if pd.isna(pct):
        return "—（歷史不足）"
    if pct >= HOT_PCT:
        return "🔥 HOT 相對高溫"
    if pct >= 0.50:
        return "🌤 WARM 中性偏溫"
    if pct >= 0.20:
        return "❄️ COOL 相對偏冷"
    return "🧊 COLD 相對極冷"


def cold_streak_days(df: pd.DataFrame) -> int:
    """連續低於 HOT_PCT 的天數（含今日）。"""
    n = 0
    for v in reversed(df["pct1y"].tolist()):
        if pd.isna(v) or v >= HOT_PCT:
            break
        n += 1
    return n


def plot_chart(df: pd.DataFrame, threshold: float) -> Path:
    """畫近 30 天溫度計圖：raw bar + ma7 line + threshold line + 狀態色塊."""
    sub = df.tail(DISPLAY_DAYS).reset_index(drop=True)
    apply_style()
    weekday_names = ["一", "二", "三", "四", "五", "六", "日"]

    fig, (ax1, ax2, ax3) = plt.subplots(
        3, 1, figsize=(14, 11), gridspec_kw={"height_ratios": [1.15, 1, 0.85]})
    fig.suptitle("H079 漲停萎縮溫度計（RATIO ma7）＋ H140 相對溫度",
                 fontsize=15, fontweight="bold", y=0.985, color=COLOR_TEXT)
    for ax in (ax1, ax2, ax3):
        style_axes(ax)

    n = len(sub)
    x = np.arange(n)

    # ── 上圖：lu_ratio_ma7 (線) + threshold (虛線) + 狀態色塊 ──
    raw_pct = sub["lu_value_ratio"] * 100
    ma_pct = sub["lu_ratio_ma"] * 100
    th_pct = threshold * 100

    # 防禦窗背景色塊
    in_defense = False
    seg_start = None
    for i in range(n):
        if sub.loc[i, "defense"] and not in_defense:
            seg_start = i
            in_defense = True
        elif not sub.loc[i, "defense"] and in_defense:
            ax1.axvspan(seg_start - 0.5, i - 0.5, color=COLOR_ACCENT_ORANGE,
                        alpha=0.15, zorder=1)
            in_defense = False
    if in_defense:
        ax1.axvspan(seg_start - 0.5, n - 0.5, color=COLOR_ACCENT_ORANGE,
                    alpha=0.15, zorder=1)

    # raw bar (淡)
    ax1.bar(x, raw_pct, color=COLOR_ACCENT_BLUE, alpha=0.35, width=0.7, zorder=2,
            label="當日 raw")
    # ma7 line
    ax1.plot(x, ma_pct, color=COLOR_ACCENT_GOLD, linewidth=2.2,
             marker="o", markersize=5, zorder=4, label=f"ma{MA_DAYS}")
    # 事件日標紅
    for i in range(n):
        if sub.loc[i, "event"]:
            ax1.plot(i, ma_pct.iloc[i], "o", color=COLOR_UP,
                     markersize=11, zorder=5)
    # 門檻線
    ax1.axhline(th_pct, color=COLOR_DOWN, linewidth=1.8, linestyle="--", zorder=3,
                label=f"門檻 {th_pct:.2f}%（全期 {int(PCT_THRESHOLD*100)} 分位）")

    # 標今日值
    ax1.annotate(f"{ma_pct.iloc[-1]:.2f}%",
                 xy=(n - 1, ma_pct.iloc[-1]),
                 xytext=(8, 6), textcoords="offset points",
                 fontsize=11, fontweight="bold", color=COLOR_ACCENT_GOLD)

    ax1.set_ylabel("漲停成交額占比 (%)", fontsize=11)
    ax1.set_title(f"近 {DISPLAY_DAYS} 交易日（橘色塊 = 防禦窗）", fontsize=12)
    ax1.legend(fontsize=10, facecolor=BG_FIG, edgecolor=COLOR_GRID, loc="upper left")
    y_max = max(raw_pct.max(), ma_pct.max(), th_pct) * 1.2
    ax1.set_ylim(0, y_max)
    ax1.set_xticks(x)
    ax1.set_xticklabels(
        [f"{d.strftime('%m-%d')}\n（週{weekday_names[d.weekday()]}）"
         for d in sub["trade_date"]],
        rotation=45, ha="right", fontsize=7,
    )

    # ── 中圖：H140 相對溫度 pct1y（觀察用，尚未回測驗證）──
    pct = sub["pct1y"]
    ax2.fill_between(x, 0, 1, where=(pct < HOT_PCT), color=COLOR_ACCENT_BLUE,
                     alpha=0.12, step="mid", zorder=1)
    ax2.plot(x, pct, color=COLOR_ACCENT_PURPLE, linewidth=2.2,
             marker="o", markersize=5, zorder=4, label=f"pct1y（{PCT_LOOKBACK} 日回看）")
    ax2.axhline(HOT_PCT, color=COLOR_ACCENT_ORANGE, linewidth=1.8, linestyle="--",
                zorder=3, label=f"熱門檻 p{int(HOT_PCT*100)}")
    for i in range(n):
        if not pd.isna(pct.iloc[i]) and pct.iloc[i] >= HOT_PCT:
            ax2.plot(i, pct.iloc[i], "o", color=COLOR_UP, markersize=10, zorder=5)
    if not pd.isna(pct.iloc[-1]):
        ax2.annotate(f"{pct.iloc[-1]:.2f}",
                     xy=(n - 1, pct.iloc[-1]), xytext=(8, 6),
                     textcoords="offset points", fontsize=11,
                     fontweight="bold", color=COLOR_ACCENT_PURPLE)
    ax2.set_ylabel("pct1y 相對溫度", fontsize=11)
    ax2.set_ylim(0, 1.05)
    ax2.set_title("H140 相對溫度（藍色區 = 低於 p80；Phase 1 初步結果，尚未回測驗證）",
                  fontsize=12)
    ax2.legend(fontsize=10, facecolor=BG_FIG, edgecolor=COLOR_GRID, loc="lower left")
    ax2.set_xticks(x)
    ax2.set_xticklabels([f"{d.strftime('%m-%d')}" for d in sub["trade_date"]],
                        rotation=45, ha="right", fontsize=7)

    # ── 下圖：漲停家數（純參考，不參與訊號）──
    cnt = sub["up_limit_count"]
    bar_colors = [COLOR_DOWN if c < 20 else (COLOR_ACCENT_ORANGE if c < 40 else COLOR_UP)
                  for c in cnt]
    ax3.bar(x, cnt, color=bar_colors, width=0.7, zorder=3,
            edgecolor=BG_AXES, linewidth=0.3)
    for i, v in enumerate(cnt):
        ax3.text(i, v + max(cnt) * 0.02, f"{int(v)}",
                 ha="center", va="bottom", fontsize=8, color=COLOR_TEXT)
    ax3.set_ylabel("漲停家數（兩市）", fontsize=11)
    ax3.set_title("漲停家數（參考用，兩個訊號都不看這個）", fontsize=12)
    ax3.set_xticks(x)
    ax3.set_xticklabels(
        [f"{d.strftime('%m-%d')}" for d in sub["trade_date"]],
        rotation=45, ha="right", fontsize=7,
    )
    ax3.set_ylim(0, cnt.max() * 1.2 if len(cnt) else 1)

    plt.tight_layout()
    out_path = PROJECT_ROOT / "output" / "breadth_thermometer.png"
    out_path.parent.mkdir(exist_ok=True)
    plt.savefig(out_path, dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out_path


def main() -> None:
    df = load_breadth_history()
    df, threshold = annotate(df)
    if df.empty:
        print("[H079 溫度計] no data")
        return

    today = df.iloc[-1]
    # 連續低於門檻天數
    below_streak = 0
    for v in reversed(df["below"].tolist()):
        if v:
            below_streak += 1
        else:
            break
    level = status_level(today, threshold, below_streak)

    out_path = plot_chart(df, threshold)
    print(f"圖表已儲存：{out_path}")

    # 自動複製到剪貼簿（macOS）
    try:
        subprocess.run(
            ["osascript", "-e",
             f'set the clipboard to (read (POSIX file "{out_path.absolute()}") as «class PNGf»)'],
            check=True, capture_output=True,
        )
        print("已複製到剪貼簿，可直接 Cmd+V 貼上")
    except Exception:
        pass

    # 終端輸出簡要
    today_ratio = today["lu_value_ratio"] * 100
    today_ma = today["lu_ratio_ma"] * 100
    th_pct = threshold * 100
    distance_pct = (today_ma - th_pct) / th_pct * 100
    print(f"\n資料日期：{today['trade_date'].strftime('%Y-%m-%d')}")
    print(f"當日 raw：{today_ratio:.2f}%   ma{MA_DAYS}：{today_ma:.2f}%   "
          f"門檻：{th_pct:.2f}%   buffer：{distance_pct:+.0f}%")
    print(f"狀態：{level}")
    if bool(today["defense"]):
        # 算事件結束 idx
        event_end_idx = df.index[df["event"]].max() if df["event"].any() else None
        if event_end_idx is not None:
            days_since = len(df) - 1 - event_end_idx
            days_left = max(0, DEFENSE_WINDOW - days_since)
            print(f"  防禦窗剩 {days_left} 天")

    # ── H140 相對溫度（觀察用，尚未回測驗證）──
    pct = today["pct1y"]
    print(f"\n[H140 相對溫度｜Phase 1 初步，未經回測驗證]")
    if pd.isna(pct):
        print(f"  歷史不足 {PCT_LOOKBACK} 日，無法計算")
    else:
        streak = cold_streak_days(df)
        print(f"  pct1y：{pct:.2f}（ma7 在過去 {PCT_LOOKBACK} 日的百分位）"
              f"   門檻：{HOT_PCT:.2f}")
        print(f"  狀態：{relative_status(pct)}")
        if streak > 0:
            print(f"  已連續 {streak} 個交易日低於 p{int(HOT_PCT*100)}")
            print(f"  參考：Phase 1 顯示 S002 Reversal 在此區間期望值為負"
                  f"（冷桶 -6.0 pts/筆 vs 熱桶 +22.6，N=518）")


if __name__ == "__main__":
    main()
