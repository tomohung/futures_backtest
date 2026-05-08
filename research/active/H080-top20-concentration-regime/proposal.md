# Proposal: 前 20 權值股成交集中度的行情分類

## ID
H080

## Derived From
Origin（原創，受 H079 廣度溫度計研究啟發）

## Trading Intuition

TAIEX 是發行量加權指數，前 20 權值股（台積電、鴻海、聯發科、台達電、中華電、富邦金……）市值合計佔大盤超過一半，其每日成交金額佔大盤總成交金額的比例（以下簡稱「集中度」）反映兩件事：

1. **資金結構**：集中度高 → 大型股獨秀；集中度低 → 中小型股活躍
2. **行情型態的可能訊號**：
   - 集中度**偏低**時，行情可能不容易大漲（資金分散、無領頭羊）甚至偏弱
   - 集中度**偏高**時，行情可能容易上漲（權值股強勢、指數有力）
   - **或者**集中度偏高只反映「波動變大、方向不確定」（權值股大量交易可能伴隨指數雙邊洗盤）

這三個方向互斥，需要用資料判定誰對。

## Hypothesis

當日「前 20 權值股成交金額佔大盤總成交金額」相對 20 日均的偏離百分比（`deviation_pct`）能區分當日 TX 日盤的行情形態（方向 × 振幅）。

具體可檢驗的子假設：

### H080-A：方向訊號（單調性）
**陳述**：用 `deviation_pct` 切 5 桶（quintile），「當日 TX 日盤漲日機率」(close > open) 隨集中度桶位呈現**單調趨勢**，且首尾兩桶差距 ≥ 8 個百分點。

### H080-B：振幅訊號（單調性）
**陳述**：用 `deviation_pct` 切 5 桶，「當日 TX 日盤平均振幅」((high–low)/open) 隨集中度桶位呈現**單調趨勢**，且首尾兩桶差距 ≥ 30%（相對值）。

### H080-C：極端格行情聚集
**陳述**：把日子分成 3 集中度桶 × 3 方向桶 × 3 振幅桶 = 27 格，至少有 2 格的條件機率相對 baseline（無條件機率）lift ≥ 80%，且 chi-square 檢定 p < 0.05。

### H080-D：大跌規避（可選）
**陳述**：某個集中度桶（推論：極低或極高）的「大跌日機率」（方向 < -0.5% 且振幅 > top tercile）相對 baseline lift ≥ 50%。

> ⚠️ **方法論限定**：本假設是**同期相關性研究**，不是預測研究。實戰可用性建立在「核心假設 A：早盤即時集中度 ≈ 全日集中度」之上，此假設目前無歷史 5 分鐘級資料可驗證，需要 Phase 1.5 累積即時資料後另行驗證（不在本研究範圍）。

## Expected Distribution

### Phase 1 預期會看到的圖像

- **集中度分佈**：`share_pct` 在 8 年期間有明顯的結構性上升（台積電權重從 ~20% 攀升至 ~40%），所以絕對值不可比，但 `deviation_pct`（相對 ma20）應呈現以 0 為中心的鐘形分佈，標準差約 5–15%
- **5 桶 quintile 趨勢**：
  - 樂觀情境：漲日機率隨集中度單調上升 (Q1 約 42% → Q5 約 53%)，振幅隨集中度單調上升或下降
  - 悲觀情境：5 桶間漲日機率差異 < 3pp，無單調趨勢
- **27 格主分析**：
  - 預期會有 2–4 格出現顯著 lift（特別是「集中度極低 + 跌 + 大振幅」、「集中度極高 + 漲 + 大振幅」這類組合）
  - 也可能發現「集中度極高」對應「大振幅但方向中性」（對應 Trading Intuition 中的第三個方向）
- **清單變動事件**：2018–2026 期間應該會看到 5–10 次明顯的清單進出榜（國巨 2018、長榮 2021、廣達/緯創 2024 等），可作為輔助診斷

## Invalidation Condition

H080 整體 GATE 條件如下，**任一通過**即進 Phase 2：

1. **方向 lift**（H080-A）：5 桶 quintile 漲日機率單調且首尾差距 ≥ 8pp
2. **振幅 lift**（H080-B）：5 桶 quintile 平均振幅單調且首尾差距 ≥ 30%
3. **大跌規避**（H080-D）：某 3 桶大跌機率相對 baseline lift ≥ 50%
4. **9 宮格極端格**（H080-C）：27 格中存在 ≥ 2 格 lift ≥ 80% 且 chi-square p < 0.05

**全部不通過**則歸檔 inconclusive，並記錄三個可能的衍生方向：
- 換訊號定義（zscore、絕對閾值）
- 換時間框架（前 50 / 前 100 權值，或非權值股集中度）
- 換預測目標（TX 夜盤、5 日 swing）

## Scope

### 樣本期間
- **2018-01-02 ~ 2026-05-07**（與 stock_day 表對齊，約 8 年、~2000 個交易日）
- ma20 暖機後實際樣本 ~1980 個交易日

