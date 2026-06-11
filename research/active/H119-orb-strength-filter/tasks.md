# Tasks: 早盤期貨延伸強度當 ORB 突破的方向濾網

## Phase 1: Distribution Research

- [ ] **定義 ORB 多方突破事件**（沿用 src/strategies/orb.py）
  - OR 窗口：08:45 → OR_end（測 09:00 與 09:30 兩版）
  - 多突破 = OR_end 後價格首次站上 OR_high；記突破時點、突破價
  - 假突破定義：突破後（a）跌回 OR_high 內 / (b) 反向碰初始 SL / (c) 未達 L3 即收盤
- [ ] **對齊期貨強度閘**：OR_end 時刻的 CDF/NYF open-anchor 延伸（≤突破時點，無 look-ahead）
- [ ] **forward 結果**（嚴格取突破之後）：續走到 L3/L4 達成率、是否假突破
- [ ] **分組對照**（核心）：
  - 高強度（≥θ：測 0.10/0.16/0.20）vs 低強度 vs 全部（無濾網）
  - 各組：N、續走 L3 率、續走 L4 率、假突破率、（零成本）平均 forward 損益%
- [ ] **forward-tautology guard**：洗牌虛無；確認分離非自我關聯
- [ ] **跨 regime**：CDF 逐年（2021–26）分組分離是否穩定
- [ ] 視覺化：續走率/假突破率 by 強度分組、by OR_end 版本

---
### GATE
**問題：分佈結果是否支持進入回測？**

- 樣本數：ORB 多突破日 N ≥ ~150（CDF 全史應足）。
- 高強度組 vs 低強度/無濾網：續走 L3/L4 率**顯著較高**、假突破率**顯著較低**。
- 改善是**增量於既有 ORB**（非重述 H118 單訊號）。
- 無 forward tautology / data snooping；跨 regime 不是單年假象。

**決定：** [x] **繼續 Phase 2**（2026-06-11；分離大、跨 regime 6/6、增量於 ORB）　[ ] Archive　[ ] 修改

---

## Phase 2: Backtest
（過 GATE 後定義）

- [ ] 進出場：既有 ORB 規則 + 強度閘（≥θ 才放行多突破）；SL/TP 沿用 orb.py
- [ ] 對照回測：**有濾網 ORB vs 無濾網 ORB**（同期、同 OR/SL/TP 參數）
- [ ] in-sample / out-of-sample（CDF 2021–24 IS / 2025–26 OOS）
- [ ] walk-forward 逐年；θ 與 OR_end 敏感度
- [ ] 成本敏感度；績效用損益%、Sharpe、勝率、maxDD、連敗長度
