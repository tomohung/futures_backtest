# Distribution Research Results: L2 趨勢確立後拉回續攻

## Date
2026-06-14

## Conditions Tested
- 資料：TX 日盤 1 分 K，2021-01 ~ 2026-06（1299 個有 EMA20 的交易日）
- Setup 偵測：L2 門檻（0.497×EMA20）ZigZag 切 leg；leg ext 自錨點達 L2d = 趨勢確立（因果）。
- 拉回：確立後第一個 ≥0.05×EMA20 的回檔（過濾微回）。已直衝到 L3 才首次拉回的 leg 不算可交易 setup。
- Trigger：A=拉回後 1 分 K 站回 5MA、B=突破前峰+1pt、C=A 且站回那根順勢確認 K、**N=確立當下即進（null 對照）**。
- 交易模擬（全因果、掃到收盤）：target=錨±L3d；stop main=拉回極值、alt=錨點。

## Sample
- ≥L2 確立 leg：**N=2523**；其中有拉回 setup：**N=2191（86.8%）**
- 各 trigger 交易數：A≈1798、C≈1745、B≈2064、N≈2497（遠超 GATE 門檻 150）

## Key Findings

### 1. Baseline（達 L2→L3 的條件機率）
| 對照 | reach L3 |
|---|---|
| 無條件（名目） | 50% |
| 達 L2 全體 leg | **58.0%** |
| 達 L2 + 有拉回 | **63.4%**（+5.4pp） |

時間梯度（對照 daystats `_CONT_L3_FROM_L2` 早86%→晚46%，趨勢一致）：
≤09:30 = 66.9% / 09:30–11:30 = 61.5% / >11:30 = 36.4%。

### 2. ★核心：等拉回 vs 不等拉回（同 anchor stop, target=L3）
| Trigger | N | win% | loss% | EV(pt) | avgR |
|---|---|---|---|---|---|
| **N 確立即進（null）** | 2497 | 58.8 | 18.3 | **+4** | 0.04 |
| **A 拉回後 5MA 站回** | 1798 | **72.5** | 8.6 | **+20** | 0.19 |
| C 站回+確認 | 1745 | 72.8 | 8.6 | +20 | 0.19 |
| B 突破前峰 | 2064 | 67.9 | 12.2 | +3 | 0.01 |

**等拉回 + 5MA 站回（A）相對「確立即進」（N），勝率 58.8%→72.5%、EV +4→+20pt、avgR 0.04→0.19，全面碾壓。** 這證明使用者直覺成立：拉回進場不是 tautology，相對正確的 null 有大幅 incremental edge（進場價更好→同停損下更少被掃、R 更高）。

**突破前峰（B）最差**（EV +3、avgR 0.01）——印證「等突破才進＝把 L2→L3 的肉讓掉」。**5MA 站回 ≫ 突破。** C 與 A 幾乎相同 → 額外確認 K 無加值，**可直接用 A**。

### 3. 停損 tight vs wide（trigger A）
| stop | win% | loss% | EV(pt) | avgR |
|---|---|---|---|---|
| main 拉回極值（緊） | 45.4 | 52.1 | +8 | **0.33** |
| alt 錨點（寬） | 72.5 | 8.6 | **+20** | 0.19 |

緊停損：勝率低但 avgR 高、EV +8；寬停損：勝率高、EV 點數高但 avgR 低（risk 大）。**兩者皆正期望**；點數最大化偏寬、風險調整偏緊 → Phase 2 掃中間值（拉回極值 − k）。

### 4. 早盤 edge（trigger A, main stop）
≤09:30 win 55.2% / 09:30–11:30 win 43.9% / >11:30 win 36.3%（N=333 noisy, open 11%）。**早盤勝率最高，呼應「突破多在 9:30 前」與 ladder reach timing。**

### 5. 拉回深度與 MAE
拉回深度中位 26pt（p25=15、p75=47）；trigger A 進場後 MAE 中位 14pt、p75 23pt。→ 停損設在拉回極值外緣（risk ~25–30pt）可保住多數贏家。圖見 `dist_pb_mae.png`。

## Vs. Expected
- 樣本量：遠超預期（2191 vs 門檻 150）。✓
- 條件續攻 > 無條件 base rate：58–63% vs 50%，+8~13pp。✓（但部分已知於 daystats）
- **拉回進場 > naive 進場**：強烈成立（核心新貢獻）。✓
- trigger A > B：成立，且 C 無加值。✓（超出原預期的明確）
- 早盤 edge：成立。✓

## Gate Decision
[x] 進入 Phase 2（使用者裁決 2026-06-14）
[ ] Archive（原因：）
[ ] 修改假設（修改內容：）

> 已通過。建議理由：核心結果（A ≫ N ≫ B、雙停損皆正 EV、早盤 edge）清晰且樣本充足。
> 須在 Phase 2 處理的保留：①交易成本（~2–4pt/筆）未計，緊停損 EV +8 扣成本後變薄；②regime 穩定性（2021–26 跨多 regime，OOS≡高波 confound）；③連敗/drawdown（avgR 僅 0.19–0.33，需看心理資本面）；④單 leg 單筆、停損後再進未模擬（保守）。

## Derived Hypotheses
- H120a：停損最佳化——拉回極值 − k×ATR / 介於緊與錨之間，找 EV×avgR 最佳點。
- H120b：抱長尾——reach L4=28.6%、L5=13.7%；target 改 L3 部分出 + 餘量 trail 博 L4/L5（MFE 中位僅 21pt 但長尾存在）。
- H120c：拉回深度作為濾網——`setups.csv` 已存 pb_depth，檢驗深/淺拉回對續攻率的預測力。
- H120d：regime 分層——按 VIX regime / 已實現波動切，驗證 edge 是否集中在特定 regime（呼應 drawdown 風險在升壓）。
