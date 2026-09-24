"""LAKSHMI strategy engine.

Importing this package registers every strategy, so `available()` and
`build()` work without the caller knowing which modules exist.
"""
from .base import (AVOID, BUY, HOLD, SELL, MarketContext, Signal, Strategy,
                   StrategyResult, available, build, register, run_all)
from . import momentum      # noqa: F401  registers MomentumStrategy
from . import mean_reversion  # noqa: F401  registers MeanReversionStrategy
from . import fii_flow        # noqa: F401  registers FIIFlowStrategy

__all__ = ["Strategy", "Signal", "StrategyResult", "MarketContext",
           "available", "build", "register", "run_all",
           "BUY", "SELL", "HOLD", "AVOID"]
