# Weekday Stats Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-weekday up/down statistics (day session, morning session, night session) to key_prices report and SR chart.

**Architecture:** Add a SQL query in `get_key_prices()` to compute open/close per session per trading day over ~40 days, aggregate by weekday in Python, then render in both `print_report()` (text table) and `plot_sr_chart()` (matplotlib table in new bottom subplot).

**Tech Stack:** Python, DuckDB, matplotlib

---

## File Map

- **Modify:** `src/analysis/key_prices.py`
  - `get_key_prices()` — add weekday stats query + aggregation (~lines 159-206)
  - `print_report()` — add weekday table after 評估 section (~line 393)
  - `plot_sr_chart()` — change gridspec to 3x2, add bottom table subplot (~lines 598-741)

No new files. No test files (this is an analysis script with no existing test infrastructure).

---

### Task 1: Add weekday stats query to `get_key_prices()`

**Files:**
- Modify: `src/analysis/key_prices.py:159-206`

- [ ] **Step 1: Add the weekday stats SQL query and aggregation**

Insert the following block just before the `result = {` line (line 194) in `get_key_prices()`. This goes after the `vol_alert` block and before `result = {`:

```python
    # Weekday 漲跌統計（近 ~40 個交易日 ≈ 2 個月）
    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        # 日盤 + 早盤：from ohlcv_1m
        day_morning_rows = conn.execute("""
            WITH trading_days AS (
                SELECT DISTINCT timestamp::DATE AS td
                FROM ohlcv_1m
                WHERE symbol = ?
                  AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
                ORDER BY td DESC
                LIMIT 40
            ),
            day_session AS (
                SELECT
                    timestamp::DATE AS td,
                    FIRST(open ORDER BY timestamp) AS day_open,
                    LAST(close ORDER BY timestamp) AS day_close
                FROM ohlcv_1m
                WHERE symbol = ?
                  AND timestamp::DATE IN (SELECT td FROM trading_days)
                  AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
                GROUP BY td
            ),
            morning_session AS (
                SELECT
                    timestamp::DATE AS td,
                    FIRST(open ORDER BY timestamp) AS morn_open,
                    LAST(close ORDER BY timestamp) AS morn_close
                FROM ohlcv_1m
                WHERE symbol = ?
                  AND timestamp::DATE IN (SELECT td FROM trading_days)
                  AND timestamp::TIME BETWEEN '09:00:00' AND '10:30:00'
                GROUP BY td
            )
            SELECT
                d.td,
                DAYOFWEEK(d.td) AS dow,
                d.day_open, d.day_close,
                m.morn_open, m.morn_close
            FROM day_session d
            LEFT JOIN morning_session m ON d.td = m.td
            ORDER BY d.td
        """, [SYMBOL, SYMBOL, SYMBOL]).fetchall()

        # 夜盤：15:00~隔日 05:00，以當日日期為基準
        night_rows = conn.execute("""
            WITH trading_days AS (
                SELECT DISTINCT timestamp::DATE AS td
                FROM ohlcv_1m
                WHERE symbol = ?
                  AND timestamp::TIME BETWEEN '08:45:00' AND '13:45:00'
                ORDER BY td DESC
                LIMIT 40
            )
            SELECT
                td,
                DAYOFWEEK(td) AS dow,
                night_open,
                night_close
            FROM (
                SELECT
                    d.td,
                    FIRST(m.open ORDER BY m.timestamp) AS night_open,
                    LAST(m.close ORDER BY m.timestamp) AS night_close
                FROM trading_days d
                JOIN ohlcv_1m m ON m.symbol = ?
                  AND (
                    (m.timestamp::DATE = d.td AND m.timestamp::TIME >= '15:00:00')
                    OR
                    (m.timestamp::DATE = d.td + INTERVAL '1 day' AND m.timestamp::TIME <= '05:00:00')
                  )
                GROUP BY d.td
            ) sub
            WHERE night_open IS NOT NULL
            ORDER BY td
        """, [SYMBOL, SYMBOL]).fetchall()

    # 彙整 by weekday（DuckDB DAYOFWEEK: 0=Sun, 1=Mon, ... 6=Sat）
    # 轉成 Python weekday: 0=Mon, ... 4=Fri
    from collections import defaultdict
    wd_data = defaultdict(lambda: {
        "day": [], "morning": [], "night": []
    })
    for row in day_morning_rows:
        td, dow, day_open, day_close, morn_open, morn_close = row
        py_wd = (dow - 1) % 7  # DuckDB 1=Mon → Python 0=Mon
        if day_open is not None and day_close is not None:
            wd_data[py_wd]["day"].append(float(day_close - day_open))
        if morn_open is not None and morn_close is not None:
            wd_data[py_wd]["morning"].append(float(morn_close - morn_open))

    for row in night_rows:
        td, dow, night_open, night_close = row
        py_wd = (dow - 1) % 7
        if night_open is not None and night_close is not None:
            wd_data[py_wd]["night"].append(float(night_close - night_open))

    def _agg(changes):
        if not changes:
            return {"up": 0, "down": 0, "avg_chg": 0.0}
        up = sum(1 for c in changes if c > 0)
        down = len(changes) - up
        avg_chg = sum(changes) / len(changes)
        return {"up": up, "down": down, "avg_chg": round(avg_chg)}

    weekday_stats = {
        "today_wd": next_day.weekday(),  # next_day = 今天的交易日
        "stats": {
            wd: {
                "day": _agg(wd_data[wd]["day"]),
                "morning": _agg(wd_data[wd]["morning"]),
                "night": _agg(wd_data[wd]["night"]),
            }
            for wd in range(5)
        }
    }
```

