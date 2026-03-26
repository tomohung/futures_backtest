#!/usr/bin/env python3
"""Parse live trading log (live.txt) into structured CSV.

Handles the messy TSV format with repeated headers, multi-row trades,
and inconsistent column layouts across monthly sections.
"""
import csv
import re
from pathlib import Path

INPUT = Path(__file__).parent / "data" / "live.txt"
OUTPUT = Path(__file__).parent / "data" / "live_parsed.csv"

# Strategy classification
STRATEGY_MAP = {
    "關鍵價轉折": "reversal",
    "拉回進場 - 關鍵價轉折": "reversal",
    "拉回進場-關鍵價轉折": "reversal",
    "開盤區間突破新高/低": "esthl",
    "拉回買進 - 開盤區間突破新高/低": "esthl",
    "開盤區間突破": "esthl",
    "開盤區間突破成本線": "esthl_costline",
}

EXHAUSTION_PATTERNS = [
    "bb<0.25後反向突破",
    "bb>0.75後反向突破",
]

SKIP_PATTERNS = [
    "無訊號",
    "無行情也無策略",
    "有行情但無策略",
]


def classify_strategy(text: str) -> str:
    """Classify entry strategy text into a category."""
    if not text or text.strip() == "":
        return ""
    text = text.strip()

    # Direct match
    if text in STRATEGY_MAP:
        return STRATEGY_MAP[text]

    # Exhaustion (bb patterns)
    for pat in EXHAUSTION_PATTERNS:
        if pat in text:
            return "exhaustion"

    # Skip patterns
    for pat in SKIP_PATTERNS:
        if pat in text:
            return "skip"

    return f"unknown:{text}"


def parse_time(t: str) -> str:
    """Convert '上午 9:03:00' / '下午 1:15:00' to 'HH:MM'."""
    if not t or t.strip() in ("", "-"):
        return ""
    t = t.strip()
    m = re.match(r"(上午|下午)\s*(\d{1,2}):(\d{2}):\d{2}", t)
    if not m:
        return t
    period, h, mi = m.group(1), int(m.group(2)), m.group(3)
    if period == "下午" and h != 12:
        h += 12
    elif period == "上午" and h == 12:
        h = 0
    return f"{h:02d}:{mi}"


def parse_price(p: str) -> str:
    """Clean price field."""
    if not p:
        return ""
    p = p.strip().replace("-", "").strip()
    if not p:
        return ""
    try:
        return str(int(float(p)))
    except ValueError:
        return ""


def is_header_row(fields: list) -> bool:
    """Check if this row is a header."""
    first = fields[0].strip() if fields else ""
    return first in ("Date", "第 1 欄")


def is_date(s: str) -> bool:
    """Check if string looks like a date YYYY/M/D."""
    return bool(re.match(r"\d{4}/\d{1,2}/\d{1,2}$", s.strip()))


def normalize_date(s: str) -> str:
    """Normalize date to YYYY-MM-DD."""
    parts = s.strip().split("/")
    return f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}"


def find_column_layout(header_fields: list) -> dict:
    """Detect column indices from header row.

    The layout varies across monthly sections (some have extra columns).
    We need to find: 進場策略, 出場策略, 時間, 方向, 進/出場價
    """
    layout = {}
    for i, f in enumerate(header_fields):
        f = f.strip()
        if f == "進場策略":
            layout["entry_strategy"] = i
        elif f == "出場策略":
            layout["exit_strategy"] = i
        elif f == "時間":
            layout["time"] = i
        elif f == "方向":
            layout["direction"] = i
        elif f == "進/出場價":
            layout["price"] = i
        elif f == "實盤 vs 預估振幅":
            layout["est_range"] = i
        elif f == "開盤格局":
            layout["pattern"] = i
    return layout


def get_field(fields: list, idx: int) -> str:
    """Safely get field by index."""
    if idx < len(fields):
        return fields[idx].strip()
    return ""


