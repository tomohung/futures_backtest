# Chart-UI 關卡圓點：波段重新上膛（re-arm per swing）

日期：2026-06-13
狀態：設計定稿（方案 B）

## 問題

chart-ui 主圖的 L1–L5「關卡觸及圓點」由 `daystats._collect_touches` 產生：以當日
累計 running low/high 為單一錨點，每階只記**第一次**觸及（`done` 集合永久標記）。

後果：同一天第二段以後的同向波段，若該階早已被前一段觸發，就不再畫。
實例 2026-06-11：08:45→09:16 上攻已點亮多方 L1–L3，10:31 從新低 42050 再起的
第二波上攻（+1337）拿不到任何多方圓點。

## 需求

每當出現一段新的同向波段，該方向 L1–L5 以該波段極值為新錨點**重新上膛**、可再次觸發
（畫出新一組圓點）。空方對稱（新的下行波段以波段高點重置）。

## 方案決策（B：每波段重算，錨＝波段極值）

評估過三案：

- **A（僅當日新極值才重算）**：因果、最簡，但**漏掉 higher-low / lower-high 波段**。
  2026-05-27 leg3（09:37 從 44658 起 +641 上攻，非當日新低）在 A 下「一顆圓點都沒有」。否決。
- **B（每波段重算）**：用與 L3 波段相同的 zigzag（L2 反轉門檻）取轉折，每段以波段極值為錨
  重新上膛。抓得到 5/27 leg3。錨點屬事後可知，但**圓點本身是真實觸及事件**。
- **C（B + 因果時序）**：把次級波段的 L1/L2 延到「≥L2 反轉確認」時點才顯示。

關鍵事實：chart-ui 的「覆盤」只畫 09:30/10:30/11:30 參考線，**不逐根隱藏未來 K**
（整天資料恆在畫面上）。因此 C 唯一的價值（拉時間軸不爆雷）在本 app 用不到，
反而會把 L1/L2 延後並擠在同一時點、更難讀。**故採 B**：每顆圓點畫在價格真正碰到的時點。

B 與 L3 波段同源（同一組 zigzag 轉折），圓點錨點 = 波段斜線起點，互相印證。
（L3 斜線只顯示淨幅 ≥L3 的段；圓點顯示每一波實際碰到的關卡，含只到 L1/L2 的小波段——刻意。）

## 設計

只動後端 `src/chart_ui/services/daystats.py`。前端 `applyTouchMarkers` 不變
（本就遍歷 `touches.bull/bear` 陣列逐點畫，多錨點只是陣列變長、同階可重複）。
不加水平關卡線、不動右側欄關卡價清單、不改 L3 波段顯示。

### 演算法

新增純函式 `_rearm_touches(bars, levels, l2_dist)`（bars=[(minute,high,low)] 昇冪）：

1. `legs = zigzag_legs(bars, threshold=l2_dist)`（**不套 L3 最小幅度**；`zigzag_legs`
   延遲 import 自 `swing_legs`，避免與 daystats 的循環依賴）。
2. 每一段 leg：錨 = `leg.start_price`（up-leg=波段低、down-leg=波段高），視窗 = `[start_min, end_min]`。
   段內逐根累計同向 excursion，每階在 excursion 首次 ≥ dist 時記一筆
   `{level, price: round(anchor±dist), time, minute}`。**done 集合 per-leg**（每段重新上膛）。
3. **Fallback**：`legs` 為空（當日無任何 ≥L2 反轉，極小波動日）→ 退回原單一 running 錨點邏輯
   （抽成 `_running_anchor_touches`），確保 L1/L2 仍畫、不回歸成空白。

`_collect_touches(conn, sel, levels)` 改為：查日盤 bars → 取 `dict(levels)["L2"]` 當 l2_dist
→ 呼叫 `_rearm_touches`。回傳結構不變。

### 副作用處理

- 同一階一天可能多筆（不同波段、不同錨價）→ 即所求，前端照畫。
- `compute_daystats` 內 `exit_advice` 吃「每階觸及分鐘」：改以**最早一次**取值
  （`setdefault` over 已按 minute 昇冪排序的 touches），維持原首觸語意，不被多錨點打亂。

## 測試

- `tests/chart_ui/test_collect_touches.py`：既有（單向上漲日，單段）→ 行為不變，續綠。
- 新增純函式單元測試：W 形（低→高→更低→更高）合成 bars，驗證同階出現多筆、錨價不同、
  分屬不同波段；另測 fallback（無 ≥L2 反轉時退回單錨）。
- `tests/chart_ui/test_exit_advice.py`：不受影響（直接測 `_exit_advice`）。

## 不做（YAGNI）

水平關卡線、C 的因果時序、右側欄關卡價清單改動、L3 斜線邏輯改動。
