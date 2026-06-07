"""
下載全市場個股分 k（FinMind TaiwanStockKBar）→ parquet landing 區 `data/stock_min_raw/`。

**下載階段完全不開 futures.duckdb**：啟動時一次把區間每日宇宙讀進記憶體後，
整個下載 loop 只碰 FinMind API + 檔案系統，因此可與 daily_update / chart-ui /
早盤簡報並行、無 DuckDB 寫鎖衝突。

每天一個檔：`data/stock_min_raw/YYYY-MM-DD.parquet`。**檔案存在 = 該日完成**（冪等續傳）；
fetched<expected（多半撞 rate limit）則不寫檔，留待重跑。

第二步「parquet → DuckDB stock_min 表」見 `load_stock_min.py`（快、幾分鐘、可隨時做）。

dataset TaiwanStockKBar 為 Sponsor 限定（6000 req/hr，一 request=一檔一天），
token 取自 env FINMIND_API_KEY；用官方 SDK use_async 批多檔。

用法：
  uv run python src/etl/download_stock_min.py --market TWSE --start 2025-06-01 --end 2026-06-05
  uv run python src/etl/download_stock_min.py            # 預設 2021-01-01 至今、全市場
"""

from __future__ import annotations

import argparse
import os
import time
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "futures.duckdb"
RAW_DIR = PROJECT_ROOT / "data" / "stock_min_raw"

STOCK_MIN_COLS = ["trade_date", "stock_id", "minute",
                  "open", "high", "low", "close", "volume"]


def day_path(d: date, raw_dir: Path = RAW_DIR) -> Path:
    """該交易日的 parquet 落地路徑。"""
    return raw_dir / f"{d.isoformat()}.parquet"


def load_universe_map(
    start: date, end: date, market: str | None = None
) -> dict[date, list[str]]:
    """一次讀 futures.duckdb 取得區間每日宇宙 {date: [symbols]}，之後下載 loop 不再碰 DB。

    宇宙取自 stock_day 當日有成交 symbols（含已下市公司，避免 survivorship bias）。
    """
    sql = (
        "SELECT trade_date, symbol FROM stock_day "
        "WHERE trade_date BETWEEN ? AND ? "
        + ("AND market = ? " if market else "")
        + "ORDER BY trade_date, symbol"
    )
    params: list = [start, end, market] if market else [start, end]
    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        rows = conn.execute(sql, params).fetchall()
    umap: dict[date, list[str]] = {}
    for d, s in rows:
        umap.setdefault(d, []).append(s)
    return umap


def normalize_kbar(df: pd.DataFrame, d: date) -> pd.DataFrame:
    """FinMind kbar df → stock_min 欄序/型別。空 df 回傳空但欄位齊全。"""
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=STOCK_MIN_COLS)
    out = df.copy()
    out["trade_date"] = d
    out["minute"] = pd.to_datetime(out["minute"], format="%H:%M:%S").dt.time
    out["stock_id"] = out["stock_id"].astype(str)
    out["volume"] = out["volume"].fillna(0).astype("int64")
    # FinMind 舊資料（如 2021 的 ETF）偶有同一分鐘重複 print（OHLC 同、volume 微差）。
    # 去重保留後到的 final print，避免日後載入 DB 時違反 PK。
    out = out.drop_duplicates(subset=["trade_date", "stock_id", "minute"], keep="last")
    return out[STOCK_MIN_COLS].reset_index(drop=True)


def write_day_parquet(d: date, df: pd.DataFrame, raw_dir: Path = RAW_DIR) -> Path:
    """用 in-memory DuckDB 把當日 df 寫成 parquet（:memory: 無檔鎖，不碰 futures.duckdb）。"""
    raw_dir.mkdir(parents=True, exist_ok=True)
    out = day_path(d, raw_dir)
    tmp = out.with_suffix(".parquet.tmp")  # 先寫 tmp 再 rename，避免中斷留半檔
    con = duckdb.connect()  # in-memory
    try:
        con.register("d_df", df)
        con.execute(f"COPY d_df TO '{tmp}' (FORMAT PARQUET)")
    finally:
        con.close()
    tmp.replace(out)
    return out


def _kbar_call(stock_id_list: list[str], date_str: str, use_async: bool) -> pd.DataFrame:
    """薄包 FinMind SDK。隔離成單一接縫供測試 monkeypatch。"""
    from FinMind.data import DataLoader

    token = os.environ["FINMIND_API_KEY"]
    dl = DataLoader()
    dl.login_by_token(api_token=token)
    return dl.taiwan_stock_kbar(
        stock_id_list=stock_id_list, date=date_str, use_async=use_async
    )


