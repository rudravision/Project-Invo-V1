"""
Common shape for every LAKSHMI strategy (Phase 2).

Rules this base class enforces, taken from the spec's own "critical rules":

* **Rule 2 - nothing hardcoded.** Every strategy carries a `params` dataclass
  and reads values from it. A strategy that reads a magic number inline is a
  strategy nobody can tune or audit.
* **Rule 14 - independently switchable.** Each strategy has an `enabled`
  flag and a registry entry, so one can be turned off without touching the
  others.
* **Rule 7 - handle gaps.** `generate()` returns a `StrategyResult` that can
  legitimately be empty, with `skipped_reason` explaining why. Returning no
  signal is a valid, common outcome and must never be an exception.

And one rule of my own, which the spec does not state but needs:

* **Filters that cannot be applied must be reported, not silently dropped.**
  If a strategy is specified to filter on market capitalisation and we have
  no market-cap data, the result says so in `filters_skipped`. Otherwise you
  believe you are trading a filtered universe when you are not.
"""
from __future__ import annotations

import abc
import dataclasses
import datetime as dt
import logging
from typing import Any, Iterable

import pandas as pd

log = logging.getLogger(__name__)

BUY, SELL, HOLD, AVOID = "BUY", "SELL", "HOLD", "AVOID"


@dataclasses.dataclass
class Signal:
    """One actionable line from one strategy."""
    strategy: str
    symbol: str
    action: str                      # BUY | SELL | HOLD | AVOID
    entry_price: float | None = None
    stop_loss: float | None = None
    target: float | None = None
    allocation_pct: float | None = None   # % of THIS strategy's capital
    rank: int | None = None
    confidence: float | None = None       # 0-100, see the warning below
    horizon_days: int | None = None
    reasoning: str = ""
    metrics: dict = dataclasses.field(default_factory=dict)
    as_of: str | None = None

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class StrategyResult:
    strategy: str
    as_of: str
    signals: list[Signal] = dataclasses.field(default_factory=list)
    skipped_reason: str | None = None
    filters_applied: list[str] = dataclasses.field(default_factory=list)
    filters_skipped: list[str] = dataclasses.field(default_factory=list)
    universe_size: int = 0
    notes: str = ""

    @property
    def ok(self) -> bool:
        return self.skipped_reason is None

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["signals"] = [s.to_dict() for s in self.signals]
        d["ok"] = self.ok
        return d


class Strategy(abc.ABC):
    """Base class. Subclasses implement `generate()` only."""

    name: str = "base"
    description: str = ""
    #: What this strategy needs in order to run at all.
    requires: tuple[str, ...] = ("daily_ohlc",)

    def __init__(self, params: Any = None, enabled: bool = True):
        self.params = params if params is not None else self.default_params()
        self.enabled = enabled

    @staticmethod
    def default_params() -> Any:  # pragma: no cover - overridden
        return None

    @abc.abstractmethod
    def generate(self, ctx: "MarketContext") -> StrategyResult:
        """Produce today's signals. Must not raise on missing data."""

    # -- helpers ---------------------------------------------------------
    def _empty(self, as_of, reason: str, **kw) -> StrategyResult:
        return StrategyResult(strategy=self.name, as_of=str(as_of),
                              skipped_reason=reason, **kw)

    def __repr__(self) -> str:
        return f"<{type(self).__name__} enabled={self.enabled}>"


@dataclasses.dataclass
class MarketContext:
    """Everything a strategy is allowed to look at.

    Passing one object keeps strategies from reaching into the database on
    their own, which is what makes them testable and keeps a backtest from
    accidentally seeing the future: the backtester builds a context that
    only holds data up to `as_of`.
    """
    as_of: dt.date
    daily: pd.DataFrame                      # symbol,date,ohlcv
    sectors: dict[str, str] = dataclasses.field(default_factory=dict)
    index_daily: pd.DataFrame | None = None
    delivery: dict[str, float] = dataclasses.field(default_factory=dict)
    flows: dict | None = None                # rolling_net() output
    valuation: dict | None = None            # latest_valuation() output
    india_vix: float | None = None
    holdings: dict[str, dict] = dataclasses.field(default_factory=dict)
    capital: float = 1_000_000.0

    def history(self, symbol: str) -> pd.DataFrame:
        d = self.daily[self.daily["symbol"] == symbol]
        return d.sort_values("date")

    def assert_no_lookahead(self) -> None:
        """Guard used by tests and the backtester."""
        if self.daily is None or self.daily.empty:
            return
        last = pd.to_datetime(self.daily["date"]).max().date()
        if last > self.as_of:
            raise ValueError(
                f"Context contains data to {last} but as_of is {self.as_of}. "
                f"A strategy must never see the future.")


# --------------------------------------------------------------------------- #
# Registry - lets strategies be enabled/disabled one at a time (rule 14)
# --------------------------------------------------------------------------- #
_REGISTRY: dict[str, type[Strategy]] = {}


def register(cls: type[Strategy]) -> type[Strategy]:
    _REGISTRY[cls.name] = cls
    return cls


def available() -> list[str]:
    return sorted(_REGISTRY)


def build(name: str, params: Any = None, enabled: bool = True) -> Strategy:
    if name not in _REGISTRY:
        raise KeyError(f"Unknown strategy '{name}'. "
                       f"Available: {', '.join(available()) or 'none'}")
    return _REGISTRY[name](params=params, enabled=enabled)


def run_all(ctx: MarketContext, names: Iterable[str] | None = None,
            enabled_map: dict[str, bool] | None = None
            ) -> dict[str, StrategyResult]:
    """Run each strategy, isolating failures.

    One broken strategy must not take the other five down with it - that is
    the whole point of running six.
    """
    enabled_map = enabled_map or {}
    out: dict[str, StrategyResult] = {}
    for n in (names if names is not None else available()):
        if not enabled_map.get(n, True):
            out[n] = StrategyResult(strategy=n, as_of=str(ctx.as_of),
                                    skipped_reason="Disabled in settings.")
            continue
        try:
            s = build(n)
            out[n] = s.generate(ctx)
        except Exception as e:  # noqa: BLE001 - deliberate isolation
            log.exception("Strategy %s failed", n)
            out[n] = StrategyResult(
                strategy=n, as_of=str(ctx.as_of),
                skipped_reason=f"Strategy failed: {e}")
    return out
