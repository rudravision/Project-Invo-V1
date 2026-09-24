"""
Independent confirmation checks for a trade candidate (spec items 7 and 11).

Why this file is written the way it is
--------------------------------------
Stacking more filters feels like it must raise your win rate. It does not,
automatically. Each filter removes some losers *and* shrinks the sample, and
on a few years of data it is very easy to add five checks, watch the
backtest improve, and have measured nothing but the past.

So every check here is:

* **Named and auditable** - one function, one plain-language reason, no
  hidden weighting. You can see exactly why a check passed or failed.
* **Independent of the score** - confirmations never silently change the
  probability. The probability still comes only from the calibrated
  out-of-sample hit rate in probability.py.
* **Measurable** - `evaluate_checks()` walks history and reports, for each
  check, how often price actually rose the next session when the check
  passed versus when it failed, and on how many observations. A check that
  does not help is meant to be dropped, not kept because it sounds right.

`UNKNOWN` is a real answer. If delivery data was never downloaded, the
delivery check reports UNKNOWN rather than quietly counting as a pass.
"""
from __future__ import annotations

import dataclasses
from typing import Callable

import numpy as np
import pandas as pd

PASS = "PASS"
FAIL = "FAIL"
UNKNOWN = "UNKNOWN"

# A check needs at least this many observations before we are willing to
# report a measured edge for it. Same standard as the probability engine.
MIN_OBSERVATIONS = 200


@dataclasses.dataclass
class Check:
    key: str
    label: str
    status: str          # PASS | FAIL | UNKNOWN
    detail: str          # plain language, always states the actual number

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def _num(row, key):
    v = row.get(key)
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if (np.isnan(f) or np.isinf(f)) else f


# --------------------------------------------------------------------------- #
# Individual checks. Each returns a Check for the given side (LONG/SHORT).
# --------------------------------------------------------------------------- #
def check_volume_surge(row, side, ctx) -> Check:
    """Is today's volume genuinely above this stock's own normal?"""
    rv = _num(row, "relative_volume")
    if rv is None:
        return Check("volume_surge", "Volume above normal", UNKNOWN,
                     "No volume history to compare against.")
    ok = rv >= 1.2
    return Check("volume_surge", "Volume above normal", PASS if ok else FAIL,
                 f"Traded {rv:.2f}x its 20-day average volume"
                 f"{' - a real surge' if ok else ' - no unusual interest'}.")


def check_volume_trend(row, side, ctx) -> Check:
    """Is volume expanding in the direction of the move?

    Rising price on rising volume is the classic confirmation; rising price
    on falling volume is the classic warning.
    """
    vz = _num(row, "vol_z")
    if vz is None:
        return Check("volume_trend", "Volume supports the move", UNKNOWN,
                     "Not enough volume history.")
    ok = vz > 0
    return Check("volume_trend", "Volume supports the move",
                 PASS if ok else FAIL,
                 f"Volume is {abs(vz):.1f} standard deviations "
                 f"{'above' if vz > 0 else 'below'} its recent average.")


def check_delivery(row, side, ctx) -> Check:
    """Delivery % - did buyers actually take shares, or was it day-trading?

    NSE publishes the share of traded quantity that resulted in delivery.
    High delivery means real ownership changed hands, not intraday churn.
    """
    d = _num(row, "delivery_pct")
    if d is None:
        return Check("delivery", "Real buying (delivery %)", UNKNOWN,
                     "Delivery data has not been downloaded for this stock.")
    ok = d >= 45.0
    return Check("delivery", "Real buying (delivery %)", PASS if ok else FAIL,
                 f"{d:.1f}% of traded volume was taken as delivery"
                 f"{' - genuine accumulation' if ok else ' - mostly intraday'}.")


