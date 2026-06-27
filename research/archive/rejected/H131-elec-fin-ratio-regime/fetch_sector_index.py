"""
H131 Phase 0：抓 TWSE 類股指數歷史（電子工業類=TSE23、金融保險類=TSE28）。

來源：TWSE MI_INDEX type=IND（逐日 JSON）。只在「價格指數」表（fields[0]=='指數'，
非 '報酬指數'）裡比對指數名稱，取收盤指數。

可續傳：已存在於 results/sector_index.csv 的日期會跳過。
交易日清單取自 taiex_day（>= START）。節流 SLEEP 秒，含重試。

用法：
  uv run python research/active/H131-elec-fin-ratio-regime/fetch_sector_index.py
"""
from __future__ import annotations
import time
from pathlib import Path

import duckdb
import pandas as pd
import requests

HERE = Path(__file__).parent
OUT = HERE / "results" / "sector_index.csv"
DB = HERE.parent.parent.parent / "data" / "futures.duckdb"
URL = "https://www.twse.com.tw/exchangeReport/MI_INDEX"
START = "2010-01-01"
SLEEP = 0.5
# 電子指數 2019H1 改名：舊「電子類指數」→ 新「電子工業類指數」，同一連續序列（無 rebase）。
ELEC_NAMES = ("電子工業類指數", "電子類指數")  # TSE23，優先新名
FIN_NAME = "金融保險類指數"                    # TSE28
HEADERS = {"User-Agent": "Mozilla/5.0"}


def _num(s: str) -> float:
    return float(str(s).replace(",", ""))


def fetch_day(d: str) -> tuple[float, float] | None:
    """d=YYYYMMDD → (elec_close, fin_close) 或 None（非交易日/缺值/日期不符）。

    污染防護：TWSE 對超出涵蓋範圍的舊日期會回「最新交易日」資料但 echoed date
    仍可能對不上 → 要求 j['date']==d，否則丟棄。
    """
    r = requests.get(URL, params={"response": "json", "date": d, "type": "IND"},
                     headers=HEADERS, timeout=30)
    r.raise_for_status()
    j = r.json()
    if j.get("stat") != "OK" or j.get("date") != d:   # 日期不符=污染，丟棄
        return None
    elec = fin = None
    for t in j.get("tables", []):
        if t.get("fields", [None])[0] != "指數":   # 只認價格指數表
            continue
        for row in t.get("data", []):
            if elec is None and row[0] in ELEC_NAMES:
                elec = _num(row[1])
            elif row[0] == FIN_NAME:
                fin = _num(row[1])
    if elec is None or fin is None:
        return None
    return elec, fin


def main() -> None:
    with duckdb.connect(str(DB), read_only=True) as c:
        dates = [r[0] for r in c.execute(
            "select trade_date from taiex_day where trade_date >= ? order by trade_date",
            [START]).fetchall()]

    done: set = set()
    rows: list[dict] = []
    if OUT.exists():
        prev = pd.read_csv(OUT)
        done = set(pd.to_datetime(prev["trade_date"]).dt.date)
        rows = prev.to_dict("records")

    todo = [d for d in dates if d not in done]
    print(f"交易日 {len(dates)}，已完成 {len(done)}，待抓 {len(todo)}", flush=True)

    for i, d in enumerate(todo, 1):
        ymd = d.strftime("%Y%m%d")
        for attempt in range(3):
            try:
                res = fetch_day(ymd)
                break
            except Exception as e:
                if attempt == 2:
                    print(f"  {ymd} FAIL {e}", flush=True)
                    res = None
                else:
                    time.sleep(2 + attempt * 2)
        if res is not None:
            rows.append({"trade_date": d, "tse23_close": res[0], "tse28_close": res[1]})
        if i % 100 == 0:
            pd.DataFrame(rows).to_csv(OUT, index=False)
            print(f"  進度 {i}/{len(todo)} 最新 {ymd} 已存檔（累計 {len(rows)}）", flush=True)
        time.sleep(SLEEP)

    df = pd.DataFrame(rows).sort_values("trade_date").reset_index(drop=True)
    df.to_csv(OUT, index=False)
    print(f"完成：{len(df)} 筆 → {OUT}", flush=True)
    print(df.head(3).to_string(), flush=True)
    print(df.tail(3).to_string(), flush=True)


if __name__ == "__main__":
    main()
