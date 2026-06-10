# Proposal: 碰觸關卡的「時點」分辨 ladder 續攻 vs 滿足點（即時延伸力為晚碰修正）

## ID
H114

## Derived From
H111（dci-long-reach-map）OOS 複驗 + H114 Phase 1 自身（2026-06-10）。
承接 **H111-d4**（把出場驅動從 look-ahead 的 `dci_daily` 遷到因果乾淨的盤中訊號）。背景：[[project_dci_verify_handoff]]。
**主軸於 Phase 1 後改寫**（原以即時 ext_long 為主角，實測主訊號是碰觸時點）。

## Trading Intuition
使用者實盤核心是**抓 ladder reach 行情**：分辨今天是 L3 / L4 / L5+ 等級，決定進場後
**何時收手（滿足點達成）、何時還有空間可加碼**。

Phase 1 實測揭穿一件事：決定「碰到 L_k 後還有沒有空間續攻 L_{k+1}」的**最強且 OOS 最穩的訊號，是『何時碰到』**——
早碰（早盤）= 後面還有大量時間/動能可延伸；晚碰（午盤）= 多半就是滿足點。這比任何延伸力讀數都強、且近乎機械。
即時延伸力（是否滾頭）退為**晚碰時的二級修正**：晚碰但延伸力還沒滾頭，續攻機率被救回。

## Hypothesis
**TX 上行擺幅首次觸及 L_k 的『時點 t_k』能顯著分辨「續攻 L_{k+1}」vs「此處即滿足點」：
早碰 → 高續攻機率（續抱/加碼）、晚碰 → 低（收手）；且此分辨力 IS/OOS 都穩。
附帶：在『晚碰』子層，碰觸當下即時 ext_long 未滾頭（ddpeak 低）能再救回續攻機率。**

主測 **L3→L4**（樣本足）；L4→L5 列探索性（樣本薄）。

## Expected Distribution（Phase 1 已驗，列為基線）
- 時點：早碰 L3 續攻 L4 ~65–70%、晚碰 ~24–31%，gap +40%（IS/OOS 幾乎相同）。
- 晚碰層 ext_long(ddpeak) 增量：IS +18% / OOS +22%（早碰層冗餘）。
- ext_long 絕對水平(level) OOS 崩、不可用；衰竭定義須用 **ddpeak（roll-over）**。

## Invalidation Condition（Phase 2 出場/加碼規則）
任一成立即**否證 / 降級**：
1. 時點分層的出場/加碼規則，**OOS 損益% / Sharpe 不優於**現行固定出場基準（時點分辨在績效上沒兌現）。
2. **贏不過 SatZone-only（est_range 耗盡）滿足點規則**——若 SatZone 已等效捕捉「早碰續攻/晚碰收手」，本規則冗餘。
3. 晚碰層加上 ext_long(ddpeak) 修正後，OOS 績效**沒有**比「純時點規則」更好（修正項無增益）。
4. 規則使連敗長度 / drawdown 惡化（即使均值改善也否決，見 [[feedback_filter_eval_includes_streaks]]）。

## Notes
- **因果鐵律**：所有預測子須在「碰到 L_k 那一分鐘」即可得（即時 ext_long、其過去斜率、時點、SatZone 狀態）；
  禁用任何當下之後才知道的量（含收盤版 dci_daily — 那是 look-ahead，正是要被取代的對象）。
- universe：OOS 複驗顯示 **窄 universe（W5/W10）連續解釋力 OOS 零衰退、W50 掉 0.12**；Phase 1 預設用 W10（W5 備案），不重蹈 W50。
- 即時延伸力「轉弱/滾頭」需定義：候選=ext_long 較其當日峰值的回落、或近 N 分鐘斜率轉負。Phase 1 探索哪種定義分辨力最強。
- 空方（下行 ladder）：H112 離散下行地圖 OOS 已 Rejected（連續訊號才成立），故本案**先只做多方上行**；空方留待 H112-d1 的連續形式另議。
- 資料窗：stock_min 2025-06~2026-06；IS=2025-06-02~2026-02-26、OOS=2026-03-01~2026-06-09（沿用複驗切分）。
</content>
