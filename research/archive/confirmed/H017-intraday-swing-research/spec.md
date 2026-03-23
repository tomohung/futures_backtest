# 日內波段交易研究：波動預測與時段分析

## 背景與動機

現有策略（ORBLong、EstHL）都基於開盤區間突破，但對「日內波動何時發生、多大、如何分配」缺乏系統性的實證研究。EstHL 已有 EMA(20) 的日波幅預測，但它是「每日一個值」，無法回答更細緻的時段問題。

本研究目標：從頭檢視日內波動特性，為未來新策略設計提供數據基礎。不預設策略方向，先讓數據說話。

## 核心問題

1. 波動集中在哪些時段？
2. 當日高低點何時出現？
3. 進場後如何設定目標價與停損？
4. 固定風險下如何分配部位？
5. 當日波動已實現後，反向訊號還能做嗎？
6. 停損後再出現訊號還能進場嗎？
7. 手上有部位時，新訊號要加碼嗎？

## 產出

一個分析腳本 `src/analysis/intraday_swing_research.py`，輸出統計表格回答上述 7 個問題。

---

## 資料載入

從 DuckDB 直接查詢，載入兩組資料：

1. **df_bars**: 全部 1 分 K（08:45–13:45），加上 `date`、`time` 欄位
2. **df_daily**: 每日彙總（DuckDB SQL 預聚合）
   - `day_open`, `day_high`, `day_low`, `day_close`, `day_volume`, `day_range`
   - `high_time`, `low_time`（使用 `ARG_MAX(high, timestamp)::TIME`）
   - `day_range_pct = day_range / day_open * 100`

參考 `src/analysis/explore_volume_signal.py` 的 `load_day_session_bars()` 模式。

---

## Q1: 波動集中時段

**方法**: 每日每分鐘計算 cumulative range（running max high - running min low），以 30 分鐘為單位統計「邊際新增波幅」佔全日的百分比。

**輸出表格**:

| 時段 | 邊際波幅% (mean) | median | std | 累積波幅% |
|------|------------------|--------|-----|-----------|

附：逐年穩定性檢查。

## Q2: 當日高低點時間分佈

**方法**: 用 `df_daily` 的 `high_time` / `low_time`，以 30 分鐘為單位做次數統計。分三組：全部、上漲日、下跌日。另外統計「高點先出現 vs 低點先出現」的比例。

**輸出表格**:

| 時段 | 高點次數 | 高點% | 低點次數 | 低點% |

附：上漲日/下跌日分開、高低點先後順序、逐年檢查。

## Q3: 進場後的目標價設定（剩餘波幅分析）

**方法**: 在每個 30 分鐘 checkpoint，計算：
- `已用波幅 = max_high_so_far - min_low_so_far`
- `剩餘上行 = day_high - max_high_so_far`
- `剩餘下行 = min_low_so_far - day_low`
- 條件分析：若低點已經出現（`low_time < checkpoint`），剩餘上行有多大？

全部以 `% of day_open` 標準化。

**輸出表格**:

| Checkpoint | P(低點已出現) | 條件剩餘上行% (mean/p25/p75) | 條件剩餘下行% |

## Q4: 固定風險下的部位分配（MAE 分析）

**方法**: 在每個 30 分鐘 checkpoint 假設做多，計算 Maximum Adverse Excursion (MAE) = `entry_close - min_low_after_entry`。這代表「進場後最大逆向波動」。

**輸出表格**:

| Entry Time | MAE mean | MAE p50 | MAE p75 | MAE p95 | 建議 SL (p75) |

附：以 `pts / entry_price * 100` 標準化、逐年檢查。

## Q5: 目標價到達後的反向訊號

**方法**: 使用 `estimate_hl.py` 的 `compute_estimate_hl_zones()` 取得每日 EstHL。計算每分鐘 `consumed_pct = running_range / EstHL * 100`。當 consumed >= 100% 後，測量剩餘時間的價格變動。

區分「上行消耗」（high 到達 EstHighLevel）vs「下行消耗」。

**輸出表格**:

| Consumed 門檻 | 觸發天數 | 觸發後平均時間 | 觸發後 avg move to close | 反轉率 |

## Q6: 停損後的再進場

**方法**: 在 09:00 模擬做多進場，設 3 種 SL（0.3%、0.5%、0.7%）。若觸發停損，測量：
- 停損後收盤方向（回升 or 繼續跌）
- 停損後最大回升幅度
- 若 10:00 前停損 vs 10:00 後停損，結果差異

**輸出表格**:

| SL 幅度 | 停損次數 | 停損後回升率 | 停損後 avg move to close | 早盤停損 vs 午盤停損 |

## Q7: 加碼分析

**方法**: 追蹤每日「新高事件」序列。定義：日盤中每次創新的 running high 為一次新高事件（需超過前高至少 1 點，避免噪音）。以 30 分鐘為單位，統計：
- 每個時段的新高事件頻率
- 第 N 次新高後的邊際上行空間
- 新高事件間的平均間隔

**輸出表格**:

| 第 N 次新高 | 出現機率 | 邊際上行(pts) | 邊際上行% | 距前次間隔(分鐘) |

---

## 關鍵檔案

| 檔案 | 用途 |
|------|------|
| `src/analysis/intraday_swing_research.py` | **新建** — 主分析腳本 |
| `src/analysis/explore_volume_signal.py` | 參考 — 資料載入模式、輸出格式 |
| `src/backtest/estimate_hl.py` | 重用 — `compute_estimate_hl_zones()` 用於 Q5 |
| `src/backtest/runner.py` | 參考 — 可能用 `load_data_with_night_ma(estimate_hl=True)` |

## 執行

```bash
uv run python src/analysis/intraday_swing_research.py
```

可加 `--question N` 參數只跑特定問題（方便開發迭代）。

## 驗證

1. 資料載入後確認交易日數 ~1248、每日 bar 數 301
2. Q1 的累積波幅% 最終應收斂至 100%
3. Q2 的高低點分佈應合計 100%
4. Q5 的 EstHL 值應與 `estimate_hl.debug_day()` 交叉驗證
5. 所有百分比標準化值應在合理範圍（0.1%–3%）

## 實作順序

1. 資料載入函式（`load_minute_bars()`, `load_daily_summary()`）
2. Q1 + Q2（純統計，最簡單，驗證資料正確性）
3. Q3 + Q4（需逐日逐分鐘迭代，邏輯相似可一起做）
4. Q5（需整合 EstHL，獨立性高）
5. Q6 + Q7（模擬交易行為，最複雜）