def check_trend(row, side, ctx) -> Check:
    """Is the stock on the right side of its own 50 and 200-day averages?"""
    a50 = _num(row, "above_sma50")
    a200 = _num(row, "above_sma200")
    if a50 is None or a200 is None:
        return Check("trend", "Trend agrees", UNKNOWN,
                     "Not enough history for the 200-day average.")
    up = bool(a50) and bool(a200)
    down = not bool(a50) and not bool(a200)
    ok = up if side == "LONG" else down
    where = ("above both its 50 and 200-day averages" if up else
             "below both its 50 and 200-day averages" if down else
             "between its 50 and 200-day averages")
    return Check("trend", "Trend agrees", PASS if ok else FAIL,
                 f"Price is {where}.")


def check_momentum(row, side, ctx) -> Check:
    """MACD histogram pointing the same way as the trade."""
    h = _num(row, "macd_hist")
    if h is None:
        return Check("momentum", "Momentum agrees", UNKNOWN,
                     "Not enough history for MACD.")
    ok = h > 0 if side == "LONG" else h < 0
    return Check("momentum", "Momentum agrees", PASS if ok else FAIL,
                 f"MACD histogram is {h:+.2f} "
                 f"({'rising' if h > 0 else 'falling'} momentum).")


def check_not_overextended(row, side, ctx) -> Check:
    """Avoid buying something already stretched, or shorting the floor."""
    r = _num(row, "rsi14")
    if r is None:
        return Check("not_overextended", "Not overextended", UNKNOWN,
                     "Not enough history for RSI.")
    ok = r < 75.0 if side == "LONG" else r > 25.0
    return Check("not_overextended", "Not overextended",
                 PASS if ok else FAIL,
                 f"RSI is {r:.0f}"
                 + ("" if ok else
                    " - already stretched, poor place to enter."))


def check_sector(row, side, ctx) -> Check:
    """Is the stock's sector pulling with it or against it?"""
    s = row.get("sector_strength") or "Unknown"
    if s == "Unknown":
        return Check("sector", "Sector agrees", UNKNOWN,
                     "This stock's sector index has not been downloaded.")
    strong = s in ("Strong", "Firm")
    weak = s in ("Weak", "Very weak")
    ok = strong if side == "LONG" else weak
    return Check("sector", "Sector agrees", PASS if ok else FAIL,
                 f"Its sector is {s.lower()} right now.")


def check_market(row, side, ctx) -> Check:
    """Is the wider market with you? Most stocks follow the index."""
    a = row.get("market_alignment") or "Unknown"
    if a == "Unknown":
        # Historical evaluation supplies the market trend per date instead
        # of a pre-computed alignment, because alignment depends on side.
        t = row.get("market_trend")
        if t in ("Bullish", "Bearish"):
            a = ("Aligned" if ((side == "LONG" and t == "Bullish")
                               or (side == "SHORT" and t == "Bearish"))
                 else "Against")
    if a == "Unknown":
        return Check("market", "Market agrees", UNKNOWN,
                     "Index data has not been downloaded.")
    # recommend.py says Aligned/Against/Neutral; the historical evaluation
    # supplies With/Against. Accept both rather than silently failing.
    ok = a in ("With", "Aligned")
    wording = {"With": "with", "Aligned": "with", "Against": "against",
               "Neutral": "neutral to"}.get(a, a.lower())
    return Check("market", "Market agrees", PASS if ok else FAIL,
                 f"The trade is {wording} the broader market trend.")


def check_liquidity(row, side, ctx) -> Check:
    """Can you actually get in and out without moving the price?"""
    t = _num(row, "turnover20")
    if t is None:
        return Check("liquidity", "Liquid enough to trade", UNKNOWN,
                     "No turnover history.")
    ok = t >= 5_00_00_000          # Rs 5 crore average daily turnover
    return Check("liquidity", "Liquid enough to trade", PASS if ok else FAIL,
                 f"About Rs {t/1e7:.1f} crore traded daily on average"
                 f"{'' if ok else ' - thin, expect slippage'}.")


