"""匯出全歷史 L3 波段（swing legs）到 CSV，附 context 欄 + 空白手動標註欄。

重用 services/swing_legs 的純函式（zigzag_legs / L2、L3 係數）與 daystats 的 EMA20，
單一唯讀連線跑完所有日盤交易日，每段一列。

欄位三類：
- 基礎（自動）：日期/方向/起終點時間價/點數/倍數/持續分鐘。
- context（自動，皆 *因果*——只用起點之前資料，避免後見之明前瞻汙染）：
    缺口        = 今日08:45開 − 昨日13:45收（隔夜淨變動，含夜盤）
    起點vs開盤  = 起點價 − 今日08:45開
    起點位置    = 反轉自日低 / 反轉自日高 / 盤中（起點是否為當下 running 極值）
    起點前波幅  = 起點前(08:45..起點)的 high-low（越小=越早/越新鮮）
    MAE         = 假設起點順勢進場後的最大逆行點數（會不會先被洗）
    最大回檔    = 段內最大反向回檔點數
    最大回檔佔比 = 最大回檔 / |點數|（走勢順暢度代理）
- 手動（空白，逐段對照 K 線填；受控字彙見 output/l3_swing_legs_欄位說明.md）：
    觸發型態 / 可即時捕捉 / 進場點明確度 / 走勢品質 / 備註

重跑安全：若輸出 CSV 已存在，會用 (日期,起點時間,方向) 合併保留已填的手動欄。

用法：
    uv run python src/chart_ui/export_swing_legs.py [--out output/l3_swing_legs.csv]
"""

from __future__ import annotations

import argparse
import csv
from datetime import date
from pathlib import Path

import duckdb

from src.chart_ui import paths
from src.chart_ui.services.daystats import SYMBOL, _ema20_range
from src.chart_ui.services.swing_legs import (
    L2_COEF,
    L3_COEF,
    NOON_MIN,
    _day_bars,
    _min_to_hhmm,
    zigzag_legs,
)

BASE_COLS = [
    "日期", "方向", "起點時間", "起點價", "終點時間", "終點價",
    "點數", "倍數", "持續分鐘",
]
CONTEXT_COLS = [
    "缺口", "起點vs開盤", "起點位置", "起點前波幅",
    "MAE", "最大回檔", "最大回檔佔比",
]
BASIS_COLS = ["當日L3距離", "當日EMA20振幅"]
MANUAL_COLS = ["觸發型態", "可即時捕捉", "進場點明確度", "走勢品質", "備註"]
COLUMNS = BASE_COLS + CONTEXT_COLS + BASIS_COLS + MANUAL_COLS

VOCAB_MD = """# L3 波段 CSV — 欄位說明 / 手動標註受控字彙

## 自動欄（context，皆因果：只用起點之前的資料）
| 欄位 | 定義 |
|---|---|
| 缺口 | 今日 08:45 開 − 昨日 13:45 收（隔夜淨變動，含夜盤；正=跳空高開） |
| 起點vs開盤 | 起點價 − 今日 08:45 開（正=起點在開盤上方） |
| 起點位置 | `反轉自日低`(多段起於當下日低) / `反轉自日高`(空段起於當下日高) / `盤中` |
| 起點前波幅 | 起點前(08:45→起點)的最高−最低，越小=波段越早/越新鮮 |
| MAE | 假設在起點順勢進場後，到終點之間的最大逆行點數（會不會先被洗掉） |
| 最大回檔 | 段內最大反向回檔點數 |
| 最大回檔佔比 | 最大回檔 / 絕對點數（越小越順暢，越大越階梯/拉扯） |

## 手動欄（逐段對照 K 線填）
| 欄位 | 受控字彙 | 說明 |
|---|---|---|
| 觸發型態 | `ORB突破` / `回踩均線` / `關卡反轉` / `假突破回手` / `區間突破` / `趨勢延續` / `無` | 起漲當下的型態 = 候選進場訊號 |
| 可即時捕捉 | `Y` / `N` / `勉強` | **最重要的目標標籤**：不靠後見之明，當下有沒有可辨識的進場理由 |
| 進場點明確度 | `1`–`5` | 訊號在現場有多清楚（含心理資本：模糊的不敢進） |
| 走勢品質 | `順暢` / `階梯` / `震盪拉扯` | 決定 trail / 抱單能不能存活 |
| 備註 | 自由文字 | 消息面、為什麼會/不會進、特殊狀況 |

> 起點/起點價是 zigzag 事後標出的最佳轉折點，非現場進場點。手動欄聚焦「起漲前/當下肉眼可見」的東西，才可能變成可執行訊號。
"""


def _session_open_close(conn) -> dict[date, tuple[float, float]]:
    """每交易日日盤 08:45 開、13:45(或最後一根)收。"""
    rows = conn.execute(
        "SELECT CAST(timestamp AS DATE) d, "
        "  arg_min(open, timestamp) o, arg_max(close, timestamp) c "
        "FROM ohlcv_1m WHERE symbol = ? "
        "AND CAST(timestamp AS TIME) BETWEEN TIME '08:45:00' AND TIME '13:45:00' "
        "GROUP BY 1 ORDER BY 1", [SYMBOL]).fetchall()
    return {d: (float(o), float(c)) for d, o, c in rows}


