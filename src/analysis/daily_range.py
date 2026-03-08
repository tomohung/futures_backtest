#!/usr/bin/env python3
"""
日盤波動 + VIX 綜合分析圖

使用方式：
    uv run python src/analysis/daily_range.py
"""
import subprocess
import urllib.request
import duckdb
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parents[2] / "data" / "futures.duckdb"
SYMBOL = "TX"
VIX_BASE = "https://www.taifex.com.tw/file/taifex/Dailydownload/vix/log2data/{ym}new.txt"


def get_daily_range(n=20):
    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        rows = conn.execute("""
            SELECT
                timestamp::DATE AS trade_date,
                MAX(high) - MIN(low) AS range_pt
            FROM ohlcv_1m
            WHERE symbol = ?
              AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
            GROUP BY trade_date
            ORDER BY trade_date DESC
            LIMIT ?
        """, [SYMBOL, n]).fetchall()
    return list(reversed(rows))


def fetch_vix(ym: str):
    """下載並解析 VIX txt，回傳 [(date, vix), ...]"""
    url = VIX_BASE.format(ym=ym)
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            raw = resp.read().decode("big5", errors="replace")
    except Exception:
        return []

    rows = []
    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) < 5:
            continue
        date_str = parts[0].strip()
        if len(date_str) != 8 or not date_str.isdigit():
            continue
        try:
            d = date(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]))
            # 多個 tab 分隔，VIX 值在第一個非空的欄位（index 2 之後）
            vix_str = next((p.strip() for p in parts[2:] if p.strip()), "")
            vix = float(vix_str)
            rows.append((d, vix))
        except (ValueError, IndexError):
            continue
    return rows


def get_vix_data(n=20):
    """取得最近 n 個有資料的 VIX 日期，自動跨月補齊"""
    today = date.today()
    months = [today.strftime("%Y%m")]
    prev = (today.replace(day=1) - timedelta(days=1))
    months.append(prev.strftime("%Y%m"))

    all_rows = []
    for ym in months:
        all_rows.extend(fetch_vix(ym))

    # 去重、排序
    seen = {}
    for d, v in all_rows:
        seen[d] = v
    sorted_rows = sorted(seen.items())
    return sorted_rows[-n:]


def setup_font():
    font_candidates = [
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode MS.ttf",
        "/Library/Fonts/Arial Unicode MS.ttf",
    ]
    for f in font_candidates:
        if Path(f).exists():
            fp = fm.FontProperties(fname=f)
            plt.rcParams["font.family"] = fp.get_name()
            return
    plt.rcParams["axes.unicode_minus"] = False