def parse_live_trades(filepath: Path) -> list[dict]:
    """Parse the live trading log into a list of trade dicts."""
    trades = []
    current_layout = None
    current_date = None
    pending_entry = None  # Accumulate entry row, wait for exit row

    with open(filepath, "r", encoding="utf-8") as f:
        for line_no, raw_line in enumerate(f, 1):
            line = raw_line.rstrip("\n\r")
            if not line.strip():
                # Empty line - flush pending entry if exists
                if pending_entry:
                    trades.append(pending_entry)
                    pending_entry = None
                continue

            fields = line.split("\t")

            # Header row: update layout
            if is_header_row(fields):
                if pending_entry:
                    trades.append(pending_entry)
                    pending_entry = None
                current_layout = find_column_layout(fields)
                continue

            if current_layout is None:
                continue

            li = current_layout
            first_field = fields[0].strip() if fields else ""

            # --- Row with a date = potential new trade entry ---
            if is_date(first_field):
                # Flush previous pending entry
                if pending_entry:
                    trades.append(pending_entry)
                    pending_entry = None

                current_date = normalize_date(first_field)
                entry_strategy_raw = get_field(fields, li.get("entry_strategy", 99))
                strategy = classify_strategy(entry_strategy_raw)

                direction = get_field(fields, li.get("direction", 99))
                time_val = parse_time(get_field(fields, li.get("time", 99)))
                price_val = parse_price(get_field(fields, li.get("price", 99)))

                if strategy == "skip":
                    # No trade this day
                    trades.append({
                        "date": current_date,
                        "strategy": "skip",
                        "strategy_raw": entry_strategy_raw,
                        "direction": "",
                        "entry_time": "",
                        "entry_price": "",
                        "exit_strategy": "",
                        "exit_time": "",
                        "exit_price": "",
                        "pnl": "",
                    })
                    continue

                if not strategy or strategy.startswith("unknown"):
                    # Observation row (watched the open but no strategy yet).
                    # The actual trade comes on a continuation row.
                    # Don't create a pending entry — just record date and move on.
                    continue

                pending_entry = {
                    "date": current_date,
                    "strategy": strategy,
                    "strategy_raw": entry_strategy_raw,
                    "direction": direction if direction in ("B", "S") else "",
                    "entry_time": time_val,
                    "entry_price": price_val,
                    "exit_strategy": "",
                    "exit_time": "",
                    "exit_price": "",
                    "pnl": "",
                }

            # --- Row without date = continuation (exit row or second trade) ---
            else:
                if not current_date:
                    continue

                # Check if this is an exit row (has exit_strategy) or a new entry on same day
                exit_strat = get_field(fields, li.get("exit_strategy", 99))
                entry_strat = get_field(fields, li.get("entry_strategy", 99))
                time_val = parse_time(get_field(fields, li.get("time", 99)))
                price_val = parse_price(get_field(fields, li.get("price", 99)))
                direction = get_field(fields, li.get("direction", 99))

                # If there's an exit strategy and we have a pending entry, this is the exit
                if exit_strat and pending_entry:
                    pending_entry["exit_strategy"] = exit_strat
                    pending_entry["exit_time"] = time_val
                    pending_entry["exit_price"] = price_val
                    # Calculate PnL
                    try:
                        ep = int(pending_entry["entry_price"]) if pending_entry["entry_price"] else None
                        xp = int(price_val) if price_val else None
                        if ep and xp:
                            if pending_entry["direction"] == "B":
                                pending_entry["pnl"] = str(xp - ep)
                            elif pending_entry["direction"] == "S":
                                pending_entry["pnl"] = str(ep - xp)
                    except (ValueError, TypeError):
                        pass
                    trades.append(pending_entry)
                    pending_entry = None

                # If there's an entry strategy, this is a new trade on the same day
                elif entry_strat:
                    if pending_entry:
                        trades.append(pending_entry)
                        pending_entry = None

                    strategy = classify_strategy(entry_strat)
                    if strategy and strategy != "skip" and not strategy.startswith("unknown"):
                        pending_entry = {
                            "date": current_date,
                            "strategy": strategy,
                            "strategy_raw": entry_strat,
                            "direction": direction if direction in ("B", "S") else "",
                            "entry_time": time_val,
                            "entry_price": price_val,
                            "exit_strategy": "",
                            "exit_time": "",
                            "exit_price": "",
                            "pnl": "",
                        }

    # Flush last pending
    if pending_entry:
        trades.append(pending_entry)

    return trades


def main():
    trades = parse_live_trades(INPUT)

    # Write CSV
    fieldnames = [
        "date", "strategy", "strategy_raw", "direction",
        "entry_time", "entry_price", "exit_strategy",
        "exit_time", "exit_price", "pnl",
    ]
    with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(trades)

    # Summary
    from collections import Counter
    strat_counts = Counter(t["strategy"] for t in trades)
    total_trades = sum(1 for t in trades if t["strategy"] != "skip")
    total_with_pnl = sum(1 for t in trades if t["pnl"] and t["strategy"] != "skip")

    print(f"Total rows: {len(trades)}")
    print(f"Total trades (excl skip): {total_trades}")
    print(f"Trades with PnL: {total_with_pnl}")
    print(f"\nStrategy breakdown:")
    for strat, count in sorted(strat_counts.items(), key=lambda x: -x[1]):
        pnl_trades = [t for t in trades if t["strategy"] == strat and t["pnl"]]
        if pnl_trades:
            total_pnl = sum(int(t["pnl"]) for t in pnl_trades)
            wins = sum(1 for t in pnl_trades if int(t["pnl"]) > 0)
            win_pct = wins / len(pnl_trades) * 100
            print(f"  {strat:<20} {count:>4} rows, {len(pnl_trades):>3} w/PnL, "
                  f"Win {win_pct:.0f}%, Total {total_pnl:+d} pts")
        else:
            print(f"  {strat:<20} {count:>4} rows")

    print(f"\nOutput: {OUTPUT}")


if __name__ == "__main__":
    main()