### 訊號定義
```
top20_value_t  = sum(stock_day.value where symbol ∈ top20_list[month(t-1)])
total_value_t  = market_breadth.total_value[t]
share_t        = top20_value_t / total_value_t
ma20_t         = rolling_mean(share, 20)[t]
std20_t        = rolling_std(share, 20)[t]
deviation_pct  = (share_t - ma20_t) / ma20_t * 100      # 主訊號（所有子假設與 GATE 條件都基於此）
zscore         = (share_t - ma20_t) / std20_t           # 補充指標（穩健性檢查；不入 GATE）
```

### 資料管線（新增）

兩張新表 + 兩支 ETL：

```sql
CREATE TABLE top20_lists (
    list_month     VARCHAR,           -- 'YYYY-MM'，月底快照
    rank           INT,               -- 1..20
    symbol         VARCHAR,
    name           VARCHAR,
    weight_pct     DECIMAL(6,3)
);

CREATE TABLE top20_concentration (
    trade_date     DATE,
    list_month     VARCHAR,           -- 套用清單的月份（t 的前一個月底，無未來函數）
    top20_value    BIGINT,
    total_value    BIGINT,
    share_pct      DECIMAL(8,4),
    ma20_share     DECIMAL(8,4),
    std20_share    DECIMAL(8,4),
    deviation_pct  DECIMAL(8,4),
    zscore         DECIMAL(8,4),
    list_changed   BOOLEAN            -- 當月清單與上月有變動
);
```

ETL 腳本：
- `src/etl/parse_top20_lists.py`：爬 TWSE 月報「市值比重」（端點待確認，候選 `STA0000004` 或 TAIEX 成份股月報）→ `top20_lists`
- `src/etl/build_top20_concentration.py`：join `stock_day` + `market_breadth` + `top20_lists` → `top20_concentration`

### 行情分類（9 宮格）

| 維度 | 切點 | 標籤 |
|---|---|---|
| **方向**：close/open – 1 | < -0.3% / ±0.3% / > +0.3% | 跌 / 平 / 漲 |
| **振幅**：(high–low)/open | tercile（資料驅動） | 小 / 中 / 大 |

主分析：3（集中度桶） × 9（方向 × 振幅） = 27 格條件機率表。

### 預測目標（TX 日盤）
- 用 `ohlcv_1m` 合成 TX 日 K（08:45 開盤 → 13:45 收盤）
- 以**主力連續合約**為準（用 `adj_close` 換算的點數變動率，但這裡用單日 OHLC 不需處理換倉跳空）
- 注意：close/open 與 high/low 用單日 raw（非 adjusted）

### 清單來源（重要決策）
- **嚴謹版（採用）**：用 t 的**前一個月底**月報快照 → 套用到 t 月份每一天，零未來函數
- 不採用「當月底快照套用本月」（會有微量未來函數）

## Notes

### 已知限制（必須在 distribution.md 顯眼處標記）
1. 🚨 **同期相關性 ≠ 預測力**：本研究結論不可直接用於實戰策略
2. 🚨 **核心假設 A 待驗證**：實戰可行性建立在「早盤即時集中度 ≈ 全日集中度」上，目前無歷史 5 分鐘級資料可驗證
3. 🚨 **月報快照法的清單漂移**：結構性變化期（2018 國巨進榜、2021 長榮進榜、2024 廣達/緯創 AI 進榜）的清單會在當月後段才反映實際排名

### 後續延伸（不在本研究範圍）
- **Phase 1.5（待議）**：建立即時集中度日記管線（每天盤中 09:00 / 09:30 / 10:00 / 10:30 / 11:00 / 12:00 / 13:00 / 13:45 各時點記錄一次「累計前 20 value / 累計總 value」），累積 60–100 日後驗證早盤 vs 全日相關性
- **Phase 2 候選方向**（GATE 通過後再決定）：
  - 當沖入場過濾器（regime filter）
  - 倉位大小調整訊號（高集中度→放大；低集中度→縮小）
  - 與既有 H079 廣度訊號合併

### Weekday 子分析（條件性）
若 Phase 1 主分析找到顯著訊號（GATE 通過），對「最強的 1–2 個訊號」做 by-weekday 拆分檢視：
- 樣本算術：~2000 交易日 / 5 weekday ≈ 400 天/weekday；對單一訊號維度（5 桶）每桶 80 天，可做；但對 27 格已太薄
- 動機：本專案歷史上有 weekday effect 紀錄（H068 reversal weekday、H071 tuesday vol paradox），故此檢視屬於合理探索
- 操作：先確認主訊號在 pooled 樣本顯著，再分 weekday 看哪一天訊號最強或最弱（特別關注是否與 H071 等既有 weekday 結論一致或衝突）

### 可參考的既有資源
- `stock_day` 表（已存在，2018–2026）：個股日 OHLCV + value
- `market_breadth.total_value`（已存在）：每日大盤總成交金額
- H079 已建立的 `parse_stock_market.py` 可作為類似 ETL 的模板