def main():
    range_data = get_daily_range(20)
    dates_r = [r[0] for r in range_data]
    ranges = [float(r[1]) for r in range_data]
    avg20_range = np.mean(ranges)
    last10_dates = dates_r[-10:]
    last10_ranges = ranges[-10:]

    vix_data = get_vix_data(20)
    vix_dates = [r[0] for r in vix_data]
    vix_vals = [r[1] for r in vix_data]
    avg20_vix = np.mean(vix_vals)

    # 趨勢線
    x_idx = np.arange(len(vix_vals))
    trend_coef = np.polyfit(x_idx, vix_vals, 1)
    trend_line = np.polyval(trend_coef, x_idx)
    trend_dir = "↑ 上升" if trend_coef[0] > 0 else "↓ 下降"
    trend_color = "#e74c3c" if trend_coef[0] > 0 else "#27ae60"

    setup_font()
    weekday_names = ["一", "二", "三", "四", "五", "六", "日"]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8))
    fig.suptitle("TX 日盤波動 & VIX 指數", fontsize=15, fontweight="bold", y=0.98)

    # ── 上圖：日盤波動 ──
    colors = ["#e74c3c" if r > avg20_range else "#3498db" for r in last10_ranges]
    bars = ax1.bar(range(10), last10_ranges, color=colors, width=0.6, zorder=3)
    for bar, v in zip(bars, last10_ranges):
        ax1.text(bar.get_x() + bar.get_width() / 2, v + 2, f"{int(v)}",
                 ha="center", va="bottom", fontsize=10, fontweight="bold")
    ax1.axhline(avg20_range, color="#f39c12", linewidth=2, linestyle="--", zorder=4,
                label=f"20日均波動 {avg20_range:.0f}pt")
    ax1.set_xticks(range(10))
    ax1.set_xticklabels(
        [f"{d}\n（週{weekday_names[d.weekday()]}）" for d in last10_dates],
        rotation=0, ha="center", fontsize=9)
    ax1.set_ylabel("波動點數（高 - 低）", fontsize=11)
    ax1.set_title("日盤波動（近10交易日）", fontsize=12)
    ax1.legend(fontsize=10)
    ax1.set_ylim(0, max(last10_ranges) * 1.2)
    ax1.yaxis.grid(True, linestyle="--", alpha=0.4)
    ax1.set_axisbelow(True)
    stats_text = (
        f"近10日均: {np.mean(last10_ranges):.0f}pt  "
        f"近20日均: {avg20_range:.0f}pt  "
        f"最大: {max(last10_ranges):.0f}pt  "
        f"最小: {min(last10_ranges):.0f}pt"
    )
    ax1.text(0.5, 0.97, stats_text, transform=ax1.transAxes, fontsize=9,
             ha="center", va="top",
             bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.8))

    # ── 下圖：VIX ──
    ax2.plot(range(len(vix_vals)), vix_vals, color="#8e44ad", linewidth=2,
             marker="o", markersize=5, zorder=3, label="VIX")
    ax2.plot(range(len(vix_vals)), trend_line, color=trend_color, linewidth=2,
             linestyle="--", zorder=4, label=f"趨勢 {trend_dir}（{trend_coef[0]:+.2f}/日）")
    ax2.axhline(avg20_vix, color="#f39c12", linewidth=1.5, linestyle=":",
                label=f"20日均 {avg20_vix:.2f}")

    # 數值標籤（最後一點 + 最高最低）
    max_i = int(np.argmax(vix_vals))
    min_i = int(np.argmin(vix_vals))
    for i in set([max_i, min_i, len(vix_vals) - 1]):
        ax2.annotate(f"{vix_vals[i]:.2f}", xy=(i, vix_vals[i]),
                     xytext=(0, 8), textcoords="offset points",
                     ha="center", fontsize=9, fontweight="bold")

    ax2.set_xticks(range(len(vix_dates)))
    ax2.set_xticklabels(
        [f"{d}\n（週{weekday_names[d.weekday()]}）" for d in vix_dates],
        rotation=0, ha="center", fontsize=8)
    ax2.set_ylabel("VIX", fontsize=11)
    ax2.set_title("台指 VIX 指數（近20交易日）", fontsize=12)
    ax2.legend(fontsize=10)
    ax2.yaxis.grid(True, linestyle="--", alpha=0.4)
    ax2.set_axisbelow(True)

    plt.tight_layout()
    out_path = Path(__file__).parents[2] / "output" / "daily_range.png"
    out_path.parent.mkdir(exist_ok=True)
    plt.savefig(out_path, dpi=150)
    print(f"圖表已儲存：{out_path}")

    # 自動複製到剪貼簿（macOS）
    try:
        subprocess.run(
            ["osascript", "-e",
             f'set the clipboard to (read (POSIX file "{out_path.absolute()}") as «class PNGf»)'],
            check=True, capture_output=True
        )
        print("已複製到剪貼簿，可直接 Cmd+V 貼上")
    except Exception:
        pass

    # 終端輸出
    print(f"\n{'日期':<12} {'波動(pt)':>8}   {'VIX':>6}")
    print("-" * 32)
    vix_dict = dict(vix_data)
    for d, r in zip(dates_r, ranges):
        v_str = f"{vix_dict[d]:.2f}" if d in vix_dict else "  —"
        marker = " ◀" if d in last10_dates else ""
        print(f"{str(d):<12} {int(r):>8}   {v_str:>6}{marker}")
    print("-" * 32)
    print(f"{'近10日平均':<12} {np.mean(last10_ranges):>8.0f}")
    print(f"{'近20日平均':<12} {avg20_range:>8.0f}   {avg20_vix:>6.2f}")
    print(f"\nVIX 趨勢：{trend_dir}（斜率 {trend_coef[0]:+.2f}/日）")

    plt.show()


if __name__ == "__main__":
    main()
