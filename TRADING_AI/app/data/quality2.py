"""
Session-aware data validation (replaces the naive weekday logic).

The old `validate_daily()` counted every absent weekday as a missing candle.
That is what produced `missing_candles: 7600`: 42 trading days had never been
downloaded, and 200 symbols x 38 absent bars looked like catastrophic
corruption rather than "we have not finished downloading".

This version asks a different question. Instead of

    "is there a bar for every weekday?"           (wrong)

it asks

    "for every CONFIRMED trading session, within the window where this
     symbol was actually listed and trading, is there a bar?"   (right)

and it classifies whatever is left over, so legitimate absences
(pre-listing, delisted, suspended, did-not-trade) never block signals while
genuine holes still do.

The gate is NOT weakened. A confirmed session with a missing bar for an
active stock is still a hard ERROR. What changed is that the system now
knows which sessions were confirmed.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from .calendar import SESSION, MarketCalendar
from .quality import Issue, QualityReport, SIGNAL_DISABLED_BANNER  # reuse types
from .repair import CLASSES, analyse_gaps

log = logging.getLogger(__name__)

# Tolerances. A small number of unexplained holes in a 200-stock universe is
# normal (illiquid names, trading halts); a large number is not.
MAX_MISSING_FRACTION = 0.02      # >2% of expected bars missing  -> ERROR
MAX_UNVERIFIED_DATES = 5         # unchecked weekdays            -> ERROR


def validate_daily_v2(df: Any, db, *, max_staleness_sessions: int = 3,
                      dataset: str = "daily_ohlc",
                      run_gap_analysis: bool = True,
                      progress=None) -> QualityReport:
    """Validate using the confirmed session calendar."""
    import pandas as pd

    from .quality import validate_daily as _base

    # Reuse all the price-sanity checks, but disable the naive missing-candle
    # and staleness checks -- they are replaced below with session-aware ones.
    holidays_all = set()
    cal = MarketCalendar(db)
    try:
        holidays_all = cal.holidays()
    except Exception:  # noqa: BLE001
        pass

    rep = _base(df, holidays=holidays_all, dataset=dataset,
                max_staleness_days=10_000)   # effectively skip base staleness
    rep.issues = [i for i in rep.issues
                  if i.check not in ("missing_candles", "stale_data")]

    if df is None or len(df) == 0:
        return rep

    # ---- session-aware staleness ----------------------------------------
    d = df.copy()
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    latest = d["date"].max()
    if pd.notna(latest):
        latest_date = latest.date()
        conn = db.connect()
        try:
            newer = conn.execute(
                "SELECT COUNT(*) FROM market_sessions WHERE status=? AND date > ?",
                (SESSION, latest_date.isoformat())).fetchone()[0]
        finally:
            conn.close()
        # A confirmed session we already know about and have not loaded is
        # the obvious case. The subtler one: the CALENDAR itself may be out
        # of date, in which case there are no "newer sessions" to count and
        # a year-old database would look perfectly fresh. So also count the
        # weekdays since the newest bar that have never been classified.
        unchecked_recent = 0
        conn = db.connect()
        try:
            known = {r[0] for r in conn.execute(
                "SELECT date FROM market_sessions WHERE date > ? AND status"
                " IN ('SESSION','HOLIDAY','WEEKEND')",
                (latest_date.isoformat(),)).fetchall()}
        finally:
            conn.close()
        probe = latest_date + dt.timedelta(days=1)
        today = dt.date.today()
        while probe <= today:
            if probe.weekday() < 5 and probe.isoformat() not in known:
                unchecked_recent += 1
            probe += dt.timedelta(days=1)

        behind = newer + unchecked_recent
        if behind > max_staleness_sessions:
            extra = (f" ({newer} confirmed, {unchecked_recent} weekday(s) "
                     f"never checked)" if unchecked_recent else "")
            rep.add("stale_data", "ERROR", behind,
                    f"Up to {behind} trading sessions have happened since "
                    f"the newest bar ({latest_date}){extra}. "
                    f"Data is out of date.")
        elif behind:
            rep.add("stale_data", "WARN", behind,
                    f"{behind} session(s) newer than {latest_date} not yet "
                    f"loaded")

    # ---- session-aware coverage -----------------------------------------
    if run_gap_analysis:
        gap = analyse_gaps(db, persist=True, progress=progress)
        rep.gap_report = gap  # type: ignore[attr-defined]

        if gap.total_expected == 0:
            rep.add("no_sessions_confirmed", "ERROR", 1,
                    "No trading sessions have been confirmed yet. Run a data "
                    "sync so the calendar can be established.")
            return rep

        missing = (gap.counts.get("SOURCE_NOT_FETCHED", 0)
                   + gap.counts.get("SOURCE_UNAVAILABLE", 0)
                   + gap.counts.get("UNEXPLAINED", 0))
        frac = missing / gap.total_expected if gap.total_expected else 0.0
        sev = "ERROR" if frac > MAX_MISSING_FRACTION else (
            "WARN" if missing else "INFO")
        rep.add("missing_candles", sev, missing,
                f"{missing:,} bars absent on confirmed trading sessions "
                f"({frac:.1%} of expected). "
                f"{len(gap.repairable_dates)} session(s) need downloading.")

        unverified = len(gap.unverified_dates)
        if unverified:
            sev = "ERROR" if unverified > MAX_UNVERIFIED_DATES else "WARN"
            rep.add("unverified_dates", sev, unverified,
                    f"{unverified} weekday(s) have not been checked against "
                    f"the NSE calendar - cannot tell holiday from missing data")

        # Legitimate absences reported as INFO so they are visible but harmless.
        for cls in ("NOT_YET_LISTED", "DELISTED", "NOT_TRADED"):
            n = gap.counts.get(cls, 0)
            if n:
                rep.add(f"legit_{cls.lower()}", "INFO", n, CLASSES[cls][1])

    return rep


def explain_for_humans(rep: QualityReport) -> list[dict]:
    """Translate the report into plain English for the GUI.

    Returns a list of {level, title, detail, action} dicts.
    """
    out = []
    for i in rep.issues:
        if i.severity == "INFO":
            continue
        title, detail, action = _translate(i)
        out.append({"level": i.severity, "title": title, "detail": detail,
                    "action": action, "check": i.check,
                    "affected": i.affected})
    return out


def _translate(i: Issue) -> tuple[str, str, str]:
    n = f"{i.affected:,}"
    table = {
        "missing_candles": (
            "Historical database is incomplete",
            f"{n} expected price records are missing for days the market was "
            f"open. Trading recommendations are disabled until this is fixed.",
            "REPAIR DATA"),
        "unverified_dates": (
            "Some dates have not been checked",
            f"{n} weekday(s) have not been matched against the official NSE "
            f"holiday calendar, so we cannot tell a holiday from a gap.",
            "REPAIR DATA"),
        "stale_data": (
            "Market data is out of date",
            f"{n} trading session(s) have happened since your last update.",
            "UPDATE NOW"),
        "duplicates": (
            "Duplicate records found",
            f"{n} price records appear more than once for the same stock "
            f"and date.", "REPAIR DATA"),
        "non_positive_prices": (
            "Impossible prices found",
            f"{n} records have a price of zero or below.", "REPAIR DATA"),
        "high_below_low": (
            "Corrupted price records",
            f"{n} records show a daily high below the daily low.",
            "REPAIR DATA"),
        "ohlc_out_of_range": (
            "Inconsistent price records",
            f"{n} records have an open or close outside the day's range.",
            "REPAIR DATA"),
        "extreme_price_jump": (
            "Unexplained large price jumps",
            f"{n} overnight moves above 60% look like unadjusted stock "
            f"splits or bad data.", "REVIEW CORPORATE ACTIONS"),
        "possible_corporate_action": (
            "Possible stock splits or bonuses detected",
            f"{n} overnight moves above 20% may be corporate actions that "
            f"need price adjustment.", "REVIEW CORPORATE ACTIONS"),
        "no_sessions_confirmed": (
            "No trading calendar yet",
            "The system has not yet confirmed which days the market was "
            "open.", "UPDATE NOW"),
        "null_prices": (
            "Incomplete price records",
            f"{n} records are missing one or more prices.", "REPAIR DATA"),
        "negative_volume": (
            "Invalid volume data",
            f"{n} records show negative trading volume.", "REPAIR DATA"),
        "zero_volume": (
            "Some stocks did not trade",
            f"{n} records show zero volume. Usually illiquid stocks.",
            "VIEW DETAILS"),
        "future_timestamps": (
            "Records dated in the future",
            f"{n} records carry a date later than today.", "REPAIR DATA"),
        "bad_timestamps": (
            "Unreadable dates",
            f"{n} records have a date that cannot be read.", "REPAIR DATA"),
        "empty_dataset": (
            "No market data yet",
            "The database contains no price history.", "UPDATE NOW"),
        "schema": (
            "Database structure problem",
            i.detail, "VIEW DETAILS"),
    }
    if i.check in table:
        return table[i.check]
    return (i.check.replace("_", " ").title(), i.detail, "VIEW DETAILS")
