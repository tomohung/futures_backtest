# Proposal: VIX regime 當 ladder 出場/sizing 的期望調節器

## ID
H117

## Derived From
H116（net-force-modifier）歸檔後的 VIX 疊圖探索（2026-06-10）。
背景：[[project_ladder_reach_timing_map]]、[[project_oos_equals_highvol_regime]]。

## Trading Intuition
之前 DCI/ext_long/vol_ratio/淨力 各種**日內力道讀數**當 ladder 調節器全 OOS 不穩。
換個層級:**ladder L3/L4/L5 達成頻率本身重度 regime-dependent**——VIX 疊圖實證:
**VIX 升壓段的深關卡(L4/L5) reach ~2× 於降壓段**。把升降段平均 → 2× 差異被洗掉,
這正是「不同 regime 該給不同期望」的核心,也可能是之前**把高/低波平均而誤殺方法**的元兇之一。

VIX 是**日線級、外生、因果可實時判**的 regime 變數（昨日 VIX 盤前即有），比日內力道穩得多。

## Hypothesis
**用因果 VIX regime（昨日 VIX vs MA20：升壓/降壓）調節 ladder 出場期望——
升壓段更積極博長尾（抱 L4/L5、餘量留多）、降壓段早收 L3 別追深關卡——
其損益%/EV 優於 regime-agnostic 固定出場。**

## Expected Distribution（Phase 1 因果版已驗,列基線）
- VIX lag 1（regime(D)=VIX(≤D−1)）疊 ladder（N=1296,2021-2026）：
  - **升壓**：多 L4 30%/L5 16%、空 L4 30%/L5 17%（深 reach ~2×）
  - **降壓**：多 L4 19%/L5 7% 、空 L4 19%/L5 10%
- 達成頻率 ~2× 差異因果守住 → 升壓段抱長尾 EV 顯著高、降壓段稀。

## Invalidation Condition
1. regime-conditioned 出場（升壓抱、降壓早收）OOS 損益%/Sharpe **不優於固定出場**——2× 達成頻率沒轉成 P&L（如升壓深 reach 伴隨更多 whipsaw/回吐吃掉長尾）。
2. **贏不過 SatZone**（SatZone 的 vol_ratio 已部分含 regime 資訊 → VIX regime 冗餘）。
3. 因果 regime 標籤對 P&L 的調節,控制「絕對波動水位」後消失（純 vol level 代理,VIX 無增量）。
4. regime 連敗/drawdown 惡化（[[feedback_filter_eval_includes_streaks]]）。

## Notes
- **★ 因果鐵律（已踩過坑）**：台指 VIX 收盤後才算出,盤前只有 D−1。regime(D) 一律用 VIX(≤D−1)。
  ⚠ **同期 VIX(D) 會造出「升偏空/降偏多」方向假象**（VIX(D) 與當日跌幅機械耦合）;
  lag 後方向偏移消失（多−空L4 +0~+3%）→ **VIX 只能判「深 reach 機率/EV」,嚴禁用來偏多空。**
- 工具已落地：`src/analysis/vix_regime.py`（因果 regime + 期望查表,已接入 morning_briefing;`--csv` 產每日標籤表）。
- regime 偵測器選擇：VIX>MA20（主）與 VIX 20日變化（輔）皆強;EMA 交叉較鈍、純水位失 magnitude 梯度。
- 資料窗：VIX 2016-11~、TX 2021-02~（疊圖以 TX 為限）。多 regime 樣本充足（不受 stock_min 2025-06 邊界限制）。
- 更大意義（方法論）：本案是「regime-conditioned 期望」的試金石;若成立,回頭重看被「平均誤殺」的舊假設。
</content>
