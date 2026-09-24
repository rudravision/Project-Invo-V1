"""
NSE trading-session calendar.

This module exists because the original system could not distinguish
"the exchange was closed" from "our download failed". It counted both as
missing data, which is what produced `missing_candles: 7600`.

The central idea is EVIDENCE. A calendar date has exactly one status:

    WEEKEND   - Saturday or Sunday. Never a session. Certain.
    HOLIDAY   - On NSE's published holiday list. Certain.
    SESSION   - We have positive evidence the market traded: a bhavcopy or
                index file was published for that date.
    UNKNOWN   - A weekday, not a known holiday, and we have no evidence
                either way. This is the honest default.

UNKNOWN is the important one. The old code implicitly treated "no data" as
"missing data". Here, UNKNOWN means *we have not checked yet*, which is a
repairable condition, not a data-quality failure. Only a confirmed SESSION
with no price row is a genuine hole.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from typing import Iterable, Sequence

log = logging.getLogger(__name__)

WEEKEND = "WEEKEND"
HOLIDAY = "HOLIDAY"
SESSION = "SESSION"
UNKNOWN = "UNKNOWN"

# NSE equity settlement holidays that are stable year to year are NOT
# hardcoded -- they move with the lunar calendar. We only hardcode the two
# that never move, as a last-resort fallback when the holiday API is down.
FIXED_HOLIDAYS_MMDD = {(1, 26), (8, 15), (10, 2)}  # Republic, Independence, Gandhi


def _d(x) -> dt.date:
    if isinstance(x, dt.datetime):
        return x.date()
    if isinstance(x, dt.date):
        return x
    return dt.date.fromisoformat(str(x)[:10])


@dataclass
class SessionInfo:
    date: dt.date
    status: str
    bhavcopy_available: bool = False
    index_available: bool = False
    symbol_count: int = 0
    evidence: str = ""

    @property
    def is_session(self) -> bool:
        return self.status == SESSION

    @property
    def is_confirmed_closed(self) -> bool:
        return self.status in (WEEKEND, HOLIDAY)


class MarketCalendar:
    """Reads and maintains the `market_sessions` table."""

    def __init__(self, db):
        self.db = db

    # -- reading -----------------------------------------------------------
    def status(self, date) -> str:
        d = _d(date)
        if d.weekday() >= 5:
            return WEEKEND
        conn = self.db.connect()
        try:
            r = conn.execute("SELECT status FROM market_sessions WHERE date=?",
                             (d.isoformat(),)).fetchone()
        finally:
            conn.close()
        return r["status"] if r else UNKNOWN

    def sessions_between(self, start, end) -> list[dt.date]:
        """Confirmed trading sessions in [start, end]."""
        conn = self.db.connect()
        try:
            rows = conn.execute(
                "SELECT date FROM market_sessions WHERE status=?"
                " AND date BETWEEN ? AND ? ORDER BY date",
                (SESSION, _d(start).isoformat(), _d(end).isoformat())).fetchall()
        finally:
            conn.close()
        return [dt.date.fromisoformat(r["date"]) for r in rows]

    def unknown_between(self, start, end) -> list[dt.date]:
        """Weekdays we have not yet classified. These need investigating."""
        conn = self.db.connect()
        try:
            known = {r["date"] for r in conn.execute(
                "SELECT date FROM market_sessions WHERE date BETWEEN ? AND ?"
                " AND status != ?",
                (_d(start).isoformat(), _d(end).isoformat(), UNKNOWN))}
        finally:
            conn.close()
        out, d, e = [], _d(start), _d(end)
        while d <= e:
            if d.weekday() < 5 and d.isoformat() not in known:
                out.append(d)
            d += dt.timedelta(days=1)
        return out

    def holidays(self) -> set[str]:
        conn = self.db.connect()
        try:
            return {r["date"] for r in conn.execute(
                "SELECT date FROM market_sessions WHERE status=?", (HOLIDAY,))}
        finally:
            conn.close()

    def summary(self, start, end) -> dict:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                "SELECT status, COUNT(*) n FROM market_sessions"
                " WHERE date BETWEEN ? AND ? GROUP BY status",
                (_d(start).isoformat(), _d(end).isoformat())).fetchall()
        finally:
            conn.close()
        out = {r["status"]: r["n"] for r in rows}
        out["UNKNOWN_WEEKDAYS"] = len(self.unknown_between(start, end))
        return out

    # -- writing -----------------------------------------------------------
    def mark(self, date, status: str, *, bhavcopy: bool | None = None,
             index: bool | None = None, symbol_count: int | None = None,
             evidence: str = "", source: str = "") -> None:
        """Record what a date was. Upgrades UNKNOWN -> known; never downgrades
        a confirmed SESSION back to UNKNOWN."""
        d = _d(date).isoformat()
        with self.db.tx() as c:
            cur = c.execute("SELECT status, bhavcopy_available,"
                            " index_available FROM market_sessions WHERE date=?",
                            (d,)).fetchone()
            if cur and cur["status"] == SESSION and status == UNKNOWN:
                return  # never forget a confirmed session
            c.execute(
                """INSERT INTO market_sessions
                   (date,status,bhavcopy_available,index_available,
                    symbol_count,evidence,source,confirmed_at)
                   VALUES (?,?,?,?,?,?,?,datetime('now'))
                   ON CONFLICT(date) DO UPDATE SET
                     status=excluded.status,
                     bhavcopy_available=MAX(bhavcopy_available,
                                            excluded.bhavcopy_available),
                     index_available=MAX(index_available,
                                         excluded.index_available),
                     symbol_count=MAX(symbol_count, excluded.symbol_count),
                     evidence=excluded.evidence,
                     source=excluded.source,
                     confirmed_at=datetime('now')""",
                (d, status,
                 int(bool(bhavcopy)) if bhavcopy is not None
                 else (cur["bhavcopy_available"] if cur else 0),
                 int(bool(index)) if index is not None
                 else (cur["index_available"] if cur else 0),
                 symbol_count or 0, evidence, source))

    def seed_weekends(self, start, end) -> int:
        """Record weekends. Cheap, certain, and stops them being questioned."""
        rows, d, e = [], _d(start), _d(end)
        while d <= e:
            if d.weekday() >= 5:
                rows.append((d.isoformat(), WEEKEND, "calendar"))
            d += dt.timedelta(days=1)
        if rows:
            with self.db.tx() as c:
                c.executemany(
                    "INSERT INTO market_sessions (date,status,evidence,"
                    "confirmed_at) VALUES (?,?,?,datetime('now'))"
                    " ON CONFLICT(date) DO NOTHING", rows)
        return len(rows)

    def load_holidays(self, holiday_dates: Iterable, source: str = "nse") -> int:
        n = 0
        for h in holiday_dates:
            try:
                d = _d(h)
            except (ValueError, TypeError):
                continue
            if d.weekday() >= 5:
                continue  # already a weekend; holiday flag adds nothing
            self.mark(d, HOLIDAY, evidence="NSE holiday master", source=source)
            n += 1
        return n

    def infer_sessions_from_data(self, min_symbols: int = 20) -> int:
        """Back-fill session status from price data we already hold.

        If a date has price rows for many symbols, the market was certainly
        open that day. This recovers the calendar for history downloaded
        before the calendar table existed.
        """
        conn = self.db.connect()
        try:
            rows = conn.execute(
                "SELECT date, COUNT(DISTINCT symbol) n FROM daily_ohlc"
                " WHERE is_synthetic=0 GROUP BY date HAVING n >= ?",
                (min_symbols,)).fetchall()
            idx = {r["date"] for r in conn.execute(
                "SELECT DISTINCT date FROM index_ohlc WHERE is_synthetic=0")}
        finally:
            conn.close()

        n = 0
        for r in rows:
            self.mark(r["date"], SESSION, bhavcopy=True,
                      index=r["date"] in idx, symbol_count=r["n"],
                      evidence=f"{r['n']} symbols have price data",
                      source="inferred_from_data")
            n += 1
        log.info("Inferred %d sessions from existing price data", n)
        return n

    def fallback_fixed_holidays(self, start, end) -> int:
        """Last resort when the holiday API is unreachable.

        Only the three date-fixed national holidays. Deliberately minimal --
        guessing lunar-calendar holidays would be worse than admitting
        ignorance.
        """
        n, d, e = 0, _d(start), _d(end)
        while d <= e:
            if d.weekday() < 5 and (d.month, d.day) in FIXED_HOLIDAYS_MMDD:
                self.mark(d, HOLIDAY, evidence="fixed national holiday",
                          source="fallback")
                n += 1
            d += dt.timedelta(days=1)
        return n


# --------------------------------------------------------------------------- #
# Symbol lifecycle
# --------------------------------------------------------------------------- #
ACTIVE, SUSPENDED, DELISTED = "ACTIVE", "SUSPENDED", "DELISTED"


class SymbolLifecycle:
    """Tracks when each symbol was actually tradeable.

    Without this, a stock that listed six months ago looks like it has years
    of "missing" history, and a delisted stock looks broken forever.
    """

    def __init__(self, db):
        self.db = db

    def rebuild(self, recent_sessions: int = 5) -> dict:
        """Recompute first/last session and status for every symbol."""
        conn = self.db.connect()
        try:
            rows = conn.execute(
                "SELECT symbol, MIN(date) mn, MAX(date) mx, COUNT(*) n"
                " FROM daily_ohlc WHERE is_synthetic=0 GROUP BY symbol"
            ).fetchall()
            sess = [r["date"] for r in conn.execute(
                "SELECT date FROM market_sessions WHERE status=?"
                " ORDER BY date DESC LIMIT ?", (SESSION, recent_sessions))]
        finally:
            conn.close()

        if not rows:
            return {"symbols": 0, "active": 0, "suspended": 0, "delisted": 0}

        latest = max(sess) if sess else None
        cutoff = min(sess) if sess else None

        counts = {ACTIVE: 0, SUSPENDED: 0, DELISTED: 0}
        payload = []
        for r in rows:
            status = ACTIVE
            note = ""
            if latest and cutoff:
                if r["mx"] < cutoff:
                    # Not seen in any of the last N sessions.
                    gap_sessions = self._sessions_since(r["mx"])
                    if gap_sessions > 30:
                        status, note = DELISTED, (
                            f"no data for {gap_sessions} sessions since {r['mx']}")
                    else:
                        status, note = SUSPENDED, (
                            f"absent for {gap_sessions} recent sessions")
            counts[status] += 1
            payload.append((r["symbol"], status, r["mn"], r["mx"],
                            r["n"], note))

        with self.db.tx() as c:
            c.executemany(
                """INSERT INTO symbol_lifecycle
                   (symbol,status,first_session,last_session,sessions_seen,note,
                    updated_at)
                   VALUES (?,?,?,?,?,?,datetime('now'))
                   ON CONFLICT(symbol) DO UPDATE SET
                     status=excluded.status,
                     first_session=MIN(first_session, excluded.first_session),
                     last_session=MAX(last_session, excluded.last_session),
                     sessions_seen=excluded.sessions_seen,
                     note=excluded.note,
                     updated_at=datetime('now')""", payload)

        return {"symbols": len(rows), "active": counts[ACTIVE],
                "suspended": counts[SUSPENDED], "delisted": counts[DELISTED]}

    def _sessions_since(self, date: str) -> int:
        conn = self.db.connect()
        try:
            return conn.execute(
                "SELECT COUNT(*) FROM market_sessions WHERE status=? AND date > ?",
                (SESSION, date)).fetchone()[0]
        finally:
            conn.close()

    def windows(self) -> dict[str, tuple[str, str, str]]:
        """symbol -> (first_session, last_session, status)."""
        conn = self.db.connect()
        try:
            return {r["symbol"]: (r["first_session"], r["last_session"],
                                  r["status"])
                    for r in conn.execute(
                        "SELECT symbol,first_session,last_session,status"
                        " FROM symbol_lifecycle")}
        finally:
            conn.close()
