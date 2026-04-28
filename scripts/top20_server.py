"""
台股上市 mini dashboard：權值前 20 / 熱門前 20 / 高價前 20 + 全市場家數。

啟動：
    uv run --python 3.12 python scripts/top20_server.py
    開瀏覽器 http://127.0.0.1:8765

資料來源：
    - 權重：https://www.taifex.com.tw/cht/9/futuresQADetail （月底更新，每日快取）
    - 全市場上市清單：https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL（每日快取）
    - 即時報價：https://mis.twse.com.tw/stock/api/getStockInfo.jsp
      （背景 thread 每 60s 拉一次全市場 1075 檔，三組排行 + 家數共用同一 snapshot）
"""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8765
TW_TZ = timezone(timedelta(hours=8))

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
MIS_REFERER = "https://mis.twse.com.tw/stock/index.jsp"

TAIFEX_WEIGHT_URL = "https://www.taifex.com.tw/cht/9/futuresQADetail"
TWSE_ALL_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TPEX_ALL_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"

# 快取
_weight_cache: dict = {"date": None, "items": []}     # taifex TSE 權重排行
_market_cache: dict = {"date": None, "tse_codes": [],  # 上市普通股代號
                       "otc_codes": [], "otc_weights": []}  # 上櫃 + 自算權重
_quote_history: dict = {"date": None, "stocks": {}}  # 同日內每檔最後已知 OHL+last，用於補揭示空缺
_snapshot_state: dict = {                             # 背景 thread 產出
    "stocks": None,        # dict[code] -> stock dict
    "breadth": None,
    "updated_at": None,
    "ts": 0.0,
}
_snapshot_lock = threading.Lock()
_snapshot_thread_started = False

SNAPSHOT_INTERVAL = 60.0   # 秒
SNAPSHOT_BATCH = 80         # 每次 mis 查多少檔
SNAPSHOT_PACING = 1.2       # 每 batch 間隔


def _http_get_json(url: str, headers: dict[str, str] | None = None) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def _http_get_text(url: str, headers: dict[str, str] | None = None) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8", errors="replace")


# ───────── taifex 權重 ─────────
def _parse_taifex_weights(html: str) -> list[dict]:
    """期交所 QA 頁的權重表是雙欄式：每個 <tr> 含 8 個 cell（兩筆 row）。"""
    items: list[dict] = []
    seen: set[str] = set()
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
        for i in range(0, len(cells), 4):
            chunk = cells[i:i + 4]
            if len(chunk) != 4:
                continue
            rank_s, code, name, weight_s = chunk
            if not (rank_s.isdigit() and code.isdigit() and "%" in weight_s):
                continue
            if code in seen:
                continue
            seen.add(code)
            try:
                weight = float(weight_s.rstrip("%"))
            except ValueError:
                continue
            items.append({"code": code, "name": name, "weight": weight})
    items.sort(key=lambda x: x["weight"], reverse=True)
    return items


def fetch_weights() -> list[dict]:
    today = datetime.now(TW_TZ).date().isoformat()
    if _weight_cache["date"] == today and _weight_cache["items"]:
        return _weight_cache["items"]
    html = _http_get_text(TAIFEX_WEIGHT_URL)
    items = _parse_taifex_weights(html)
    if not items:
        raise RuntimeError("無法解析期交所權重表")
    _weight_cache.update({"date": today, "items": items})
    return items


# ───────── 全市場 snapshot ─────────
def _is_common_4digit(code: str) -> bool:
    return bool(code and len(code) == 4 and code.isdigit() and code[0] != "0")


def fetch_market_data() -> dict:
    """日快取：上市代號清單、上櫃代號清單與上櫃自算權重。"""
    today = datetime.now(TW_TZ).date().isoformat()
    if _market_cache["date"] == today and _market_cache["tse_codes"]:
        return _market_cache

    # 上市
    tse_data = _http_get_json(TWSE_ALL_URL)
    tse_codes = [r["Code"] for r in tse_data if _is_common_4digit(r.get("Code", ""))]

    # 上櫃 + 估算市值權重
    otc_data = _http_get_json(TPEX_ALL_URL)
    otc_rows = []
    for r in otc_data:
        code = r.get("SecuritiesCompanyCode", "")
        if not _is_common_4digit(code):
            continue
        try:
            cap = float(r.get("Capitals", 0))
            close = float(r.get("Close", 0))
            mv = cap * close
        except (TypeError, ValueError):
            continue
        if mv <= 0:
            continue
        otc_rows.append({"code": code, "name": r.get("CompanyName", code).strip(), "market_value": mv})
    total_mv = sum(x["market_value"] for x in otc_rows) or 1.0
    for x in otc_rows:
        x["weight"] = x["market_value"] / total_mv * 100
    otc_rows.sort(key=lambda x: x["weight"], reverse=True)
    otc_codes = [x["code"] for x in otc_rows]

    _market_cache.update({
        "date": today,
        "tse_codes": tse_codes,
        "otc_codes": otc_codes,
        "otc_weights": otc_rows,
    })
    return _market_cache


