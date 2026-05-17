# Proposal: NVF Reach Multiples & Direction Asymmetry

## ID
H092

## Derived From
H070-night-vol-estrange-reach（Phase 1 distribution）

## Trading Intuition
H070 已經證明夜盤波動(NVF norm)對日盤 EstRange 觸及率有顯著解釋力(R²=0.097, 跨年 5/6 穩定),但只列了 `reach ≥ 0.618 / 1.0 / 1.2` 三格,且把「碰到 upper」與「碰到 lower」合併計算(`day_hl / EmaHL`)。

從 S001 EstHL 與 morning briefing 警示的實務需求看,有兩個未被回答的問題:

1. **0.75× 這個關鍵中段** — 0.618 與 1.0 之間落差 47pp(STOP 區間 77%→30%),`0.75` 是 S003/H019 等多策略使用的中段觸發位,缺數據。
2. **方向偏向** — STOP 天到底是「兩邊都觸不到」還是「單邊明顯較弱」?如果方向不對稱(例如 STOP 天較常觸 lower 不觸 upper),意味著夜盤萎縮日具有方向性 bias,對單向策略(EstHL long-only / S003 short-only)有不同含義。

此外,H070 的 NVF 計算為 SMA20(舊版),H075 已將 production 升級為 **EMA20 + expanding median**。需以新方法重算,才能用於現行策略決策。

## Hypothesis
在 EMA20 + expanding median NVF 方法下,2021-01 ~ 2026-05 樣本中:

- **H1 (0.75 中段)**:reach ≥ 0.75 的機率在 STOP 區間(norm < threshold)約落在 0.618 與 1.0 中間,且仍呈現單調隨 norm 提升的趨勢。
- **H2 (方向不對稱)**:STOP 天的 `reach_upper_X` 與 `reach_lower_X` 在至少一個 multiple(0.618 / 0.75 / 1.0 / 1.2)上呈現 ≥ 10pp 的差距,且方向跨年至少 4/6 一致。

## Expected Distribution
- 全樣本約 1,250+ 個交易日(H070 為 1,226;延伸到 2026-05 ≈ +20 天)
- 5 個 NVF 桶(< 0.70 / 0.70-0.85 / 0.85-1.00 / 1.00-1.30 / ≥ 1.30)× 4 個 multiple × {upper / lower / either} = 60 格機率
- 預期 STOP 桶(< 0.70)的 reach_upper / reach_lower 兩者皆低於全樣本,但是否對稱、跨年是否一致為未知
- 預期 0.75 reach 在 STOP 桶介於 45–60%(在 0.618=77% 與 1.0=30% 之間,但不等距)

## Invalidation Condition
- **H1 invalid**:0.75 reach 在 STOP 桶與 0.618 reach 或 1.0 reach 差距小於 5pp(代表 0.75 是冗餘訊息)
- **H2 invalid**:任一 multiple 上 upper/lower 差距 < 10pp,或方向跨年不一致(< 4/6)→ 視為 STOP 天無方向 bias,合併 reach 已足夠

## Notes
- 「upper / lower」定義:從 day_open(08:45 收盤價)起,`up_dist = day_high - day_open`,`dn_dist = day_open - day_low`;`reach_upper_X = up_dist >= X * EmaHL`,`reach_lower_X = dn_dist >= X * EmaHL`
- 此定義避開 SatZone 滾動更新的複雜性,純粹測「日內單邊 reach 能力」
- EmaHL 計算與 `src/strategies/estimate_hl_exit.py` 一致(EMA20 of day_session HL, shift 1)
- NVF threshold 與 `src/analysis/key_prices.py:_compute_night_vol_filter` 一致(EMA20 + expanding median + warmup 60 nights fallback 0.93)
- 不需要 Phase 2 backtest 觸發 — 此假設目的為描述性分析,Phase 2 與否取決於 GATE 是否揭露可操作的方向偏向
