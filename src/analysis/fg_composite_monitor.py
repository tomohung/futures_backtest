"""
S004 fg-composite 每日監控

每日輸出：
  - 今日 comp_z 與閾值（threshold=3.97）
  - 是否觸發進場訊號
  - 4 個指標分項 z 值（看哪個是主要驅動）
  - 距上次觸發 N 個交易日

使用：
  uv run python src/analysis/fg_composite_monitor.py
  uv run python src/analysis/fg_composite_monitor.py --tail 10  # 顯示最近 10 日
"""

from __future__ import annotations

import argparse
from pathlib import Path
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)

PROJECT_ROOT = Path(__file__).parent.parent.parent
H084_DIR = PROJECT_ROOT / "research" / "active" / "H084-correction-bottom-survey"
H084_ARCHIVE = PROJECT_ROOT / "research" / "archive" / "confirmed" / "H084-correction-bottom-survey"

# spec lock-in（與 S004 spec.md 一致）
THRESHOLD = 3.97
ROLLING_WIN = 1250
WARMUP_MIN_PERIODS = 250
COOLDOWN_DAYS = 5
MAX_OPEN = 5
HOLD_DAYS = 250

INDICATORS = {
    "vix_pct":             {"sign": +1, "label": "VIX_pct        "},
    "taiex_dist_125ma_z":  {"sign": -1, "label": "z 125MA        "},
    "margin_drop_60d_pct": {"sign": -1, "label": "margin_drop_60d"},
    "econ_score":          {"sign": -1, "label": "econ_score     "},
}


def find_indicators_csv() -> Path:
    for d in (H084_DIR, H084_ARCHIVE):
        f = d / "results" / "indicators.csv"
        if f.exists():
            return f
    raise FileNotFoundError("無法找到 H084 indicators.csv")


def load_indicators() -> pd.DataFrame:
    df = pd.read_csv(find_indicators_csv(), parse_dates=["trade_date"])
    df = df.dropna(subset=list(INDICATORS.keys())).reset_index(drop=True)
    df = df[["trade_date"] + list(INDICATORS.keys())].sort_values("trade_date").reset_index(drop=True)
    return df


def compute_composite(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    z_cols = []
    for col, meta in INDICATORS.items():
        sign = meta["sign"]
        x_oriented = out[col].astype(float) * sign
        roll = x_oriented.rolling(window=ROLLING_WIN, min_periods=WARMUP_MIN_PERIODS)
        med = roll.median()
        q25 = roll.quantile(0.25)
        q75 = roll.quantile(0.75)
        iqr = (q75 - q25).clip(lower=1e-9)
        out[f"z_{col}"] = (x_oriented - med) / iqr
        z_cols.append(f"z_{col}")
    out["comp_z"] = out[z_cols].sum(axis=1)
    return out


def find_last_trigger(sig_valid: pd.DataFrame) -> pd.Timestamp | None:
    trig = sig_valid[sig_valid["comp_z"] >= THRESHOLD]
    if len(trig) == 0:
        return None
    return trig["trade_date"].max()


def render_row(r: pd.Series, today: bool = False) -> str:
    triggered = r["comp_z"] >= THRESHOLD
    flag = "🔴 TRIGGER" if triggered else " " * 10
    if today and not triggered:
        flag = "          "

    z_parts = []
    for col, meta in INDICATORS.items():
        zv = r[f"z_{col}"]
        if pd.isna(zv):
            z_parts.append(f"{meta['label']}=  N/A")
            continue
        bar = "█" * max(0, min(int(abs(zv) * 2), 8))
        sign_str = "+" if zv >= 0 else "-"
        z_parts.append(f"{meta['label']}={sign_str}{abs(zv):4.2f} {bar}")
    return (
        f"{r['trade_date'].date()}  comp_z={r['comp_z']:+5.2f}  {flag}  | "
        + "  ".join(z_parts)
    )


def main() -> None:
    p = argparse.ArgumentParser(description="S004 fg-composite daily monitor")
    p.add_argument("--tail", type=int, default=5, help="顯示最近 N 日（預設 5）")
    args = p.parse_args()

    ind = load_indicators()
    sig = compute_composite(ind)
    sig_valid = sig.dropna(subset=["comp_z"]).sort_values("trade_date").reset_index(drop=True)

    today_row = sig_valid.iloc[-1]
    last_trig_date = find_last_trigger(sig_valid)

    print("=" * 110)
    print("S004 fg-composite 每日監控")
    print("=" * 110)
    print(f"  Spec : comp_z >= {THRESHOLD} → 進場 1 倉 (cooldown {COOLDOWN_DAYS}td, max {MAX_OPEN} 倉, hold {HOLD_DAYS}td)")
    print(f"  資料 : {sig_valid['trade_date'].min().date()} ~ {sig_valid['trade_date'].max().date()} (N={len(sig_valid)})")

    # Today summary
    print()
    print(f"  今日 ({today_row['trade_date'].date()}): comp_z = {today_row['comp_z']:+.2f}", end="")
    if today_row["comp_z"] >= THRESHOLD:
        print("  → 🔴 TRIGGER（建議進場 1 倉，若 cooldown 與 max_open 條件成立）")
    else:
        gap = THRESHOLD - today_row["comp_z"]
        print(f"  → 距觸發閾值 {THRESHOLD} 還差 {gap:+.2f}")

    if last_trig_date is not None:
        days_since = (sig_valid["trade_date"].iloc[-1] - last_trig_date).days
        # 找 trade_date 內距 last_trig_date 的交易日數
        trade_days_since = len(sig_valid[(sig_valid["trade_date"] > last_trig_date)])
        print(f"  上次觸發: {last_trig_date.date()}  ({days_since} 曆日 / {trade_days_since} 交易日 前)")
    else:
        print(f"  上次觸發: 無紀錄")

    # 4 indicator breakdown today
    print()
    print(f"  今日 4 指標分項 z 值（fear-direction; 高 = fear; ≥ 1.0 視為高貢獻）:")
    for col, meta in INDICATORS.items():
        zv = today_row[f"z_{col}"]
        raw = today_row[col]
        if pd.isna(zv):
            print(f"    {meta['label']}: z=  N/A   raw={raw}")
            continue
        bar_len = max(0, min(int(abs(zv) * 4), 16))
        bar = "█" * bar_len
        side = "fear>" if zv >= 0 else "<calm"
        print(f"    {meta['label']}: z={zv:+5.2f}  raw={raw:7.2f}   {side}  {bar}")

    # Recent N days table
    print()
    print(f"  最近 {args.tail} 個交易日 comp_z 走勢:")
    print("  " + "-" * 105)
    recent = sig_valid.tail(args.tail)
    for _, r in recent.iterrows():
        is_today = (r["trade_date"] == today_row["trade_date"])
        print("  " + render_row(r, today=is_today))


if __name__ == "__main__":
    main()