Then add `"weekday_stats": weekday_stats,` to the `result` dict (after `"vol_alert": vol_alert,`).

- [ ] **Step 2: Verify the query runs without error**

Run:
```bash
uv run python -c "
from src.analysis.key_prices import get_key_prices
data = get_key_prices()
ws = data['weekday_stats']
print(f\"Today weekday: {ws['today_wd']}\")
for wd in range(5):
    s = ws['stats'][wd]
    d = s['day']
    print(f\"  wd={wd}: day {d['up']}漲/{d['down']}跌 avg={d['avg_chg']}pt\")
"
```

Expected: prints 5 lines of weekday stats with reasonable numbers (each weekday should have 7-9 samples from 40 trading days).

- [ ] **Step 3: Commit**

```bash
git add src/analysis/key_prices.py
git commit -m "feat(key_prices): add weekday stats query for day/morning/night sessions"
```

---

### Task 2: Add weekday stats to text report

**Files:**
- Modify: `src/analysis/key_prices.py` — `print_report()` function

- [ ] **Step 1: Add weekday stats table to print_report()**

Insert the following block in `print_report()` after the `vol_alert` section (after line 392, before the `# 支撐壓力` comment on line 394):

```python
    # Weekday 漲跌統計
    wd_stats = d.get("weekday_stats")
    if wd_stats:
        wd_names = {0: "一", 1: "二", 2: "三", 3: "四", 4: "五"}
        today_wd = wd_stats["today_wd"]

        def _fmt(s):
            total = s["up"] + s["down"]
            if total == 0:
                return "—"
            pct = s["up"] / total * 100
            sign = "+" if s["avg_chg"] >= 0 else ""
            return f"{s['up']}漲/{s['down']}跌 {pct:.0f}% 均{sign}{s['avg_chg']:.0f}pt"

        print()
        print("### Weekday 漲跌統計（近 2 個月）")
        print()
        print("|      | 日盤 08:45-13:45 | 早盤 09:00-10:30 | 夜盤 15:00-05:00 |")
        print("|------|------------------|------------------|------------------|")
        for wd in range(5):
            s = wd_stats["stats"][wd]
            marker = " ◀" if wd == today_wd else ""
            label = f"週{wd_names[wd]}{marker}"
            print(f"| {label:4s} | {_fmt(s['day']):16s} | {_fmt(s['morning']):16s} | {_fmt(s['night']):16s} |")
```

- [ ] **Step 2: Verify the text report output**

Run:
```bash
uv run python src/analysis/key_prices.py 2>/dev/null | grep -A 8 "Weekday"
```

Expected: a markdown table with 5 weekday rows, today's row marked with ◀, each cell showing `N漲/N跌 NN% 均±NNpt`.

- [ ] **Step 3: Commit**

```bash
git add src/analysis/key_prices.py
git commit -m "feat(key_prices): add weekday stats text table to report"
```

---

### Task 3: Add weekday stats table to SR chart

**Files:**
- Modify: `src/analysis/key_prices.py` — `plot_sr_chart()` function

- [ ] **Step 1: Modify gridspec from 2x2 to 3x2 and add table subplot**

In `plot_sr_chart()`, replace the gridspec and subplot creation block (lines 599-606):

Old code:
```python
    fig = plt.figure(figsize=(16, 10), layout="constrained")
    gs = fig.add_gridspec(2, 2, height_ratios=[3, 1], width_ratios=[5, 1],
                          hspace=0.08)
    ax     = fig.add_subplot(gs[0, 0])
    ax_vp  = fig.add_subplot(gs[0, 1], sharey=ax)
    ax_macd = fig.add_subplot(gs[1, 0], sharex=ax)
    ax_empty = fig.add_subplot(gs[1, 1])
    ax_empty.set_visible(False)
```

