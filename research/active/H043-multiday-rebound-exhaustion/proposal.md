# Proposal: Multi-Day Rebound Exhaustion

## ID
H043

## Derived From
S002-reversal + S003-exhaustion（H036）概念延伸

## Trading Intuition
連續大跌後出現反彈，價格回到昨日/前日成本之上，30 分 K BB%B(open) > 1。但均線方向仍向下，代表中期趨勢尚未改變。此時反彈本身已走到極端（BB%B > 1），是反彈竭盡的訊號，適合順原趨勢做空。

反之，連續大漲後回調，價格跌到昨日/前日成本之下，BB%B(open) < 0，均線仍向上，回調竭盡，適合順原趨勢做多。

與 H042 的差異：H042 先看 30 分 K BB%B 是否極端，再 bypass MA 方向；H043 先看價格是否在昨/前日成本之上但 MA 仍向下（多日趨勢未改變），再用 1 分 K BB%B 極端作為反彈竭盡的進場訊號。

## Hypothesis
當價格在昨/前日成本之上但 30 分 K MA 方向仍向下時，若 1 分 K BB%B > 1（反彈推到極端），做空的勝率與期望值優於一般 Reversal 交易。反之，價格在昨/前日成本之下但 MA 仍向上，1 分 K BB%B < 0 時做多亦然。

## Expected Distribution
- BB%B 極端且 MA 方向與 BB%B 相反（BB%B > 1 + MA↓ 或 BB%B < 0 + MA↑）的出現頻率
- 這些情境下的日內反轉幅度（MFE）應較一般 Reversal 大
- 因為順 MA 方向交易，勝率預期高於 H042（逆 MA）

## Invalidation Condition
- 樣本數過少無法得出結論（門檻待 Phase 1 後決定）
- 勝率 < 40% 或 PF < 1.0
- 反彈竭盡後未出現有效反轉（MAE > MFE），代表反彈延續而非竭盡

## Notes
- 進出場沿用 Reversal 策略邏輯（BB latch + trigger + SatZone exit）
- 核心差異在進場情境：BB%B 極端 + MA 方向一致 = 反彈/回調竭盡
- 與 S003 Exhaustion 的差異：Exhaustion 要求夜盤創新高/低 + ORB 反向突破；H043 使用 Reversal 的 BB latch + trigger 機制
- 「昨/前日成本」可用 VWAP 或收盤價定義，Phase 1 時再決定

### H044 實盤比對的相關發現
H044 分析了 Reversal 實盤 vs 回測差異（2024/11~2026/03）：
- 48 筆「實盤有做、回測沒做」中，最大宗是 **TRIGGER_MISSED（31 筆，87% 勝率，+3,385 pts）**
  - 方向對、BB 有 setup，但 MA5 crossing + CCD/exhaustion 觸發條件未同時滿足
  - 使用者能以肉眼確認轉折，不需所有條件同時滿足
- 另有 12 筆 DIR_BLOCKED：BC zone + MA 方向與實盤相反
  - 單純放寬 BC zone 在回測中幾乎無效（+24 pts / 5 年）
  - 放寬 outside 方向反而讓 PF 下降
- → H043 的「多日趨勢 + 反彈竭盡」框架可能是比「單純放寬方向」更好的解法：它不是無條件放寬，而是在特定多日情境下（BC zone 位置 + MA 方向 + BB%B 極端）賦予更高信心的進場理由
- 詳見：`research/active/H044-reversal-live-vs-backtest/results/distribution.md`
- **驗證基準**：H043 完成後，應回頭比對 H044 的 live-only 清單（22 筆 TRIGGER_MISSED，91% 勝率），確認是否成功捕捉到這些實盤交易
