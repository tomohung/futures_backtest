# DCI-intraday v1 — 盤中雙軸版規格（09:30 讀數，驅動出場階梯）

> 設計 spec，**非 confirmed 結果**。把 DCI 從「收盤事後標籤」重設計成
> 「09:30 盤中即時、驅動 H095 出場階梯」的版本。核心轉變：盤中只剩「開盤錨」
> 這根脊椎，因此放棄收盤版的 sign(收−昨收) 票，改以**開盤錨動能 + 全市場廣度**
> 兩條正交軸合成。
> 來源：H095 reach-ladder-exit；與收盤版 `dci_spec.md` 並列。

---

## 0. 為什麼要重設計（而不是直接搬收盤版）

收盤版 DCI 的三因子（W/H/B）有兩個在 09:30 失效或半失效：

| 因子（收盤版） | 09:30 盤中可得性 |
|---|---|
| `sign(收 − 昨收)` | 拿得到，但夾帶**隔夜跳空**——跳空發生在開盤前，與「開盤後台指往哪衝多遠」無關，純噪音 |
| 成交值前 20 名單（H） | **半失效**：排名 09:30 還在洗，且有 look-ahead 味 |
| 當日收盤（W/H 的 last） | **拿不到** |
| 漲跌家數（B） | 拿得到，09:30 仍在變動但方向已具參考性 |

而 H095 的目標 **reach 是 open-anchor**（從當日開盤量到高/低的擺幅）。實證
（`dci_voteset_compare.py`，N=1227，2020-12~2026-06）顯示：把每檔投票從
「sign(收−昨收)+sign(收−今開)」改成**只投 sign(收−今開)**，對 open-anchor reach
的鑑別力在每一項指標都提升（point-biserial 多方 +0.389→+0.445、空方 −0.503→−0.537；
強帶命中、十分位單調性一致變好）。原因是**訊號與目標同錨**。

盤中版把這個發現升級成原則：**以開盤錨為脊椎**，並保留「幅度」與「廣度確認」
兩個收盤版看不到的維度。

---

## 1. 前置依賴（擋路的真瓶頸）

本規格在現有資料下**一行都驗證不了**。`stock_day` 只有日線。盤中版需要：

- 約 40 檔（權值前 20 + 視需要擴充）的**盤中分時價**，至少 09:30 一個定點快照（逐分更佳）。
- 全市場 **running 漲跌家數**（up/down/listed）在 09:30 的當下值。

→ 校正前必須先界定並開始蒐集此盤中快照流（另立資料規格）。本文件的所有門檻與
權重均標示為 `待盤中資料校正`。

---

## 2. 兩條正交軸（皆 09:30 即時、∈ −1 ~ +1）

刻意**不**塌成單一數字。「2330 一根猛拉但廣度不跟」與「全市場鎖死同方向」
會給出同一個舊式 DCI 值，但對出場階梯是相反決策——這是收盤版最大盲點。

### Axis 1 — Thrust（方向 × 幅度）

權值龍頭「離開今天開盤多遠、多用力」。

**每檔個股的開盤錨動能**（∈ −1 ~ +1）：
```
m_i = tanh( (price_now_i − open_i) / range_i )
```
- `range_i` = 該股 causal EMA20(日振幅 high−low)——跨年自我標準化，與 reach 目標同一把尺。
- `tanh` 飽和化：保留幅度資訊（勝過收盤版的純 sign），又防少數爆量股綁架。
- **不做全日→早盤的縮放係數 κ**（設計決策）：thrust 是相對指標，09:30 偏小不影響
  排序與門檻校正；省去一個自由參數。

**Thrust**（權值加權平均）：
```
thrust = Σ w_i · m_i / Σ w_i        (i ∈ 權值前 20；w_i = 權重，初版用成交值近似)
```

### Axis 2 — Breadth（廣度確認）

這波是不是**全市場**一起動，還是少數權值獨拉。直接複用收盤版 B，取 09:30 即時值：
```
breadth = (up_count − down_count) / listed_count     (全市場 running，09:30 當下)
```
（設計決策：用**全市場漲跌家數**，而非「權值股之間的同向一致性」——代表更廣的
參與度，且複用既有 breadth 基礎設施。）

