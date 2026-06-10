# Archive: 碰觸時點分辨 ladder 續攻（ext_long 為晚碰修正）

## Status
Confirmed（描述性：碰觸時點為 ladder 續攻 robust separator）

## Summary
原問「碰到 L_k 當下的即時 ext_long 能否分辨續攻 vs 滿足點」。Phase 1 實測**主訊號是『碰觸時點』而非延伸力**:早碰 L3 → 高續攻、晚碰 → 收手。改寫主軸後 Phase 2 回測 + 經 H116 全 TX 史多 regime 驗證,**時點分辨力跨所有 regime 穩定**,確立為 ladder 續攻主軸。

## Key Evidence
- Phase 1：早碰 vs 晚碰 L3→L4 續攻 gap IS +39% / OOS +41%（10:05 為 IS 中位,真實結構是「~10:30 平台 + 斷崖」）。
- **H116 多 regime 背書**：全 TX 史 666 事件,低/中/高波 + 2022 熊,早碰−晚碰 gap **+23~35% 跨 regime 全穩**。
- Phase 2 bracket：規則A(早碰才持有) OOS +0.030% vs always-hold −0.030% → 時點過濾有效。
- 達成地圖：11:30 前已捕獲全日 reach ~70%（[[project_ladder_reach_timing_map]]）。

## Why Confirmed
碰觸時點對 ladder 續攻的分辨力是本研究線唯一**跨 5 年所有 regime 都穩**的訊號;且已內嵌於 journal_checklist 時間閘(10:30 鎖/11:00-11:30 L3 天花板)→ 多 regime 資料背書了既有 checklist 時間軸設計。

## 限制（非 live 新策略的理由）
- 作 bracket P&L 規則 OOS **不優於既有 SatZone**、判定 68% 冗餘（無效條件 #2）→ 非「優於既有工具的獨立新 edge」。
- ext_long（含使用者早盤增幅 / 累積淨力 H116）各形式多 regime OOS 皆不穩（無效條件 #3）。
- 定位：checklist 時間軸的實證背書 + 「晚碰 L3 不要抱」硬紀律,不另立 live 策略。

## Derived Hypotheses
- H115（已 rejected）：vol_ratio vs DCI 當 room 軸 → 符號翻轉否決。
- H116（已 rejected）：累積淨力早碰層修正 → 多 regime 不穩否決,但回饋本案多 regime 驗證。

## Links
- Proposal：proposal.md
- Distribution：results/distribution.md
- Backtest：results/backtest.md（含 OOS + SatZone 對撞 + CUT 敏感度 + 上修 verdict）
</content>
