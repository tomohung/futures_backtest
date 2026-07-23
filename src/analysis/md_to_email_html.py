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
