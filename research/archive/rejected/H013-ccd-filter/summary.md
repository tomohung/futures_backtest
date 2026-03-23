# Archive: CCD (Cumulative Candle Delta) 進場濾網

## Status
Rejected

## Summary
測試 OR 窗口內的累積 K 棒方向成交量（CCD）能否作為 EstHL 或 ORBLong 的進場濾網。假設 CCD > 0 代表多方成交量佔優，突破做多成功率應較高。結果顯示 CCD 正負號對勝率幾乎無預測力，且方向每年翻轉。

## Key Evidence
- CCD > 0 vs CCD < 0 勝率差異不到 3%（EstHL 1 分：59.6% vs 58.6%；ORBLong 1 分：52.9% vs 56.0%）
- 5 分鐘 K 棒更差：EstHL CCD < 0 的 WR 反而更高（64.8% vs 56.5%）
- 篩選代價極高：只保留 CCD > 0，EstHL 總損益從 +4,240 降至 +2,244（-47%）
- 年度穩定性：CCD 優勢方向每年翻轉（2023 正、2024 負、2025 負、2026 正），無穩定規律
- 分位數異常：EstHL Q2（輕度看空 CCD）表現最佳（WR 70%），CCD 極值反而是反向指標

## Why Rejected
CCD 正負號無預測力，方向每年不一致，且篩選代價高。K 棒方向的累積成交量在 OR 窗口這麼短的時間內無法區分真假突破。

## Derived Hypotheses
- 若要利用成交量訊息，應探索：進場 bar 本身成交量相對大小（vs 20MA）、OR 窗口內最大量 bar 方向、tick-level 主動買賣比

## Links
- Proposal: specs/strategies/2026-03-12-ccd-filter.md
