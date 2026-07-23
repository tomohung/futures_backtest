# 早盤簡報 Email 化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 morning_briefing 的分析產出（文字報告 + 4 張圖表）組成暗色 HTML email，平日盤前經現有 06:00 launchd 自動寄出。

**Architecture:** 兩個新檔——`md_to_email_html.py`（純函式 markdown→inline-styled HTML renderer，可單測）與 `email_briefing.py`（跑 4 個分析腳本擷取 stdout、收 `output/*.png`、組信、以 stdlib urllib 打 Resend REST API，圖用 `content_id` inline 附件）。排程不新增 plist，改把 email 併入現有 `run-daily-update.sh` 的早上那次執行（`--skip-update`，避免第二個 DuckDB 寫入者）。

**Tech Stack:** Python 3.14 / stdlib（`urllib`, `base64`, `subprocess`, `re`）/ Resend REST API / pytest / launchd（既有）。

## Global Constraints

- Renderer 只需覆蓋分析腳本實際吐出的 markdown 構造：`#`~`####` 標題、`|...|` 表格（含 `---`/`:` 對齊列）、`**粗體**`、`> ` blockquote、`---` hr、`- `/`* ` 清單、空行分段。**不做通用 markdown 引擎**。
- Email 必須 **inline 樣式**（客戶端剝 `<style>`/class）。暗色系沿用 `../trading_spirit/scripts/email_alerts.py`：底 `#111` / 文字 `#e8e8e8` / accent `#d4a574` / 表格等寬 `ui-monospace` / th `#d4a574` 底線。
- 箭頭上色 **台股漲紅跌綠**：`↑` = `#e06666`、`↓` = `#57bb8a`。
- 圖表用 Resend **inline attachment**：欄位 `filename` / `content`（base64 字串）/ `content_id`；HTML 端 `<img src="cid:<content_id>">`。
- Resend 呼叫用 stdlib `urllib`（不加依賴），帶常規 `User-Agent`（Cloudflare 擋預設 python-urllib）。環境變數：`RESEND_API_KEY`（缺則 warn + `return 0`）、`ALERT_EMAIL_TO`（預設 `tomohung@gmail.com`）、`ALERT_EMAIL_FROM`（預設 `onboarding@resend.dev`）。
- `from src.analysis... import ...` 在 `uv run` 下可用（`packages = ["src"]` 已安裝）。
- 測試放 `tests/`，pytest class/function 皆可；renderer 為純函式免 DB。
- 分析腳本 stdout 需濾掉雜訊行（含「圖表已儲存」「已複製到剪貼簿」「已儲存」者）。
- Commit 訊息結尾加：`Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`。

---

## File Structure

| 檔案 | 責任 |
|---|---|
| `src/analysis/md_to_email_html.py`（新） | 純函式 `render(markdown) -> str`：markdown 段 → inline-styled HTML 片段 |
| `tests/test_md_to_email_html.py`（新） | renderer 各構造單元測試 |
| `src/analysis/email_briefing.py`（新） | orchestrator：跑分析、收圖、`build_email`、`send`（Resend） |
| `tests/test_email_briefing.py`（新） | 雜訊過濾、build_email 組裝、缺 key 時 skip 的測試 |
| `run-daily-update.sh`（改） | ETL 後在早上追加呼叫 `email_briefing.py --skip-update` |
| `deploy/com.tomo.futures-daily.plist`（改） | `EnvironmentVariables` 加 `RESEND_API_KEY` |

---

## Task 1: Markdown → Email HTML renderer

**Files:**
- Create: `src/analysis/md_to_email_html.py`
- Test: `tests/test_md_to_email_html.py`

**Interfaces:**
- Consumes: 無（純函式，stdlib `re` only）
- Produces: `render(markdown: str) -> str` — 回傳 inline-styled HTML 片段字串（無外層 `<html>`/`<body>`；供 Task 2 組進 email 容器）。

- [ ] **Step 1: Write the failing tests**

Create `tests/test_md_to_email_html.py`:

