# Distribution Research Results: 實現波動「溫度計」預判深reach延續

## Date
2026-07-16

## Conditions Tested
- 樣本：TX 日盤 zero-strategy，N=1339 交易日，2021-02 ~ 2026-07-15（EMA20 warmup 後）。
- **溫度計（因果、trailing-only）**：
  - `temp_ladder(W)` = trailing W 日 open-anchor ladder 達成 anyL4（excursion≥0.977×causalEMA20）/ anyL5（≥1.225×）頻率，W∈{5,10,20}
  - `temp_night(W)` = trailing W 夜 deep-STOP 頻率（night_norm<0.8，沿用 key_prices NVF）
- **目標**：未來 H 日 anyL4 / anyL5 率，H∈{1,3,5,10}
- **三虛無基準**：① persistence（IID 洗牌）② 現有 vix_regime 分層 ③ deep-STOP vs ladder 共線性
- snooping 防線：先看預測變數分佈定桶（tertile）、再看基準率+自相關定 effective-N、最後才揭 forward。

## Sample
- 總樣本數：1339 交易日（deep-STOP 1307 夜）
- 時間範圍：2021-02 ~ 2026-07-15
- 市場：台指期 TX 日盤（08:45–13:45）

## Key Findings

### 0. 無條件基準率（設計校驗通過）
anyL4 = **24.8%**、anyL5 = ~12%、多/空 L4 對稱、anyL4(≤11:30)=17.0%、anyL4(≤10:30)=11.4%、deep-STOP 夜 35.7%。
與 ladder 設計目標（25% / 12.5%）幾乎完美對齊，證明 reach 事實表計算正確。

### 1. ★ daily anyL4 幾乎是 IID（clustering 極弱）
ACF：ρ(lag1)=**+0.07**、lag2 +0.07、lag3 起 ≈ +0.01 → 0。
**「今天有沒有碰 L4」日與日之間幾乎不相關**。深 reach 主要由當日開盤/消息驅動，路徑依賴極弱。
這從根本上限制了任何 trailing 溫度計的預判力上限。

### 2. 溫度桶 → forward：spread 小且在 IID null 帶內（虛無①未過）
tertile 冷/中/熱 → 未來 H 日 anyL4：冷→熱 spread 僅 +1%~+8%（最大在 W10/H1，且熱桶 effective N 僅 ~34）。
IID 洗牌 null：真實 spread 落在 null 的 **75–89 分位**，**未超過 p95**。
→ 觀察到的持續性與「隨機洗牌後仍會出現的假 spread」無法區分。

### 3. ★★ 決定性：溫度資訊被現有 vix_regime 完全吸收（虛無②未過）
在同一 VIX regime 內再切高/低溫，未來 5 日 anyL4 的「高−低溫」增量：

| W,H | 升壓 增量 | 降壓 增量 |
|---|---|---|
| 10,5 | **−2%** (N815) | **−2%** (N510) |
| 20,5 | −0% (N805) | −4% (N510) |
| 10,3 | −3% (N815) | −1% (N512) |

增量全部 ≈0 或**負**（且樣本充足 N=500~800）。regime 本身把升壓/降壓的未來 reach 拉開（30% vs 16%），
但**在 regime 之內，ladder 溫度再也分不出任何 forward 差距**。溫度計沒有 vix_regime 之外的增量資訊。

### 4. 極端冷桶（用戶 L3-only 觀察的直接檢定）：mean-revert 到基準、不可交易
trailing 10 日 **0 次 L4**（最冷）之後：未來 1 日 anyL4=19.7%（僅 −5pp）、3 日 22.0%、**5 日 24.5%、10 日 23.7%（回到基準）**。
→ 極冷 streak 只給次日 −5pp 的微弱壓低，**到第 5 天完全 revert 回 24.8% 基準**。冷 streak 不預測續冷、也不預測反轉。

### 5. ☆ 實況鐵證：2026/04/22 → 04/23
04/21–04/22：`tempL4_10=0.0`（連 10 日零 L4，最冷可能值，降壓）。
**04/23：anyL4=1、anyL5=1、rng=1679（全窗最大振幅）**，regime 當日翻升壓。
最冷讀數的隔日即爆最大 move — 冷 streak 對「接下來」零預判力的教科書級案例。

### 6. deep-STOP 非 additive（虛無③未過）
corr(temp_ladder, temp_night)=−0.39（中度負相關，同一波動因子的代理）。
2×2（ladder 冷/熱 × 夜盤 多/少 STOP）forward 全落 23–27%，夜盤維度不帶額外 forward 資訊。

## Vs. Expected
- 符合 proposal 的**無效條件全部命中**：剔除 persistence 後 edge 在 null 帶內；regime 分層內拉不開；
  極端桶 revert 到基準；deep-STOP 不 additive。
- 唯一意外：daily anyL4 的 clustering 比預期更弱（ACF lag1 僅 0.07），使溫度計上限比想像更低。

## Gate Decision
**預判訊號：不過 GATE（建議 Reject 預測性宣稱）。**
- [ ] 進入 Phase 2
- [x] Archive（原因：溫度計對未來深 reach 的預判力 (a) 落在 IID null 帶內、(b) 在 vix_regime 分層內增量≈0/負、
      (c) 極端冷桶到 H=5 即 revert 回基準。資訊已被現有 vix_regime 吸收，無獨立可交易 edge。）
- [ ] 修改假設

**但觀測 tile 照建**（用戶明確要求；描述性看盤工具，不宣稱預判）：近 N 日 L4/L5 達成率、
deep-STOP 頻率趨勢、溫度方向箭頭、與 vix_regime 並列。定位＝「現在冷/熱的即時溫度計」而非「預測器」。

## Derived Hypotheses
- （無新的預測性衍生）核心副產品：**確認 vix_regime 已是深 reach 預判的充分統計量**——
  未來若要提升深 reach 預判，方向應是找 regime *之外* 的當日盤前變數（如選擇權 IV term、隔夜 gap、
  國際期貨夜間振幅），而非 trailing 已實現 ladder 頻率。可另立假設。
