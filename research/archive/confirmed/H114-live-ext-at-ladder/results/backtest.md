# Backtest Results: 碰觸時點分辨 ladder 續攻（ext_long 為晚碰修正）

## Date
2026-06-10

## Parameters
- 事件型 bracket trade：L3 首觸當下價 p_L3 進場做多;target=p_L3+0.266×EMA20（L3→L4 增量）、stop=−1.0R、皆未到→收盤平。
- 損益% = 點數/p_L3×100;未持有日=L3 滿足收手（貢獻 0）。
- 規則 A（主）：t_k ≤ 10:30 才持有。規則 B：A ∪（晚碰 且 W10 ext_long ddpeak<IS中位）。
- 基準：always-hold、SatZone-only（EstRange_SatUpper 量加權,生產同款）。
- 腳本 `backtest.py`（A/B/always + CUT 敏感度）、`satzone_compare.py`（vs SatZone）、`h114_extgrowth.py`（早盤增幅）。
- L3 事件 N=149（IS 105 / OOS 44）;SatZone 對撞剔暖機後 146。

## Results

### 1. 時點規則 vs 無腦持有（時點過濾有效,IS/OOS 一致）
| 規則 | IS 平均% | IS Sharpe | IS maxDD | OOS 平均% | OOS Sharpe | OOS maxDD |
|---|---|---|---|---|---|---|
| A 純時點(≤10:30) | +0.062 | 0.23 | −1.49 | **+0.030** | 0.07 | −2.68 |
| B 時點+ext修正 | +0.064 | 0.24 | −1.12 | +0.033 | 0.08 | −3.12 |
| always-hold | +0.035 | 0.14 | −1.39 | **−0.030** | −0.07 | −3.86 |
- 無腦持有 OOS 為負（勝率 45%）;丟掉晚碰後 OOS 翻正 → **時點過濾本身有效、且 OOS 守住**。
- **B vs A 無 OOS 增益**（平均幾乎相同、maxDD 略差）→ ext_long 修正項 OOS 未證實（無效條件 #3 觸發）。

### 2. CUT 切點敏感度（IS/OOS 張力）
| CUT | IS Sharpe | OOS 平均% | OOS Sharpe | OOS maxDD |
|---|---|---|---|---|
| 09:45 | 0.13 | **+0.103** | **0.22** | **−1.15** |
| 10:00 | 0.12 | +0.050 | 0.11 | −1.85 |
| 10:30 | 0.23 | +0.030 | 0.07 | −2.68 |
| 11:00 | 0.18 | +0.009 | 0.02 | −2.68 |
- **IS 偏好寬切（10:30）、OOS 偏好早切（09:45）**;切點越寬 OOS 單調變差 → IS 的 10:30 平台是輕度過擬合,OOS-誠實切點是 09:45~10:00。

### 3. vs SatZone-only（無效條件 #2 — 關鍵）
| 規則 | IS 平均% | IS Sharpe | OOS 平均% | OOS Sharpe | OOS maxDD |
|---|---|---|---|---|---|
| A 早碰才持有 | **+0.061** | 0.22 | +0.030 | 0.07 | −2.68 |
| SatZone 未滿足才持有 | +0.032 | 0.12 | **+0.092** | **0.21** | **−1.06** |
- **A 贏 IS、SatZone 贏 OOS**;且兩規則判定**一致率 68%**（早碰↔未滿足、晚碰↔已滿足高度相關）。
- 2×2 交互在小樣本不穩（IS 最佳格「早碰∩已滿足 +0.204」OOS 變最差 −0.262）→ 無穩定組合 edge。
- → **時點規則大程度是 SatZone 的代理,且 OOS 不優於 SatZone**。

### 4. 使用者衍生想法：早盤 ext_long「增幅」（h114_extgrowth.py）
早碰子集,依 09:15→09:30 / 09:15→10:00 ext_long 增幅（力道續增 vs 轉弱）分組,forward-guarded：
- 09:15→10:00：IS gap +25%（合直覺）但 **OOS 翻成 −20~−25%**;09:15→09:30 OOS −31~−42%。
- 4 個 OOS 格全負、IS 正 → **IS 過擬合、OOS 不重現**（樣本 OOS 12~17,不宣稱反指標,但無 OOS 支持）。

## Walk-Forward Summary
IS=2025-06~2026-02（105 L3 事件）、OOS=2026-03~2026-06（44）。時點規則 A 在 IS/OOS 皆優於 always-hold（穩）;但對撞 SatZone：IS 勝、OOS 負,且 68% 冗餘。ext_long 各形式（水平/斜率/自峰回落/早盤增幅）OOS 全不守。

## Parameter Sensitivity
- CUT：IS 10:30 vs OOS 09:45 張力（見上）→ 取 09:45~10:00 較穩健保守。
- ext_long universe/門檻：對 OOS 無正貢獻,任何形式皆脆。
- bracket（target=0.266×EMA20 / 1R stop）：未細掃,屬訊號驗證非參數優化。

## Verdict（2026-06-10 上修,經 H116 多 regime 驗證）
**[x] Confirmed（描述性：碰觸時點為 ladder 續攻的 robust separator,多 regime 驗證）
　＋ 但「優於 SatZone 的獨立 P&L 新規則」否決、ext_long 修正否決。**

依據：
- ✅✅ **碰觸時點分辨力經 H116 多 regime 驗證紮實**：全 TX 史 666 事件、低/中/高波 + 2022 熊,早碰−晚碰 gap **+23~35% 跨 regime 全穩**（原 H114 僅單窗 +40%）→ 從 Inconclusive **上修為 Confirmed-描述性**。
- ✅ 操作上**已內嵌於 journal_checklist 的時間閘**（10:30 鎖、11:00-11:30 L3 天花板）→ H114/H116 等於用多 regime 資料**驗證了 checklist 時間軸設計是對的**。
- ❌ **無效條件 #2**：作為 bracket P&L 規則 OOS 不優於 SatZone、68% 冗餘 → **非「優於既有工具的獨立新 edge」**,不另立 live 策略。
- ❌ **無效條件 #3**：ext_long（含使用者早盤增幅 / H116 累積淨力）多 regime 皆 OOS 不穩,否決。

**結論定位**：時點＝ladder 續攻主軸(已驗證、已在 checklist 用);ext_long/量/淨力各形式皆非穩定增量。
不晉升為新 live 策略,作為 checklist 時間軸的多 regije 實證背書 + 「晚碰 L3 不要抱」硬紀律。

## Derived Hypotheses
- **H114-d1**：碰觸時點 × 關卡 的續攻地圖（純時點,免量）作為 SatZone 的「快取版」啟發法——值不值得當 S001 的看盤簡化規則（不另開回測,屬使用手冊）。
- **H114-d2**：晚碰∩延伸力未滾頭=「午盤二次發動」型態（IS +0.075 但 OOS 5 筆）→ 待更多 bear/高波 OOS 重驗。
- **H114-d3（已測否決）**：早盤 ext_long 增幅（09:15→09:30/10:00）→ OOS 符號翻轉,不支持。
- **觀察**：ext_long 全形式（水平/斜率/自峰回落/早盤增幅）OOS 皆脆 → 延伸力對「ladder 續攻決策」無穩定增量;時點/SatZone 的「耗竭」邏輯才是主軸。
</content>
