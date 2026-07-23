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
