"""
H084 Step 0.2：HWM 段切標定 TAIEX 歷史底部事件，分類為 Tier A/B/C/D。

演算法（High Water Mark / 高水位段切）：
  - 維持資料起點以來的「歷史新高」(ATH) 作為峰值參考
  - 當 close 從 ATH 跌幅 ≥ MIN_DRAWDOWN (5%) → 進入事件，開始追蹤 trough
  - 當 close 重新 ≥ 啟動時的 ATH → 事件結束（recovery 確認）
  - 若資料結束時尚未 recover → 事件標為 open

特點：
  - 每個 (ATH-recovery) 周期內只取最深 trough，不會被中間反彈切碎
  - 2008-2014 的長熊市會是一個 Tier A 事件，吞沒中間的 2009/2010 子波段
    （這是已知取捨：focus on TW，跨市結構性問題另案處理）

Tier 定義：
  Tier A: drawdown ≥ 30%
  Tier B: 20% ≤ drawdown < 30%
  Tier C: 10% ≤ drawdown < 20%
  Tier D: 5%  ≤ drawdown < 10%

輸出：
  - results/tiers.csv：事件清單表
  - results/tiers_chart.png：TAIEX 線圖 + Tier 標記

用法：
  uv run python research/active/H084-correction-bottom-survey/zigzag_tiers.py
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "futures.duckdb"
RESULTS_DIR = Path(__file__).parent / "results"

# 進入事件的最小跌幅（從 ATH 起算）
MIN_DRAWDOWN = 0.05

# Sub-event 偵測：Tier A/B macro 內部用此 zigzag 門檻找次級谷
SUB_EVENT_TIERS = {"A", "B"}
SUB_ZIGZAG_THRESHOLD = 0.10
SUB_MIN_DRAWDOWN = 0.10


def classify_tier(drawdown_pct: float) -> str:
    """根據 drawdown 幅度分類。"""
    if drawdown_pct >= 0.30:
        return "A"
    if drawdown_pct >= 0.20:
        return "B"
    if drawdown_pct >= 0.10:
        return "C"
    if drawdown_pct >= 0.05:
        return "D"
    return "unclassified"


def detect_events_hwm(df: pd.DataFrame, min_drawdown: float = MIN_DRAWDOWN) -> pd.DataFrame:
    """
    HWM 段切：每個 ATH-recovery 周期一個事件，事件內取最深 trough。

    Returns DataFrame with columns:
      peak_date, peak_value, trough_date, trough_value,
      recovery_date, recovery_value, drawdown_pct, recovery_pct,
      decline_days, recovery_days, total_days, tier, is_open
    """
    df = df.sort_values("trade_date").reset_index(drop=True)

    events: list[dict] = []

    # 初始 ATH：第一筆
    ath_value = float(df.iloc[0]["close"])
    ath_date = df.iloc[0]["trade_date"]

    in_event = False
    event_start_ath_value = None
    event_start_ath_date = None
    trough_value = None
    trough_date = None

    for i in range(1, len(df)):
        c = float(df.iloc[i]["close"])
        d = df.iloc[i]["trade_date"]

        if not in_event:
            if c >= ath_value:
                # 創新高（或追平）→ 更新 ATH
                ath_value, ath_date = c, d
            elif (ath_value - c) / ath_value >= min_drawdown:
                # 跌幅達門檻 → 進入事件
                in_event = True
                event_start_ath_value = ath_value
                event_start_ath_date = ath_date
                trough_value = c
                trough_date = d
        else:
            # 事件中
            if c < trough_value:
                trough_value, trough_date = c, d
            if c >= event_start_ath_value:
                # 重回啟動時 ATH → 事件結束
                drawdown_pct = (event_start_ath_value - trough_value) / event_start_ath_value
                events.append({
                    "peak_date": event_start_ath_date,
                    "peak_value": event_start_ath_value,
                    "trough_date": trough_date,
                    "trough_value": trough_value,
                    "recovery_date": d,
                    "recovery_value": c,
                    "drawdown_pct": round(drawdown_pct * 100, 2),
                    "recovery_pct": round((c - trough_value) / trough_value * 100, 2),
                    "decline_days": (trough_date - event_start_ath_date).days,
                    "recovery_days": (d - trough_date).days,
                    "total_days": (d - event_start_ath_date).days,
                    "tier": classify_tier(drawdown_pct),
                    "is_open": False,
                })
                # 重置
                in_event = False
                ath_value, ath_date = c, d

    # 末端 open event
    if in_event:
        drawdown_pct = (event_start_ath_value - trough_value) / event_start_ath_value
        last_close = float(df.iloc[-1]["close"])
        last_date = df.iloc[-1]["trade_date"]
        events.append({
            "peak_date": event_start_ath_date,
            "peak_value": event_start_ath_value,
            "trough_date": trough_date,
            "trough_value": trough_value,
            "recovery_date": None,
            "recovery_value": None,
            "drawdown_pct": round(drawdown_pct * 100, 2),
            "recovery_pct": round((last_close - trough_value) / trough_value * 100, 2),
            "decline_days": (trough_date - event_start_ath_date).days,
            "recovery_days": (last_date - trough_date).days,
            "total_days": (last_date - event_start_ath_date).days,
            "tier": classify_tier(drawdown_pct),
            "is_open": True,
        })

    return pd.DataFrame(events)


def zigzag_segment(df_segment: pd.DataFrame,
                   threshold: float = SUB_ZIGZAG_THRESHOLD) -> list[tuple[date, float, str]]:
    """
    在 macro 事件內部跑 zigzag。

    假設 segment 第一筆 = peak（macro 啟動的 ATH），最後一筆視作隱含 pivot。
    Returns list of (date, value, kind) 交替，kind in {'peak', 'trough'}。
    """
    if len(df_segment) < 2:
        return []

    pivots: list[tuple[date, float, str]] = []
    pivots.append((df_segment.iloc[0]["trade_date"],
                   float(df_segment.iloc[0]["close"]), "peak"))

    state = "down"  # 從 peak 起始 → 朝下找 trough
    extreme_value = float(df_segment.iloc[0]["close"])
    extreme_date = df_segment.iloc[0]["trade_date"]

    for i in range(1, len(df_segment)):
        c = float(df_segment.iloc[i]["close"])
        d = df_segment.iloc[i]["trade_date"]

        if state == "down":
            if c < extreme_value:
                extreme_value, extreme_date = c, d
            elif (c - extreme_value) / extreme_value >= threshold:
                pivots.append((extreme_date, extreme_value, "trough"))
                state = "up"
                extreme_value, extreme_date = c, d
        else:  # 'up'
            if c > extreme_value:
                extreme_value, extreme_date = c, d
            elif (extreme_value - c) / extreme_value >= threshold:
                pivots.append((extreme_date, extreme_value, "peak"))
                state = "down"
                extreme_value, extreme_date = c, d

    # segment 末端：若最後一個 extreme 還沒被收進 pivots，補上
    last_kind = "peak" if state == "up" else "trough"
    if not pivots or pivots[-1][0] != extreme_date:
        pivots.append((extreme_date, extreme_value, last_kind))

    return pivots


def detect_sub_events(taiex: pd.DataFrame, macro_events: pd.DataFrame) -> pd.DataFrame:
    """
    對每個 Tier A/B macro 事件，在其 peak→recovery 區間內找 sub-event。

    Sub-event 定義：(peak_i, trough_i, peak_{i+1}) 三段 zigzag pivot
      - drawdown ≥ SUB_MIN_DRAWDOWN
      - 與 macro trough_date 不同（去重）

    Returns DataFrame，欄位同 macro events 加上 `parent_macro_idx`、`tier` 後綴 `-sub`。
    """
    sub_rows: list[dict] = []

    for macro_idx, macro in macro_events.iterrows():
        if macro["tier"] not in SUB_EVENT_TIERS:
            continue

        end_date = macro["recovery_date"] if pd.notna(macro["recovery_date"]) else taiex["trade_date"].iloc[-1]
        seg = taiex[(taiex["trade_date"] >= macro["peak_date"])
                    & (taiex["trade_date"] <= end_date)].reset_index(drop=True)
        if len(seg) < 5:
            continue

        pivots = zigzag_segment(seg, threshold=SUB_ZIGZAG_THRESHOLD)

        # 從 pivots 抽取每個 (peak, trough, next_peak) 三段
        for i in range(len(pivots)):
            if pivots[i][2] != "trough":
                continue
            # 找最近的前 peak
            prev_peak = None
            for j in range(i - 1, -1, -1):
                if pivots[j][2] == "peak":
                    prev_peak = pivots[j]
                    break
            if prev_peak is None:
                continue
            # 找最近的後 peak
            next_peak = None
            for j in range(i + 1, len(pivots)):
                if pivots[j][2] == "peak":
                    next_peak = pivots[j]
                    break

            trough_date_pv, trough_value_pv = pivots[i][0], pivots[i][1]

            # 跟 macro trough 同日 → 去重
            if trough_date_pv == macro["trough_date"]:
                continue

            drawdown_pct = (prev_peak[1] - trough_value_pv) / prev_peak[1]
            if drawdown_pct < SUB_MIN_DRAWDOWN:
                continue

            recovery_pct = ((next_peak[1] - trough_value_pv) / trough_value_pv
                            if next_peak is not None else None)
            recovery_date_pv = next_peak[0] if next_peak is not None else None

            sub_rows.append({
                "peak_date": prev_peak[0],
                "peak_value": prev_peak[1],
                "trough_date": trough_date_pv,
                "trough_value": trough_value_pv,
                "recovery_date": recovery_date_pv,
                "recovery_value": next_peak[1] if next_peak is not None else None,
                "drawdown_pct": round(drawdown_pct * 100, 2),
                "recovery_pct": round(recovery_pct * 100, 2) if recovery_pct is not None else None,
                "decline_days": (trough_date_pv - prev_peak[0]).days,
                "recovery_days": (recovery_date_pv - trough_date_pv).days if recovery_date_pv else None,
                "total_days": ((recovery_date_pv or end_date) - prev_peak[0]).days,
                "tier": classify_tier(drawdown_pct) + "-sub",
                "is_open": next_peak is None,
                "parent_macro_idx": macro_idx,
                "parent_macro_tier": macro["tier"],
            })

    return pd.DataFrame(sub_rows)


def load_taiex() -> pd.DataFrame:
    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        df = conn.execute("""
            SELECT trade_date, close
            FROM taiex_day
            ORDER BY trade_date
        """).fetchdf()
    df["close"] = df["close"].astype(float)
    return df


def plot_events(taiex: pd.DataFrame, events: pd.DataFrame, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(16, 7))
    ax.plot(taiex["trade_date"], taiex["close"], color="#333", linewidth=0.8, label="TAIEX")

    tier_colors = {
        "A": ("#c8102e", 0.20),
        "B": ("#e97132", 0.16),
        "C": ("#f4b400", 0.12),
        "D": ("#cccccc", 0.05),
        "A-sub": ("#c8102e", 0.0),
        "B-sub": ("#e97132", 0.0),
        "C-sub": ("#f4b400", 0.0),
        "unclassified": ("#999999", 0.03),
    }

    # 先畫 macro events 的背景帶
    for _, ev in events.iterrows():
        if str(ev["tier"]).endswith("-sub") or ev["tier"] == "D":
            continue
        start = ev["peak_date"]
        end = ev["recovery_date"] if pd.notna(ev["recovery_date"]) else taiex["trade_date"].iloc[-1]
        color, alpha = tier_colors.get(ev["tier"], ("#888", 0.05))
        ax.axvspan(start, end, color=color, alpha=alpha, zorder=0)

    # 再畫所有 trough 標記（macro + sub）
    for _, ev in events.iterrows():
        tier = str(ev["tier"])
        if tier == "D":
            continue
        is_sub = tier.endswith("-sub")
        color, _ = tier_colors.get(tier, ("#888", 0.05))
        marker = "v" if is_sub else "o"
        size = 28 if is_sub else 50
        ax.scatter([ev["trough_date"]], [ev["trough_value"]],
                   color=color, s=size, marker=marker, zorder=3,
                   edgecolor="white", linewidth=1)
        label = f"{tier} {ev['drawdown_pct']:.0f}%"
        if ev["is_open"]:
            label += "*"
        ax.annotate(
            label,
            xy=(ev["trough_date"], ev["trough_value"]),
            xytext=(0, -16 if not is_sub else 14), textcoords="offset points",
            ha="center", fontsize=7 if is_sub else 8,
            color=color, fontweight="bold",
        )

    ax.set_title("TAIEX historical drawdown events (HWM segmentation) - H084", fontsize=14)
    ax.set_xlabel("Date")
    ax.set_ylabel("TAIEX Close")
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=110)
    plt.close(fig)


def main() -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    taiex = load_taiex()
    print(f"TAIEX: {len(taiex)} rows, {taiex['trade_date'].min()} ~ {taiex['trade_date'].max()}")

    macro_events = detect_events_hwm(taiex, min_drawdown=MIN_DRAWDOWN)
    macro_events["parent_macro_idx"] = pd.NA
    # Macro 自身的 parent_macro_tier 標記為自己（regime 即自己）
    macro_events["parent_macro_tier"] = macro_events["tier"]
    print(f"Macro events: {len(macro_events)}")

    sub_events = detect_sub_events(taiex, macro_events)
    print(f"Sub events: {len(sub_events)}")

    # 合併成同一個 DataFrame
    events = pd.concat([macro_events, sub_events], ignore_index=True)
    events = events.sort_values(["trough_date"]).reset_index(drop=True)

    tier_counts = events["tier"].value_counts().sort_index()
    print("\n=== Tier 分佈 ===")
    print(tier_counts)

    print("\n=== 主要事件詳細（Tier A/B/C/A-sub/B-sub/C-sub，依 drawdown 排序）===")
    main_tiers = ["A", "B", "C", "A-sub", "B-sub", "C-sub"]
    main_events = events[events["tier"].isin(main_tiers)].sort_values(
        "drawdown_pct", ascending=False
    )
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 200)
    cols = ["peak_date", "trough_date", "recovery_date",
            "drawdown_pct", "recovery_pct",
            "decline_days", "recovery_days", "tier", "is_open",
            "parent_macro_idx", "parent_macro_tier"]
    print(main_events[cols].to_string(index=False))

    csv_path = RESULTS_DIR / "tiers.csv"
    events.to_csv(csv_path, index=False)
    print(f"\nCSV → {csv_path}")

    chart_path = RESULTS_DIR / "tiers_chart.png"
    plot_events(taiex, events, chart_path)
    print(f"Chart → {chart_path}")


if __name__ == "__main__":
    main()
