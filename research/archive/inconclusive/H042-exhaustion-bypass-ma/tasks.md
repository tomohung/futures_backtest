# Tasks: Exhaustion Bypass MA Direction

## Phase 1: Distribution Research（已完成，假設轉向）

- [x] 計算歷史所有交易日的 30 分 K BB(20, open) %B 值
- [x] 統計 BB%B > 1 或 < 0 的出現頻率與分佈
- [x] 在 BB%B 極端日中，找出被 MA 方向濾網擋掉的 Reversal setup
- [x] 分析這些被擋交易的 MFE / MAE 分佈（假設進場後的表現）
- [x] 對比：BB%B 極端 vs 正常區間的 Reversal 交易績效差異
- [x] **轉向**：BB%B 極端與 MA blocking 交叉僅 4 筆，改用 Exhaustion 作為 bypass 條件
- [x] 分析 46 筆被擋交易按 block type / exhaustion / BC zone 的績效差異

---
### GATE
**結果：修改假設後進入 Phase 2**

BB%B 極端不可行（交叉樣本僅 4 筆）。Exhaustion 是更有效的 bypass 篩選（N=36, WR 55.6% vs N=10, WR 40%）。假設轉向為「Exhaustion bypass MA」，Phase 1 數據支持進入 Phase 2。

---

## Phase 2: Backtest

- [x] 在 Reversal 策略中加入 exhaustion bypass MA 邏輯
- [x] 設定回測參數（手續費 0、滑價 0，沿用 Reversal baseline）
- [x] 執行 in-sample 回測（2021–2024）
- [x] 執行 out-of-sample 驗證（2025–2026）
- [x] 與原始 Reversal 策略對比（加入 bypass 前後差異）
- [x] Delta 分析：49 筆 extra trades，WR 36.7%
- [x] 回頭比對 H044 live-only 清單：12 筆 DIR_BLOCKED，捕捉率 33%（4/12）
