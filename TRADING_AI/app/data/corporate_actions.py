"""
Corporate-action detection and price adjustment (spec item 3).

Principle: NEVER delete a large price move, and never silently "correct" one.
A 50% overnight drop is either a 1:2 split (adjust it) or a genuine crash
(keep it). Getting that wrong corrupts every indicator and backtest, so this
module classifies each event by CONFIDENCE and only adjusts what it can
justify:

  CONFIRMED  - matches a corporate action published by NSE for that date
  INFERRED   - the gap lands within tolerance of a simple, common ratio
               (1:2, 1:5, 2:1, 3:1 ...) which a genuine market move almost
               never does, AND the intraday range does not span the gap
  UNRESOLVED - a big move we cannot explain. NOT adjusted. Flagged for you.

Raw prices are never modified. Adjusted prices are written to a separate
table, rebuildable from raw at any time.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# Ratios that occur in real corporate actions. A genuine market move landing
# within 1.5% of one of these on the same day is possible but rare; combined
# with the intraday-range test below, false positives are very unlikely.
COMMON_RATIOS = {
    0.5: "1:2 split or 1:1 bonus", 0.3333: "1:3", 0.25: "1:4",
    0.2: "1:5 split", 0.1: "1:10 split", 0.6667: "2:3", 0.4: "2:5",
    0.75: "3:4", 0.6: "3:5", 0.05: "1:20", 0.02: "1:50", 0.01: "1:100",
    2.0: "2:1 reverse", 3.0: "3:1 reverse", 5.0: "5:1 reverse",
    10.0: "10:1 reverse",
}
RATIO_TOLERANCE = 0.015     # 1.5%
GAP_THRESHOLD = 0.20        # investigate moves beyond +/-20%


@dataclass
class ActionEvent:
    symbol: str
    ex_date: str
    gap: float                  # close/prev_close - 1
    factor: float               # multiply PRE-event prices by this
    reason: str
    confidence: str             # CONFIRMED | INFERRED | UNRESOLVED
    ratio_text: str = ""
    detail: str = ""

    def to_row(self) -> tuple:
        return (self.symbol, self.ex_date, self.factor, self.reason,
                self.ratio_text, self.confidence, "detector", self.gap)


def _nearest_ratio(price_ratio: float) -> tuple[float, str] | None:
    """price_ratio = close / prev_close. Returns (ratio, label) if it matches."""
    for r, label in COMMON_RATIOS.items():
        if abs(price_ratio - r) <= RATIO_TOLERANCE * max(r, 1.0):
            return r, label
    return None


def detect_events(df: pd.DataFrame,
                  known_actions: dict[tuple[str, str], str] | None = None,
                  ) -> list[ActionEvent]:
    """Scan a long-format OHLCV frame for corporate-action candidates.

    `known_actions` maps (symbol, ex_date) -> description, from NSE's
    corporate-actions feed. Anything matched there is CONFIRMED.
    """
    known_actions = known_actions or {}
    if df is None or df.empty:
        return []

    d = df.copy()
    d["date"] = pd.to_datetime(d["date"])
    d = d.sort_values(["symbol", "date"])
    g = d.groupby("symbol")
    d["prev_close"] = g["close"].shift(1)
    d["prev_low"] = g["low"].shift(1)
    d["prev_high"] = g["high"].shift(1)
    d["gap"] = d["close"] / d["prev_close"] - 1

    cand = d[(d["prev_close"].notna()) & (d["gap"].abs() > GAP_THRESHOLD)]
    events: list[ActionEvent] = []

    for r in cand.itertuples():
        iso = r.date.date().isoformat()
        price_ratio = float(r.close / r.prev_close)
        key = (r.symbol, iso)

        # --- 1. confirmed against the exchange feed -----------------------
        if key in known_actions:
            match = _nearest_ratio(price_ratio)
            factor = match[0] if match else price_ratio
            events.append(ActionEvent(
                r.symbol, iso, float(r.gap), float(factor),
                known_actions[key], "CONFIRMED",
                match[1] if match else "",
                "Matched an NSE-published corporate action on this date"))
            continue

        # --- 2. inferred from the ratio -----------------------------------
        match = _nearest_ratio(price_ratio)
        if match is not None:
            # A genuine crash usually shows a wide intraday range that
            # overlaps the previous day's range. A split does not: the whole
            # day trades at the new scale.
            gap_spans_range = (
                (r.gap < 0 and float(r.high) < float(r.prev_low)) or
                (r.gap > 0 and float(r.low) > float(r.prev_high)))
            if gap_spans_range:
                events.append(ActionEvent(
                    r.symbol, iso, float(r.gap), float(match[0]),
                    f"Inferred {match[1]}", "INFERRED", match[1],
                    "Gap matches a standard ratio and the whole session "
                    "traded at the new price scale"))
                continue

        # --- 3. unexplained -----------------------------------------------
        events.append(ActionEvent(
            r.symbol, iso, float(r.gap), 1.0,
            "Unexplained large move", "UNRESOLVED", "",
            f"Overnight move of {r.gap:+.1%} with no matching corporate "
            f"action. NOT adjusted - review manually."))

    return events


def load_known_actions(db, since: dt.date | None = None
                       ) -> dict[tuple[str, str], str]:
    """Read corporate actions previously stored from NSE's feed."""
    conn = db.connect()
    try:
        q = "SELECT symbol, ex_date, action_type, details FROM corporate_actions"
        args = []
        if since:
            q += " WHERE ex_date >= ?"
            args.append(since.isoformat())
        return {(r["symbol"], str(r["ex_date"])[:10]):
                f"{r['action_type']}: {r['details'] or ''}".strip(": ")
                for r in conn.execute(q, args)}
    finally:
        conn.close()


