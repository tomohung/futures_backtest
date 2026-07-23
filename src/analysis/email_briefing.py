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
    """跑 src/analysis/<script>，回傳過濾雜訊後的 stdout（markdown）。

    強制 matplotlib 非互動 Agg backend（MPLBACKEND=Agg）：腳本內的 plt.show()
    在寄信流程不該彈出 GUI 視窗阻塞；Agg 下 show() 為 no-op，savefig 照常運作。
    """
    proc = subprocess.run(
        [sys.executable, str(ANALYSIS_DIR / script)],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        env={**os.environ, "MPLBACKEND": "Agg"},
    )
    lines = [
        ln for ln in proc.stdout.splitlines()
        if not any(noise in ln for noise in _NOISE)
    ]
    text = "\n".join(lines).strip()

    if proc.returncode != 0:
        print(
            f"⚠ {script} 非零退出 (exit {proc.returncode}): {(proc.stderr or '')[-500:]}",
            file=sys.stderr,
        )
        return f"> ⚠️ 本段（{script}）產生失敗（exit {proc.returncode}），內容可能不完整。\n\n{text}"

    return text


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
                "content_type": "image/png",
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
