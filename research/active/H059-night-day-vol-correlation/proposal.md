# Proposal: Night-Day Volatility Correlation

## ID
H059

## Derived From
Origin

## Trading Intuition
夜盤波動大的日子，隔天日盤是「延續」（繼續大波動）還是「消耗」（能量用完，日盤反而縮小）？
若存在穩定的相關性，可在日盤開盤前根據夜盤振幅調整當日策略參數（如 EstRange、停損幅度）。

## Hypothesis
夜盤振幅（15:00~05:00 的 H-L）與隔天日盤振幅（08:45~13:45 的 H-L）
存在正相關（r > 0.3），即夜盤波動大 → 隔天日盤也傾向波動大。

## Expected Distribution
- 散佈圖呈現正相關趨勢
- 將夜盤振幅分 quartile 後，Q4（最大波動）組的日盤振幅中位數 > Q1 組的 1.3 倍以上
- 可能存在非線性：極端夜盤波動後日盤反而收斂

## Invalidation Condition
- Pearson / Spearman 相關係數 < 0.2 且 p > 0.05
- 或 quartile 分組後日盤振幅無單調趨勢

## Notes
- 夜盤定義：前一天 15:00 ~ 當天 05:00
- 日盤定義：當天 08:45 ~ 13:45
- 配對方式：同一個「交易日」的夜盤 + 日盤
- 需排除夜盤無資料或成交量極低的日子
