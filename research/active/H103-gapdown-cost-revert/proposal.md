# Proposal: 跳空跌破成本 → 折價回補做多（Gap-Down Cost Reversion Long）

## ID
H103

## Derived From
H102（淨空開盤裸突破）的 **distribution 階段**。
H102 把「沒 S/R 就往那走」的裸突破假設證偽，但收斂出唯一穩健訊號：
跳空跌破兩條成本之下、上方大段空間 → 往成本回補（mean-reversion 做多）。
本假設把該訊號獨立出來、用對的進出場（目標=成本、停損=當日低）重做。

## Trading Intuition
開盤大幅**跌破昨日與前日成本（VWAP）**＝今日開在「折價於近期成本」之處。
若上方最近的成本還隔著一大段距離（≥ 一個 L4 reach 的振幅空間），代表上方有
乾淨的回補跑道、且有「成本」這個磁吸目標。重挫折價 + 上方空間大 → 傾向反彈
回成本。這是經典 gap-down 回 VWAP 的多單，但**只有多方成立**（H102 證實對稱的
gap-up 做空無 edge——gap-up 是低能量死水日）。

## Hypothesis
**進場條件（盤前/開盤即可判定）：**
```
open < min(vwap_last, vwap_prev)                 # 跌破兩條成本（gap-down 全在成本下方）
up_clear = min(vwap_last, vwap_prev) − open      # 到最近上方成本的距離
ema20    = causal-EMA20(日盤振幅)                 # 對齊 H095
up_clear_norm = up_clear / ema20  ≥  0.977 (L4)   # 上方有大段回補空間
→ 做多
```
**陳述**：符合上述條件的日子，往上回補（up 方向）顯著優於往下續跌，且「回補到最近
上方成本價」的達成率與盈虧比，足以構成正期望、可交易的 mean-reversion 多單。

**H102 已知支撐數據**（distribution 階段，N≈111）：
- 跳空下方 × up_clear L4–L5（N=47）：同向(多) L3 72% vs 反向 47% → **+26pp**
- 跳空下方 × up_clear >L5（N=64）：同向(多) L3 80% vs 反向 62% → **+17pp**
- 對照：跳空下方 × up_clear<L4（N=289，成本就在近上方）→ 方向差 −2%（無 edge，需排除）

## Expected Distribution
- 進場後「觸及最近上方成本價」的達成率明顯高於同幅度往下的續跌率。
- MFE（向上）分佈右偏、MAE（向下）相對受控 → 正盈虧比。
- up_clear_norm 越大（折價越深 + 空間越大）→ 回補達成率單調越高（延續 H102 單調性）。
- 屬高能量日（H102：擺幅 ~1.05–1.10×ema20），須接受波動與一定反向 excursion。

## Invalidation Condition
- 進場（含實際時點與成本/滑價）後，回補到成本的達成率**未明顯優於**baseline 或往下續跌率。
- up_clear_norm 與回補達成率**無單調關係**（折價深度不帶資訊）。
- 盈虧比 / 期望值在加上手續費滑價後不為正；或連敗長度、drawdown 過大（依
  `feedback_filter_eval_includes_streaks`，保護心理資本優先）。
- OOS（時間外）期望值崩潰（H102 grid 為事後切，過擬合風險須以 OOS 把關）。

## Notes
- **這是 mean-reversion 不是 breakout**：進出場不沿用 ORB（ORB 反咬 56–68%）。
  Phase 1 要先決定進場時點（開盤即進 / 等下影止穩確認 / 首次回測某參考價），
  出場目標看「最近上方成本價」，停損看當日低點或固定 R。
- **方向不對稱是 feature**：只做多，不做對稱 gap-up 空（H102 已證無 edge）。
- 規則先寫死再回測，避免在 H102 grid 上二次過擬合。
- 與 NVF hard rule：本訊號為高能量日，Phase 2 需檢查是否與 NVF 衝突 / 可並存。
