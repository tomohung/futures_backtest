# Daily TAIFEX Data Download & Update System

## 目的

自動化從期交所下載每日 TX 台指期 tick 資料，並執行完整 ETL pipeline，使資料庫保持最新狀態，不需手動介入。

## 新增檔案

| 檔案 | 說明 |
|------|------|
| `src/etl/download.py` | HTTP 下載器（純 stdlib，無新相依） |
| `src/etl/daily_update.py` | Pipeline 整合腳本 |
| `specs/daily_update.md` | 本規格文件 |

## 使用方式

### 完整每日更新

```bash
# 自動偵測起始日，下載到昨天，跑全部 ETL
uv run python src/etl/daily_update.py

# 指定日期範圍
uv run python src/etl/daily_update.py --start 2026-02-01 --end 2026-02-28

# 跳過下載（已手動放好 zip）
uv run python src/etl/daily_update.py --skip-download

# 跳過驗證（加速）
uv run python src/etl/daily_update.py --skip-validate
```

### 只下載

```bash
# 自動偵測起始日，下載到昨天
uv run python src/etl/download.py

# 指定範圍
uv run python src/etl/download.py --start 2026-02-01 --end 2026-02-28

# 預覽（不實際下載）
uv run python src/etl/download.py --dry-run

# 調整下載間隔（預設 1 秒）
uv run python src/etl/download.py --delay 2.0
```

## 下載邏輯（`download.py`）

### URL 格式

```
https://www.taifex.com.tw/file/taifex/Dailydownload/Dailydownload/Daily_YYYY_MM_DD.zip
```

### 自動起始日偵測

`detect_start_date()` 掃描 `data/raw/**/Daily_*.zip`，找到最新 zip 的隔天作為起始日。若磁碟上沒有任何 zip，預設從昨天開始。

### 原子性寫入

下載先寫到 `.zip.tmp`，完整下載後再 `rename()` 為正式檔名，防止部分下載殘留。

### 非交易日偵測

期交所在非交易日（週末、例假日）仍可能回傳內容，但非有效 zip。偵測方式：

1. **HTTP 404** → 回傳 `'non_trading'`，不寫檔
2. **Magic-byte 檢查**：檔案前 4 bytes 不等於 `PK\x03\x04`（zip local file header）→ 非交易日，丟棄

### `download_one()` 回傳值

| 值 | 意義 |
|----|------|
| `'saved'` | zip 成功寫入磁碟 |
| `'skipped'` | 磁碟上已存在，略過 |
| `'non_trading'` | 非交易日（HTML 或 404） |
| `'error'` | 網路錯誤或其他例外 |

## Pipeline 步驟（`daily_update.py`）

| Step | 腳本 | 說明 | 可跳過 |
|------|------|------|--------|
| 0 | `download.py` | 下載 zip 檔 | `--skip-download` |
| 1 | `parse_rpt.py` | zip → ticks 表 | — |
| 2 | `build_1m.py` | ticks → ohlcv_1m 表 | — |
| 3 | `build_continuous.py` | 換倉 + Panama adj_close | — |
| 4 | `validate.py` | 資料驗證 | `--skip-validate` |

各 step 透過 `subprocess` 執行，使用 `sys.executable` 確保在同一 venv 下運行，同時避免多個 DuckDB 寫入連線衝突。

每個 step 如果回傳非零 exit code，pipeline 立即停止（validate 除外：失敗只發出 WARN）。

## 相依性

無新增第三方相依。下載器完全使用 Python stdlib：

- `urllib.request` — HTTP 下載
- `urllib.error` — HTTP 錯誤處理
- `argparse` — CLI
- `pathlib`, `datetime`, `re`, `time` — 標準工具

## 冪等性

- `download.py`：若目標 zip 已存在則 `'skipped'`，不重複下載
- ETL steps 1–3：各自支援增量匯入（已匯入的 trade_date 跳過）
- 可安全重複執行整個 pipeline

## 建議排程（cron）

```cron
# 每天 09:00 TST 執行（確保昨日結算完畢）
0 1 * * * cd /path/to/futures_backtest && uv run python src/etl/daily_update.py >> logs/daily_update.log 2>&1
```

（cron 時間為 UTC，台灣 09:00 = UTC 01:00）
