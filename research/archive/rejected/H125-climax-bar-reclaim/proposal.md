# Proposal: Climax Bar Reclaim 反轉做多

## ID
H125

## Derived From
Origin（原創，來自 2026-06-17 盤中觀察）

## Trading Intuition
2026-06-17 台指期日盤：早盤悶盤約 2 小時（低波壓縮）。約 11:21 起出現一段**連續多根 1 分 K 持續放量的下殺**，跌破早盤盤整區下緣（把區間下方停損掃出來）。賣壓在接近今低處耗盡止跌，11:31 收盤站上「這段下跌 leg 裡成交量最大那根 K（climax bar）」的高點後，價格一路上攻且全日振幅放大。

直覺：這是典型的「假跌破 / spring（停損獵殺）」。出量本身不預測方向（已被 H063/H064 否定），真正的 edge 來自**「破底失敗 + 收回」這個結構**——climax bar 標記了停損被掃的那一刻，收盤收復它的高點，等於市場用真金白銀確認破底失敗。

## Hypothesis
在台指期日盤，當一段下跌 leg 中**成交量最大的 K（climax bar）的高點，被後續某根 K 的收盤價站上**時做多，後續 forward 報酬分佈相對於正確的虛無分佈呈現正期望值 / 右偏。

形式化進場觸發（多）：
1. Causal 偵測一段下跌 leg（起點、最小幅度待 Phase 1 定義，考慮重用 `PREP-2-leg-detection`）
2. 找出該 leg 內成交量最大的 K（climax bar）
3. 後續某根 K 的 close > climax bar 的 high → 進場

## Expected Distribution
- 觸發事件後 N 分鐘（15/30/60/到收盤）的 forward 報酬中位數 > 0，分佈右偏
- 「事前有壓縮」「late-morning 觸發」「leg 幅度較大」等切片應比整體更佳（若壓縮真有加分）
- 觸發後伴隨**振幅放大**（盤中後續 range 擴張），可作為波動 regime 訊號

## Invalidation Condition
- forward 報酬分佈相對**正確虛無分佈**（如：所有「跌破前低/盤整下緣」事件、或同日 IID 洗牌的條件期望）**沒有顯著正向超額** → 訊號只是描述性相關，不是 edge（比照 H063 的 tautology 教訓）
- 或符合條件的歷史樣本數不足以做切片分析（< GATE 門檻）
- 或正向只集中在「整體 drift」可解釋的範圍（~52% 上漲，比照 H063/H064），切片後無任何維度脫穎而出

## Notes
- 與既有 Rejected 假設的區隔：
  - **H062**（volume-spike-breakout）：用單根凸量 K **順勢**突破；本假設用下跌 leg 的 climax bar 當參考、方向為**反轉做多**、需收盤**收復** climax bar 高點。
  - **H063/H064**（large-order）：tick 大單聚集無方向力；本假設不賭「出量→方向」，edge 來自破底失敗結構，出量只用來定位 climax bar。
  - **H061**（morning-dip-reversal）：BB/KD 機械超賣每天觸發、無 selectivity；本假設用「收復 climax bar 高點」做結構確認，selectivity 來自破底再收回。
  - **H054**（VSA no-supply）：趨勢回檔量縮續做多；本假設是區間/下殺後的反轉，非趨勢續勢。
- Phase 1 採**寬定義**（不要求壓縮前提）撈全部 climax-reclaim 事件，把「事前是否有壓縮 / 觸發時間 / leg 幅度 / 是否跌破早盤區間下緣」當切片維度，一次看出各條件是否加分。
- 遵循研究慣例：先看零策略原始 forward excursion，且每個對稱切片都實測；務必對照正確虛無分佈（前瞻條件期望 / IID 洗牌）。
