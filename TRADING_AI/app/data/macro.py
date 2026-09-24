"""
Market-wide data: FII/DII flows and index valuation (LAKSHMI Phase 1).

These are *per-day* facts about the whole market, not per-stock rows, so they
get their own tables. Two strategies in the LAKSHMI spec depend on them:

* FII Flow Reversal  -> 20-day rolling FII and DII net flow
* RSI Mean Reversion -> Nifty PE and India VIX

Sourcing, honestly
------------------
NSE publishes both, free:

* FII/DII cash activity - ``/api/fiidiiTradeReact`` (an internal endpoint the
  website itself calls; it is public but undocumented and can return 403)
* P/E, P/B and dividend yield - the daily Indices reports archive
* India VIX - the India VIX historical data archive

Because the undocumented endpoint can refuse us at any time, every loader
here is also reachable from a **CSV file the user downloads by hand** from
NSE's own website. That is the difference between a system that stops
working the day an endpoint changes and one that does not. We never bypass a
403: if NSE refuses, we say so and fall back to the file.

Nothing in this module invents a number. A missing day stays missing.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

log = logging.getLogger(__name__)

# Values arrive in rupees crore. Store exactly what the source published.
UNITS = "INR crore"

_NUM = re.compile(r"-?[\d,]+\.?\d*")


def _num(v) -> float | None:
    """Parse '12,345.67', '(1,234)', '-', '' or None into a float or None."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).strip()
    if not t or t in {"-", "--", "NA", "N/A", "nan"}:
        return None
    neg = t.startswith("(") and t.endswith(")")
    m = _NUM.search(t.replace("(", "-").replace(")", ""))
    if not m:
        return None
    try:
        f = float(m.group(0).replace(",", ""))
    except ValueError:
        return None
    return -abs(f) if neg else f


_DATE_FORMATS = ("%Y-%m-%d", "%d-%b-%Y", "%d-%m-%Y", "%d/%m/%Y",
                 "%d-%b-%y", "%b %d, %Y", "%d %b %Y")


def parse_date(v) -> str | None:
    """Accept the several date spellings NSE uses. Return ISO, or None."""
    if v is None:
        return None
    if isinstance(v, dt.datetime):
        return v.date().isoformat()
    if isinstance(v, dt.date):
        return v.isoformat()
    t = str(v).strip()
    if not t:
        return None
    for f in _DATE_FORMATS:
        try:
            return dt.datetime.strptime(t, f).date().isoformat()
        except ValueError:
            continue
    return None


@dataclass
class FlowRow:
    date: str
    fii_buy: float | None = None
    fii_sell: float | None = None
    fii_net: float | None = None
    dii_buy: float | None = None
    dii_sell: float | None = None
    dii_net: float | None = None
    segment: str = "cash"
    source: str = "unknown"

    def filled_net(self) -> "FlowRow":
        """Derive net from buy/sell when the source omitted it (and vice
        versa is not possible, so it stays None)."""
        if self.fii_net is None and None not in (self.fii_buy, self.fii_sell):
            self.fii_net = round(self.fii_buy - self.fii_sell, 2)
        if self.dii_net is None and None not in (self.dii_buy, self.dii_sell):
            self.dii_net = round(self.dii_buy - self.dii_sell, 2)
        return self


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
def parse_nse_fiidii(payload) -> list[FlowRow]:
    """Parse NSE's /api/fiidiiTradeReact payload.

    Shape (observed): a list of dicts, one per category, e.g.
        [{"category": "FII/FPI *", "date": "24-Sep-2026",
          "buyValue": "12115.00", "sellValue": "11589.00",
          "netValue": "526.00"}, {"category": "DII **", ...}]

    Anything unexpected is skipped rather than guessed at.
    """
    if not isinstance(payload, (list, tuple)):
        return []

    by_date: dict[str, FlowRow] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        d = parse_date(item.get("date") or item.get("tradeDate"))
        if not d:
            continue
        cat = str(item.get("category") or item.get("Category") or "").upper()
        buy = _num(item.get("buyValue", item.get("buySales")))
        sell = _num(item.get("sellValue"))
        net = _num(item.get("netValue"))

        row = by_date.setdefault(d, FlowRow(date=d, source="nse:fiidii"))
        if "FII" in cat or "FPI" in cat:
            row.fii_buy, row.fii_sell, row.fii_net = buy, sell, net
        elif "DII" in cat:
            row.dii_buy, row.dii_sell, row.dii_net = buy, sell, net

    return [r.filled_net() for r in by_date.values()]


