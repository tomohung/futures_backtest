# Archive: ORB + EstHL 出場策略（ORBWithEstHLExitStrategy）

## Status
Confirmed

## Summary
結合 ORB 進場（08:45-08:57 OR、08:58-09:15 進場窗口）與 EstHL SatZone 兩段式出場，加入 BigCost 大戶成本濾網、30 分 K 20MA 方向濾網、Dow Theory 追蹤停損。Long-only，跳過週四/五。2021-2026 全期 162 筆交易，總損益 +4,674 點，PF 2.42，Sharpe 5.12，每年都正。

## Key Evidence
- 全期：162 筆，WR 58.6%，PF 2.42，EV +28.9 pts，Sharpe 5.12，MaxDD -0.2%
- 年度：2021 +508、2022 +653、2023 +359、2024 +1,072、2025 +1,411、2026 YTD +671
- SL 倍數 0.25 三時段（2021-24/2025/2026）均穩定，無偏科
- BigCost 2 日最佳（PF 1.50、EV +16.7）
- OR 長度 8:45-8:57（13 bars）越長越好
- Entry_end 9:15 + EmaHL bfill 最佳（+3,720 vs 舊版 +2,857）
- 星期濾網：skip Thu+Fri 後 WR 63.4%、PF 2.53（原 55.7%/1.73）
- EstRange EMA 替換舊版 EmaHL：+4,674 vs +4,240（+10% 改善）

## Why Confirmed
策略在 6 年回測中每年正損益，Sharpe 5.12 為所有策略最高。進場濾網（BigCost、OR 寬度、趨勢 MA、星期效應）和出場機制（SatZone + Dow Trail）都經過系統性測試，參數穩健無過擬合跡象。已成為實盤策略之一。

## Derived Hypotheses
- H003: OR% 濾網（ORBLong 專用）
- H004: EstHL + ORBLong 組合配置
- Direction A（EstHL 進場 + ORBLong 出場混合策略）

## Links
- Proposal: specs/strategies/2026-03-09-orb-with-est-high-low-exit.md
