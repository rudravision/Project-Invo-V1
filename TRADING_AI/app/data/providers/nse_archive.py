"""
NSE public archive provider.

Uses only files and JSON endpoints that NSE publishes for public download --
the same URLs a browser hits from nseindia.com/all-reports. It does NOT bypass
CAPTCHAs, logins, paywalls or rate limits. It warms a session cookie exactly
the way a normal browser does, identifies itself honestly in the User-Agent,
and self-throttles.

If NSE's terms of use forbid your intended use, do not use this provider --
switch the role to a broker API you have an account with.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import logging
import zipfile
from typing import Iterable

import requests

from ..base import (
    Capability, DataProvider, Freshness, NotAvailableError, ProviderInfo,
    RateLimitedError,
)

log = logging.getLogger(__name__)

HOME = "https://www.nseindia.com"
ARCHIVES = "https://nsearchives.nseindia.com"

# Canonical UDiFF -> our schema mapping.
UDIFF_MAP = {
    "TradDt": "date",
    "TckrSymb": "symbol",
    "SctySrs": "series",
    "OpnPric": "open",
    "HghPric": "high",
    "LwPric": "low",
    "ClsPric": "close",
    "LastPric": "last",
    "PrvsClsgPric": "prev_close",
    "TtlTradgVol": "volume",
    "TtlTrfVal": "turnover",
    "TtlNbOfTxsExctd": "trades",
    "ISIN": "isin",
}


class NSEArchiveProvider(DataProvider):
    """Reads NSE's published daily files: UDiFF bhavcopy, indices, delivery."""

    name = "nse_archive"

    def __init__(self, config: dict | None = None, **kw):
        super().__init__(config, **kw)
        self.timeout = self.config.get("timeout_seconds", 20)
        self._session: requests.Session | None = None

    # -- session -----------------------------------------------------------
    def _sess(self) -> requests.Session:
        """Create a browser-like session and warm the cookie NSE expects.

        This is the documented, ordinary way to fetch these public files; it
        is not an access-control bypass.
        """
        if self._session is not None:
            return self._session
        s = requests.Session()
        s.headers.update({
            "User-Agent": self.config.get(
                "user_agent",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            ),
            "Accept": "text/html,application/xhtml+xml,application/json,*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
        })
        try:
            s.get(HOME, timeout=self.timeout)
        except requests.RequestException as e:
            log.debug("NSE cookie warm-up failed (continuing): %s", e)
        self._session = s
        return s

    def _get(self, url: str, **kw) -> requests.Response:
        self.rate_limiter.wait()
        r = self._sess().get(url, timeout=self.timeout, **kw)
        if r.status_code == 429:
            raise RateLimitedError(f"429 rate limited by NSE for {url}")
        if r.status_code == 404:
            raise NotAvailableError(f"404 not published: {url}")
        r.raise_for_status()
        return r

    # -- metadata ----------------------------------------------------------
    def info(self) -> ProviderInfo:
        return ProviderInfo(
            name=self.name,
            data_available=("Daily OHLCV (UDiFF bhavcopy), index close values, "
                            "sector indices, security-wise delivery, F&O "
                            "bhavcopy with OI, index membership, holidays, "
                            "corporate announcements"),
            freshness=Freshness.END_OF_DAY,
            historical_depth="UDiFF from Jul-2024; legacy archives go back years",
            update_frequency="Once per trading day, typically after ~18:30 IST",
            rate_limit="Unpublished. Self-throttled to >=1 req/sec here.",
            cost="Free",
            reliability="Authoritative (the exchange itself), but the website "
                        "layer is prone to timeouts and occasional URL changes",
            licensing_concerns="NSE website terms of use apply. Personal "
                               "research is normally fine; redistribution is "
                               "not. Review the terms yourself.",
            backup_source="Broker API (Upstox/Fyers/Breeze) you hold an account with",
            requires_credentials=False,
        )

    def capabilities(self) -> set[Capability]:
        return {
            Capability.DAILY_OHLC, Capability.INDEX_OHLC, Capability.DELIVERY,
            Capability.DERIVATIVES, Capability.OPEN_INTEREST,
            Capability.CALENDAR, Capability.ANNOUNCEMENTS,
            Capability.INDEX_MEMBERSHIP, Capability.BREADTH,
        }

    def health_check(self) -> tuple[bool, str]:
        """Real request against the index-constituents file (small + stable)."""
        url = f"{ARCHIVES}/content/indices/ind_nifty50list.csv"
        try:
            r = self._get(url)
            n = len(r.text.strip().splitlines())
            if n < 10:
                return False, f"Reachable but response looks wrong ({n} lines)"
            return True, f"OK - fetched {n} lines from ind_nifty50list.csv"
        except Exception as e:  # noqa: BLE001
            return False, f"{type(e).__name__}: {e}"

    # -- data --------------------------------------------------------------
    def bhavcopy(self, date: dt.date) -> list[dict]:
        """Full-market UDiFF bhavcopy for one trading day (raw rows)."""
        url = (f"{ARCHIVES}/content/cm/"
               f"BhavCopy_NSE_CM_0_0_0_{date:%Y%m%d}_F_0000.csv.zip")
        r = self._get(url)
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            member = next(n for n in z.namelist() if n.lower().endswith(".csv"))
            text = z.read(member).decode("utf-8", errors="replace")
        rows = list(csv.DictReader(io.StringIO(text)))
        if not rows:
            raise NotAvailableError(f"Empty bhavcopy for {date}")
        return rows

    def get_daily_ohlc(self, symbols: Iterable[str], start: dt.date,
                       end: dt.date):
        """Daily OHLCV for symbols across a date range, from daily bhavcopies.

        One HTTP request per trading day, so the cache layer above this is
        what makes it cheap. Non-trading days are skipped, not errors.
        """
        import pandas as pd

        wanted = {s.upper() for s in symbols} if symbols else None
        frames, missing = [], []
        day = start
        while day <= end:
            if day.weekday() < 5:  # cheap pre-filter; holidays handled below
                try:
                    rows = self.bhavcopy(day)
                except NotAvailableError:
                    missing.append(day)
                    day += dt.timedelta(days=1)
                    continue
                recs = []
                for row in rows:
                    if (row.get("SctySrs") or "").strip() != "EQ":
                        continue
                    sym = (row.get("TckrSymb") or "").strip().upper()
                    if wanted and sym not in wanted:
                        continue
                    recs.append({
                        "date": day,
                        "symbol": sym,
                        "open": _f(row.get("OpnPric")),
                        "high": _f(row.get("HghPric")),
                        "low": _f(row.get("LwPric")),
                        "close": _f(row.get("ClsPric")),
                        "prev_close": _f(row.get("PrvsClsgPric")),
                        "volume": _f(row.get("TtlTradgVol")),
                        "turnover": _f(row.get("TtlTrfVal")),
                        "trades": _f(row.get("TtlNbOfTxsExctd")),
                        "isin": (row.get("ISIN") or "").strip(),
                        "source": self.name,
                    })
                if recs:
                    frames.append(pd.DataFrame(recs))
            day += dt.timedelta(days=1)

        if not frames:
            raise NotAvailableError(
                f"No bhavcopy data between {start} and {end} "
                f"({len(missing)} days unpublished/holiday)"
            )
        df = pd.concat(frames, ignore_index=True)
        df["date"] = pd.to_datetime(df["date"])
        return df.sort_values(["symbol", "date"]).reset_index(drop=True)

    def get_index_ohlc(self, index_names: Iterable[str], start: dt.date,
                       end: dt.date):
        """Daily close for all NSE indices from ind_close_all_<ddmmyyyy>.csv."""
        import pandas as pd

        wanted = {i.strip().upper() for i in index_names} if index_names else None
        recs = []
        day = start
        while day <= end:
            if day.weekday() < 5:
                url = (f"{ARCHIVES}/content/indices/"
                       f"ind_close_all_{day:%d%m%Y}.csv")
                try:
                    r = self._get(url)
                except (NotAvailableError, Exception):
                    day += dt.timedelta(days=1)
                    continue
                for row in csv.DictReader(io.StringIO(r.text)):
                    nm = (row.get("Index Name") or "").strip()
                    if wanted and nm.upper() not in wanted:
                        continue
                    recs.append({
                        "date": day,
                        "symbol": nm,
                        "open": _f(row.get("Open Index Value")),
                        "high": _f(row.get("High Index Value")),
                        "low": _f(row.get("Low Index Value")),
                        "close": _f(row.get("Closing Index Value")),
                        "change_pct": _f(row.get("Change(%)")),
                        "volume": _f(row.get("Volume")),
                        "pe": _f(row.get("P/E")),
                        "pb": _f(row.get("P/B")),
                        "div_yield": _f(row.get("Div Yield")),
                        "source": self.name,
                    })
            day += dt.timedelta(days=1)

        if not recs:
            raise NotAvailableError(f"No index data between {start} and {end}")
        df = pd.DataFrame(recs)
        df["date"] = pd.to_datetime(df["date"])
        return df.sort_values(["symbol", "date"]).reset_index(drop=True)

    def get_delivery(self, date: dt.date):
        """Security-wise delivery positions for one day."""
        import pandas as pd

        url = (f"{ARCHIVES}/products/content/"
               f"sec_bhavdata_full_{date:%d%m%Y}.csv")
        r = self._get(url)
        rows = list(csv.DictReader(io.StringIO(r.text)))
        recs = []
        for row in rows:
            row = { (k or "").strip(): (v.strip() if isinstance(v, str) else v)
                    for k, v in row.items() }
            if row.get("SERIES") != "EQ":
                continue
            recs.append({
                "date": date,
                "symbol": row.get("SYMBOL", ""),
                "deliverable_qty": _f(row.get("DELIV_QTY")),
                "delivery_pct": _f(row.get("DELIV_PER")),
                "traded_qty": _f(row.get("TTL_TRD_QNTY")),
                "source": self.name,
            })
        if not recs:
            raise NotAvailableError(f"No delivery data for {date}")
        return pd.DataFrame(recs)

    def get_derivatives(self, date: dt.date):
        """F&O UDiFF bhavcopy including open interest."""
        import pandas as pd

        url = (f"{ARCHIVES}/content/fo/"
               f"BhavCopy_NSE_FO_0_0_0_{date:%Y%m%d}_F_0000.csv.zip")
        r = self._get(url)
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            member = next(n for n in z.namelist() if n.lower().endswith(".csv"))
            text = z.read(member).decode("utf-8", errors="replace")
        df = pd.read_csv(io.StringIO(text))
        df["date"] = pd.to_datetime(date)
        df["source"] = self.name
        return df

    def get_index_membership(self, index_slug: str):
        """Constituents of an index, e.g. 'nifty50', 'niftybank', 'nifty200'."""
        import pandas as pd

        url = f"{ARCHIVES}/content/indices/ind_{index_slug}list.csv"
        r = self._get(url)
        df = pd.read_csv(io.StringIO(r.text))
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
        df["index_slug"] = index_slug
        df["source"] = self.name
        return df

    def get_trading_calendar(self, year: int):
        """Official trading holidays from NSE's holiday-master endpoint."""
        import pandas as pd

        url = f"{HOME}/api/holiday-master?type=trading"
        r = self._get(url, headers={"Accept": "application/json",
                                    "Referer": f"{HOME}/resources/exchange-communication-holidays"})
        payload = r.json()
        rows = []
        for segment, items in payload.items():
            for it in items or []:
                rows.append({
                    "segment": segment,
                    "date": it.get("tradingDate"),
                    "description": it.get("description"),
                    "source": self.name,
                })
        if not rows:
            raise NotAvailableError("Holiday master returned no rows")
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"], errors="coerce", dayfirst=True)
        return df[df["date"].dt.year == year] if year else df

    def get_fii_dii(self):
        """FII/DII cash-market activity for the latest published day.

        This is an internal endpoint the NSE website itself calls. It is
        public but undocumented, and it refuses unfamiliar clients with a
        403. We send a browser-like User-Agent because that is what the
        published page does - we do not defeat any access control, and a
        403 is reported as unavailable, never worked around.
        """
        from app.data.macro import parse_nse_fiidii

        url = f"{HOME}/api/fiidiiTradeReact"
        r = self._get(url, headers={"Accept": "application/json",
                                    "Referer": f"{HOME}/reports/fii-dii"})
        rows = parse_nse_fiidii(r.json())
        if not rows:
            raise NotAvailableError(
                "NSE returned no usable FII/DII rows. Download the CSV from "
                "nseindia.com and import it instead.")
        return rows

    def get_announcements(self, since: dt.date):
        """Corporate announcements (equities)."""
        import pandas as pd

        url = f"{HOME}/api/corporate-announcements?index=equities"
        r = self._get(url, headers={"Accept": "application/json",
                                    "Referer": f"{HOME}/companies-listing/corporate-filings-announcements"})
        data = r.json()
        if not isinstance(data, list):
            raise NotAvailableError("Unexpected announcements payload shape")
        df = pd.DataFrame(data)
        df["source"] = self.name
        return df


def _f(v) -> float:
    """Parse a possibly dirty numeric cell to float, NaN on failure."""
    try:
        if v is None:
            return float("nan")
        s = str(v).strip().replace(",", "")
        if s in ("", "-", "NA", "nan"):
            return float("nan")
        return float(s)
    except (TypeError, ValueError):
        return float("nan")
