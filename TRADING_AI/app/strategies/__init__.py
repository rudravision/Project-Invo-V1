"""LAKSHMI strategy engine.

Importing this package registers every strategy, so `available()` and
`build()` work without the caller knowing which modules exist.
"""
from .base import (AVOID, BUY, HOLD, SELL, MarketContext, Signal, Strategy,
                   StrategyResult, available, build, register, run_all)
from . import momentum  # noqa: F401  (registers MomentumStrategy)

__all__ = ["Strategy", "Signal", "StrategyResult", "MarketContext",
           "available", "build", "register", "run_all",
           "BUY", "SELL", "HOLD", "AVOID"]