def persist_events(db, events: list[ActionEvent]) -> dict:
    if not events:
        return {"stored": 0}
    with db.tx() as c:
        c.executemany(
            "INSERT INTO adjustment_factors (symbol,ex_date,factor,reason,"
            "ratio_text,confidence,source,detected_gap)"
            " VALUES (?,?,?,?,?,?,?,?)"
            " ON CONFLICT(symbol,ex_date,reason) DO UPDATE SET"
            "  factor=excluded.factor, confidence=excluded.confidence,"
            "  detected_gap=excluded.detected_gap",
            [e.to_row() for e in events])
    counts: dict[str, int] = {}
    for e in events:
        counts[e.confidence] = counts.get(e.confidence, 0) + 1
    return {"stored": len(events), **counts}


def build_adjusted_series(db, symbols: list[str] | None = None,
                          progress=None) -> dict:
    """Rebuild `daily_ohlc_adjusted` from raw prices + adjustment factors.

    Back-adjustment: every bar BEFORE an ex-date is multiplied by the
    cumulative factor, so returns across the event are continuous. Volume is
    divided by the same factor so turnover stays comparable.

    Only CONFIRMED and INFERRED factors are applied. UNRESOLVED events are
    deliberately left alone.
    """
    conn = db.connect()
    try:
        where = ""
        args: list = []
        if symbols:
            where = f" AND symbol IN ({','.join('?' * len(symbols))})"
            args = list(symbols)
        px = pd.read_sql_query(
            "SELECT symbol,date,open,high,low,close,volume FROM daily_ohlc"
            f" WHERE is_synthetic=0{where} ORDER BY symbol,date", conn, params=args)
        fac = pd.read_sql_query(
            "SELECT symbol,ex_date,factor,confidence FROM adjustment_factors"
            " WHERE confidence IN ('CONFIRMED','INFERRED')", conn)
    finally:
        conn.close()

    if px.empty:
        return {"symbols": 0, "rows": 0, "adjusted_symbols": 0}

    px["date"] = pd.to_datetime(px["date"])
    fmap: dict[str, list[tuple[pd.Timestamp, float]]] = {}
    for r in fac.itertuples():
        fmap.setdefault(r.symbol, []).append(
            (pd.Timestamp(r.ex_date), float(r.factor)))

    out_rows = []
    adjusted_syms = 0
    for i, (sym, g) in enumerate(px.groupby("symbol")):
        if progress and i % 50 == 0:
            progress(f"Adjusting prices: {i} symbols")
        g = g.sort_values("date").copy()
        events = sorted(fmap.get(sym, []))
        cum = np.ones(len(g), dtype=float)
        if events:
            adjusted_syms += 1
            for ex_date, factor in events:
                # bars strictly before the ex-date get scaled
                mask = (g["date"] < ex_date).to_numpy()
                cum[mask] *= factor
        g["adj_factor"] = cum
        for c in ("open", "high", "low", "close"):
            g[c] = g[c] * cum
        g["volume"] = g["volume"] / np.where(cum == 0, 1.0, cum)
        out_rows.extend(
            (r.symbol, r.date.date().isoformat(), _r(r.open), _r(r.high),
             _r(r.low), _r(r.close), float(r.volume or 0), float(r.adj_factor))
            for r in g.itertuples())

    with db.tx() as c:
        c.execute("DELETE FROM daily_ohlc_adjusted")
        c.executemany(
            "INSERT INTO daily_ohlc_adjusted (symbol,date,open,high,low,"
            "close,volume,adj_factor) VALUES (?,?,?,?,?,?,?,?)", out_rows)

    return {"symbols": int(px["symbol"].nunique()), "rows": len(out_rows),
            "adjusted_symbols": adjusted_syms}


