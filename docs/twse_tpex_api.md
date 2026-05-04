# TWSE / TPEX 公開 API 備忘

證交所（TWSE）與櫃買中心（TPEX）的歷史每日行情都有公開 RWD endpoint，
網頁上的「CSV 下載」按鈕背後就是同一支 API。可直接用於歷史資料回補。

## TWSE（上市）

### 每日收盤行情（MI_INDEX）
對應頁面：<https://www.twse.com.tw/zh/trading/historical/mi-index.html>

```
https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX
```

舊版 endpoint 仍可用：`https://www.twse.com.tw/exchangeReport/MI_INDEX`

| 參數 | 說明 | 範例 |
|------|------|------|
| `date` | 日期，`YYYYMMDD` | `20260430` |
| `type` | 分類代碼 | `ALL`（全部）、`ALLBUT0999`（不含權證/特別股）、`MS`（大盤統計）、`0049`（封閉式基金）、產業別代碼如 `28` |
| `response` | 回傳格式 | `json`、`csv`、`html` |

範例：
```bash
curl "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date=20260430&type=ALL&response=csv" -o mi_index.csv
curl "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date=20260430&type=ALL&response=json"
```

回傳 JSON 結構（多表）：
```json
{
  "tables": [
    { "title": "...", "fields": [...], "data": [[...], ...], "notes": [...] },
    ...
  ]
}
```

注意：
- CSV 一個檔案內含**多個表格**（價格指數、漲跌統計、每日收盤行情…），各區塊以空行分隔，需自行切段解析
- 非交易日：`data` 為空，舊版回 `stat: "很抱歉，沒有符合條件的資料!"`
- 歷史深度約可回溯到 2004 年

## TPEX（上櫃）

### 上櫃當日彙總資訊（highlight）
對應頁面：<https://www.tpex.org.tw/zh-tw/mainboard/trading/info/highlight.html>

```
https://www.tpex.org.tw/www/zh-tw/afterTrading/highlight
```

| 參數 | 說明 | 範例 |
|------|------|------|
| `date` | 日期，**西元 `YYYY/MM/DD`**（注意斜線，跟 TWSE 不同） | `2026/04/30` |
| `response` | 回傳格式 | `json`、`csv`、`html` |
| `id` | 通常空字串即可 | `` |

範例：
```bash
curl "https://www.tpex.org.tw/www/zh-tw/afterTrading/highlight?date=2026/04/30&id=&response=json"
curl "https://www.tpex.org.tw/www/zh-tw/afterTrading/highlight?date=2026/04/30&id=&response=csv"
```

回傳 JSON 結構：
```json
{
  "stat": "ok",
  "date": "20260430",
  "tables": [
    { "title": "上櫃股票當日彙總資訊", "date": "115/04/30", "fields": [...], "data": [[...]], "notes": [...] }
  ]
}
```

### TPEX 其他常用 endpoint（同 base `/www/zh-tw/afterTrading/`）

| Path | 內容 |
|------|------|
| `dailyQuotes` | 上櫃個股日成交資訊（等同 TWSE 的 STOCK_DAY_ALL） |
| `peQuotes` | 本益比、殖利率 |
| `dailyStockInst` | 三大法人買賣超 |

## TWSE vs TPEX 差異整理

| 項目 | TWSE | TPEX |
|------|------|------|
| Base URL | `twse.com.tw/rwd/zh/afterTrading/` | `tpex.org.tw/www/zh-tw/afterTrading/` |
| 日期格式 | `YYYYMMDD` | `YYYY/MM/DD` |
| 回傳日期顯示 | 西元 or 民國 | **民國年**（`115/04/30`） |
| 狀態欄位 | 部分 endpoint 有 `stat` | 有 `stat: "ok"` |

## 抓取注意事項

- **頻率限制**：建議 sleep 3–5 秒/次。TWSE 對連續抓取會封 IP（曾遇過 5 分鐘禁存取）
- **非交易日**：直接跳過（`data` 為空或 `stat` 非 ok）
- 歷史回補建議用 JSON 格式（`tables[i].fields` + `tables[i].data` 直接組裝），CSV 解析較麻煩
- 若要長期排程，搭配既有 `src/etl/daily_update.py` 的偵測機制，從上次成功日期 +1 開始補