def _num(v) -> float | None:
    if v in (None, "", "-"):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _first_price(s) -> float | None:
    """mis 五檔欄位格式 '2270.0000_2275.0000_...'，回傳第一個正價（跳過 0 與佔位）。"""
    if not s or s == "-":
        return None
    for p in s.split("_"):
        v = _num(p)
        if v is not None and v > 0:
            return v
    return None


def _fetch_quotes_batch(channels: list[str]) -> list[dict]:
    """channels 已含 'tse_' 或 'otc_' 前綴的 ex_ch 字串。"""
    ex_ch = "|".join(channels)
    url = (
        "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
        f"?ex_ch={urllib.parse.quote(ex_ch, safe='|')}&json=1&delay=0"
    )
    return _http_get_json(url, headers={"Referer": MIS_REFERER}).get("msgArray", [])


def compute_snapshot() -> tuple[dict[str, dict], dict]:
    """拉上市+上櫃全部，回傳 (stocks_by_code, breadth_summary)。"""
    md = fetch_market_data()
    channels = [f"tse_{c}.tw" for c in md["tse_codes"]] + \
               [f"otc_{c}.tw" for c in md["otc_codes"]]
    today = datetime.now(TW_TZ).date().isoformat()
    if _quote_history["date"] != today:
        _quote_history["date"] = today
        _quote_history["stocks"] = {}
    history = _quote_history["stocks"]
    stocks: dict[str, dict] = {}
    up = down = flat = no_trade = limit_up = limit_down = 0
    for i in range(0, len(channels), SNAPSHOT_BATCH):
        batch = channels[i:i + SNAPSHOT_BATCH]
        try:
            rows = _fetch_quotes_batch(batch)
        except Exception:
            rows = []
        for row in rows:
            code = row.get("c")
            if not code:
                continue
            prev = _num(row.get("y"))
            last = _num(row.get("z"))
            op = _num(row.get("o"))
            hi = _num(row.get("h"))
            lo = _num(row.get("l"))
            up_lim = _num(row.get("u"))
            dn_lim = _num(row.get("w"))
            vol_lots = _num(row.get("v"))  # 累計成交量（張）

            # last 缺值時：先用買賣五檔中價，再用上一輪 history
            if last is None:
                bid = _first_price(row.get("b"))
                ask = _first_price(row.get("a"))
                if bid is not None and ask is not None:
                    last = (bid + ask) / 2
                elif bid is not None:
                    last = bid
                elif ask is not None:
                    last = ask
            hist = history.get(code, {})
            if last is None and hist.get("last") is not None:
                last = hist["last"]
            if op is None and hist.get("open") is not None:
                op = hist["open"]
            if hi is None and hist.get("high") is not None:
                hi = hist["high"]
            if lo is None and hist.get("low") is not None:
                lo = hist["low"]
            history[code] = {"last": last, "open": op, "high": hi, "low": lo}

            # 估算成交金額：優先用 last，其次 open，再退到 prev
            basis = last if last is not None else (op if op is not None else prev)
            stocks[code] = {
                "code": code,
                "name": row.get("n", code),
                "market": row.get("ex", "").lower() or "tse",  # 'tse' or 'otc'
                "prev": prev,
                "open": op,
                "high": hi,
                "low": lo,
                "last": last,
                "vol_lots": vol_lots,
                "trade_value": (basis * vol_lots * 1000) if (basis and vol_lots) else 0.0,
                "t": row.get("t", ""),
            }

            # 家數
            if last is None or prev is None:
                no_trade += 1
            elif last > prev:
                up += 1
                if up_lim and abs(last - up_lim) < 1e-6:
                    limit_up += 1
            elif last < prev:
                down += 1
                if dn_lim and abs(last - dn_lim) < 1e-6:
                    limit_down += 1
            else:
                flat += 1
        if i + SNAPSHOT_BATCH < len(channels):
            time.sleep(SNAPSHOT_PACING)

    breadth = {
        "up": up, "down": down, "flat": flat,
        "limit_up": limit_up, "limit_down": limit_down,
        "no_trade": no_trade,
        "total_listed": len(md["tse_codes"]) + len(md["otc_codes"]),
        "total_quoted": len(stocks),
        "tse_count": len(md["tse_codes"]),
        "otc_count": len(md["otc_codes"]),
    }
    return stocks, breadth


