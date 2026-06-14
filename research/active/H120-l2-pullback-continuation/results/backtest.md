# Backtest Results: L2 趨勢確立後拉回續攻（trigger A 5MA 站回）

## Date
2026-06-14

## Parameters
- **進場**：L2 門檻 ZigZag 偵測 leg → ext 達 L2d 確立方向 → 第一個 ≥0.05×EMA20 拉回 → **拉回後 1 分 K 收盤站回 5MA（trigger A）**進場（每 leg 一筆）。已直衝 L3 才首次拉回的 leg 不交易。
- **停損**：`stop = pb_low − alpha×(pb_low − anchor)`，**alpha=0.75**（偏趨勢起點的寬結構停損；IS/WF 最佳且穩定）。
- **出場**：mode=L3（錨±L3d 固定停利）為基準；**trail 0.5**（達 L3 後改 trail 0.5×L3d 博 L4/L5）為抱尾變體。
- **時間窗**：起點 ≤ 11:30（與 swing_legs 一致）。
- **成本**：每筆 round-trip 3pt（baseline）。
- **資料**：TX 日盤 1 分 K，2021-01 ~ 2026-06。IS=<2025、OOS=≥2025。
- 績效：損益% = pnl點數 / 進場價 × 100；Sharpe 為**每筆** mean/std；maxDD/連敗以損益%累計。

## Results

| Metric | In-Sample (<2025) | Out-of-Sample (≥2025) |
|---|---|---|
| # Trades | 1052 | 413 |
| Win Rate | 70.6% | 74.8% |
| EV / trade (pt) | 11.1 | 32.8 |
| 總損益% | 64.6% | 43.6% |
| Sharpe (per-trade) | 0.235 | 0.331 |
| Max Drawdown (損益%) | −2.0% | −2.1% |
| Max Loss Streak | 5 | 4 |
| avg R | 0.18 | 0.26 |

（出場改 trail 0.5：IS 總損益% 103.4%、Sharpe 0.236、勝率 54%、maxDD −2.9%。）

## Walk-Forward Summary
每個 test 年用「該年之前所有資料」選 alpha（by Sharpe），alpha* 穩定收斂於 **0.75**（僅 2022 選 0.5）。逐年 test 結果**全部為正**：

| 年 | N | 勝率 | 總損益% | Sharpe | maxDD% | 連敗 |
|---|---|---|---|---|---|---|
| 2021 | 243 | 66.7% | 12.9 | 0.167 | −2.0 | 5 |
| 2022 | 270 | 67.0% | 15.1 | 0.224 | −1.4 | 4 |
| 2023 | 259 | 70.7% | 10.9 | 0.220 | −1.2 | 4 |
| 2024 | 280 | 73.2% | 22.1 | 0.297 | −1.1 | 3 |
| 2025 | 263 | 74.1% | 21.2 | 0.292 | −2.1 | 4 |
| 2026* | 150 | 76.0% | 22.4 | 0.394 | −1.9 | 3 |

WF 拼接：N=1222、勝率 71.8%、總損益% 91.7%、Sharpe 0.278、maxDD −2.1%、最大連敗 4。
（*2026 僅至 06 月）

## Parameter Sensitivity
- **停損 alpha（穩健、單向）**：緊停（alpha=0）Sharpe 0.023、連敗 17（不可用）；隨 alpha↑ 單調改善至 0.75（Sharpe 0.231）後 1.0 略降。最佳區間 0.75~1.0，**寬結構停損為硬結論**。
- **成本（穩健）**：cost 0→6pt，Sharpe 0.302→0.168，**到 6pt 仍正**；baseline 3pt Sharpe 0.235。
- **時間窗（不敏感）**：≤09:30 / 09:30–11:30 / >11:30 三桶 Sharpe 0.195~0.254 皆正；早盤 win% 略高但寬停損後差異收斂。≤11:30 為合理選擇。
- **出場（風格選擇，非優劣）**：L3 固定 vs trail 0.5 Sharpe 持平（0.235 vs 0.236），trail 總損益% ×1.6（博尾），代價是 win% 70%→54%、maxDD 略增。

## Verdict
[x] Confirmed　[ ] Rejected　[ ] Inconclusive

> 建議 Confirmed。依據：①IS/OOS 一致且 OOS 不衰退（Sharpe 0.235→0.331）；②逐年與 walk-forward **全部為正**，alpha* 穩定收斂；③對成本穩健（≤6pt 正）；④maxDD 僅 −2%、最大連敗 ≤5（心理資本可承受）；⑤參數最佳化後通過 OOS + walk-forward。無 proposal 任一無效條件成立（樣本足、條件勝率 >> base rate、R:R 正）。
>
> 誠實保留：OOS 期 EV 點數（32.8pt）受高波/高指數放大，但**損益% 與 Sharpe 同步走高**證明非純點數效應；逐年損益% 穩定。per-trade Sharpe 數值看似中等（0.235），因每筆報酬小、筆數多（~260/年），年化解讀需保守，故以「逐年全正 + 低回撤」作為主要證據而非年化 Sharpe。

## Derived Hypotheses
- H120b（抱尾，已部分驗證）：trail 0.5 把總損益% 拉到 1.6×、Sharpe 持平 → 值得獨立做分批出（拿 L3 一部分 + 餘量 trail 博 L4/L5），對照 [[feedback_trail_giveback_is_scaleout_cost]]。
- H120c：拉回深度 / 站回時 5MA 斜率作為濾網，篩掉弱續攻（`setups.csv` 已有 pb_depth）。
- H120d：regime 分層——升壓 regime 是否該收緊抱尾（[[project_drawdown_risk_in_highvol_not_low]]：回撤風險在升壓）。
- H120e：晉升 live 後，與既有 EstHL / Reversal 的相關性與資金配置（[[user_trading_focus]]）。
