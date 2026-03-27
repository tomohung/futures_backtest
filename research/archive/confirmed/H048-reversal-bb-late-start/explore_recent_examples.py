"""
H048: Show recent examples of early BB latch trades.
"""

from datetime import time as dtime
import numpy as np
import pandas as pd
from backtesting import Backtest
from src.backtest.runner import load_data_for_reversal
from src.strategies.reversal import ReversalStrategy


def main():
    print("Loading data...")
    df = load_data_for_reversal()

    trade_log = []

    class DetailedReversal(ReversalStrategy):
        def _reset_daily(self):
            super()._reset_daily()
            self._first_latch_time = None
            self._first_latch_dir = None
            self._latch_price = None
            self._bb_val = None

        def next(self):
            was_long = self._bb_long_touched
            was_short = self._bb_short_touched
            was_entered = self._entered

            super().next()

            cur_ts = self.data.index[-1]
            cur_date = cur_ts.date()
            cur_time = cur_ts.time()
            close = float(self.data.Close[-1])

            # Detect first latch
            if self._first_latch_time is None:
                if not was_long and self._bb_long_touched:
                    self._first_latch_time = cur_time
                    self._first_latch_dir = "long"
                    self._latch_price = close
                    self._bb_val = float(self.data.BB_Lower[-1])
                elif not was_short and self._bb_short_touched:
                    self._first_latch_time = cur_time
                    self._first_latch_dir = "short"
                    self._latch_price = close
                    self._bb_val = float(self.data.BB_Upper[-1])

            # Detect entry
            if not was_entered and self._entered:
                trade_log.append({
                    "date": cur_date,
                    "latch_time": self._first_latch_time,
                    "latch_price": self._latch_price,
                    "bb_val": self._bb_val,
                    "entry_time": cur_time,
                    "entry_price": close,
                    "direction": "long" if self.position.is_long else "short",
                })

    bt = Backtest(df, DetailedReversal, cash=1_000_000, commission=0.00004,
                  exclusive_orders=True, trade_on_close=True)
    stats = bt.run()

    # Merge PnL from backtesting.py trades
    bt_trades = stats["_trades"].copy()
    bt_trades["trade_date"] = pd.to_datetime(bt_trades["EntryTime"]).dt.date
    bt_trades["exit_time"] = pd.to_datetime(bt_trades["ExitTime"]).dt.strftime("%H:%M")
    bt_trades["exit_price"] = bt_trades["ExitPrice"]

    for rec in trade_log:
        match = bt_trades[bt_trades["trade_date"] == rec["date"]]
        if not match.empty:
            row = match.iloc[0]
            rec["exit_time_str"] = row["exit_time"]
            rec["exit_price"] = row["exit_price"]
            rec["pnl"] = row["PnL"]

    # Show recent examples
    early = [t for t in trade_log if t.get("latch_time") and t["latch_time"] < dtime(9, 5)]
    late = [t for t in trade_log if t.get("latch_time") and t["latch_time"] >= dtime(9, 5)]

    def show(trades, n=3):
        for t in trades[-n:]:
            pnl = t.get("pnl")
            result = ""
            if pnl is not None:
                result = "WIN" if pnl > 0 else "LOSS"
            print(f"  日期：{t['date']}")
            print(f"  方向：{t['direction']}")
            print(f"  BB Latch：{t['latch_time'].strftime('%H:%M')}  price={t['latch_price']:.0f}  BB={t['bb_val']:.0f}")
            print(f"  進場：{t['entry_time'].strftime('%H:%M')}  price={t['entry_price']:.0f}")
            if "exit_time_str" in t:
                print(f"  出場：{t['exit_time_str']}  price={t['exit_price']:.0f}  PnL={pnl:+.0f} ({result})")
            print()

    print(f"\n早期 BB Latch (< 09:05) 最近 3 筆：\n")
    show(early, 3)

    print(f"晚期 BB Latch (≥ 09:05) 最近 3 筆（對照）：\n")
    show(late, 3)


if __name__ == "__main__":
    main()