# Column spellings seen in NSE / broker CSV exports of the same data.
_FLOW_ALIASES = {
    "date": ("date", "tradedate", "trade date", "reportdate"),
    "fii_buy": ("fiibuy", "fii buy", "fiibuyvalue", "fii gross purchase",
                "fpibuy", "fii purchases"),
    "fii_sell": ("fiisell", "fii sell", "fiisellvalue", "fii gross sales",
                 "fpisell", "fii sales"),
    "fii_net": ("fiinet", "fii net", "fiinetvalue", "fpinet",
                "fii net purchase/sales"),
    "dii_buy": ("diibuy", "dii buy", "diibuyvalue", "dii gross purchase"),
    "dii_sell": ("diisell", "dii sell", "diisellvalue", "dii gross sales"),
    "dii_net": ("diinet", "dii net", "diinetvalue",
                "dii net purchase/sales"),
}


def _norm_header(h: str) -> str:
    return re.sub(r"[^a-z0-9 /]", "", str(h or "").strip().lower())


def _map_columns(header: Sequence[str], aliases: dict) -> dict[str, int]:
    out: dict[str, int] = {}
    norm = [_norm_header(h) for h in header]
    for field, names in aliases.items():
        for i, h in enumerate(norm):
            squashed = h.replace(" ", "")
            if h in names or squashed in [n.replace(" ", "") for n in names]:
                out[field] = i
                break
    return out


def parse_flows_csv(text: str, source: str = "csv") -> list[FlowRow]:
    """Parse a hand-downloaded FII/DII CSV.

    Deliberately tolerant about column naming, because the user will be
    downloading this from a web page, not an API contract.
    """
    rows: list[FlowRow] = []
    reader = csv.reader(io.StringIO(text))
    header = None
    for raw in reader:
        if not raw or all(not str(c).strip() for c in raw):
            continue
        if header is None:
            cols = _map_columns(raw, _FLOW_ALIASES)
            if "date" in cols and len(cols) >= 2:
                header = cols
            continue
        d = parse_date(raw[header["date"]]) if header["date"] < len(raw) else None
        if not d:
            continue

        def g(f):
            i = header.get(f)
            return _num(raw[i]) if i is not None and i < len(raw) else None

        rows.append(FlowRow(date=d, fii_buy=g("fii_buy"), fii_sell=g("fii_sell"),
                            fii_net=g("fii_net"), dii_buy=g("dii_buy"),
                            dii_sell=g("dii_sell"), dii_net=g("dii_net"),
                            source=source).filled_net())
    if header is None:
        raise ValueError(
            "Could not find a date column and any FII/DII column in this "
            "file. Download the FII/DII activity CSV from nseindia.com and "
            "try again without editing it.")
    return rows


_VAL_ALIASES = {
    "date": ("date", "date ", "tradedate"),
    "pe": ("pe", "p/e", "pe ratio", "p/e ratio"),
    "pb": ("pb", "p/b", "pb ratio", "p/b ratio"),
    "div_yield": ("div yield", "divyield", "dividend yield",
                  "div yield %", "dividend yield %"),
    "close": ("close", "closing value", "index value", "closing index value"),
}


def parse_valuation_csv(text: str, index_name: str = "Nifty 50",
                        source: str = "csv") -> list[dict]:
    """Parse NSE's 'P/E, P/B & Div Yield' CSV export."""
    out: list[dict] = []
    reader = csv.reader(io.StringIO(text))
    header = None
    for raw in reader:
        if not raw or all(not str(c).strip() for c in raw):
            continue
        if header is None:
            cols = _map_columns(raw, _VAL_ALIASES)
            if "date" in cols and ("pe" in cols or "pb" in cols):
                header = cols
            continue
        d = parse_date(raw[header["date"]])
        if not d:
            continue

        def g(f):
            i = header.get(f)
            return _num(raw[i]) if i is not None and i < len(raw) else None

        out.append({"date": d, "index_name": index_name, "pe": g("pe"),
                    "pb": g("pb"), "div_yield": g("div_yield"),
                    "close": g("close"), "source": source})
    if header is None:
        raise ValueError(
            "Could not find a date column and a P/E or P/B column in this "
            "file. Download 'P/E, P/B & Div Yield values' from nseindia.com.")
    return out


# --------------------------------------------------------------------------- #
# Storage
# --------------------------------------------------------------------------- #
def store_flows(db, rows: Iterable[FlowRow]) -> int:
    rows = [r for r in rows if r and r.date]
    if not rows:
        return 0
    with db.tx() as conn:
        conn.executemany(
            "INSERT INTO fii_dii_flows"
            " (date,fii_buy,fii_sell,fii_net,dii_buy,dii_sell,dii_net,"
            "  segment,source)"
            " VALUES (?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(date) DO UPDATE SET"
            "  fii_buy=excluded.fii_buy, fii_sell=excluded.fii_sell,"
            "  fii_net=excluded.fii_net, dii_buy=excluded.dii_buy,"
            "  dii_sell=excluded.dii_sell, dii_net=excluded.dii_net,"
            "  segment=excluded.segment, source=excluded.source",
            [(r.date, r.fii_buy, r.fii_sell, r.fii_net, r.dii_buy,
              r.dii_sell, r.dii_net, r.segment, r.source) for r in rows])
    return len(rows)


