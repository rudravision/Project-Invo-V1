"""
Does a setting actually work, or did it just fit the past? (spec item 11)

The temptation after a losing backtest is to try settings until one looks
good, then trade it. That is how backtests lie. A parameter sweep will
always produce a winner - even on random data - because you are picking the
luckiest of many tries.

So this module never reports a single "best" number. For every setting it
runs one backtest over the whole period and then scores the FIRST half and
the SECOND half separately:

    first half  -> what you would have seen when choosing the setting
    second half -> what you would then have actually earned

If a setting looks brilliant in the first half and poor in the second, it
was fitted, not found. `verdict()` says so in plain words. The honest
outcome of a sweep is often "nothing here survives", and this module is
built to be able to say that.

There is no look-ahead: each backtest ranks on the previous close and enters
at the next open, exactly as the live path does. Splitting the equity curve
afterwards adds no information to the simulation.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import math
from typing import Callable, Iterable

import numpy as np
import pandas as pd

from app.analytics.indicators import max_drawdown
from app.analytics.ranking import RankConfig

from .engine import BacktestConfig, CostModel, run_backtest

TRADING_DAYS = 252


@dataclasses.dataclass
class Setting:
    rebalance_days: int
    top_n: int

    @property
    def label(self) -> str:
        return (f"rebalance every {self.rebalance_days}d, "
                f"top {self.top_n}")

    def to_dict(self) -> dict:
        return {"rebalance_days": self.rebalance_days, "top_n": self.top_n,
                "label": self.label}


# Deliberately small. A wide grid is a licence to overfit, and every extra
# combination raises the chance that the winner is luck.
DEFAULT_GRID: list[Setting] = [
    Setting(5, 5),      # the current default
    Setting(10, 5),
    Setting(21, 5),     # roughly monthly - far fewer costs
    Setting(21, 3),
    Setting(63, 5),     # quarterly
]


def _segment_stats(eq: pd.Series) -> dict:
    """Return/vol/drawdown for one slice of an equity curve."""
    if eq is None or len(eq) < 3:
        return {"return_pct": float("nan"), "cagr_pct": float("nan"),
                "sharpe": float("nan"), "max_dd_pct": float("nan"),
                "days": int(0 if eq is None else len(eq))}
    total = float(eq.iloc[-1] / eq.iloc[0] - 1)
    years = max(len(eq) / TRADING_DAYS, 1e-9)
    cagr = (1 + total) ** (1 / years) - 1 if total > -1 else -1.0
    r = eq.pct_change().dropna()
    sharpe = (float(r.mean() / r.std() * math.sqrt(TRADING_DAYS))
              if len(r) > 2 and r.std() > 0 else float("nan"))
    return {"return_pct": total * 100, "cagr_pct": cagr * 100,
            "sharpe": sharpe, "max_dd_pct": max_drawdown(eq) * 100,
            "days": int(len(eq))}


def verdict(first: dict, second: dict) -> str:
    """Plain-language reading of the two halves."""
    a, b = first.get("return_pct"), second.get("return_pct")
    if a is None or b is None or (isinstance(a, float) and np.isnan(a)) \
            or (isinstance(b, float) and np.isnan(b)):
        return "Not enough data to judge"
    if a <= 0 and b <= 0:
        return "Lost money in both halves"
    if a > 0 and b <= 0:
        return "Worked then stopped working - likely fitted to the past"
    if a <= 0 < b:
        return "Only worked in the later half - not evidence of an edge"
    if b < a * 0.3:
        return "Much weaker in the second half - treat with caution"
    return "Positive in both halves"


def sweep(daily: pd.DataFrame, *, warmup: int = 130,
          capital: float = 1_000_000.0,
          grid: Iterable[Setting] | None = None,
          rank_cfg: RankConfig | None = None,
          costs: CostModel | None = None,
          progress: Callable[[str], None] | None = None) -> pd.DataFrame:
    """Backtest every setting once and score both halves of each run."""
    grid = list(grid if grid is not None else DEFAULT_GRID)
    d = daily.copy()
    d["date"] = pd.to_datetime(d["date"])
    dates = sorted(d["date"].unique())
    if len(dates) < warmup + 60:
        return pd.DataFrame()

    start = pd.Timestamp(dates[warmup]).date()
    end = pd.Timestamp(dates[-1]).date()
    rows = []
    for i, s in enumerate(grid, 1):
        if progress:
            progress(f"Testing {s.label} ({i} of {len(grid)})...")
        cfg = BacktestConfig(start=start, end=end,
                             rebalance_days=s.rebalance_days,
                             top_n=s.top_n, initial_capital=capital,
                             warmup_bars=warmup)
        res = run_backtest(d, cfg, rank_cfg or RankConfig(),
                           costs or CostModel())
        eq = res.equity
        if eq is None or len(eq) < 10:
            continue
        mid = len(eq) // 2
        first = _segment_stats(eq.iloc[:mid])
        second = _segment_stats(eq.iloc[mid:])
        rows.append({
            **s.to_dict(),
            "trades": int(res.stats.get("trades", 0)),
            "cost_drag_pct": float(res.stats.get("cost_drag_pct", float("nan"))),
            "full_return_pct": float(res.stats.get("total_return_pct",
                                                   float("nan"))),
            "first_half_return_pct": first["return_pct"],
            "second_half_return_pct": second["return_pct"],
            "first_half_sharpe": first["sharpe"],
            "second_half_sharpe": second["sharpe"],
            "max_dd_pct": float(res.stats.get("max_drawdown_pct",
                                              float("nan"))),
            "split_date": str(eq.index[mid].date()),
            "verdict": verdict(first, second),
        })

    return pd.DataFrame(rows)


def conclusion(table: pd.DataFrame) -> dict:
    """What the sweep as a whole is entitled to claim.

    Written to be able to conclude "none of these work", because on a
    strategy that loses money after costs that is the likely truth and the
    user needs to hear it.
    """
    if table is None or table.empty:
        return {"ok": False,
                "headline": "Not enough history to test any setting.",
                "detail": "Download more data and try again."}

    survived = table[table["verdict"] == "Positive in both halves"]
    best_first = table.sort_values("first_half_return_pct",
                                   ascending=False).iloc[0]

    if survived.empty:
        return {
            "ok": False,
            "headline": "No setting made money in both halves of the test.",
            "detail": (
                f"The best-looking setting on the earlier period "
                f"({best_first['label']}, "
                f"{best_first['first_half_return_pct']:+.1f}%) went on to do "
                f"{best_first['second_half_return_pct']:+.1f}% afterwards. "
                f"Picking a setting because it topped a table is how "
                f"backtests mislead. On this evidence the strategy should "
                f"not be traded with real money."),
            "best_on_paper": best_first["label"],
        }

    pick = survived.sort_values("second_half_return_pct",
                                ascending=False).iloc[0]
    return {
        "ok": True,
        "headline": (f"{len(survived)} of {len(table)} settings were positive "
                     f"in both halves."),
        "detail": (
            f"Most consistent: {pick['label']} - "
            f"{pick['first_half_return_pct']:+.1f}% then "
            f"{pick['second_half_return_pct']:+.1f}%, "
            f"{int(pick['trades'])} trades, costs "
            f"{pick['cost_drag_pct']:.1f}% of capital. Consistency across "
            f"both halves is weak evidence, not proof - two halves of one "
            f"history is a small sample."),
        "recommended": {"rebalance_days": int(pick["rebalance_days"]),
                        "top_n": int(pick["top_n"])},
    }


def cost_hurdle(costs: CostModel | None = None,
                rebalance_days: int = 5) -> dict:
    """How much the strategy must earn per trade just to break even.

    This is the number that decides whether frequent trading can ever work.
    """
    c = costs or CostModel()
    # Ask the cost model itself rather than re-deriving the arithmetic, so
    # this can never drift away from what the backtest actually charges.
    notional = 200_000.0          # a realistic position for Rs 10 lakh
    round_trip = (c.buy_cost(notional) + c.sell_cost(notional)) / notional * 100
    per_year = TRADING_DAYS / max(rebalance_days, 1)
    return {
        "round_trip_cost_pct": round(round_trip, 4),
        "round_trips_per_year": round(per_year, 1),
        "annual_cost_pct": round(round_trip * per_year, 2),
        "note": (f"At roughly {round_trip:.2f}% per round trip and "
                 f"{per_year:.0f} round trips a year, costs alone take about "
                 f"{round_trip * per_year:.1f}% a year. The strategy has to "
                 f"beat that before you earn anything."),
    }