def _snapshot_loop() -> None:
    while True:
        try:
            stocks, breadth = compute_snapshot()
            _snapshot_state["stocks"] = stocks
            _snapshot_state["breadth"] = breadth
            _snapshot_state["updated_at"] = datetime.now(TW_TZ).strftime("%Y-%m-%d %H:%M:%S")
            _snapshot_state["ts"] = time.time()
        except Exception as e:
            print(f"[snapshot] error: {e}")
        time.sleep(SNAPSHOT_INTERVAL)


def _ensure_snapshot_thread() -> None:
    global _snapshot_thread_started
    with _snapshot_lock:
        if _snapshot_thread_started:
            return
        threading.Thread(target=_snapshot_loop, daemon=True, name="snapshot").start()
        _snapshot_thread_started = True


# ───────── 各排行組裝 ─────────
def _make_row(s: dict) -> dict:
    """把 stock dict 轉成蠟燭圖前端用的 row（含 *_pct）。"""
    prev = s.get("prev")
    last = s.get("last")  # 留 None；前端遇 None 只畫 wick 不畫 body
    op = s.get("open")
    hi = s.get("high")
    lo = s.get("low")

    def pct(v):
        if v is None or prev in (None, 0):
            return None
        return (v - prev) / prev * 100

    return {
        "code": s["code"],
        "name": s.get("name", s["code"]),
        "market": s.get("market", "tse"),
        "prev": prev,
        "open": op,
        "high": hi,
        "low": lo,
        "last": last,
        "vol_lots": s.get("vol_lots"),
        "trade_value": s.get("trade_value", 0.0),
        "open_pct": pct(op),
        "high_pct": pct(hi),
        "low_pct": pct(lo),
        "last_pct": pct(last),
    }


def _weight_top20_rows(stocks: dict[str, dict] | None) -> list[dict]:
    weights = fetch_weights()[:20]
    rows = []
    for w in weights:
        s = (stocks or {}).get(w["code"]) or {"code": w["code"], "name": w["name"], "market": "tse"}
        row = _make_row(s)
        row["weight"] = w["weight"]
        rows.append(row)
    return rows


def _otc_weight_top20_rows(stocks: dict[str, dict] | None) -> list[dict]:
    """上櫃權值前 20（以市值估算的 weight 排序）。"""
    md = fetch_market_data()
    rows = []
    for w in md["otc_weights"][:20]:
        s = (stocks or {}).get(w["code"]) or {"code": w["code"], "name": w["name"], "market": "otc"}
        row = _make_row(s)
        row["weight"] = w["weight"]
        rows.append(row)
    return rows


def _hot_top20_rows(stocks: dict[str, dict] | None) -> list[dict]:
    if not stocks:
        return []
    sortable = [s for s in stocks.values() if (s.get("trade_value") or 0) > 0]
    sortable.sort(key=lambda s: s["trade_value"], reverse=True)
    return [_make_row(s) for s in sortable[:20]]


def _price_top20_rows(stocks: dict[str, dict] | None) -> list[dict]:
    if not stocks:
        return []
    # 用 last（盤中）或 prev（盤前）做基準價
    def base(s):
        return s.get("last") or s.get("prev") or 0
    sortable = [s for s in stocks.values() if base(s) > 0]
    sortable.sort(key=base, reverse=True)
    return [_make_row(s) for s in sortable[:20]]


def build_payload() -> dict:
    _ensure_snapshot_thread()
    stocks = _snapshot_state["stocks"]
    breadth = _snapshot_state["breadth"]
    snap_at = _snapshot_state["updated_at"]

    return {
        "served_at": datetime.now(TW_TZ).strftime("%Y-%m-%d %H:%M:%S"),
        "snapshot_at": snap_at,
        "snapshot_ready": stocks is not None,
        "breadth": breadth,
        "tse_weight_top20": _weight_top20_rows(stocks),
        "otc_weight_top20": _otc_weight_top20_rows(stocks),
        "hot_top20": _hot_top20_rows(stocks),
        "price_top20": _price_top20_rows(stocks),
    }


