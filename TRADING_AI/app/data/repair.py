"""
Gap detection, classification and repair.

The validator's job is to say "this is broken". This module's job is to say
WHY it is broken and what to do about it.

Every hole in the price history is classified into exactly one bucket:

  LEGITIMATE (not a data problem -- must never block signals)
    NOT_YET_LISTED     date precedes the symbol's first trading session
    DELISTED           date follows the symbol's last session, symbol gone
    NOT_TRADED         we HAVE that day's bhavcopy and the symbol is simply
                       absent from it -- suspended, or zero trades
    HOLIDAY / WEEKEND  the exchange was closed

  REPAIRABLE (a real hole, with a known remedy)
    SOURCE_NOT_FETCHED we never downloaded that session's file
    SOURCE_UNAVAILABLE we tried and the source did not have it

  UNRESOLVED (needs a human)
    UNVERIFIED_DATE    a weekday we have not classified yet
    UNEXPLAINED        confirmed session, bhavcopy held, symbol active,
                       yet no row -- should not happen; flagged loudly

Only REPAIRABLE and UNEXPLAINED gaps are data-quality errors. That is the
distinction the old code was missing, and it is why it reported 7,600
"missing candles" that were mostly just days it had never attempted.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections import Counter
from dataclasses import dataclass, field

from .calendar import (ACTIVE, DELISTED, HOLIDAY, SESSION, SUSPENDED, UNKNOWN,
                       WEEKEND, MarketCalendar, SymbolLifecycle)

log = logging.getLogger(__name__)

# classification -> (is_problem, human explanation)
CLASSES = {
    "NOT_YET_LISTED":     (False, "Stock had not listed yet"),
    "DELISTED":           (False, "Stock was delisted or removed"),
    "NOT_TRADED":         (False, "Exchange open but this stock did not trade"),
    "HOLIDAY":            (False, "Market holiday"),
    "WEEKEND":            (False, "Weekend"),
    "SOURCE_NOT_FETCHED": (True,  "We never downloaded this trading day"),
    "SOURCE_UNAVAILABLE": (True,  "Source did not have this trading day"),
    "UNVERIFIED_DATE":    (True,  "Weekday not yet checked against the calendar"),
    "UNEXPLAINED":        (True,  "Unexplained hole - needs review"),
}

REPAIRABLE = {"SOURCE_NOT_FETCHED", "SOURCE_UNAVAILABLE", "UNVERIFIED_DATE"}


@dataclass
class GapReport:
    counts: Counter = field(default_factory=Counter)
    by_symbol: dict[str, Counter] = field(default_factory=dict)
    repairable_dates: set[str] = field(default_factory=set)
    unverified_dates: set[str] = field(default_factory=set)
    total_expected: int = 0
    total_present: int = 0

    @property
    def problems(self) -> int:
        return sum(n for c, n in self.counts.items() if CLASSES.get(c, (True,))[0])

    @property
    def legitimate(self) -> int:
        return sum(n for c, n in self.counts.items()
                   if not CLASSES.get(c, (True,))[0])

    def summary(self) -> str:
        lines = [
            f"Coverage: {self.total_present:,} of {self.total_expected:,} "
            f"expected bars present "
            f"({100 * self.total_present / self.total_expected:.1f}%)"
            if self.total_expected else "Coverage: no expected bars",
            "",
            "Gap classification:",
        ]
        for cls, n in self.counts.most_common():
            is_problem, desc = CLASSES.get(cls, (True, cls))
            tag = "PROBLEM  " if is_problem else "ok       "
            lines.append(f"  {tag} {cls:<20} {n:>8,}  {desc}")
        lines.append("")
        lines.append(f"  Real problems : {self.problems:,}")
        lines.append(f"  Legitimate    : {self.legitimate:,}")
        if self.repairable_dates:
            lines.append(f"  Sessions to re-fetch: {len(self.repairable_dates)}")
        if self.unverified_dates:
            lines.append(f"  Dates to verify     : {len(self.unverified_dates)}")
        return "\n".join(lines)


def analyse_gaps(db, start: dt.date | None = None, end: dt.date | None = None,
                 symbols: list[str] | None = None,
                 persist: bool = True, progress=None) -> GapReport:
    """Classify every missing (symbol, session) pair in the window."""
    cal = MarketCalendar(db)
    rep = GapReport()

    conn = db.connect()
    try:
        bounds = conn.execute(
            "SELECT MIN(date) mn, MAX(date) mx FROM daily_ohlc"
            " WHERE is_synthetic=0").fetchone()
        if not bounds or not bounds["mn"]:
            return rep
        # The window must span every CONFIRMED session, not merely the dates
        # we happen to hold prices for. Otherwise a session we never
        # downloaded at all falls outside the analysis and is never reported.
        sb = conn.execute(
            "SELECT MIN(date) mn, MAX(date) mx FROM market_sessions"
            " WHERE status=?", (SESSION,)).fetchone()
        lo = min(x for x in (bounds["mn"], sb["mn"] if sb else None) if x)
        hi = max(x for x in (bounds["mx"], sb["mx"] if sb else None) if x)
        start = start or dt.date.fromisoformat(lo)
        end = end or dt.date.fromisoformat(hi)

        sessions = [r["date"] for r in conn.execute(
            "SELECT date FROM market_sessions WHERE status=?"
            " AND date BETWEEN ? AND ? ORDER BY date",
            (SESSION, start.isoformat(), end.isoformat()))]
        session_meta = {r["date"]: r["bhavcopy_available"] for r in conn.execute(
            "SELECT date, bhavcopy_available FROM market_sessions"
            " WHERE status=? AND date BETWEEN ? AND ?",
            (SESSION, start.isoformat(), end.isoformat()))}

        q = ("SELECT symbol, date FROM daily_ohlc WHERE is_synthetic=0"
             " AND date BETWEEN ? AND ?")
        args = [start.isoformat(), end.isoformat()]
        have: dict[str, set[str]] = {}
        for r in conn.execute(q, args):
            have.setdefault(r["symbol"], set()).add(r["date"])

        life = {r["symbol"]: (r["first_session"], r["last_session"], r["status"])
                for r in conn.execute(
                    "SELECT symbol,first_session,last_session,status"
                    " FROM symbol_lifecycle")}
    finally:
        conn.close()

    unverified = [d.isoformat() for d in cal.unknown_between(start, end)]
    rep.unverified_dates = set(unverified)

    syms = symbols or sorted(have)
    session_set = set(sessions)
    rep.total_expected = len(syms) * len(sessions)

    persist_rows = []
    for i, sym in enumerate(syms):
        if progress and i % 25 == 0:
            progress(f"Classifying gaps: {i}/{len(syms)} symbols")
        present = have.get(sym, set())
        rep.total_present += len(present & session_set)
        first, last, status = life.get(sym, (None, None, ACTIVE))
        counter = Counter()

        for d in sessions:
            if d in present:
                continue
            if first and d < first:
                cls = "NOT_YET_LISTED"
            elif last and d > last and status == DELISTED:
                cls = "DELISTED"
            elif session_meta.get(d):
                # We hold that day's bhavcopy and the symbol is not in it.
                cls = "NOT_TRADED"
            else:
                cls = "SOURCE_NOT_FETCHED"
                rep.repairable_dates.add(d)
            counter[cls] += 1
            if persist and cls in REPAIRABLE:
                persist_rows.append((sym, d, cls, CLASSES[cls][1]))

        rep.counts.update(counter)
        rep.by_symbol[sym] = counter

    # Unverified weekdays are a DATABASE-level condition, counted once per
    # date. Multiplying by the symbol count (as the old code effectively did)
    # inflates a 38-day gap into a frightening 7,600.
    if unverified:
        rep.counts["UNVERIFIED_DATE"] = len(unverified)

    if persist and persist_rows:
        with db.tx() as c:
            c.executemany(
                "INSERT INTO data_gaps (symbol,date,classification,detail)"
                " VALUES (?,?,?,?) ON CONFLICT(symbol,date) DO UPDATE SET"
                " classification=excluded.classification, resolved=0",
                persist_rows[:200_000])

    return rep


# --------------------------------------------------------------------------- #
# Repair planning
# --------------------------------------------------------------------------- #
@dataclass
class RepairPlan:
    verify_dates: list[str] = field(default_factory=list)
    refetch_sessions: list[str] = field(default_factory=list)
    need_index: list[str] = field(default_factory=list)
    reason: str = ""

    @property
    def total_requests(self) -> int:
        return len(self.verify_dates) + len(self.refetch_sessions) + \
            len(self.need_index)

    @property
    def is_empty(self) -> bool:
        return self.total_requests == 0


def plan_repair(db, gap: GapReport, start: dt.date, end: dt.date) -> RepairPlan:
    """Turn a gap report into a concrete list of downloads."""
    plan = RepairPlan()
    plan.verify_dates = sorted(gap.unverified_dates)
    plan.refetch_sessions = sorted(gap.repairable_dates)

    conn = db.connect()
    try:
        sessions = [r["date"] for r in conn.execute(
            "SELECT date FROM market_sessions WHERE status=? AND date BETWEEN ? AND ?",
            (SESSION, start.isoformat(), end.isoformat()))]
        have_idx = {r["date"] for r in conn.execute(
            "SELECT DISTINCT date FROM index_ohlc WHERE is_synthetic=0")}
    finally:
        conn.close()
    plan.need_index = sorted(set(sessions) - have_idx)

    bits = []
    if plan.verify_dates:
        bits.append(f"{len(plan.verify_dates)} unchecked weekdays")
    if plan.refetch_sessions:
        bits.append(f"{len(plan.refetch_sessions)} sessions never downloaded")
    if plan.need_index:
        bits.append(f"{len(plan.need_index)} sessions missing index data")
    plan.reason = "; ".join(bits) or "nothing to repair"
    return plan


# --------------------------------------------------------------------------- #
# Resumable download queue
# --------------------------------------------------------------------------- #
class DownloadQueue:
    """Persistent work queue so an interrupted download resumes cleanly."""

    def __init__(self, db):
        self.db = db

    def enqueue(self, dataset: str, keys: list[str], priority: int = 100) -> int:
        if not keys:
            return 0
        with self.db.tx() as c:
            c.executemany(
                "INSERT INTO download_queue (dataset,key,status,priority)"
                " VALUES (?,?,'PENDING',?)"
                " ON CONFLICT(dataset,key) DO UPDATE SET"
                "   status=CASE WHEN download_queue.status='DONE' THEN 'DONE'"
                "               ELSE 'PENDING' END,"
                "   priority=excluded.priority",
                [(dataset, k, priority) for k in keys])
        return len(keys)

    def pending(self, dataset: str, limit: int = 10_000,
                max_attempts: int = 3) -> list[str]:
        conn = self.db.connect()
        try:
            return [r["key"] for r in conn.execute(
                "SELECT key FROM download_queue WHERE dataset=?"
                " AND status IN ('PENDING','FAILED') AND attempts < ?"
                " ORDER BY priority, key LIMIT ?",
                (dataset, max_attempts, limit))]
        finally:
            conn.close()

    def mark(self, dataset: str, key: str, status: str,
             error: str | None = None) -> None:
        with self.db.tx() as c:
            c.execute(
                "UPDATE download_queue SET status=?, attempts=attempts+1,"
                " last_error=?, updated_at=datetime('now')"
                " WHERE dataset=? AND key=?",
                (status, (error or "")[:400], dataset, key))

    def stats(self, dataset: str | None = None) -> dict:
        conn = self.db.connect()
        try:
            if dataset:
                rows = conn.execute(
                    "SELECT status, COUNT(*) n FROM download_queue"
                    " WHERE dataset=? GROUP BY status", (dataset,)).fetchall()
            else:
                rows = conn.execute(
                    "SELECT status, COUNT(*) n FROM download_queue"
                    " GROUP BY status").fetchall()
            return {r["status"]: r["n"] for r in rows}
        finally:
            conn.close()

    def reset_failed(self, dataset: str) -> int:
        with self.db.tx() as c:
            cur = c.execute(
                "UPDATE download_queue SET status='PENDING', attempts=0"
                " WHERE dataset=? AND status='FAILED'", (dataset,))
            return cur.rowcount