def fetch_kbar_day(stock_ids: list[str], d: str, max_retries: int = 4) -> pd.DataFrame:
    """抓單日全宇宙分 k；rate-limit/連線錯誤指數退避重試。最終失敗則 raise。"""
    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            return _kbar_call(stock_ids, d, use_async=True)
        except Exception as e:  # noqa: BLE001 — 退避重試所有暫態錯誤
            last_err = e
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # 1,2,4,8...秒
    raise RuntimeError(f"fetch_kbar_day {d} 重試 {max_retries} 次仍失敗: {last_err}")


def download_day(d: date, universe: list[str], raw_dir: Path = RAW_DIR) -> tuple[int, int]:
    """抓單日 → normalize → 寫 parquet。回傳 (fetched, expected)。

    只有「全數取得」才寫檔（檔案存在=完成）；fetched<expected 一律不寫、留待重跑
    （fetched==0 多半是撞 FinMind rate limit，SDK 會吞錯回空 df 而不 raise）。
    """
    expected = len(universe)
    if expected == 0:
        return 0, 0
    try:
        raw = fetch_kbar_day(universe, d.isoformat())
    except Exception as e:  # noqa: BLE001
        print(f"  {d} 抓取失敗，跳過待重抓：{e}", flush=True)
        return 0, expected
    norm = normalize_kbar(raw, d)
    fetched = norm["stock_id"].nunique() if len(norm) else 0
    if fetched < expected:
        warn = " ⚠ 可能撞 rate limit" if fetched == 0 else ""
        print(f"  {d}: 宇宙{expected} 取得{fetched} → 不寫檔待重抓{warn}", flush=True)
        return fetched, expected
    out = write_day_parquet(d, norm, raw_dir)
    print(f"  {d}: 宇宙{expected} 取得{fetched} rows={len(norm)} → {out.name}", flush=True)
    return fetched, expected


# FinMind Sponsor 限額 = 6000 requests/小時（一個 request = 一檔一天）。
# 留 margin，自我節流到 RATE_PER_HOUR；超量則等最舊請求滿一小時釋出。
RATE_PER_HOUR = 5500
_window: list[tuple[float, int]] = []  # (timestamp, request_count)


def _throttle(need: int, limit: int = RATE_PER_HOUR) -> None:
    """滑動視窗節流：確保任一小時內發出的 request 數 ≤ limit。"""
    now = time.time()
    while _window and now - _window[0][0] > 3600:
        _window.pop(0)
    used = sum(c for _, c in _window)
    while _window and used + need > limit:
        wait = 3600 - (now - _window[0][0]) + 1
        print(f"  ⏳ rate-limit 保護：本小時已用 {used}/{limit}，本日需 {need}，"
              f"等 {wait/60:.0f} 分鐘釋出…", flush=True)
        time.sleep(min(wait, 300))
        now = time.time()
        while _window and now - _window[0][0] > 3600:
            _window.pop(0)
        used = sum(c for _, c in _window)
    _window.append((now, need))


def _quota_available() -> bool:
    """探一筆已知有資料的 stock-day，確認 FinMind quota 尚未耗盡（非空回傳）。"""
    try:
        df = fetch_kbar_day(["2330"], "2026-05-29")
        return df is not None and len(df) > 0
    except Exception:
        return False


def main() -> None:
    p = argparse.ArgumentParser(
        description="下載個股分 k（FinMind TaiwanStockKBar）→ parquet landing 區")
    p.add_argument("--start", type=date.fromisoformat, default=date(2021, 1, 1))
    p.add_argument("--end", type=date.fromisoformat, default=date.today())
    p.add_argument("--market", choices=["TWSE", "TPEX"], default=None,
                   help="預設全市場；指定則只抓單一市場")
    args = p.parse_args()

    if not os.environ.get("FINMIND_API_KEY"):
        raise SystemExit("缺 env FINMIND_API_KEY")

    # 一次讀宇宙（唯一碰 futures.duckdb 的地方），之後不再開 DB
    umap = load_universe_map(args.start, args.end, args.market)
    all_days = sorted(umap)
    todo = [d for d in all_days if not day_path(d).exists()]
    print(f"交易日 {len(all_days)}，待下載 {len(todo)}"
          f"（已落地 {len(all_days)-len(todo)} 跳過）→ {RAW_DIR}", flush=True)

    # 啟動 gate：quota 仍耗盡（探測秒回空）就等釋出，避免整批白跑
    while todo and not _quota_available():
        print("  ⏳ FinMind quota 目前耗盡（探測回空），等 10 分鐘後重試…", flush=True)
        time.sleep(600)

    for i, d in enumerate(todo, 1):
        univ = umap[d]
        _throttle(len(univ))
        print(f"[{i}/{len(todo)}] {d}", flush=True)
        download_day(d, univ)


if __name__ == "__main__":
    main()