# ───────── 前端 ─────────
HTML = r"""<!doctype html>
<html lang="zh-TW">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>台股 mini dashboard</title>
<style>
  :root { color-scheme: dark; }
  html, body { margin: 0; padding: 0; height: 100%; overflow: hidden;
    background: #0e1626; color: #cfd8e3;
    font-family: -apple-system, "Noto Sans TC", "PingFang TC", sans-serif; }
  body { display: flex; flex-direction: column; }
  /* 頂部單列：標題 + 家數 + 更新時間 */
  #topbar { flex: 0 0 auto; display: flex; align-items: center; gap: 18px;
    padding: 6px 14px; border-bottom: 1px solid #1f2a3d; min-height: 40px; }
  #topbar h1 { font-size: 13px; font-weight: 500; margin: 0; color: #cfd8e3;
    white-space: nowrap; }
  .b-item { display: flex; gap: 5px; align-items: baseline; }
  .b-label { font-size: 11px; color: #7b8aa3; }
  .b-num { font-size: 18px; font-weight: 600; font-variant-numeric: tabular-nums;
    line-height: 1; }
  .b-item.up .b-num { color: #ef4f4f; }
  .b-item.down .b-num { color: #2ecc71; }
  .b-item.flat .b-num { color: #cfd8e3; }
  .b-item.muted .b-num { color: #7b8aa3; font-size: 15px; }
  .b-meta { margin-left: auto; font-size: 11px; color: #7b8aa3; white-space: nowrap; }
  /* 2x2 grid：4 張圖等大 */
  #grid { flex: 1 1 0; min-height: 0; display: grid;
    grid-template-columns: 1fr 1fr; grid-template-rows: 1fr 1fr; }
  section.chart-block { min-height: 0; min-width: 0; display: flex;
    flex-direction: column; padding: 2px 12px 0;
    border-right: 1px solid #1f2a3d; border-bottom: 1px solid #1f2a3d; }
  section.chart-block:nth-child(2n) { border-right: none; }
  section.chart-block:nth-last-child(-n+2) { border-bottom: none; }
  .chart-title { flex: 0 0 auto; display: flex; align-items: baseline; gap: 8px;
    padding: 2px 0; }
  .chart-title h2 { font-size: 12px; font-weight: 500; margin: 0; color: #cfd8e3; }
  .chart-title .sub { font-size: 11px; color: #7b8aa3; }
  svg.chart { flex: 1 1 0; min-height: 0; width: 100%; display: block; }
  .axis text { fill: #7b8aa3; font-size: 11px; }
  .axis line { stroke: #1f2a3d; stroke-width: 1; }
  .axis .zero { stroke: #34425e; }
  .label { fill: #cfd8e3; font-size: 11px; }
  .label.otc { fill: #f5b942; }
  .sublabel { fill: #7b8aa3; font-size: 10px; }
  .wick { stroke-width: 1.5; }
  .body { stroke: none; }
  .up { fill: #ef4f4f; } .up-stroke { stroke: #ef4f4f; }
  .down { fill: #2ecc71; } .down-stroke { stroke: #2ecc71; }
  .flat { fill: #7b8aa3; } .flat-stroke { stroke: #7b8aa3; }
</style>
</head>
<body>
<div id="topbar">
  <h1>台股上市 dashboard</h1>
  <div class="b-item up"><span class="b-label">上漲</span><span class="b-num" id="b-up">—</span></div>
  <div class="b-item down"><span class="b-label">下跌</span><span class="b-num" id="b-down">—</span></div>
  <div class="b-item flat"><span class="b-label">平盤</span><span class="b-num" id="b-flat">—</span></div>
  <div class="b-item up"><span class="b-label">漲停</span><span class="b-num" id="b-lu">—</span></div>
  <div class="b-item down"><span class="b-label">跌停</span><span class="b-num" id="b-ld">—</span></div>
  <div class="b-item muted"><span class="b-label">未交易</span><span class="b-num" id="b-nt">—</span></div>
  <span class="b-meta" id="meta">載入中…</span>
</div>

<div id="grid">
  <section class="chart-block">
    <div class="chart-title"><h2>上市權值前 20</h2><span class="sub" id="sub-tse-w"></span></div>
    <svg class="chart" id="chart-tse-w"></svg>
  </section>

  <section class="chart-block">
    <div class="chart-title"><h2>上櫃權值前 20</h2><span class="sub" id="sub-otc-w"></span></div>
    <svg class="chart" id="chart-otc-w"></svg>
  </section>

  <section class="chart-block">
    <div class="chart-title"><h2>熱門前 20（成交金額・上市+上櫃）</h2><span class="sub" id="sub-hot"></span></div>
    <svg class="chart" id="chart-hot"></svg>
  </section>

  <section class="chart-block">
    <div class="chart-title"><h2>高價前 20（股價・上市+上櫃）</h2><span class="sub" id="sub-price"></span></div>
    <svg class="chart" id="chart-price"></svg>
  </section>
</div>

<script>
const Y_MIN = -10, Y_MAX = 10;
const PAD = { top: 8, right: 30, bottom: 78, left: 38 };

function yScale(p, top, plotH) {
  const c = Math.max(Y_MIN, Math.min(Y_MAX, p));
  return top + (Y_MAX - c) / (Y_MAX - Y_MIN) * plotH;
}

function fmtMoney(v) {
  if (v == null) return '';
  if (v >= 1e8) return (v/1e8).toFixed(1) + '億';
  if (v >= 1e4) return (v/1e4).toFixed(0) + '萬';
  return Math.round(v) + '';
}

function renderChart(svgId, rows, subFn) {
  const svg = document.getElementById(svgId);
  // 讀容器實際像素，viewBox 1:1 對應，文字不會被拉伸
  const W = svg.clientWidth || 800;
  const H = svg.clientHeight || 240;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.setAttribute('preserveAspectRatio', 'none');

  if (!rows || rows.length === 0) {
    svg.innerHTML = `<text x="${W/2}" y="${H/2}" text-anchor="middle" fill="#7b8aa3" font-size="12">尚未取得資料（首次需 ~30 秒）</text>`;
    return;
  }
  const PLOT_W = W - PAD.left - PAD.right;
  const PLOT_H = H - PAD.top - PAD.bottom;
  const n = rows.length;
  const slot = PLOT_W / n;
  const bodyW = Math.max(4, slot * 0.55);

  let s = '';
  // 軸線
  s += `<g class="axis">`;
  for (const tick of [-10,-5,0,5,10]) {
    const y = yScale(tick, PAD.top, PLOT_H);
    const cls = tick === 0 ? 'zero' : '';
    s += `<line class="${cls}" x1="${PAD.left}" x2="${W-PAD.right}" y1="${y}" y2="${y}"/>`;
    const color = tick > 0 ? '#ef4f4f' : (tick < 0 ? '#2ecc71' : '#7b8aa3');
    s += `<text x="${PAD.left-6}" y="${y+4}" text-anchor="end" fill="${color}">${tick}%</text>`;
  }
  s += `</g>`;

  rows.forEach((r, i) => {
    const cx = PAD.left + slot * (i + 0.5);
    const op = r.open_pct, lp = r.last_pct, hp = r.high_pct, lop = r.low_pct;
    const hasRange = hp !== null && lop !== null;
    const hasBody  = op !== null && lp !== null;
    const noData   = op === null && lp === null && hp === null && lop === null;

    // 顏色：有 body 看 last vs open；無 body 用 wick 中點 vs 0 判紅綠
    let cls = 'flat';
    if (hasBody) {
      if (lp > op) cls = 'up';
      else if (lp < op) cls = 'down';
    } else if (hasRange) {
      const mid = (hp + lop) / 2;
      if (mid > 0.05) cls = 'up';
      else if (mid < -0.05) cls = 'down';
    }

    if (noData) {
      // 盤前 / 完全無資料：0% 細線
      const y0 = yScale(0, PAD.top, PLOT_H);
      s += `<line class="wick flat-stroke" x1="${cx-bodyW/2}" x2="${cx+bodyW/2}" y1="${y0}" y2="${y0}"/>`;
    } else {
      if (hasRange) {
        const yh = yScale(hp, PAD.top, PLOT_H), yl = yScale(lop, PAD.top, PLOT_H);
        s += `<line class="wick ${cls}-stroke" x1="${cx}" x2="${cx}" y1="${yh}" y2="${yl}"/>`;
      }
      if (hasBody) {
        const top = yScale(Math.max(op, lp), PAD.top, PLOT_H);
        const bot = yScale(Math.min(op, lp), PAD.top, PLOT_H);
        const h = Math.max(2, bot - top);
        s += `<rect class="body ${cls}" x="${cx - bodyW/2}" y="${top}" width="${bodyW}" height="${h}"/>`;
      } else if (hasRange) {
        // 揭示間隔內無 z：以 wick 中點畫一條短橫線示意「無 body」
        const ym = yScale((hp + lop) / 2, PAD.top, PLOT_H);
        s += `<line class="wick ${cls}-stroke" x1="${cx-bodyW/3}" x2="${cx+bodyW/3}" y1="${ym}" y2="${ym}" stroke-dasharray="2 2"/>`;
      }
    }

    // 直式股名（top-to-bottom，每字保持正向）；上櫃用橘字提示
    const lx = cx, ly = H - PAD.bottom + 4;
    const lblCls = r.market === 'otc' ? 'label otc' : 'label';
    s += `<text class="${lblCls}" x="${lx}" y="${ly}" text-anchor="middle"
            style="writing-mode: vertical-rl; text-orientation: upright; letter-spacing: 0.5px;"
          >${r.name}</text>`;

    // 副標：放在 wick 上方
    if (subFn) {
      const sub = subFn(r);
      if (sub) {
        const yh = (hp !== null) ? yScale(hp, PAD.top, PLOT_H) : yScale(0, PAD.top, PLOT_H);
        s += `<text class="sublabel" x="${cx}" y="${Math.max(yh - 3, 10)}" text-anchor="middle">${sub}</text>`;
      }
    }
  });

  svg.innerHTML = s;
}

function render(data) {
  // 大盤家數
  const b = data.breadth;
  const setNum = (id, v) => document.getElementById(id).textContent = (v ?? '—');
  if (b) {
    setNum('b-up', b.up);
    setNum('b-down', b.down);
    setNum('b-flat', b.flat);
    setNum('b-lu', b.limit_up);
    setNum('b-ld', b.limit_down);
    setNum('b-nt', b.no_trade);
    const tseN = b.tse_count ?? '—';
    const otcN = b.otc_count ?? '—';
    document.getElementById('meta').textContent =
      `上市 ${tseN} + 上櫃 ${otcN} = ${b.total_quoted}/${b.total_listed} 檔・snapshot ${data.snapshot_at ?? '—'}`;
  } else {
    document.getElementById('meta').textContent = '計算中（首次約 30 秒）…';
  }

  // 四個排行
  renderChart('chart-tse-w', data.tse_weight_top20,
    r => r.weight ? `占${r.weight.toFixed(2)}%` : '');
  renderChart('chart-otc-w', data.otc_weight_top20,
    r => r.weight ? `估${r.weight.toFixed(2)}%` : '');
  renderChart('chart-hot', data.hot_top20,
    r => r.trade_value > 0 ? fmtMoney(r.trade_value) : '');
  renderChart('chart-price', data.price_top20,
    r => r.last ? `$${r.last}` : (r.prev ? `$${r.prev}` : ''));

  document.getElementById('sub-tse-w').textContent = `taifex 月底權重`;
  document.getElementById('sub-otc-w').textContent = `估算（流通股本×昨收）`;
  document.getElementById('sub-hot').textContent = `累計張數 × 最新價 × 1000`;
  document.getElementById('sub-price').textContent = `依當下成交價（盤前以昨收）`;
}

async function refresh() {
  try {
    const r = await fetch('/api/data', { cache: 'no-store' });
    const d = await r.json();
    _lastData = d;
    render(d);
  } catch (e) {
    document.getElementById('meta').textContent = '更新失敗：' + e;
  }
}

let _lastData = null;
async function refreshAndRender() { await refresh(); }
window.addEventListener('resize', () => { if (_lastData) render(_lastData); });

refresh();
setInterval(refresh, 60_000);
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            self._send(200, HTML.encode("utf-8"), "text/html; charset=utf-8")
            return
        if self.path.startswith("/api/data"):
            try:
                payload = build_payload()
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self._send(200, body, "application/json; charset=utf-8")
            except Exception as e:
                self._send(500, json.dumps({"error": str(e)}).encode(), "application/json")
            return
        self._send(404, b"not found", "text/plain")


def main() -> None:
    print(f"server: http://127.0.0.1:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