def _leg_context(bars, lg, session_open: float | None) -> dict:
    """全部因果（起點前）＋段內路徑品質。bars=[(minute,high,low)] 昇冪。"""
    sm, em, sp = lg["start_min"], lg["end_min"], lg["start_price"]
    pre = [(h, l) for (m, h, l) in bars if m <= sm]
    pre_hi = max(h for h, _ in pre) if pre else None
    pre_lo = min(l for _, l in pre) if pre else None
    pre_range = round(pre_hi - pre_lo) if pre else ""

    if lg["dir"] == "up":
        pos = "反轉自日低" if (pre_lo is not None and sp <= pre_lo + 1e-6) else "盤中"
    else:
        pos = "反轉自日高" if (pre_hi is not None and sp >= pre_hi - 1e-6) else "盤中"

    seg = [(h, l) for (m, h, l) in bars if sm <= m <= em]
    if lg["dir"] == "up":
        mae = max(0.0, sp - min(l for _, l in seg))
        run, mr = -1e18, 0.0
        for h, l in seg:
            run = max(run, h)
            mr = max(mr, run - l)
    else:
        mae = max(0.0, max(h for h, _ in seg) - sp)
        run, mr = 1e18, 0.0
        for h, l in seg:
            run = min(run, l)
            mr = max(mr, h - run)

    amp_abs = abs(lg["end_price"] - sp)
    return {
        "起點vs開盤": round(sp - session_open) if session_open is not None else "",
        "起點位置": pos,
        "起點前波幅": pre_range,
        "MAE": round(mae),
        "最大回檔": round(mr),
        "最大回檔佔比": round(mr / amp_abs, 2) if amp_abs > 0 else "",
    }


def _rows_for_day(conn, sel: date, oc: dict, prev_close: float | None) -> list[dict]:
    ema20 = _ema20_range(conn, sel)
    if not ema20:
        return []
    l2_dist, l3_dist = L2_COEF * ema20, L3_COEF * ema20
    bars = _day_bars(conn, sel)
    session_open = oc.get(sel, (None, None))[0]
    gap = (round(session_open - prev_close)
           if session_open is not None and prev_close is not None else "")
    raw = zigzag_legs(bars, threshold=l2_dist)
    rows = []
    for lg in raw:
        if lg["start_min"] >= NOON_MIN:
            continue
        amp_abs = abs(lg["end_price"] - lg["start_price"])
        if amp_abs < l3_dist:
            continue
        row = {
            "日期": sel.isoformat(),
            "方向": "多" if lg["dir"] == "up" else "空",
            "起點時間": _min_to_hhmm(lg["start_min"]),
            "起點價": round(lg["start_price"]),
            "終點時間": _min_to_hhmm(lg["end_min"]),
            "終點價": round(lg["end_price"]),
            "點數": round(lg["end_price"] - lg["start_price"]),
            "倍數": round(amp_abs / l3_dist, 1),
            "持續分鐘": lg["end_min"] - lg["start_min"],
            "缺口": gap,
            "當日L3距離": round(l3_dist, 1),
            "當日EMA20振幅": round(ema20, 1),
        }
        row.update(_leg_context(bars, lg, session_open))
        rows.append(row)
    return rows


def _load_existing_manual(path: Path) -> dict[tuple, dict]:
    """重跑時保留已填的手動欄，key=(日期,起點時間,方向)。"""
    if not path.exists():
        return {}
    out = {}
    with path.open(encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            key = (r.get("日期", ""), r.get("起點時間", ""), r.get("方向", ""))
            out[key] = {c: r.get(c, "") for c in MANUAL_COLS}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="output/l3_swing_legs.csv")
    args = ap.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    prior_manual = _load_existing_manual(out)

    with duckdb.connect(str(paths.DUCKDB_PATH), read_only=True) as conn:
        oc = _session_open_close(conn)
        days = [r[0] for r in conn.execute(
            "SELECT DISTINCT CAST(timestamp AS DATE) d FROM ohlcv_1m "
            "WHERE symbol = ? ORDER BY d", [SYMBOL]).fetchall()]
        all_rows = []
        prev_close = None
        for d in days:
            all_rows.extend(_rows_for_day(conn, d, oc, prev_close))
            if d in oc:
                prev_close = oc[d][1]

    kept = 0
    for row in all_rows:
        key = (row["日期"], row["起點時間"], row["方向"])
        m = prior_manual.get(key)
        for c in MANUAL_COLS:
            row[c] = m[c] if m else ""
        if m and any(m[c] for c in MANUAL_COLS):
            kept += 1

    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(all_rows)

    vocab = out.with_name("l3_swing_legs_欄位說明.md")
    vocab.write_text(VOCAB_MD, encoding="utf-8")

    print(f"{len(all_rows)} legs across {len(days)} days → {out}")
    print(f"保留已填手動列 {kept} 列；欄位說明 → {vocab}")


if __name__ == "__main__":
    main()