---

## 3. Regime 分類器（餵給出場階梯）

```
confirm = breadth · sign(thrust)        # 廣度有沒有站在 thrust 那一邊（同向為正）

if |thrust| ≥ τ and confirm ≥ β:   TREND    # 真趨勢日：全市場確認的單向力道
elif |thrust| ≥ τ and confirm < β: NARROW   # 窄基拉抬：龍頭動但廣度不跟，脆弱
else:                              CHOP     # 盤整：力道不足
```

| Regime | 語意 | 出場階梯傾向 |
|---|---|---|
| TREND | 廣度確認的單向趨勢 | 放階梯跑，目標放寬到 L4/L5、寬 trail |
| NARROW | 龍頭獨拉、廣度不跟 | 視為騙線，提早了結 / 不追 |
| CHOP | 力道不足 | 緊出場，L3 內收 |

- `τ`（thrust 門檻）、`β`（confirm 門檻）：**待盤中資料校正**。沿用收盤版同套方法
  （對 open-anchor reach 做 point-biserial / 強帶命中 / 十分位單調性），多空**分開**校。
- 多空不對稱原則沿用收盤版 §5：空方廣度鑑別力約為多方 2 倍，預期 `β` 在空方可較寬鬆。

---

## 4. 與 H095 出場階梯的接點

Regime → 階梯行為的精確對應，需對齊現行 L3/L4/L5 階梯的決策粒度（哪一階開始
trail、哪一階強制了結）。**此節結構已定，細節 TODO**，待與階梯實作對齊後補：

- TREND → `TODO：起始 trail 階 / 目標上限階`
- NARROW → `TODO：提早了結觸發階`
- CHOP → `TODO：強制了結階`

---

## 5. Pseudocode

```python
import math

def dci_intraday(weight_rows, breadth, tau, beta):
    """
    weight_rows : list[(price_now, open, ema20_range, weight)]  權值前20，09:30 快照
    breadth     : (up_count, down_count, listed_count)          全市場 09:30 running
    tau, beta   : 門檻（待盤中資料校正）
    """
    num = den = 0.0
    for p, op, rng, w in weight_rows:
        if rng and rng > 0:
            m = math.tanh((p - op) / rng)
            num += m * w; den += w
    thrust = num / den if den else 0.0
    bdth = (breadth[0] - breadth[1]) / breadth[2] if breadth[2] else 0.0
    confirm = bdth * (1 if thrust > 0 else -1 if thrust < 0 else 0)

    if abs(thrust) >= tau and confirm >= beta:
        regime = "TREND"
    elif abs(thrust) >= tau:
        regime = "NARROW"
    else:
        regime = "CHOP"
    return {"thrust": thrust, "breadth": bdth, "confirm": confirm, "regime": regime}
```

---

## 6. 校正計畫（上線前必做，對齊鐵律 OOS）

1. 蒐集盤中 09:30 快照流（見 §1），累積足量交易日。
2. 對「當日是否達 open-anchor L3 / L4」做 thrust、breadth、confirm 的分位 / 迴歸分析
   （多、空分開），沿用 `dci_voteset_compare.py` 框架。
3. 由「達標機率明顯跳升」處定 `τ`、`β`；逐年檢查穩定性（尤其多方窄幅多頭年）。
4. **必須 out-of-sample 驗證**才能標記 Confirmed、晉升 live。

---

## 7. 註記與待辦

- 本版只用權值前 20 算 thrust；是否補回「熱門股」universe（用**昨日**成交值前 20，
  保因果）為 thrust 的第二來源，列為後續可測項。
- κ 已刻意省略（§2）；若校正發現 09:30 thrust 動態範圍過窄、門檻難定，再考慮加回。
- 路徑/加速度（08:45→09:30 consensus 斜率）與 W-vs-B 確認閘為「野心版（方向 C）」
  的加值項，待本雙軸版站穩後再評估。
- 開放參數一覽：`range_i 的 EMA span`、`τ`、`β`、權重來源（權重表 vs 成交值近似）。
