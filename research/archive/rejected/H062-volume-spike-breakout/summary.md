# Archive: Volume Spike Breakout

## Status
Rejected

## Summary
9:10 後出現凸量 K（過去 20 根均量 × 3 倍），後續 K 收盤突破高/低點進場，目標價為凸量 K 振幅、RR=1:1。在修正進場價為「突破 K 的收盤價」後，所有時段、倍數、濾網組合都無法覆蓋 2 點手續費成本。

## Key Evidence

**V1 錯誤假設（entry = 凸量 K 高/低點）**：
- Sharpe 2.21、每年正獲利、OOS 優於 IS
- 但此結果是 bug：等於「免費」拿到突破 K 收盤與凸量 K 高/低點的價差

**V2 修正後（entry = 突破 K 收盤價）**：
- IS (2021-2023): N=3,698 WR=49.0% PF=0.74 Avg=**-2.4 點** Total=-8,691
- OOS (2024-2026): N=2,965 WR=49.2% PF=0.86 Avg=**-1.9 點** Total=-5,687
- **每年都虧損**（2021-2026）

**深度救援測試（均無效）**：
- 時段切分（早盤最佳 Avg=-0.9）
- 最低振幅 ≥ 20/30 點
- 固定點數目標（10~100）
- TP/SL 倍率（0.5x~1.5x 共 25 組，含 R:R=2:1）
- KD 同向動能濾網 + KD 極值反濾網（>80 不做多、<20 不做空）
- 凸量 K 方向濾網（candle / RS_05/06/07）
- MA65 趨勢濾網（含夜盤連續計算）
- 凸量可重用（反向突破也進場）
- Weekday 過濾

最接近正的組合：早盤+min30pts+max2，Avg=+0.4 點（滑價就吃掉）。
R:R=2:1 + max_sig=1 組合 OOS 看似轉正（+1.0），但 IS 仍負、年度不穩（2021-2024 全虧，2025-2026 才正），判斷為運氣而非 edge。

## Why Rejected

**進場時機的結構性矛盾**：
- **掛單凸量 K 高/低點**：假突破過多，WR 僅 31%
- **收盤確認進場**：收盤價已超過凸量 K 高/低點一段，目標空間不夠覆蓋成本

凸量 K 本身是大資金行動的結果，後續突破收盤價很可能已「內含」那段波動。

## Key Lesson

**進場價的假設非常重要**。V1 的 bug 讓策略看起來 Sharpe 2.2、年年正獲利，修正後直接翻轉成年年虧損。未來任何策略必須：
1. 明確定義進場機制（限價 / 市價 / 收盤確認）
2. 驗證進場價在實盤可執行
3. 檢查進場價是否無意間「吃掉」了策略的 edge

## Derived Hypotheses

（均已在 Phase 2 深度探索中驗證無效，不建議開新假設）

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- Backtest：results/backtest.md
- 探索腳本：explore.py、explore_v2.py、explore_v3.py、explore_v4.py
- 回測腳本：backtest.py
