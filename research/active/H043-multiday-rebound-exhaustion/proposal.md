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