def store_valuation(db, rows: Iterable[dict]) -> int:
    rows = [r for r in rows if r and r.get("date")]
    if not rows:
        return 0
    with db.tx() as conn:
        conn.executemany(
            "INSERT INTO market_valuation"
            " (date,index_name,pe,pb,div_yield,close,source)"
            " VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(date,index_name) DO UPDATE SET"
            "  pe=excluded.pe, pb=excluded.pb,"
            "  div_yield=excluded.div_yield, close=excluded.close,"
            "  source=excluded.source",
            [(r["date"], r.get("index_name", "Nifty 50"), r.get("pe"),
              r.get("pb"), r.get("div_yield"), r.get("close"),
              r.get("source", "unknown")) for r in rows])
    return len(rows)


# --------------------------------------------------------------------------- #
# Reading
# --------------------------------------------------------------------------- #
def flow_series(db, days: int | None = None) -> list[dict]:
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT * FROM fii_dii_flows ORDER BY date").fetchall()
    finally:
        conn.close()
    out = [dict(r) for r in rows]
    return out[-days:] if days else out


def rolling_net(db, window: int = 20) -> dict:
    """Rolling FII and DII net flow - the input the FII strategy needs.

    Returns UNKNOWN rather than a partial sum when there are fewer than
    `window` observations, because a 6-day sum compared against a threshold
    designed for 20 days would silently mislead.
    """
    rows = flow_series(db)
    have = len(rows)
    if have < window:
        return {"available": False, "observations": have, "window": window,
                "reason": (f"Only {have} day(s) of FII/DII data stored; "
                           f"{window} are needed. Download more history."),
                "units": UNITS}
    recent = rows[-window:]
    fii = [r["fii_net"] for r in recent if r["fii_net"] is not None]
    dii = [r["dii_net"] for r in recent if r["dii_net"] is not None]
    if len(fii) < window or len(dii) < window:
        return {"available": False, "observations": have, "window": window,
                "reason": ("Some days in the window have no net figure, so a "
                           "rolling total would be misleading."),
                "units": UNITS}
    return {"available": True, "window": window,
            "as_of": recent[-1]["date"],
            "rows": recent,
            "fii_net": round(sum(fii), 2), "dii_net": round(sum(dii), 2),
            "fii_net_latest": recent[-1]["fii_net"],
            "dii_net_latest": recent[-1]["dii_net"],
            "observations": have, "units": UNITS}


def latest_valuation(db, index_name: str = "Nifty 50") -> dict | None:
    conn = db.connect()
    try:
        r = conn.execute(
            "SELECT * FROM market_valuation WHERE index_name=?"
            " ORDER BY date DESC LIMIT 1", (index_name,)).fetchone()
    finally:
        conn.close()
    return dict(r) if r else None


def india_vix_latest(db) -> dict | None:
    """India VIX is stored as an index series like any other index."""
    from app.analytics.indices import norm
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT index_name, date, close FROM index_ohlc"
            " ORDER BY date DESC LIMIT 400").fetchall()
    finally:
        conn.close()
    for r in rows:
        if norm(r["index_name"]) in ("INDIA VIX", "INDIAVIX", "NIFTY VIX"):
            return {"date": r["date"], "value": r["close"]}
    return None


# --------------------------------------------------------------------------- #
# File import (the fallback that keeps this working when an endpoint 403s)
# --------------------------------------------------------------------------- #
def import_flows_file(db, path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"No such file: {p}")
    rows = parse_flows_csv(p.read_text(encoding="utf-8", errors="replace"),
                           source=f"file:{p.name}")
    n = store_flows(db, rows)
    log.info("Imported %d FII/DII rows from %s", n, p.name)
    return {"imported": n, "file": p.name,
            "first": rows[0].date if rows else None,
            "last": rows[-1].date if rows else None}


def import_valuation_file(db, path: str | Path,
                          index_name: str = "Nifty 50") -> dict:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"No such file: {p}")
    rows = parse_valuation_csv(
        p.read_text(encoding="utf-8", errors="replace"),
        index_name=index_name, source=f"file:{p.name}")
    n = store_valuation(db, rows)
    log.info("Imported %d valuation rows from %s", n, p.name)
    return {"imported": n, "file": p.name,
            "first": rows[0]["date"] if rows else None,
            "last": rows[-1]["date"] if rows else None}
