"""列出最近 10 次交易的詳細資訊"""

from backtest import MorningDipReversalStrategy, load_data
from backtesting import Backtest

df = load_data(start="2025-01-01")
bt = Backtest(df, MorningDipReversalStrategy,
              cash=200_000, commission=0.0, trade_on_close=True)

params = dict(
    bb_period=15, bb_std=2.0, ma5_period=5,
    kd_period=9, kd_smooth=3, kd_threshold=20.0,
    sl_pct=0.3, tp_pct=0.6, use_bb=True, use_kd=False,
)
stats = bt.run(**params)
trades = stats["_trades"]

print("最近 10 次交易:")
print(f"{'日期':>12s}  {'進場時間':>10s}  {'出場時間':>10s}  {'進場價':>8s}  {'出場價':>8s}  {'損益':>8s}")
print("-" * 70)

for _, t in trades.tail(10).iterrows():
    entry_time = t["EntryTime"]
    exit_time = t["ExitTime"]
    entry_price = t["EntryPrice"]
    exit_price = t["ExitPrice"]
    pnl = t["PnL"]
    sign = "+" if pnl > 0 else ""
    print(f"{entry_time.strftime('%Y-%m-%d')}  {entry_time.strftime('%H:%M'):>10s}  "
          f"{exit_time.strftime('%H:%M'):>10s}  {entry_price:>8.0f}  {exit_price:>8.0f}  "
          f"{sign}{pnl:>7.0f}")
