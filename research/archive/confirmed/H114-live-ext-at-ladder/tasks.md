# Tasks: 碰到關卡當下的即時延伸力分辨續攻 vs 滿足點

## Phase 1: Distribution Research

- [x] **關卡碰觸事件抽取**：TX 上行擺幅首觸 L3/L4/L5 分鐘 t_k。事件 N=255（L3→L4 IS105/OOS44、L4→L5 IS53/OOS20）。
- [x] **碰觸當下的即時 ext_long**：自算逐分鐘 W5/W10 序列，取 t_k 當下 level/slope/ddpeak(自峰回落)。
- [x] **結果標記**：t_k 之後是否再觸及 L_{k+1}（forward-guarded）。
- [x] **核心對照**：強−弱 gap IS/OOS。結果：level 崩(+25%→0%)、slope 噪音、**ddpeak 守(+17%→+15%)**。
- [x] **增量檢定**：控制碰觸時點後 → ext_long 僅在**晚碰層**有增量(L3→L4 IS+18%/OOS+22%)，早碰層冗餘。satcons 無分辨力。SatZone 完整版留 Phase 2。
- [x] **定義敏感度**：三種衰竭定義比較 → **ddpeak（roll-over）最穩**，level OOS 崩。
- [x] **主發現（意外）**：**碰觸時點才是主訊號**（L3→L4 早碰 vs 晚碰 gap +39%/+41%，極穩），ext_long 退為晚碰修正。
- [ ] 視覺化（Phase 2 前補）：續攻率 vs 時點 + 晚碰層 ext_long 疊圖。

---
### GATE
**問題：即時-當下延伸力的續攻分辨力是否 OOS 守得住、且贏過既有 SatZone？**

- 樣本門檻：L3、L4 碰觸事件 **IS ≥30 天 且 OOS ≥15 天**（L5 預期偏薄，列為探索性、不作判定依據）。
- 方向：即時 ext_long 強−弱 gap **OOS ≥ ~12%** 且方向與 IS 一致（明顯優於早盤凍結讀數的 +7%）。
- 增量：控制時點 + 當下擺幅 + SatZone 後仍存活；非純動能/套套邏輯。
- data snooping：universe / 衰竭定義的選擇不可只憑 OOS 表現挑（先在 IS 定、OOS 只驗）。

**決定：** [ ] 繼續 Phase 2　[ ] 直接 Archive　[ ] 修改假設後重跑

---

## Phase 2: Backtest（出場/加碼規則，主軸=碰觸時點）

決策規則（碰到 L_k 當下，皆因果乾淨）：
- **時點主規則**：早碰（t_k ≤ IS 中位時點）→ 續抱/加碼，目標 L_{k+1}；晚碰 → 於 L_k 收手（滿足點）。
- **晚碰修正**：晚碰但即時 ext_long(ddpeak) 低（未滾頭）→ 改判續抱。

- [x] 事件型 bracket trade（L3 觸發起點；target=+0.266×EMA20/stop=−1R/收盤平）。
- [x] 規則 A：純時點（≤CUT 才持有）。
- [x] 規則 B：A + 晚碰∩ext_long(ddpeak<IS中位) 修正。
- [x] 基準：always-hold、SatZone-only（EstRange_SatUpper 量加權）。
- [x] IS 損益%/Sharpe/連敗/maxDD；OOS 驗證 + CUT 切點敏感度（IS 10:30 vs OOS 09:45 張力）。
- [x] 對撞：B vs A（ext 修正 OOS 無增益）、A vs SatZone（68% 冗餘、OOS 輸 SatZone）。
- [x] 使用者衍生：早盤 ext_long 增幅（h114_extgrowth.py）→ OOS 符號翻轉，否決。
- [ ] （verdict 後）視覺化清單 — 視裁決決定是否做。
</content>
