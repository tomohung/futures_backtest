"""
Estimated H-L Split Exit Mixin — partial close at SatZone + trailing stop for remainder.

H031 Phase 2: Instead of closing 100% at SatZone, close `satzone_exit_portion` at
SatZone (Phase 2 = 5MA confirmation), then trail the remainder with a stop at
`trail_ema_fraction × EmaHL` below the highest high since touch.

Usage
-----
    class MyStrategy(EstimateHLSplitExitMixin, Strategy):
        satzone_exit_portion: float = 0.5  # 50% at SatZone, 50% trailing
        trail_ema_fraction: float = 0.3    # trailing stop = 0.3 × EmaHL

        def init(self):
            self._init_estimate_hl_exit()

        def next(self):
            self._record_bar()
            if self.position.is_long:
                exit_action = self._check_long_split_exit()
                if exit_action == "partial":
                    self.position.close(portion=self.satzone_exit_portion)
                elif exit_action == "full":
                    self.position.close()
"""

from collections import deque

import numpy as np

from src.strategies.estimate_hl_exit import EstimateHLExitMixin


class EstimateHLSplitExitMixin(EstimateHLExitMixin):
    """Mixin: partial close at SatZone, trailing stop for remainder.

    Adds on top of EstimateHLExitMixin:
      - satzone_exit_portion: fraction to close at SatZone (0.0–1.0)
        - 1.0 = original behavior (close all at SatZone)
        - 0.5 = close 50% at SatZone, trail remaining 50%
      - trail_ema_fraction: trailing stop distance as fraction of EmaHL
    """

    def _reset_estimate_hl_exit(self) -> None:
        super()._reset_estimate_hl_exit()
        self._split_partial_done: bool = False
        self._trail_highest: float = -np.inf
        self._trail_lowest: float = np.inf

    def _check_long_split_exit(self) -> str | None:
        """Return 'partial', 'full', or None.

        - 'partial': SatZone Phase 2 triggered, close satzone_exit_portion
        - 'full': trailing stop hit on remainder, close everything
        - None: no exit
        """
        portion = getattr(self, "satzone_exit_portion", 1.0)
        trail_frac = getattr(self, "trail_ema_fraction", 0.3)

        # portion=1.0 → original behavior
        if portion >= 1.0:
            if self._check_long_exit():
                return "full"
            return None

        close = float(self.data.Close[-1])
        high = float(self.data.High[-1])

        if not self._split_partial_done:
            # Phase 1+2: wait for SatZone touch + 5MA confirmation
            if self._check_long_exit():
                self._split_partial_done = True
                self._trail_highest = high
                return "partial"
            return None

        # Partial already done → trail the remainder
        self._trail_highest = max(self._trail_highest, high)

        ema_hl = float(self.data.EmaHL[-1])
        if np.isnan(ema_hl) or ema_hl <= 0:
            return None

        trail_stop = self._trail_highest - trail_frac * ema_hl
        if close < trail_stop:
            return "full"

        return None

    def _check_short_split_exit(self) -> str | None:
        """Mirror of _check_long_split_exit for short positions."""
        portion = getattr(self, "satzone_exit_portion", 1.0)
        trail_frac = getattr(self, "trail_ema_fraction", 0.3)

        if portion >= 1.0:
            if self._check_short_exit():
                return "full"
            return None

        close = float(self.data.Close[-1])
        low = float(self.data.Low[-1])

        if not self._split_partial_done:
            if self._check_short_exit():
                self._split_partial_done = True
                self._trail_lowest = low
                return "partial"
            return None

        self._trail_lowest = min(self._trail_lowest, low)

        ema_hl = float(self.data.EmaHL[-1])
        if np.isnan(ema_hl) or ema_hl <= 0:
            return None

        trail_stop = self._trail_lowest + trail_frac * ema_hl
        if close > trail_stop:
            return "full"

        return None
