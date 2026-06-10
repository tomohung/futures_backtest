# Archive: VIX regime 當 ladder 出場期望調節器

## Status
Confirmed（描述性：VIX regime 為 ladder 期望/回撤的因果、多 regime 驗證 context）
＋ 機械 target 切換規則否決（同 H114 結構）

## Summary
VIX regime（昨日 VIX vs MA20,因果/盤前可判）對 ladder L3/L4/L5 達成的調節:升壓段深關卡 reach ~2× 降壓段,
且抱尾的**回撤風險反直覺地在升壓(非降壓)**。作為看盤期望 + 回撤紀律 context 成立(已上線 morning briefing);
但作為「機械 target 切換出場規則」OOS 不贏固定出場,不晉升 live。

## Key Evidence
- 觸及率（因果 VIX lag,N=1296,2021-2026 含 2022 熊）：升壓 多L4 30%/L5 16%、降壓 19%/7%（深 reach ~2×;L1/L2 regime 不敏感,效應沿關卡加深放大,L5 2.3×）。
- 轉換鏈 P(下|本) L4→L5：多 升51%/降36%、空 升59%/降52% → 空方深尾肥於多方,降壓尤甚。
- ★ 回撤拆解（反直覺）：抱滿尾 maxDD 升壓 **−9.08** vs 降壓 **−3.61**;升壓抱尾 Sharpe 無增益、降壓抱尾/blend Sharpe 0.06 最佳。
- 半半 blend（L4 trim 一半 + 餘量 trail）兩 regime 最穩 → 驗證 journal_checklist 現行做法。
- 方向：因果上多空近對稱（同期「升偏空」是 VIX(D) look-ahead 假象,lag 後消失,多−空L4≈0）。

## Why Confirmed（描述性）
假設核心是「VIX regime 調節 ladder 期望」這個結構,而它**因果、多 regime(含熊市)、N=1296 驗證且已上線**。
同 H114：描述性發現 Confirmed,作為 context/期望工具（非 live 機械策略,不進 strategies/live/）。

## 不成立的部分
機械規則「regime-conditioned target 切換（升壓 L5/降壓 L4）優於固定出場」**OOS 否決**（輸固定 L5,Invalidation #1）;
EV 上抱尾兩 regime 皆微幅最佳（賠付不對稱）,差別在變異 → regime 用法收斂為「微調 trim 比例 + 看盤期望」,非切 target。

## Derived Hypotheses / 落地
- 已寫入 `src/analysis/vix_regime.py`（因果 regime + 期望/回撤動作查表）→ key_prices → morning briefing 剪貼簿。
- checklist 用法：升壓多 trim 控回撤、降壓少 trim 可抱;空方深尾(降壓仍 52%)可抱、多方降壓(36%)多 trim。
- 記憶：[[project_vix_regime_ladder_causal]]、[[project_drawdown_risk_in_highvol_not_low]]、[[project_ladder_reach_timing_map]]。
- checklist 真正待修非 regime 而是 DCI 軸（OOS 不穩,H111）;regime 與碰觸時點(H114)才是站得住的 context 軸。

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md（觸及率/轉換鏈/多空/regime,因果）
- Backtest：results/backtest.md（Phase 2 regime 出場 + 回撤拆解 + verdict）
- 腳本：explore.py、h117_transition_path.py、backtest.py
</content>
