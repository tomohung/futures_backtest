"""Tests for email_briefing orchestration (no real subprocess / no real send)."""
import base64
import io
import types
import urllib.error

import src.analysis.email_briefing as eb


def test_run_section_filters_noise(monkeypatch):
    fake_stdout = "# 標題\n\n內容行\n圖表已儲存：output/x.png\n已複製到剪貼簿，可貼上"

    def fake_run(cmd, capture_output, text, cwd, env=None):
        return types.SimpleNamespace(stdout=fake_stdout, returncode=0)

    monkeypatch.setattr(eb.subprocess, "run", fake_run)
    md = eb.run_section("key_prices.py")
    assert "標題" in md and "內容行" in md
    assert "圖表已儲存" not in md
    assert "已複製到剪貼簿" not in md


def test_run_section_forces_agg_backend(monkeypatch):
    """寄信流程不該彈出 GUI 圖窗：run_section 必須以 MPLBACKEND=Agg 跑子程序。"""
    captured = {}

    def fake_run(cmd, capture_output, text, cwd, env=None):
        captured["env"] = env
        return types.SimpleNamespace(stdout="", returncode=0)

    monkeypatch.setattr(eb.subprocess, "run", fake_run)
    eb.run_section("daily_range.py")
    assert captured["env"] is not None
    assert captured["env"].get("MPLBACKEND") == "Agg"


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


def test_send_returns_0_on_success(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "fake-key")
    called = {"urlopen": False}

    class FakeResponse:
        def __enter__(self):
            called["urlopen"] = True
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

        def read(self):
            return b'{"id":"abc"}'

    monkeypatch.setattr(eb.urllib.request, "urlopen", lambda *a, **k: FakeResponse())

    rc = eb.send("<div>x</div>", [], "2026-07-24")

    assert rc == 0
    assert called["urlopen"] is True


def test_send_returns_1_on_http_error(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "fake-key")

    def raise_http_error(*a, **k):
        raise urllib.error.HTTPError(
            url="https://api.resend.com/emails",
            code=403,
            msg="Forbidden",
            hdrs=None,
            fp=io.BytesIO(b"blocked"),
        )

    monkeypatch.setattr(eb.urllib.request, "urlopen", raise_http_error)

    rc = eb.send("<div>x</div>", [], "2026-07-24")

    assert rc == 1


def test_send_returns_1_on_url_error(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "fake-key")

    def raise_url_error(*a, **k):
        raise urllib.error.URLError("no route")

    monkeypatch.setattr(eb.urllib.request, "urlopen", raise_url_error)

    rc = eb.send("<div>x</div>", [], "2026-07-24")

    assert rc == 1


def test_build_email_multiple_charts_get_unique_cids(monkeypatch, tmp_path):
    png_a = tmp_path / "sr_chart.png"
    png_a.write_bytes(b"\x89PNG\r\n\x1a\nFAKE_A")
    png_b = tmp_path / "30m_chart.png"
    png_b.write_bytes(b"\x89PNG\r\n\x1a\nFAKE_B")
    monkeypatch.setattr(eb, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(
        eb,
        "SECTIONS",
        [("key_prices.py", [("sr_chart.png", "支撐壓力"), ("30m_chart.png", "30 分 K")])],
    )
    monkeypatch.setattr(eb, "run_section", lambda script: "# 關鍵價格\n\n內容")

    html, attachments = eb.build_email("2026-07-24")

    assert len(attachments) == 2
    cids = [att["content_id"] for att in attachments]
    assert len(set(cids)) == 2
    for cid in cids:
        assert f'src="cid:{cid}"' in html
