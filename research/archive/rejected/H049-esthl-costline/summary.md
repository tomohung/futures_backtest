# Archive: EstHL Costline — VWAP 突破進場

## Status
Rejected

## Summary
嘗試將實盤中「開盤區間突破成本線」的 21 筆交易（71.4% WR, PF 7.39）量化為機械式策略。核心概念：用前日 VWAP 位置判斷日盤方向，在 OR 範圍內整理後進場。歷史掃描證實前日 VWAP gap 方向對日盤走勢完全沒有預測力（48% ≈ 擲硬幣），機械式規則的各種組合均無 edge。

## Key Evidence
- 全市場 VWAP gap 方向預測力：48.0%（N=1,260 交易日），等同隨機
- 機械掃描所有規則組合：WR 48-50%, PF 1.0, MFE/MAE 1.0
- 實盤 21 筆的 86% 方向一致率是主觀篩選的結果，非 VWAP 本身的預測力
- 加入 gap 門檻、OR 寬度限制、整理收斂度等篩選條件均無法改善結果

## Why Rejected
前日 VWAP 作為方向信號沒有統計 edge。實盤��優異表現來自交易者的主觀盤面判斷與 EstHL 出場框架，無法歸因於 VWAP 位置這個單一因子。Costline 交易的 edge 本質上是主觀的、不可機械化的。

## Derived Hypotheses
- H056（已建）：Night Session 30m MACD + SMA Regime Classification — 用夜盤技術指標做日盤方向 filter
- HXXX：VWAP as Direction Filter for EstHL — 僅在 VWAP 同側做 OR 突破（作為濾網而非獨立策略）

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- Explore script：explore.py