def check_no_recent_announcement(row, side, ctx) -> Check:
    """Any corporate announcement in the last few sessions?

    This is a caution flag, not a sentiment reading. We report that an
    announcement exists and let you look at it - we do not pretend to score
    whether news is bullish or bearish, because that would be an invented
    number.
    """
    n = row.get("announcements_7d")
    if n is None:
        return Check("no_announcement", "No unread company news", UNKNOWN,
                     "Company announcements have not been downloaded.")
    n = int(n)
    return Check("no_announcement", "No unread company news",
                 PASS if n == 0 else FAIL,
                 "No company announcements in the last 7 sessions."
                 if n == 0 else
                 f"{n} company announcement(s) in the last 7 sessions - "
                 f"read them before trading.")


# Order matters only for display.
CHECKS: dict[str, Callable] = {
    "volume_surge": check_volume_surge,
    "volume_trend": check_volume_trend,
    "delivery": check_delivery,
    "trend": check_trend,
    "momentum": check_momentum,
    "not_overextended": check_not_overextended,
    "sector": check_sector,
    "market": check_market,
    "liquidity": check_liquidity,
    "no_announcement": check_no_recent_announcement,
}


def run_checks(row, side: str, ctx: dict | None = None) -> list[Check]:
    ctx = ctx or {}
    return [fn(row, side, ctx) for fn in CHECKS.values()]


def summarise(checks: list[Check]) -> dict:
    """Counts plus an honest one-line reading."""
    passed = [c for c in checks if c.status == PASS]
    failed = [c for c in checks if c.status == FAIL]
    unknown = [c for c in checks if c.status == UNKNOWN]
    known = len(passed) + len(failed)
    return {
        "passed": len(passed),
        "failed": len(failed),
        "unknown": len(unknown),
        "known": known,
        "text": (f"{len(passed)} of {known} checks agree"
                 + (f" ({len(unknown)} unknown)" if unknown else "")),
        "failed_labels": [c.label for c in failed],
        "unknown_labels": [c.label for c in unknown],
    }


# --------------------------------------------------------------------------- #
# Does any of this actually help? Measure it.
# --------------------------------------------------------------------------- #
def evaluate_checks(feat: pd.DataFrame, side: str = "LONG",
                    horizon: int = 1,
                    min_observations: int = MIN_OBSERVATIONS) -> pd.DataFrame:
    """Measure each check against what price actually did next.

    `feat` must hold one row per symbol per date with the indicator columns
    and a forward return column `fwd_ret` already computed out-of-sample.

    Returns one row per check with the hit rate when it passed, the hit rate
    when it failed, the difference (the check's measured edge), and the
    observation counts behind both. A positive `edge_pct` on a large sample
    is evidence; anything else is not.
    """
    if feat.empty or "fwd_ret" not in feat.columns:
        return pd.DataFrame(columns=["check", "label", "n_pass", "n_fail",
                                     "hit_pass_pct", "hit_fail_pct",
                                     "edge_pct", "verdict"])

    win = feat["fwd_ret"] > 0 if side == "LONG" else feat["fwd_ret"] < 0
    rows = []
    for key, fn in CHECKS.items():
        status = feat.apply(lambda r: fn(r, side, {}).status, axis=1)
        label = fn(feat.iloc[0], side, {}).label
        m_pass, m_fail = status == PASS, status == FAIL
        n_pass, n_fail = int(m_pass.sum()), int(m_fail.sum())
        hp = float(win[m_pass].mean() * 100) if n_pass else float("nan")
        hf = float(win[m_fail].mean() * 100) if n_fail else float("nan")
        edge = hp - hf if (n_pass and n_fail) else float("nan")

        if n_pass < min_observations or n_fail < min_observations:
            verdict = "Not enough data to judge"
        elif edge > 1.0:
            verdict = "Helps"
        elif edge < -1.0:
            verdict = "Hurts - consider dropping"
        else:
            verdict = "No measurable effect"

        rows.append({"check": key, "label": label, "n_pass": n_pass,
                     "n_fail": n_fail, "hit_pass_pct": hp, "hit_fail_pct": hf,
                     "edge_pct": edge, "verdict": verdict})

    return (pd.DataFrame(rows)
            .sort_values("edge_pct", ascending=False, na_position="last")
            .reset_index(drop=True))
