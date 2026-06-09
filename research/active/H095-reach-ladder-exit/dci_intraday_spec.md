# DCI-intraday v2 — 盤中實證版規格（多空異構、09:15/09:30 雙時點）

> **狀態：Phase-1 實證骨架，非 confirmed（未 OOS）。** v2 以首批盤中資料
> （stock_min，2025-06~2026-02，**上市 TWSE-only**，N=181）的實測重寫 v1 的設計猜想。
> 核心思想（thrust≠breadth、不塌成單一數字）獲證實；但**公式、多空結構、regime gate、
> 決策時點全部被資料改寫**。來源：H095 reach-ladder-exit；與收盤版 `dci_spec.md` 並列。
>
> 實證出處（results/）：`dci_intraday_calibrate.md`、`dci_snapshot_sweep.md`、
> `dci_formula_compare.md`、`dci_universe_sweep.md`、`dci_short_combine.md`。

---

## v1 → v2 changelog（資料推翻/修正了什麼）

| v1 設計猜想 | v2 實證結論（N=181，上市-only） |
|---|---|
| 單一 thrust（權值前20）+ breadth，**對稱雙軸** | **多空根本是不同因子**：多方=集中龍頭 thrust；空方=廣度（幅度+計數） |
| `confirm = breadth·sign(thrust)`，需廣度確認才算 TREND | **多方 breadth 是反指標**（r≈−0.12）；確認閘**反而扣分**，移除 |
| NARROW（高 thrust 低廣度）= 騙線、要 fade | **窄基領漲反而更會延伸**；不該 fade（語意翻轉） |
| 多空「同因子不同權重」(.40/.35/.25 vs .30/.30/.40) | 舊合成實測：dci_long r=+0.15、**dci_short r=−0.16（方向錯）** |
| 空方廣度鑑別力 ≈ 2× 多方（沿用收盤版） | **相反**：多方強(+0.35)、空方弱(+0.24)；空方天生難測 |
| 09:30 單一決策時點 | **時點不對稱**：多方 09:15 已成形、空方 09:30 才成熟 |
| thrust 用權值前20 固定清單；熱門股列為待測 | **動態 value 排名 > 固定清單**；熱門略輸權值（多方） |

---

## 0. 為什麼重設計（v1 動機，仍成立）

收盤版 DCI 三因子（W/H/B）兩個在 09:30 失效/半失效：`sign(收−昨收)` 夾帶隔夜跳空噪音、
`收盤` 拿不到。而 H095 目標 **reach 是 open-anchor**（開盤量到高/低的擺幅）。
`dci_voteset_compare.py`（N=1227）證實：每檔改投**只 sign(收−今開)**，對 open-anchor reach
鑑別力全面提升——**訊號與目標同錨**。盤中版把此升級為原則：**以開盤錨為脊椎**。

v2 補充：實測進一步顯示「同錨」還不夠，**幅度(tanh) 比純 sign 再好一截**（同 universe
多L4 +0.11→+0.27），且**多空要用不同因子**（見 §2）。

---

## 1. 資料依賴與現況

需要：個股**盤中分時**（open + ≤t 現價）算 thrust 與 running 漲跌家數。

### 1.1 資料來源與落地（已部分到位）
- `stock_min` 表（FinMind `TaiwanStockKBar`，分K）。ETL：`download_stock_min.py`→parquet→`load_stock_min.py`。
- **現況**：已載入 2025-06-02~2026-02-26（**上市 TWSE-only**，`--market TWSE`）。
  主下載續抓中（→2026-06）；**TPEX 盤中、2025-06 之前、2026-02-27 缺**（待補）。

### 1.2 breadth 範圍：採**上市-only**（現階段定案）
- 受限於 stock_min 為上市-only，且**「上市 breadth 行不行」本身就是待測項**，
  v2 全程用上市 breadth。τ/β 與空方 B 訊號**日後加 TPEX 須複驗**（caveat 保留）。

### 1.3 校準資料管線
1. 每日重建 09:15 與 09:30 兩個快照：每檔 `(open, price@t)`、running 漲跌家數。
2. 對 open-anchor reach（L3/L4）跑分位/相關（**多空分開**）。
3. 由達標率跳升處定門檻；逐年穩定性 + **OOS** 後才 Confirmed、接出場階梯。

---

## 2. 公式：多空異構（v2 核心）

> 不塌成單一數字（v1 思想保留），但**多空各用不同因子**（v2 實證）：
> **多方要「集中的結構性龍頭」，空方要「廣度」。**

通用個股開盤錨動能（∈ −1~+1）：
```
m_i = tanh( (price@t_i − open_i) / range_i )
range_i = 該股 causal EMA20(日振幅 high−low)   # 跨年自我標準化，與 reach 同尺
```
universe 加權平均：`thrust(U) = Σ sel_i·m_i / Σ sel_i`（sel_i = 選集所用成交值）。

### 2.1 多方訊號 `dci_long`（決策時點 **09:15**）
```
dci_long = thrust(W)    W = 動態「20日均成交值」前 20~50（結構性大型股，value-weighted）
```
- 實測多L4 r ≈ **+0.35**（W-20~50，09:15≈09:30）。**集中**最好：放寬到 100 略降；
  熱門 universe(H) 略輸權值；**動態 value 排名 > 固定21清單**（+0.27→+0.35）。
- **breadth 不進多方公式**（對多方 r≈−0.12，反指標）。
- 無官方比重表 → 用成交值近似權重（caveat）。

