# dci_long 調節 H095 出場 — 交易效果（B，指示性）

> 腳本 `dci_exit_modulate.py`，輸出 `dci_exit_modulate.txt` / `_trades.csv`。
> 重用 phase2_path_backtest 的 EstHL long-only 進場 + L1/L2/L3 階梯。
> **窗內 N=44（2025-06~2026-02），in-sample，區間偏多頭 → 指示性，非 confirmed。**

## ① dci_long@09:15 對「實際交易」的排序力 —— 強，這是真價值
| | corr |
|---|---|
| dci_long vs MFE(進場後最大有利擺幅, 點) | **+0.529** |
| dci_long vs 到 L4 | +0.477 |
| dci_long vs trail pnl | +0.499 |

| 分組(中位切) | N | 到L3 | 到L4 | MFE均(點) | fixed均pnl |
|---|---|---|---|---|---|
| **dci_long 高** | 22 | 68% | **50%** | 223 | **+45.8** |
| dci_long 低 | 22 | 18% | **9%** | 87 | **−30.5** |

→ **dci_long@09:15 真的能分辨「這筆會不會跑」**：高分組到 L4 達 50%（低分組只 9%）、
每筆 fixed 期望值 +45.8 vs −30.5。訊號在**交易層級**有料，不只 TX 指數層級。

## ② 但「切換出場模式(fixed↔trail)」沒用 —— 修正調節方向
| 出場政策（窗內 44 筆，點） | 總 | 均 | 勝率 |
|---|---|---|---|
| 全 fixed（收 L3） | **336** | 7.6 | 23% |
| 全 trail(5ma) | 248 | 5.6 | 32% |
| 調節：高→trail / 低→fixed | 219 | 5.0 | 30% |
| 反向對照：高→fixed / 低→trail | **365** | 8.3 | — |

- **fixed 在高、低兩組都贏 trail**（高組 fixed 45.8 > trail 40.5）→ 我「高分組放 trail 博延伸」的調節**反而扣分**，反向更好。
- 原因＝**trail 回吐**（與既有 l4_trim「trim/hold EV 中性」、memory「trail 回吐是入場費」一致）：
  就算當天會到 L4，5ma trail 把延伸利潤吐回去，不如 fixed 在 L3 直接落袋。
- **結論：dci_long 不是「出場模式開關」，切換 fixed/trail 是錯的槓桿。**

## ③ 真正的槓桿是「進場篩選 / 加碼」，不是出場模式
- 高 dci_long 22 筆 fixed 總 ≈ **+1008 點**（均 45.8）；低 dci_long 22 筆 ≈ **−671 點**（均 −30.5）。
- **低 dci_long 那半就是賠錢的一半**。用 dci_long@09:15 把它濾掉 / 縮手，留高分組打 fixed-L3，
  才是訊號的正確用法（窗內把總損益從 336 拉到 ~1008，且砍掉一半爛單）。
- **dci_short 是額外逆風濾網**：dci_short 高時 long 單 到L4=23%、trail均 −22.6；低時 36%、+33.9。

## 對 spec §4 的修正
v2 spec §4 假設「regime → 出場階梯行為」。實測（此窗）顯示**價值在進場端**：
- regime（dci_long 高/低、dci_short 逆風）→ **進場篩選 + 部位大小**，出場維持 fixed-L3。
- 出場端唯一還沒測、且可能有用的變體：**高 dci_long 把目標從 L3 抬到 L4（bank L4，非 trail）**，
  避開 trail 回吐又吃延伸 → 列為下一步。

## 限制 & 下一步
- N=44、in-sample、偏多頭、單一出場槓桿。**擴樣本(→2026-06 + 回補) + OOS** 才能定論。
- 下一步候選：(a) 把 dci_long/dci_short 做成**進場濾網**，在能算 dci 的窗內看篩選後績效；
  (b) 測「高 dci_long → 目標抬到 L4(bank)」出場變體；(c) 等資料擴充做 OOS。
