# 突破時間點與勝率分析

## 背景與動機

兩個策略（EstHL、ORBLong）都在特定時間窗口內偵測突破進場，但目前不清楚**突破發生的精確分鐘**是否影響勝率。

假設：
- **09:00**（現貨開盤）：多空角力最激烈，假突破可能較多
- **09:05 / 09:10**：程式單集中發動時段
- ORBLong 的 09:30–11:00 窗口中，早期 vs 晚期突破可能有差異

## 分析方法

### 資料來源
- backtesting.py 的 `_trades["EntryTime"]` 已記錄精確進場時間戳，直接提取即可
- 不需修改任何策略程式碼

### 進場時間提取
```python
trades["EntryTime"] = pd.to_datetime(trades["EntryTime"])
trades["entry_minute"] = trades["EntryTime"].dt.strftime("%H:%M")
trades["win"] = (trades["PnL"] > 0).astype(int)
```

### 五段分析

1. **逐分鐘統計**（全期）— 每個進場分鐘的筆數、勝率、均損益、總損益、PF
2. **5 分鐘桶統計** — 合併為 5 分鐘區間提高統計顯著性
   - EstHL: 08:55–09:15 區間
   - ORBLong: 09:30–11:00 區間
3. **關鍵時段對比**
   - EstHL: 09:00 前 vs 09:00 vs 09:01 後
   - ORBLong: 早期(09:31-09:45) vs 中期(09:46-10:15) vs 晚期(10:16-11:00)
4. **年度穩定性** — 5 分鐘桶 × 年度的勝率交叉表
5. **進場時間分布直方圖**（ASCII）

### 注意事項
- EstHL 全期約 161 筆、ORBLong 約 325 筆，逐分鐘可能樣本不足
- 以 5 分鐘桶為主要判斷依據
- 年度穩定性檢查作為 out-of-sample 驗證

## 實作

| 檔案 | 用途 |
|------|------|
| `specs/strategies/2026-03-16-breakout-timing.md` | 本規格文件 |
| `src/backtest/explore_breakout_timing.py` | 分析腳本 |

## 驗證

```bash
uv run python src/backtest/explore_breakout_timing.py --strategy esthl
uv run python src/backtest/explore_breakout_timing.py --strategy orblong
```

確認輸出表格完整、交易筆數加總與已知一致。