### 2.2 空方訊號 `dci_short`（決策時點 **09:30**）
```
dci_short = z(s_thr) + z(s_B)          等權（α=0.50 即 in-sample 最佳，非過擬合）
  s_thr = −thrust(W_wide)   W_wide = 寬權值前 50~100（≈帶幅度的廣度）
  s_B   = −(up−down)/active  全 TWSE 上市 running 家數
```
- 單一各 r≈+0.186；**等權合成 r≈+0.24、AUC 0.64**。兩者相關僅 +0.23 → **真互補**
  （s_thr=少數龍頭殺多兇；s_B=多少檔在跌）。「兩者皆高」格達標率 39% vs base 21.5%。
- **空方 09:15 還弱、09:30 才成熟**；窄龍頭對空方無效，**需要寬 universe / 家數**。
- z 標準化在 live 需用 rolling 統計（實作細節，§6）。

---

## 3. Regime 與方向（v2 修正：移除確認閘）

v1 的 `confirm` 確認閘與 NARROW=fade 被實證推翻（多方 breadth 反指標）。v2 簡化為
**各邊用自己的訊號直接定強度**：

```
# 方向（10:00 前該站哪邊；實測 sign(thrust) 命中：09:15 強thrust 77%、09:30 82%）
dir = sign(dci_long_thrust)            # 多方 thrust 的符號即方向最佳預測

# reach 強度 → 出場階梯
long_strength  : dci_long  ≥ τ_L  → 高延伸機率（放階梯跑到 L4/L5）
short_strength : dci_short ≥ τ_S  → 高下行延伸（空單放階梯 / 多單緊收）
否則 → CHOP（力道不足，緊出場 L3 內收）
```

- `τ_L`、`τ_S`：**待定切點**。實證指引：多 L4 forward 力道五分位在頂兩分位明顯跳升
  （09:15 達 51%）；空方 z-sum 頂段達標率 ~39%。確切數值待 OOS 後固定。
- **NARROW 不再 fade**：高 thrust + 低 breadth 反而延伸機率更高，併入 long_strength。
- 多空**分開**校（門檻、甚至 universe 寬度都不同）。

| 訊號狀態 | 語意 | 出場階梯傾向 |
|---|---|---|
| dci_long ≥ τ_L | 龍頭集中拉抬（含窄基） | 放階梯跑，目標 L4/L5、寬 trail |
| dci_short ≥ τ_S | 全面性賣壓（幅度+家數） | 空單放跑 / 多單提早了結 |
| 皆 < τ | 力道不足 | 緊出場，L3 內收 |

---

## 4. 與 H095 出場階梯的接點（TODO，下一步 B）

`reach ladder` L3/L4/L5 的 trail/了結粒度對齊後補。下一步將把本 regime 真接上
出場階梯，在 181 天交易層面驗證有沒有用（spec §4 → 研究下一步）：
- long_strength 高 → `TODO：起始 trail 階 / 目標上限階`
- short_strength 高 → `TODO：空單放跑階 / 多單提早了結階`
- CHOP → `TODO：強制了結階`

---

## 5. Pseudocode（v2）

```python
import math, numpy as np

def m_i(price_now, open_, ema20_range):
    if not ema20_range or ema20_range <= 0:
        return None
    return math.tanh((price_now - open_) / ema20_range)

def thrust(rows):                      # rows: [(price_now, open, ema20_range, sel_value)]
    num = den = 0.0
    for p, op, rng, w in rows:
        m = m_i(p, op, rng)
        if m is None or not w or w <= 0:
            continue
        num += m * w; den += w
    return num / den if den else 0.0

def dci_long(weight_rows_0915):        # W = 20日均值前 20~50（value-weighted）
    return thrust(weight_rows_0915)

def dci_short(wide_rows_0930, up, down, active, zstat):
    s_thr = -thrust(wide_rows_0930)               # 寬權值前 50~100
    s_B   = -((up - down) / active) if active else 0.0
    # z：用 rolling 統計（mean/std）標準化，等權相加
    return zstat.z('thr', s_thr) + zstat.z('B', s_B)

# 方向：sign(dci_long)；強度：dci_long≥τ_L / dci_short≥τ_S（τ 待 OOS 定）
```

---

## 6. 校準計畫（部分完成；OOS 待資料）

- ✅ **已完成（Phase-1，N=181 上市-only）**：多空因子鑑別力、universe×寬度、時點、空方合成。
- ⏳ **待做**：
  1. **τ_L、τ_S 切點固定**：由達標率跳升處定，多空分開。
  2. **z 標準化的 live 化**：rolling window 的 mean/std（避免 look-ahead）。
  3. **擴樣本 + OOS**：等主下載到 2026-06、回補 2025-06 之前；目標往 N≈1200 靠，
     **必須 out-of-sample** 才能 Confirmed、晉升 live。
  4. **加 TPEX 後複驗**空方 B / 寬權值訊號是否穩定。

---

## 7. 註記與待辦

- **時點不對稱**是 feature：多方 09:15 決策、空方 09:30；可分別觸發不同階梯動作。
- 方向預測（§3 dir）是本批最具操作價值的副產物（強 thrust 09:30 對 10:00 前方向 82%），
  但 `dir_10` 含部分既成擺幅（套套邏輯），以 `dir_full`（58% vs 53% base）為較乾淨估計。
- 開放參數：W 寬度（多 20~50 / 空 50~100）、`range_i` EMA span、`τ_L/τ_S`、z window、權重來源。
- 野心版（路徑/加速度、08:45→09:30 斜率）待本版站穩再評估。
