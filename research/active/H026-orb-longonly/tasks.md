# Tasks: ORB Long-Only 做多專注策略

## Phase 1: Distribution Research

- [x] Phase 6 Step 0 探索：機制濾網（ADX/ATR%/RealVol）與 ORB 勝率相關性分析
- [x] 確認機制濾網方向放棄（|r| < 0.13）
- [x] 做多 vs 雙向 Ph4 Hybrid 年度比較
- [x] ADX 做多四分位分層分析

---
### GATE
**問題：分佈結果是否支持進入回測？**
**決定：** 通過。ADX 高（>25）對應更好的做多表現（Q4 win% 57%, exp +29.9），且用戶決策聚焦做多。進入回測。

---

## Phase 2: Backtest

- [x] Step 1：`ORBPhase4HybridStrategy` 加入 `long_only=True`
- [x] Step 2：做多 Grid 優化（tp_or_multiplier x sl_pct，24 組）
- [x] Step 3：加入 `long_adx_min` / `adx_period` 參數
- [x] Step 4：`runner.py` 計算日線 ADX 並對齊至 1 分線
- [x] Step 5：ADX 濾網 Grid 測試
- [x] Step 6：加入 `summary_all.py`
- [x] 最終結果：`ORBLongStrategy` 為現行最佳做多策略