```python
"""Unit tests for the markdown → email-HTML renderer (pure function)."""
from src.analysis.md_to_email_html import render


def test_h1_and_h3_headers():
    out = render("# 標題一\n\n### 小節")
    assert "<h1" in out and "標題一" in out
    assert "<h3" in out and "小節" in out
    assert "color:#d4a574" in out  # accent


def test_pipe_table_becomes_html_table():
    md = "| 項目 | 值 |\n|------|----:|\n| 高 | 100 |\n| 低 | 90 |"
    out = render(md)
    assert "<table" in out and "</table>" in out
    assert out.count("<tr>") == 3          # 1 header row + 2 data rows
    assert "<th" in out and "項目" in out
    assert "<td" in out and "100" in out
    assert "text-align:right" in out       # `----:` → right align


def test_bold_becomes_strong():
    out = render("這是 **重點** 內容")
    assert "<strong>重點</strong>" in out


def test_up_down_arrows_colored_red_green():
    out = render("多 ↑ 空 ↓")
    assert "#e06666" in out  # ↑ 紅
    assert "#57bb8a" in out  # ↓ 綠


def test_blockquote():
    out = render("> 提示一行\n> 提示二行")
    assert "<blockquote" in out
    assert "提示一行" in out and "提示二行" in out


def test_hr_and_list():
    out = render("- 甲\n- 乙\n\n---")
    assert "<ul" in out and out.count("<li") == 2
    assert "<hr" in out


def test_html_special_chars_escaped():
    out = render("a < b & c > d")
    assert "&lt;" in out and "&amp;" in out and "&gt;" in out


def test_plain_lines_become_paragraph():
    out = render("純文字一行")
    assert "<p" in out and "純文字一行" in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_md_to_email_html.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.analysis.md_to_email_html'`

- [ ] **Step 3: Write the renderer**

Create `src/analysis/md_to_email_html.py`:

```python
"""Minimal markdown → inline-styled HTML for email (dark theme).

Only covers the constructs the morning-briefing analysis scripts emit:
headers (#..####), pipe tables (with `---`/`:` alignment rows), **bold**,
> blockquote, --- hr, - / * lists, blank-line paragraphs. NOT a general
markdown engine. Palette matches trading_spirit/scripts/email_alerts.py.
"""
from __future__ import annotations

import re

_ACCENT = "#d4a574"
_TEXT = "#e8e8e8"
_MUTED = "#888"
_BORDER = "#2a2a2a"
_UP = "#e06666"    # 台股漲紅
_DOWN = "#57bb8a"  # 台股跌綠

_HEADER_SIZE = {1: 20, 2: 17, 3: 15, 4: 13}


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _inline(s: str) -> str:
    """Escape, then apply **bold** and ↑/↓ arrow coloring."""
    s = _esc(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = s.replace("↑", f'<span style="color:{_UP}">↑</span>')
    s = s.replace("↓", f'<span style="color:{_DOWN}">↓</span>')
    return s


def _split_row(line: str) -> list[str]:
    line = line.strip()
    if not line.startswith("|"):
        return []
    return [c.strip() for c in line.strip("|").split("|")]


def _is_table_sep(line: str) -> bool:
    cells = _split_row(line)
    return bool(cells) and all(
        re.fullmatch(r":?-+:?", c.strip() or "") for c in cells
    )


def _aligns(sep_cells: list[str]) -> list[str]:
    out = []
    for c in sep_cells:
        c = c.strip()
        left, right = c.startswith(":"), c.endswith(":")
        out.append("center" if left and right else "right" if right else "left")
    return out


def _header(level: int, text: str) -> str:
    size = _HEADER_SIZE.get(level, 13)
    mt = 20 if level <= 2 else 16
    return (
        f'<h{level} style="color:{_ACCENT};font-size:{size}px;'
        f'margin:{mt}px 0 8px">{_inline(text)}</h{level}>'
    )


def _table(header: list[str], rows: list[list[str]], aligns: list[str]) -> str:
    def al(j: int) -> str:
        return aligns[j] if j < len(aligns) else "left"

    thead = "".join(
        f'<th style="text-align:{al(j)};padding:6px 10px;'
        f'border-bottom:2px solid {_ACCENT};white-space:nowrap">{_inline(h)}</th>'
        for j, h in enumerate(header)
    )
    body = []
    for row in rows:
        tds = "".join(
            f'<td style="text-align:{al(j)};padding:6px 10px;'
            f'border-bottom:1px solid {_BORDER};font-variant-numeric:tabular-nums;'
            f'white-space:nowrap">{_inline(c)}</td>'
            for j, c in enumerate(row)
        )
        body.append(f"<tr>{tds}</tr>")
    return (
        '<table style="border-collapse:collapse;font-size:13px;'
        'font-family:ui-monospace,SFMono-Regular,Menlo,monospace;'
        'margin:8px 0;width:100%">'
        f'<thead><tr>{thead}</tr></thead><tbody>{"".join(body)}</tbody></table>'
    )


def render(markdown: str) -> str:
    lines = markdown.replace("\r\n", "\n").split("\n")
    parts: list[str] = []
    para: list[str] = []
    i, n = 0, len(lines)

    def flush_para() -> None:
        if para:
            text = "<br>".join(_inline(x) for x in para)
            parts.append(f'<p style="margin:8px 0;color:{_TEXT}">{text}</p>')
            para.clear()

    while i < n:
        stripped = lines[i].strip()

        if not stripped:
            flush_para()
            i += 1
            continue

        if stripped == "---":
            flush_para()
            parts.append(
                f'<hr style="border:none;border-top:1px solid {_BORDER};margin:16px 0">'
            )
            i += 1
            continue

        m = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if m:
            flush_para()
            parts.append(_header(len(m.group(1)), m.group(2)))
            i += 1
            continue

        if stripped.startswith("|") and i + 1 < n and _is_table_sep(lines[i + 1]):
            flush_para()
            header = _split_row(lines[i])
            aligns = _aligns(_split_row(lines[i + 1]))
            i += 2
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(_split_row(lines[i]))
                i += 1
            parts.append(_table(header, rows, aligns))
            continue

        if stripped.startswith(">"):
            flush_para()
            quote = []
            while i < n and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip()[1:].strip())
                i += 1
            inner = "<br>".join(_inline(x) for x in quote)
            parts.append(
                f'<blockquote style="margin:8px 0;padding:8px 12px;'
                f'border-left:3px solid {_ACCENT};color:{_MUTED}">{inner}</blockquote>'
            )
            continue

        if re.match(r"^[-*]\s+", stripped):
            flush_para()
            items = []
            while i < n and re.match(r"^[-*]\s+", lines[i].strip()):
                items.append(re.sub(r"^[-*]\s+", "", lines[i].strip()))
                i += 1
            lis = "".join(
                f'<li style="margin:2px 0">{_inline(x)}</li>' for x in items
            )
            parts.append(
                f'<ul style="margin:8px 0;padding-left:20px;color:{_TEXT}">{lis}</ul>'
            )
            continue

        para.append(stripped)
        i += 1

    flush_para()
    return "\n".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_md_to_email_html.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add src/analysis/md_to_email_html.py tests/test_md_to_email_html.py
git commit -m "feat(email): markdown→inline-styled HTML renderer for briefing email

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `email_briefing.py` orchestrator + Resend 寄信

**Files:**
- Create: `src/analysis/email_briefing.py`
- Test: `tests/test_email_briefing.py`

**Interfaces:**
- Consumes: `src.analysis.md_to_email_html.render`（Task 1）。
- Produces（供 Task 3 從 shell 呼叫，並供測試）：
  - `run_section(script: str) -> str` — 跑 `src/analysis/<script>`，回傳過濾雜訊後的 stdout markdown。
  - `build_email(target: str) -> tuple[str, list[dict]]` — 回傳 `(full_html, attachments)`；attachments 元素為 `{"filename","content"(base64 str),"content_id"}`。
  - `send(html: str, attachments: list[dict], target: str) -> int` — 缺 `RESEND_API_KEY` 回 0 且不連線；成功回 0，失敗回 1。
  - `main(argv=None) -> int` — 無 `--skip-update` 時先跑 `daily_update.py`；組信並 `send`。
  - 模組屬性 `OUTPUT_DIR`（Path）、`SECTIONS`（list）供測試 monkeypatch。

- [ ] **Step 1: Write the failing tests**

Create `tests/test_email_briefing.py`:

```python
"""Tests for email_briefing orchestration (no real subprocess / no real send)."""
import base64
import types

import src.analysis.email_briefing as eb


