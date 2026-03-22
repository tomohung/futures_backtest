# EstHL Latch + 新高確認策略

## 背景與動機

現行 EstHL 策略（`ORBWithEstHLExitStrategy`）在 OR 突破 + 所有 filter 通過時立即進場。
但部分假突破場景中，價格短暫突破 OR high 後隨即回落，造成停損。

**核心假設**：如果突破是真的，價格應該會持續創新高。用 EstHL 條件作為 latch（武裝信號），等後續出現新的 session high 才真正進場，可過濾假突破、提升勝率。

## 兩種確認模式

### Mode 0：任意 bar 新高（any_bar）

- Latch 武裝後，任何後續 1 分 K 的 High > 武裝時的 session high → 進場
- 反應快，但可能被瞬間突刺騙進

### Mode 1：5 分 K 收盤新高（5min_close）

- Latch 武裝後，等下一根 5 分 K 收盤
- 該 5 分 K 的最高價 > 武裝時的 session high → 進場
- 較保守，過濾瞬間突刺，但進場價可能稍差（延遲最多 ~5 分鐘）

## 策略設計

### 參數

| 參數 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `confirm_mode` | int | 0 | 0=any_bar, 1=5min_close |
| `latch_entry_end_min` | int | 630 | 確認截止時間（10:30），超過放棄 |
| 其餘 | — | — | 同 ORBWithEstHLExitStrategy |

### 進場邏輯

```
每根 bar:
  1. 更新 session_high = max(session_high, High)  ← 從 8:45 開始

  2. Latch 武裝階段（8:58–9:15，同原本 entry window）：
     - Close > or_high AND 所有 filter 通過
     - → latch_armed = True
     - → 記錄 session_high_at_latch（當時的 session high）
     - → 記錄 latch_sl_dist = sl_ema_fraction × EmaHL
     - 不進場

  3. 確認階段（latch_armed AND not entered AND cur_time ≤ 10:30）：
     Mode 0:
       - High > session_high_at_latch → 進場
     Mode 1:
       - 追蹤 5 分 K running high（每根 bar 更新）
       - 在 5 分 K slot 切換時（= 上一根 5 分 K 收完）：
         若 5min_candle_high > session_high_at_latch → 進場
         否則 reset 5min_candle_high，繼續等

  4. 進場執行：
     - buy(size=1)
     - sl_price = entry_close - latch_sl_dist
     - entered = True
```

### 出場邏輯（完全同現有 EstHL）

1. Fixed SL：entry - sl_ema_fraction × EmaHL
2. SatZone 兩階段（Phase 1 觸碰 + Phase 2 跌破 5MA）
3. Dow Theory trailing stop（9:45 後啟動）
4. 13:30 強制平倉

### 5 分 K slot 定義

- slot = `(hour × 60 + minute) // 5 × 5`
- 例：8:45→525, 8:50→530, 8:55→535, 9:00→540
- slot 切換 = 新 bar 的 slot ≠ 前一根 bar 的 slot → 前一根 5 分 K 收盤

### SL 錨定

- `sl_dist` 在 latch 武裝時計算（用當時的 EmaHL）
- `sl_price` 基於進場價（entry_close - sl_dist），非武裝時的 close

## 回測結果（2021-01-01 ~ 2026-03-19）

### 總覽比較

| 指標 | 基準 EstHL | Mode 0 (any_bar) | Mode 1 (5min_close) |
|------|-----------|-------------------|---------------------|
| 交易次數 | 161 | 155 | 153 |
| 勝率 | 58.4% | 58.7% | 56.9% |
| 平均獲利 | +87 pts | +82 pts | +80 pts |
| 平均虧損 | -53 pts | -52 pts | -49 pts |
| PF | 2.35 | 2.30 | 2.13 |
| EV | +29.1 pts | +27.2 pts | +24.0 pts |
| 總損益 | ~4,686 pts | ~4,216 pts | ~3,672 pts |

### 交易重疊分析（Mode 0 vs 基準）

| 項目 | 數據 |
|------|------|
| 重疊率 | 100%（Latch 的 155 筆全部在基準 161 筆裡） |
| Latch 獨有交易 | 0 筆 |
| 基準獨有交易 | 6 筆（全虧，avg -68.5 pts，total -411 pts） |
| 平均進場延遲 | 2.8 分鐘（92% 在 1-5 分鐘內） |
| 進場價差 | Latch 平均貴 5 點 |
| 重疊交易 PnL 差 | 32.9 → 27.2（-5.7 pts ≈ 進場價差） |

## 結論：❌ Latch 不適合作為加碼點

1. **Latch 沒有產生新的交易信號**：155 筆 latch 交易是基準 161 筆的完全子集，沒有獨立的加碼機會
2. **延遲進場只是墊高成本**：平均晚 2.8 分鐘、貴 5 點，EV 下降幾乎等於進場價差
3. **過濾效果有限**：只過濾 6 筆全虧交易（-411 pts），但不穩定
4. **作為「加碼點」無意義**：既然是同一筆交易只是晚進場，不如在基準點直接部位壓滿

### 啟示

ORB 突破後的「新高確認」不具備獨立的 alpha，因為 92% 的交易在 1-5 分鐘內就會創新高——這本來就是突破動能的一部分。若要找加碼點，應尋找**時間或邏輯上獨立的信號**，例如回踩不破、盤中二次突破等。

## 相關檔案

- `src/strategies/orb_est_hl_latch.py` — 策略實作
- `src/backtest/run_orb_est_hl_latch.py` — runner script
