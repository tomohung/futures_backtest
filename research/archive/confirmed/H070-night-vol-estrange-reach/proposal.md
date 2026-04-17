# Proposal: Night Vol → EstRange Reach Rate

## ID
H070

## Derived From
H066/H067（夜盤波動濾網）的延伸——從「策略勝率」回到更基本的問題：夜盤波動影響日盤振幅本身

## Trading Intuition
H066/H067 證明夜盤波動影響策略績效，但原因是什麼？最基本的可能性是：夜盤波動直接影響日盤能不能走到 EstRange。如果夜盤大波動後日盤更容易觸及甚至超過 EstRange，那所有依賴 EstRange 的策略（EstHL 的 SatZone、EstRange Spread 的 credit capture）都會受益。

目前 EstRange Spread 用星期加權（Tue/Wed fraction=0.75 vs others=0.618），但也許真正該加權的基準是前一晚夜盤波動，而非星期幾。

## Hypothesis
1. 日盤 HL / EstRange 的觸及率（reach rate）與前晚夜盤 night_norm 正相關
2. 夜盤高波動（norm >= 1.0）的日子，日盤更容易觸及或超過 1× EstRange
3. 夜盤波動對 reach rate 的解釋力優於星期加權

## Expected Distribution
- 夜盤高波動組（norm >= 1.0）：reach rate > 70%，mean HL/EstRange > 0.9
- 夜盤低波動組（norm < 0.85）：reach rate < 55%，mean HL/EstRange < 0.8
- 差異在多數年份穩定

## Invalidation Condition
- 高低組 reach rate 差異 < 10%
- 跨年方向不一致（< 4/6 年）
- 星期加權的解釋力仍優於夜盤波動

## Notes
- EstRange 定義：`estimate_hl.py` 中的 est_avg（slot-level running average）
- Reach rate 定義：日盤 (High - Low) >= EstRange 的比例
- 也分析超過 1× 的頻率（HL/EstRange > 1.0, 1.2, 1.5）
- 交叉分析：night_norm × weekday，確認哪個解釋力更強
