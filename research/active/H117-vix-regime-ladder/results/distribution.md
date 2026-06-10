# Distribution Research Results: VIX regime × ladder 達成頻率（因果）

## Date
2026-06-10

## Conditions Tested
- VIX regime 因果偵測器（皆當日/盤前可算）× TX ladder L3/L4/L5 達成頻率（zero-strategy 全日 reach）。
- **★ 因果鐵律**：台指 VIX 收盤後算出 → regime(D) 用 VIX(<D)（merge_asof backward,不含當日）。
- 偵測器：VIX>MA20、VIX 20/10 日變化、EMA10>40、純水位>24。
- 腳本 `explore.py`;panel `results/vix_ladder_panel.csv`。

## Sample
- N=1296（2021-02~2026-06,TX 分K 起點限制）;VIX 2016-11 起、多 regime（含 2022 熊、2020 雖無 TX 分K）。

## Key Findings

### 1. ★ 深關卡達成頻率 ~2× regime 差異（因果守住,主結果）
主偵測器 VIX>MA20（LAG）：
| regime | 多 L3/L4/L5 | 空 L3/L4/L5 | 多−空L4 |
|---|---|---|---|
| **升壓** (n637) | 59/**30/16**% | 55/**30/17**% | +0% |
| **降壓** (n659) | 44/**19/7**% | 42/**19/10**% | +1% |
- **升壓段 L4 ~30% / L5 ~16%,降壓段 L4 ~19% / L5 ~7%**：深關卡(尤其 L5)**~2×**。全偵測器一致。

### 2. ★★ 方向偏移是同期假象（因果檢定,重要）
- 偷看 VIX(D)（同期）：升 多−空L4 **−5%**、降 **+7%**（看似升偏空、降偏多）。
- **LAG VIX(D−1)（因果）：多−空L4 全偵測器都 ≈0（+0~+3%）→ 方向偏移消失。**
- 根因：VIX(D) 由當日大跌算出,與「當日空方達深」**機械同期耦合**,非預測。
- → **VIX 只能判「深 reach 機率/EV」,嚴禁用來偏多空。** （使用者 causality 直覺抓出此坑。）

### 3. 偵測器選擇
- VIX>MA20 與 VIX 20/10 日變化皆強（升降深 reach 清楚 2×）;EMA 交叉稍鈍、純水位>24 失 magnitude 梯度（高 28 vs 低 24,差異小）。
- 採 **VIX>MA20 為主**（直觀、responsive）。

## Vs. Expected
- **符合**：深 reach ~2× regime 差異成立且因果守住。
- **修正**：原疊圖看到的「升偏空/降偏多」**經因果檢定為假象**,排除——只保留 magnitude。

### 4. Phase 1-B：續攻轉換 + 路徑回吐品質（`h117_transition_path.py`,因果）
**regime 也調節「碰到後續攻」機率,尤其深尾：**
| regime | P(L4\|L3) | P(L5\|L4) |
|---|---|---|
| 升壓 | 51% | **52%** |
| 降壓 | 44% | **36%** |
- L4→L5：升壓 52% vs 降壓 36%（**+16pp**）→ 到 L4 後升壓抱尾有利、降壓該收（比 checklist「L4→L5 一律擲銅板」更精細）。

**路徑回吐（碰 L3 後最大逆行 MAE/EMA20,越近 0 越好抱）：**
| regime | 續攻日 中位/平均 | 失敗日 中位 |
|---|---|---|
| 升壓 | −0.12 / −0.20 | −0.43 |
| 降壓 | −0.12 / −0.14 | −0.34 |
- **續攻日 median 回吐兩 regime 相同（−0.12）→ 升壓 2× 深 reach 沒被 whipsaw 吃掉、一樣好抱**;
  升壓僅平均回吐略深（−0.20,少數深洗仍續攻）、失敗日回吐較大（−0.43 vs −0.34,停損管理）。
- → **2× 頻率 + L4→L5 高續攻 轉得成可實現長尾 EV**（非假象）。

## Gate Decision
**[x] 繼續 Phase 2（Phase 1-B 已補完,支持規則化）**
- magnitude 2× + L4→L5 續攻 +16pp + 路徑可實現（續攻 median 回吐相同）→ 三項齊備,因果守住。
- Phase 2：regime-conditioned 出場（升壓抱 L4/L5、降壓 L3 早收）vs 固定出場 vs SatZone-only;IS/OOS（跨 regime）損益%/Sharpe/連敗/maxDD;控絕對波動水位看 VIX 增量。

- [x] 繼續 Phase 2　[ ] 先補 Phase 1　[ ] Archive

## Derived Hypotheses
- **方法論（記憶）**：VIX 是同期 vol 量測 → 同日 VIX→reach 是 look-ahead,必 lag;magnitude 因果真、direction 假象。
- **回看舊假設**：ladder reach ~2× regime-dependent → 之前被「升降段平均」稀釋而 OOS 不穩的力道訊號（H114/H115/H116）,值不值得在**單一 regime 內**重評（而非跨 regime 平均）。
</content>