def test_run_section_filters_noise(monkeypatch):
    fake_stdout = "# 標題\n\n內容行\n圖表已儲存：output/x.png\n已複製到剪貼簿，可貼上"

    def fake_run(cmd, capture_output, text, cwd):
        return types.SimpleNamespace(stdout=fake_stdout, returncode=0)

    monkeypatch.setattr(eb.subprocess, "run", fake_run)
    md = eb.run_section("key_prices.py")
    assert "標題" in md and "內容行" in md
    assert "圖表已儲存" not in md
    assert "已複製到剪貼簿" not in md


def test_build_email_embeds_chart_and_attachment(monkeypatch, tmp_path):
    # 一段有文字 + 一張圖的假 section
    png = tmp_path / "sr_chart.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\nFAKE")
    monkeypatch.setattr(eb, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(eb, "SECTIONS", [("key_prices.py", [("sr_chart.png", "支撐壓力")])])
    monkeypatch.setattr(eb, "run_section", lambda script: "# 關鍵價格\n\n| a | b |\n|---|---|\n| 1 | 2 |")

    html, attachments = eb.build_email("2026-07-24")

    assert "關鍵價格" in html
    assert "<table" in html
    assert len(attachments) == 1
    att = attachments[0]
    assert att["filename"] == "sr_chart.png"
    assert att["content_id"]
    assert base64.b64decode(att["content"]) == b"\x89PNG\r\n\x1a\nFAKE"
    assert f'src="cid:{att["content_id"]}"' in html


def test_build_email_skips_missing_chart(monkeypatch, tmp_path):
    monkeypatch.setattr(eb, "OUTPUT_DIR", tmp_path)  # 空目錄，無圖
    monkeypatch.setattr(eb, "SECTIONS", [("daily_range.py", [("daily_range.png", "波動")])])
    monkeypatch.setattr(eb, "run_section", lambda script: "")

    html, attachments = eb.build_email("2026-07-24")
    assert attachments == []


def test_send_skips_without_api_key(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    called = {"urlopen": False}
    monkeypatch.setattr(eb.urllib.request, "urlopen",
                        lambda *a, **k: called.__setitem__("urlopen", True))
    rc = eb.send("<div>x</div>", [], "2026-07-24")
    assert rc == 0
    assert called["urlopen"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_email_briefing.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.analysis.email_briefing'`

- [ ] **Step 3: Write the orchestrator**

Create `src/analysis/email_briefing.py`:

```python
#!/usr/bin/env python3
"""跑早盤分析 → 組暗色 HTML email → Resend 寄出。

用法：
  uv run python src/analysis/email_briefing.py               # 先跑 ETL 再寄
  uv run python src/analysis/email_briefing.py --skip-update # 略過 ETL（pipeline 用，ETL 剛跑完）

環境變數：
  RESEND_API_KEY   必填，缺則 warn + exit 0（不擋 pipeline）
  ALERT_EMAIL_TO   收件人，預設 tomohung@gmail.com
  ALERT_EMAIL_FROM 寄件人，預設 onboarding@resend.dev
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

from src.analysis.md_to_email_html import render

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ANALYSIS_DIR = PROJECT_ROOT / "src" / "analysis"
ETL_DIR = PROJECT_ROOT / "src" / "etl"
OUTPUT_DIR = PROJECT_ROOT / "output"
RESEND_ENDPOINT = "https://api.resend.com/emails"

# 分析腳本 stdout 裡的非報告雜訊行（含以下任一子字串即剔除）
_NOISE = ("圖表已儲存", "已複製到剪貼簿", "已儲存", "剪貼簿")

# (腳本檔名, [(緊接圖檔, 圖說)])。文字取自各腳本 stdout；圖取自 output/。
SECTIONS: list[tuple[str, list[tuple[str, str]]]] = [
    ("key_prices.py", [("sr_chart.png", "支撐壓力"), ("30m_chart.png", "30 分 K")]),
    ("daily_range.py", [("daily_range.png", "日盤波動 + VIX")]),
    ("breadth_thermometer.py", [("breadth_thermometer.png", "漲停萎縮溫度計")]),
    ("fg_composite_monitor.py", []),
]


def run_section(script: str) -> str:
    """跑 src/analysis/<script>，回傳過濾雜訊後的 stdout（markdown）。"""
    proc = subprocess.run(
        [sys.executable, str(ANALYSIS_DIR / script)],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )
    lines = [
        ln for ln in proc.stdout.splitlines()
        if not any(noise in ln for noise in _NOISE)
    ]
    return "\n".join(lines).strip()


def _chart_html(cid: str, caption: str) -> str:
    return (
        '<figure style="margin:16px 0">'
        f'<figcaption style="color:#888;font-size:12px;margin-bottom:4px">{caption}</figcaption>'
        f'<img src="cid:{cid}" alt="{caption}" '
        'style="max-width:100%;border-radius:8px;display:block"></figure>'
    )


def build_email(target: str) -> tuple[str, list[dict]]:
    """組完整 HTML 與 inline 附件清單。"""
    body: list[str] = []
    attachments: list[dict] = []
    cid_n = 0

    for script, charts in SECTIONS:
        md = run_section(script)
        if md:
            body.append(render(md))
        for filename, caption in charts:
            path = OUTPUT_DIR / filename
            if not path.exists():
                continue
            cid = f"chart{cid_n}"
            cid_n += 1
            attachments.append({
                "filename": filename,
                "content": base64.b64encode(path.read_bytes()).decode(),
                "content_id": cid,
            })
            body.append(_chart_html(cid, caption))

    inner = "\n".join(body)
    html = f"""\
<div style="background:#111;color:#e8e8e8;padding:24px;max-width:900px;
font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
  <h2 style="color:#d4a574;margin:0 0 20px">台指早盤簡報 — {target}</h2>
  {inner}
  <p style="margin-top:28px;color:#666;font-size:12px">
    由 run-daily-update.sh 自動寄出 · 資料來源 morning_briefing 分析腳本</p>
</div>"""
    return html, attachments


def send(html: str, attachments: list[dict], target: str) -> int:
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        print("⚠ RESEND_API_KEY 未設定，跳過寄信", file=sys.stderr)
        return 0

    payload = {
        "from": os.environ.get("ALERT_EMAIL_FROM", "onboarding@resend.dev"),
        "to": os.environ.get("ALERT_EMAIL_TO", "tomohung@gmail.com"),
        "subject": f"[台指早盤] {target} 關鍵價格簡報",
        "html": html,
    }
    if attachments:
        payload["attachments"] = attachments

    req = urllib.request.Request(
        RESEND_ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "futures-briefing/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp_body = resp.read().decode("utf-8", "replace")
        print(f"✓ 已寄出早盤簡報 → {payload['to']} ({resp_body})")
        return 0
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        print(f"⚠ Resend API 失敗 ({e.code}): {detail}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"⚠ 寄信連線失敗: {e.reason}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--skip-update" not in argv:
        subprocess.run(
            [sys.executable, str(ETL_DIR / "daily_update.py")],
            check=True,
            cwd=str(PROJECT_ROOT),
        )
    target = date.today().isoformat()
    html, attachments = build_email(target)
    return send(html, attachments, target)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_email_briefing.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/analysis/email_briefing.py tests/test_email_briefing.py
git commit -m "feat(email): email_briefing orchestrator — 分析→組信→Resend 寄出

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: 排程整合（run-daily-update.sh + plist env）

**Files:**
- Modify: `run-daily-update.sh`（ETL 之後、早上追加 email）
- Modify: `deploy/com.tomo.futures-daily.plist`（`EnvironmentVariables` 加 `RESEND_API_KEY`）

**Interfaces:**
- Consumes: `src/analysis/email_briefing.py`（Task 2 的 `main`，`--skip-update`）。
- Produces: 無新程式介面；改動排程行為（早上 ETL 後自動寄信）。

- [ ] **Step 1: 在 run-daily-update.sh 的 ETL 之後、早上追加 email 呼叫**

打開 `run-daily-update.sh`，找到這段：

```bash
uv run python src/etl/daily_update.py "$@"
status=$?

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 更新結束 (exit=$status)"
exit $status
```

改成（在 `exit $status` 前插入 email 步驟；email 失敗不影響 ETL 退出碼）：

```bash
uv run python src/etl/daily_update.py "$@"
status=$?

# 早盤簡報 email：只在早上跑（ETL 剛完成故 --skip-update），失敗不影響 ETL job。
hour=$(date '+%H')
if [ "$status" -eq 0 ] && [ "$hour" -lt 12 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 寄送早盤簡報 email…"
    uv run python src/analysis/email_briefing.py --skip-update || \
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ⚠ email 寄送失敗（已忽略）"
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 更新結束 (exit=$status)"
exit $status
```

- [ ] **Step 2: 語法檢查**

Run: `bash -n run-daily-update.sh`
Expected: 無輸出（語法 OK）

- [ ] **Step 3: 手動端到端驗證（真的寄一封）**

Run: `uv run python src/analysis/email_briefing.py --skip-update`
Expected: 終端印 `✓ 已寄出早盤簡報 → tomohung@gmail.com (...)`；信箱收到一封含文字表格 + 4 張圖的暗色 email。
（若印 `⚠ RESEND_API_KEY 未設定` 表示該 shell 沒帶 key——`RESEND` 已在互動 shell env，直接跑即可；launchd 環境另由 Step 4 補。）

- [ ] **Step 4: 在 plist 補 RESEND_API_KEY（launchd 環境看不到互動 shell env）**

打開 `deploy/com.tomo.futures-daily.plist`，在 `EnvironmentVariables` 的 `<dict>` 內、`FINMIND_API_KEY` 那組之後，加入（值填實際 key，取自互動 shell 的 `echo $RESEND_API_KEY`）：

```xml
		<key>RESEND_API_KEY</key>
		<string>re_實際金鑰填這裡</string>
```

- [ ] **Step 5: 用 deploy.sh 部署（勿直接 cp）**

> ⚠️ 不可直接 `cp deploy/com.tomo.futures-daily.plist ~/Library/LaunchAgents/...`——repo 內 plist 的 `RESEND_API_KEY` 只是佔位符 `__RESEND_API_KEY__`，直接複製會把佔位字串當成真的 key 裝進 launchd 環境。真實金鑰只能存在於 `~/Library/LaunchAgents` 的複本，絕不可進版控。

```bash
RESEND_API_KEY=... bash deploy/deploy.sh
```
`deploy/deploy.sh` 會把 `__RESEND_API_KEY__` 替換成真實金鑰、`plutil -lint` 驗證、並 unload/load 重載 launchd。
Expected: `plutil` 印 `OK`；`launchctl load` 無錯誤；輸出 `✓ 已部署 com.tomo.futures-daily → ...`。
（可選冒煙測試：`launchctl start com.tomo.futures-daily` 手動觸發一次，看 `logs/launchd/daily.log` 是否印出寄信行——注意會真的跑 ETL。）

- [ ] **Step 6: Commit**

```bash
git add run-daily-update.sh deploy/com.tomo.futures-daily.plist
git commit -m "feat(email): 早上 ETL 後自動寄早盤簡報（沿用 06:00 launchd，加 RESEND key）

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

> 注意：`deploy/com.tomo.futures-daily.plist` 內含真實金鑰，commit 前確認此 repo 對此類 secret 的既有慣例（既有檔已含 `FINMIND_API_KEY` 明文，故沿用同慣例）。

---

## Self-Review

**Spec coverage：**
- 文字報告全包 + 4 圖 inline → Task 2 `SECTIONS` + `build_email`（key_prices/daily_range/breadth/fg_composite；4 png CID 附件）✅
- Markdown→HTML 渲染 → Task 1 renderer ✅
- 暗色 inline 樣式 + 漲紅跌綠箭頭 → Task 1 palette/`_inline` ✅
- Resend stdlib urllib + env vars + 缺 key skip → Task 2 `send` ✅
- 排程 launchd 平日 06:00 → Task 3 沿用現有 `com.tomo.futures-daily`（06:00 平日），避免第二寫入者 ✅
- 非交易日照寄（無 guard）→ 未加 guard ✅
- morning_briefing.py 不動 → 未列入改動 ✅
- 雜訊行過濾 → Task 2 `_NOISE` + `run_section` ✅

**Placeholder scan：** 無 TBD/TODO；唯一佔位是 Task 3 Step 4 的 `re_實際金鑰填這裡`（本質需人工填入的 secret，非程式佔位）。✅

**Type consistency：** `render(str)->str`（Task 1）被 Task 2 import 一致；`run_section`/`build_email`/`send`/`main` 簽章在 Interfaces 與程式碼一致；attachment dict 欄位 `filename`/`content`/`content_id` 與測試斷言一致。✅
