# Performance Log: L2 拉回續攻 (S005)

> ## ⛔ RETIRED 2026-06-15 — 前視偏誤，績效作廢
> 下表所有數字**無效**。回測（backtest.py）用 ZigZag leg 終點 `em` 當進場搜尋上界，
> 而 `em` 是反轉後才確認的**未來資訊**，系統性濾掉失敗站回。
> 完全 causal 重寫後：**Sharpe 0.48→0.04、總損益% 108→16、勝率 79→62%**，逐年接近 break-even。
> 試過深度/離峰/空間濾網、只做多空、按星期、單部位約束皆無法救回。
> 驗證：`research/archive/rejected/H120-l2-pullback-continuation/results/causal_validation.md`。
> Pine 指標（`indicators/tradingview/swing_levels_tx.pine`）與 chart-ui h120 圖層**保留**作行情參考。

## Backtest Summary（⚠️ 以下為作廢的前視偏誤數字，僅留存對照）（部署版：trigger A, alpha=0.75, ≤12:00, 拉回深度≥0.25, mode=L3, cost=3pt, 固定1倉）
2021-01 ~ 2026-06。績效用損益%（pnl點數/進場價×100）；Sharpe=每筆 mean/std。

| Metric | In-Sample (<2025) | Out-of-Sample (≥2025) |
|---|---|---|
| # Trades | 546 | 246 |
| Win Rate (target命中) | 76.7% | 85.0% |
| EV / trade (pt) | 20.0 | 60.6 |
| 總損益% | 60.8% | 48.1% |
| Sharpe (per-trade) | 0.399 | 0.681 |
| Max Drawdown (損益%) | −2.3% | −1.1% |
| Max Loss Streak | 4 | 2 |
| avg R | 0.30 | 0.44 |

全樣本：N=792、勝率 79.3%、EV 32.6pt、總損益% 108.8%、Sharpe 0.484、maxDD −2.3%、avgR 0.35。
（未過濾深度的全量 ≤12:00 版本：N=1465、總損益% 135.5%、Sharpe 0.337；濾掉淺拉回後筆數 −46% 但 Sharpe/avgR 大升、總點數僅 −20%。）

## Annual Breakdown（部署版，固定1倉）
| Year | N | 勝率 | 總損益% | Sharpe | maxDD% | 連敗 |
|---|---|---|---|---|---|---|
| 2021 | 130 | 73.8% | 15.1 | 0.328 | −2.3 | 4 |
| 2022 | 133 | 76.7% | 15.4 | 0.452 | −1.1 | 2 |
| 2023 | 127 | 77.2% | 10.4 | 0.400 | −0.9 | 2 |
| 2024 | 156 | 78.8% | 19.9 | 0.461 | −1.6 | 3 |
| 2025 | 150 | 84.0% | 23.3 | 0.633 | −1.1 | 2 |
| 2026* | 96 | 86.5% | 24.8 | 0.778 | −1.0 | 2 |

逐年全正；OOS(≥2025) 不衰退反而更強（Sharpe 0.40→0.68）。*2026 至 06 月。
（加碼版會再放大深拉回部分的報酬與變異，此表為固定1倉的基準。）

## 驗證狀態
- 參數最佳化（停損 alpha）通過 OOS + walk-forward（alpha* 穩定收斂 0.75）。
- 對成本穩健（≤6pt 仍正）。
- 保留：OOS≡高波 regime（[[project_oos_equals_highvol_regime]]）；EV 點數受高指數/高波放大，但損益%/Sharpe/勝率同步走高、逐年穩定。深拉回桶樣本較小，加碼倍數封 2.5×。

## 變更紀錄
- 2026-06-14：由 H120 晉升 live。部署採 ≤12:00 + 拉回深度≥0.25 過濾、深度分級加碼。