def _r(v) -> float | None:
    return None if v is None or (isinstance(v, float) and np.isnan(v)) \
        else round(float(v), 4)


def unresolved_report(db, limit: int = 200) -> pd.DataFrame:
    """Events a human still needs to look at."""
    conn = db.connect()
    try:
        return pd.read_sql_query(
            "SELECT symbol, ex_date, detected_gap, reason, confidence"
            " FROM adjustment_factors WHERE confidence='UNRESOLVED'"
            " ORDER BY ABS(detected_gap) DESC LIMIT ?", conn, params=[limit])
    finally:
        conn.close()


def run_corporate_action_pass(db, progress=None) -> dict:
    """Full pass: detect, classify, persist, rebuild adjusted prices."""
    def say(m):
        if progress:
            progress(m)

    say("Loading price history for corporate-action scan...")
    conn = db.connect()
    try:
        df = pd.read_sql_query(
            "SELECT symbol,date,open,high,low,close,volume FROM daily_ohlc"
            " WHERE is_synthetic=0 ORDER BY symbol,date", conn)
    finally:
        conn.close()
    if df.empty:
        return {"detected": 0, "stored": 0, "adjusted": {}}

    say("Detecting splits, bonuses and other corporate actions...")
    known = load_known_actions(db)
    events = detect_events(df, known)
    stats = persist_events(db, events)

    say(f"Found {len(events)} event(s); rebuilding adjusted prices...")
    adj = build_adjusted_series(db, progress=progress)

    return {"detected": len(events), **stats, "adjusted": adj}


# --------------------------------------------------------------------------- #
# Quarantine
# --------------------------------------------------------------------------- #
def quarantined_symbols(db, threshold: float = GAP_THRESHOLD) -> dict[str, str]:
    """Stocks whose price history we do not trust, and why.

    A stock with an overnight move we could not explain is either carrying an
    unadjusted corporate action or bad vendor data. Either way its indicators
    are wrong, so it must not produce a trade idea.

    The alternative - refusing to show ANY recommendation because 17 stocks
    out of 200 have unexplained jumps - disables the tool permanently, since
    those are historical events that no amount of re-downloading will fix.
    Excluding the affected stocks is both safer and more honest: the other
    183 are unaffected and their data is sound.
    """
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT symbol, ex_date, detected_gap FROM adjustment_factors"
            " WHERE confidence='UNRESOLVED' AND ABS(COALESCE(detected_gap,0))>=?",
            (threshold,)).fetchall()
    finally:
        conn.close()

    out: dict[str, str] = {}
    for r in rows:
        sym = r["symbol"]
        note = (f"unexplained {float(r['detected_gap']):+.0%} move on "
                f"{r['ex_date']}")
        out[sym] = f"{out[sym]}; {note}" if sym in out else note
    return out


def quarantine_summary(db) -> dict:
    q = quarantined_symbols(db)
    return {"count": len(q), "symbols": sorted(q),
            "reasons": q,
            "note": (f"{len(q)} stock(s) are excluded from recommendations "
                     f"because of an unexplained large price move. The rest "
                     f"of the market is unaffected.") if q else
                    "No stocks are quarantined."}


EXTREME_GAP = 0.60


def symbols_with_extreme_jumps(df, threshold: float = EXTREME_GAP
                               ) -> dict[str, str]:
    """Stocks showing an overnight move so large it cannot be a real move.

    Derived straight from the price frame so quarantine still works before
    the corporate-action detector has ever run on this database.
    """
    if df is None or len(df) == 0:
        return {}
    d = df.sort_values(["symbol", "date"]).copy()
    prev = d.groupby("symbol")["close"].shift(1)
    # Build the column before filtering. Assigning a full-length Series to an
    # already-filtered (possibly empty) frame makes pandas reindex and invent
    # all-NA rows, which produced a phantom quarantined symbol.
    d["gap_pct"] = (d["close"] / prev) - 1
    hit = d[prev.notna() & (d["gap_pct"].abs() > threshold)]
    out: dict[str, str] = {}
    for r in hit.itertuples():
        day = getattr(r.date, "date", lambda: r.date)()
        note = f"unexplained {r.gap_pct:+.0%} move on {day}"
        out[r.symbol] = (f"{out[r.symbol]}; {note}"
                         if r.symbol in out else note)
    return out
