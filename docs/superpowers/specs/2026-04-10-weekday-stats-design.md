# Weekday 漲跌統計

## 目標

在 key_prices 報表中新增按星期幾統計的日盤漲跌資訊（近 2 個月），幫助判斷今日方向偏好。

## 修改範圍

僅修改 `src/analysis/key_prices.py`。

## 資料查詢

在 `get_key_prices()` 新增一段 SQL，從 `ohlcv_1m` 取過去約 40 個交易日的資料，按交易日分組計算兩個時段：

### 時段 1：完整日盤 08:45~13:45

- open = 當日第一根 1 分 K 的 open
- close = 當日最後一根 1 分 K 的 close
- 漲 = close > open；跌 = close <= open
- 漲跌幅 = close - open（點數）

### 時段 2：早盤 09:00~10:30

- open = 09:00 那根 1 分 K 的 open
- close = 10:30 那根 1 分 K 的 close
- 同上邏輯

### 彙整

按 weekday（0=一 ~ 4=五）彙整：漲次、跌次、勝率、平均漲跌幅（點數）。結果存入 `result["weekday_stats"]`。

資料結構：

```python
result["weekday_stats"] = {
    "today_wd": int,  # 今天星期幾 (0=一)
    "stats": {
        0: {  # 週一
            "day": {"up": int, "down": int, "avg_chg": float},
            "morning": {"up": int, "down": int, "avg_chg": float},
        },
        # 1~4 同上
    }
}
```

## 文字報表

在 `print_report()` 的「評估」區塊之後、「支撐壓力」之前，新增：

```
### Weekday 漲跌統計（近 2 個月）

|      | 日盤 08:45-13:45       | 早盤 09:00-10:30       |
|------|------------------------|------------------------|
| 週一 | 5漲/3跌 63% 均+42pt   | 4漲/4跌 50% 均+12pt   |
| 週二 | ...                    | ...                    |
| 週三 | ...                    | ...                    |
| 週四 | ...                    | ...                    |
| 週五 | ...                    | ...                    |
```

今天的 weekday 那行加上 ` ◀` 標記。

## 圖表

SR 圖（`plot_sr_chart`）右下角的 `ax_empty`（目前 `set_visible(False)`）改為可見，用 `ax.table()` 繪製同一張 weekday 統計表格。

配色：
- 背景：`#16213e`（與圖表一致）
- 文字：`#cccccc`
- 漲：`#ef5350`（紅）
- 跌：`#26a69a`（綠）
- 今天的 weekday 行背景高亮

## 不做的事

- 不修改 morning_briefing.py 的呼叫流程
- 不新增檔案
- 不改動其他現有區塊的邏輯