New code:
```python
    fig = plt.figure(figsize=(16, 12), layout="constrained")
    gs = fig.add_gridspec(3, 2, height_ratios=[3, 1, 0.6], width_ratios=[5, 1],
                          hspace=0.08)
    ax     = fig.add_subplot(gs[0, 0])
    ax_vp  = fig.add_subplot(gs[0, 1], sharey=ax)
    ax_macd = fig.add_subplot(gs[1, 0], sharex=ax)
    ax_empty = fig.add_subplot(gs[1, 1])
    ax_empty.set_visible(False)
    ax_table = fig.add_subplot(gs[2, :])
```

- [ ] **Step 2: Add the table rendering code**

Insert the following block just before `out_path = ...` (before line 726), after the MACD x-axis label block:

```python
    # ── Weekday 統計表格（底部）──────────────────────────
    ax_table.set_facecolor("#16213e")
    ax_table.set_xlim(0, 1)
    ax_table.set_ylim(0, 1)
    ax_table.axis("off")

    wd_stats = data.get("weekday_stats")
    if wd_stats:
        wd_names = {0: "一", 1: "二", 2: "三", 3: "四", 4: "五"}
        today_wd = wd_stats["today_wd"]

        def _fmt_cell(s):
            total = s["up"] + s["down"]
            if total == 0:
                return "—", "#cccccc"
            pct = s["up"] / total * 100
            sign = "+" if s["avg_chg"] >= 0 else ""
            text = f"{s['up']}漲/{s['down']}跌 {pct:.0f}% 均{sign}{s['avg_chg']:.0f}pt"
            color = "#ef5350" if pct > 50 else "#26a69a" if pct < 50 else "#cccccc"
            return text, color

        col_labels = ["", "日盤 08:45-13:45", "早盤 09:00-10:30", "夜盤 15:00-05:00"]
        cell_text = []
        cell_colors = []
        for wd in range(5):
            s = wd_stats["stats"][wd]
            marker = " ◀" if wd == today_wd else ""
            row_label = f"週{wd_names[wd]}{marker}"
            day_txt, day_clr = _fmt_cell(s["day"])
            morn_txt, morn_clr = _fmt_cell(s["morning"])
            night_txt, night_clr = _fmt_cell(s["night"])
            cell_text.append([row_label, day_txt, morn_txt, night_txt])
            if wd == today_wd:
                cell_colors.append(["#2a3a5e"] * 4)
            else:
                cell_colors.append(["#16213e"] * 4)

        table = ax_table.table(
            cellText=cell_text,
            colLabels=col_labels,
            cellLoc="center",
            loc="center",
        )
        table.auto_set_font_size(False)
        table.set_fontsize(9)

        for (row, col), cell in table.get_celld().items():
            cell.set_edgecolor("#444466")
            if row == 0:
                # header
                cell.set_facecolor("#1a1a2e")
                cell.set_text_props(color="#f9ca24", fontweight="bold")
            else:
                cell.set_facecolor(cell_colors[row - 1][col])
                if col == 0:
                    cell.set_text_props(color="#cccccc", fontweight="bold")
                else:
                    # Color based on win rate
                    s_key = ["day", "morning", "night"][col - 1]
                    s = wd_stats["stats"][row - 1][s_key]
                    total = s["up"] + s["down"]
                    if total > 0:
                        pct = s["up"] / total * 100
                        clr = "#ef5350" if pct > 50 else "#26a69a" if pct < 50 else "#cccccc"
                    else:
                        clr = "#cccccc"
                    cell.set_text_props(color=clr)

        table.scale(1, 1.5)
        ax_table.set_title(
            "Weekday 漲跌統計（近 2 個月）",
            color="#eeeeee", fontsize=10, pad=4,
        )
```

- [ ] **Step 3: Include ax_table in the dark-theme styling loop**

Change the existing line (around line 609):
```python
    for a in (ax, ax_vp, ax_macd):
```
to:
```python
    for a in (ax, ax_vp, ax_macd, ax_table):
```

- [ ] **Step 4: Verify the chart renders correctly**

Run:
```bash
uv run python src/analysis/key_prices.py
```

Expected: SR chart now has 3 rows — K-line+VP on top, MACD in middle, weekday stats table at bottom spanning full width. Table shows 5 weekday rows with 3 session columns, colored red/green by win rate, today's row highlighted.

- [ ] **Step 5: Commit**

```bash
git add src/analysis/key_prices.py
git commit -m "feat(key_prices): add weekday stats table to SR chart bottom"
```
