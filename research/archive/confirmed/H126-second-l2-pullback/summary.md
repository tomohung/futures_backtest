# Archive: 同向第二次 L2 拉回續攻

## Status
Confirmed（含 caveats）

## Summary
同一交易日、同方向出現第 2 次（含以上）causal L2 拉回續攻 setup（`2nd+`）、且 entry∈[09:30,11:30] 時，
其續航顯著優於第一次，可瞄更遠的 L4/L5/trail。回測證實此「序數條件」從 H120 的 break-even 母體切出正 EV
子集，回撤/連敗大幅改善。源於 2026-06-24 盤面觀察。

## Key Evidence
（2nd+∈[09:30,11:30] N=120｜IS 80 / OOS 40；alpha=1.0 錨點寬停；cost=3pt；績效用損益%）
- **序數增量**：2nd+（L4 目標）tot +11.2% / Sharpe 0.16 / maxDD −3.1% / 連敗 7；
  1st 對照（=母體）tot −1.0% / Sharpe ~0 / maxDD −16.4% / 連敗 10。
- **瞄更遠成立**：L4/trail 的 EV/avgR 為 L3 的 2–3×（trail0.5 IS Sharpe 0.231）。
- **OOS 站得住**：L4/L5/trail OOS Sharpe 0.15–0.20 ≈ IS；只有最保守 L3 OOS 崩（0.028）。
- **每年皆正**：target=L4 下 2021–2026 六年 EV 全正，無虧損年。
- **穩健**：成本到 6pt 仍正；11:30 cutoff 最佳（>12:00 稀釋、全日崩）；alpha 單調，寬停最佳。

## Why Confirmed
H127 已先證「序數本身」是乾淨因果訊號（非前置延伸/時間/趨勢日 selection 假象）。Phase 2 回測再證該訊號
在真實停損+成本下切出正 EV、回撤連敗顯著優於母體，且參數優化（alpha,target）後 OOS 驗證通過、逐年皆正。
邏輯與統計兩面一致 → Confirmed。

## Caveats
- N 薄（120 / OOS 40 / 每年 14–28）；每筆 Sharpe「真實但溫和」(0.15–0.23)。
- 深目標 OOS 偏強部分與高波 regime confounded（`project_oos_equals_highvol_regime`：OOS≡高波）。
- alpha=1.0 寬停 → 單筆風險點數大（高波年 EV 大、損益% 持平）。

## Derived Hypotheses
- **H128**：2nd+ 專屬更寬停損（停在第一次極值外）的賠率曲線（alpha=1.0 最佳已是線索）。
- **H129**：序數 dose-response（3rd>2nd？逐次 EV 遞增則加碼第 3+ 次）。

## Deployment
- chart-ui：在**既有 l2_pullback 指標上加序數標示**（2nd+ 高亮），重用 detect_day 單一真相源（詳見對話結論）。
- 可選晉升 strategies/live/SXXX（如要，複製 backtest.py 過去）。

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md（+ entries.csv, ordinal_excursion.png）
- Backtest：results/backtest.md（+ bt_trades.csv, equity_curve.png）
- Scripts：explore.py, backtest.py
- 相關：H127（rejected，driver 歸因確認序數乾淨）、H120（rejected，母體 break-even）
