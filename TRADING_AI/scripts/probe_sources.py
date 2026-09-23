#!/usr/bin/env python3
"""
Probe every candidate data source with REAL requests and write a dated report.

This script exists because nobody -- including the AI that wrote this code --
should claim a data source works without testing it. It makes one small,
polite request per endpoint, records exactly what came back, and writes the
result to reports/source_probe_<timestamp>.json.

It does NOT bypass CAPTCHAs, logins or rate limits. Endpoints that require
credentials are reported as SKIPPED unless you have supplied them.

Usage:
    python scripts/probe_sources.py
    python scripts/probe_sources.py --json      # machine-readable to stdout
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import os
import sys
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    import requests
except ImportError:
    sys.exit("requests is not installed. Run INSTALL first.")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
TIMEOUT = 20
HOME = "https://www.nseindia.com"
ARCHIVES = "https://nsearchives.nseindia.com"


def last_weekday(offset_days: int = 1) -> dt.date:
    """Most recent weekday at least `offset_days` back (crude, ignores holidays)."""
    d = dt.date.today() - dt.timedelta(days=offset_days)
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d


def nse_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/json,*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
    })
    try:
        s.get(HOME, timeout=TIMEOUT)
    except requests.RequestException:
        pass
    return s


class Probe:
    def __init__(self):
        self.results: list[dict] = []
        self.session = nse_session()

    def run(self, name: str, url: str, check, requires_creds: bool = False,
            creds_env: str | None = None, headers: dict | None = None):
        rec = {
            "source": name, "url": url, "requires_credentials": requires_creds,
            "status": "UNKNOWN", "http_status": None, "latency_ms": None,
            "detail": "", "bytes": 0,
            "checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        }

        if requires_creds and creds_env and not os.environ.get(creds_env):
            rec["status"] = "SKIPPED"
            rec["detail"] = (f"Needs credentials. Set ${creds_env} to test. "
                             f"Not attempted -- no guessing.")
            self.results.append(rec)
            self._print(rec)
            return rec

        t0 = time.time()
        try:
            r = self.session.get(url, timeout=TIMEOUT, headers=headers or {})
            rec["latency_ms"] = int((time.time() - t0) * 1000)
            rec["http_status"] = r.status_code
            rec["bytes"] = len(r.content)
            if r.status_code == 200:
                ok, detail = check(r)
                rec["status"] = "WORKING" if ok else "REACHABLE_BUT_UNEXPECTED"
                rec["detail"] = detail
            elif r.status_code in (401, 403):
                rec["status"] = "BLOCKED"
                rec["detail"] = (f"HTTP {r.status_code}. Access controlled. "
                                 f"Not bypassing -- use an authorised route.")
            elif r.status_code == 404:
                rec["status"] = "NOT_PUBLISHED"
                rec["detail"] = "HTTP 404 - file/date not published at this URL."
            elif r.status_code == 429:
                rec["status"] = "RATE_LIMITED"
                rec["detail"] = "HTTP 429 - backing off, as required."
            else:
                rec["status"] = "FAILED"
                rec["detail"] = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            rec["latency_ms"] = int((time.time() - t0) * 1000)
            rec["status"] = "FAILED"
            rec["detail"] = f"{type(e).__name__}: {str(e)[:200]}"

        self.results.append(rec)
        self._print(rec)
        time.sleep(1.0)  # be polite
        return rec

    @staticmethod
    def _print(rec: dict):
        icon = {
            "WORKING": "[ OK ]", "SKIPPED": "[SKIP]", "BLOCKED": "[BLOK]",
            "NOT_PUBLISHED": "[404 ]", "RATE_LIMITED": "[429 ]",
            "FAILED": "[FAIL]", "REACHABLE_BUT_UNEXPECTED": "[WARN]",
        }.get(rec["status"], "[????]")
        lat = f"{rec['latency_ms']}ms" if rec["latency_ms"] is not None else "-"
        print(f"{icon} {rec['source']:<32} {lat:>8}  {rec['detail'][:90]}")


# ---- individual response validators --------------------------------------
def check_csv_lines(minimum: int):
    def _c(r):
        n = len(r.text.strip().splitlines())
        return n >= minimum, f"{n} CSV lines"
    return _c


def check_zip_csv(r):
    try:
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            names = z.namelist()
            csvs = [n for n in names if n.lower().endswith(".csv")]
            if not csvs:
                return False, f"zip has no CSV: {names[:3]}"
            head = z.read(csvs[0]).decode("utf-8", "replace").splitlines()
            return len(head) > 10, f"zip -> {csvs[0]}, {len(head)} rows"
    except zipfile.BadZipFile:
        return False, "not a valid zip (probably an HTML error page)"


def check_json(keyhint: str = ""):
    def _c(r):
        try:
            data = r.json()
        except ValueError:
            return False, "200 but body is not JSON"
        if isinstance(data, list):
            return len(data) > 0, f"JSON array, {len(data)} items"
        if isinstance(data, dict):
            ks = list(data.keys())[:5]
            ok = (keyhint in data) if keyhint else bool(ks)
            return ok, f"JSON object, keys={ks}"
        return False, f"unexpected JSON type {type(data).__name__}"
    return _c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="print JSON only")
    ap.add_argument("--out", default=None, help="output path for the report")
    args = ap.parse_args()

    d1 = last_weekday(1)
    d2 = last_weekday(2)

    if not args.json:
        print("=" * 110)
        print(f"DATA SOURCE PROBE  --  {dt.datetime.now().isoformat(timespec='seconds')}")
        print(f"Testing with recent weekday dates: {d1} and {d2}")
        print("Real requests only. Nothing is assumed to work.")
        print("=" * 110)

    p = Probe()

    # --- NSE public archives ---
    p.run("nse:index_constituents_n50",
          f"{ARCHIVES}/content/indices/ind_nifty50list.csv",
          check_csv_lines(20))
    p.run("nse:index_constituents_n200",
          f"{ARCHIVES}/content/indices/ind_nifty200list.csv",
          check_csv_lines(100))
    p.run("nse:bhavcopy_udiff_cm",
          f"{ARCHIVES}/content/cm/BhavCopy_NSE_CM_0_0_0_{d1:%Y%m%d}_F_0000.csv.zip",
          check_zip_csv)
    p.run("nse:bhavcopy_udiff_cm_d2",
          f"{ARCHIVES}/content/cm/BhavCopy_NSE_CM_0_0_0_{d2:%Y%m%d}_F_0000.csv.zip",
          check_zip_csv)
    p.run("nse:bhavcopy_udiff_fo",
          f"{ARCHIVES}/content/fo/BhavCopy_NSE_FO_0_0_0_{d1:%Y%m%d}_F_0000.csv.zip",
          check_zip_csv)
    p.run("nse:index_close_all",
          f"{ARCHIVES}/content/indices/ind_close_all_{d1:%d%m%Y}.csv",
          check_csv_lines(20))
    p.run("nse:sec_delivery_full",
          f"{ARCHIVES}/products/content/sec_bhavdata_full_{d1:%d%m%Y}.csv",
          check_csv_lines(100))
    p.run("nse:holiday_master",
          f"{HOME}/api/holiday-master?type=trading",
          check_json(),
          headers={"Accept": "application/json",
                   "Referer": f"{HOME}/resources/exchange-communication-holidays"})
    p.run("nse:corp_announcements",
          f"{HOME}/api/corporate-announcements?index=equities",
          check_json(),
          headers={"Accept": "application/json",
                   "Referer": f"{HOME}/companies-listing/corporate-filings-announcements"})
    p.run("nse:equity_quote_meta",
          f"{HOME}/api/quote-equity?symbol=RELIANCE",
          check_json(),
          headers={"Accept": "application/json",
                   "Referer": f"{HOME}/get-quotes/equity?symbol=RELIANCE"})

    # --- Broker / third-party APIs ---
    p.run("upstox:v3_historical_nifty",
          "https://api.upstox.com/v3/historical-candle/"
          f"NSE_INDEX%7CNifty%2050/days/1/{d1:%Y-%m-%d}/{d1 - dt.timedelta(days=10):%Y-%m-%d}",
          check_json("data"),
          headers={"Accept": "application/json"})
    p.run("upstox:instruments_nse",
          "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz",
          lambda r: (r.content[:2] == b"\x1f\x8b", f"gzip payload {len(r.content)} bytes"))
    p.run("upstox:live_quote",
          "https://api.upstox.com/v2/market-quote/quotes?instrument_key=NSE_INDEX%7CNifty%2050",
          check_json(), requires_creds=True, creds_env="UPSTOX_ACCESS_TOKEN")
    p.run("yahoo:chart_nifty",
          "https://query1.finance.yahoo.com/v8/finance/chart/%5ENSEI?range=1mo&interval=1d",
          check_json("chart"))
    p.run("yahoo:chart_reliance",
          "https://query1.finance.yahoo.com/v8/finance/chart/RELIANCE.NS?range=1mo&interval=1d",
          check_json("chart"))

    # --- Report ---
    summary = {}
    for r in p.results:
        summary[r["status"]] = summary.get(r["status"], 0) + 1

    report = {
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "test_dates": {"d1": str(d1), "d2": str(d2)},
        "summary": summary,
        "results": p.results,
        "disclaimer": ("Snapshot from one machine at one moment. Endpoints "
                       "change. Re-run before relying on any source."),
    }

    out = Path(args.out) if args.out else (
        Path(__file__).resolve().parents[1] / "reports" /
        f"source_probe_{dt.datetime.now():%Y%m%d_%H%M%S}.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("=" * 110)
        print("SUMMARY: " + "  ".join(f"{k}={v}" for k, v in sorted(summary.items())))
        print(f"Report written to: {out}")
        working = [r["source"] for r in p.results if r["status"] == "WORKING"]
        print(f"\nConfirmed working ({len(working)}): {', '.join(working) or 'NONE'}")
        if not working:
            print("\nNothing worked. Check your internet connection, or a "
                  "firewall/VPN may be blocking these hosts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
