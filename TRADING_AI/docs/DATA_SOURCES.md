# Free / Public NSE Data Sources — Evaluation

**Researched:** 23 September 2026
**Verification status:** ⚠️ **NOT verified from the machine that wrote this document.**

The environment used to build this project has no network route to
`nseindia.com`, `nsearchives.nseindia.com`, `api.upstox.com` or
`query1.finance.yahoo.com` (TCP blocked; DNS resolves). Every probe returned
`FAILED — SSLError`. That result is recorded verbatim in
`reports/source_probe_20260923_175958.json`.

**Therefore: nothing in the tables below is claimed to work.** The columns
describe what each source is *documented* to provide. The `VERIFIED` column is
filled in only by running, on your own machine:

```
python scripts/probe_sources.py
```

That script writes a dated JSON report with the real HTTP status, latency and
payload shape for each endpoint. Trust that file, not this one.

---

## 1. Primary candidates — official NSE published files

These are files NSE publishes for public download from `all-reports`. No login,
no CAPTCHA, no paywall. Ordinary browser headers and a warm-up cookie are used,
which is how a normal browser fetches them — this is not an access-control
bypass.

| SOURCE | DATA AVAILABLE | REAL-TIME / DELAYED | HISTORICAL DEPTH | UPDATE FREQUENCY | RATE LIMIT | COST | RELIABILITY | LICENSING / TERMS CONCERNS | BACKUP SOURCE | VERIFIED |
|---|---|---|---|---|---|---|---|---|---|---|
| **NSE CM UDiFF Bhavcopy**<br>`nsearchives…/content/cm/BhavCopy_NSE_CM_0_0_0_<YYYYMMDD>_F_0000.csv.zip` | Daily OHLC, close, prev-close, volume, turnover, trade count, ISIN, series — **whole market** | End of day (~18:30 IST) | UDiFF format from **08-Jul-2024**; legacy `cm<DD><MON><YYYY>bhav.csv.zip` before that | Once per trading day | Not published. Self-throttle ≥1 req/s | **₹0** | Authoritative (the exchange). Website layer times out often; URL format changed in 2024 | NSE website terms of use. Personal research generally OK; **redistribution is not**. Read the terms yourself | Broker API; Yahoo (cross-check only) | ❓ run probe |
| **NSE F&O UDiFF Bhavcopy**<br>`…/content/fo/BhavCopy_NSE_FO_…csv.zip` | Futures & options OHLC, settle, contracts, **open interest**, change in OI | End of day | From Jul-2024 (UDiFF) | Daily | Same | **₹0** | Same as CM | Same | Broker API | ❓ run probe |
| **Security-wise delivery**<br>`…/products/content/sec_bhavdata_full_<DDMMYYYY>.csv` | Deliverable quantity, **delivery %**, traded qty | End of day | Several years | Daily | Same | **₹0** | Good; occasionally late | Same | *(none free — see limitations)* | ❓ run probe |
| **All-indices close**<br>`…/content/indices/ind_close_all_<DDMMYYYY>.csv` | OHLC + close for **every** NSE index incl. all sector indices, P/E, P/B, div yield | End of day | Years | Daily | Same | **₹0** | Good | Same | Broker API | ❓ run probe |
| **Index constituents**<br>`…/content/indices/ind_<slug>list.csv` | Membership + **industry/sector label** for NIFTY 50/100/200/500, Bank, IT, … | Static, revised semi-annually | Current snapshot only (no history) | On index review | Same | **₹0** | High | Same | Manual CSV | ❓ run probe |
| **Holiday master**<br>`nseindia.com/api/holiday-master?type=trading` | Official trading holidays per segment | Static | Current year | On publication | Same | **₹0** | High | Same | Hard-coded fallback list | ❓ run probe |
| **Corporate announcements**<br>`nseindia.com/api/corporate-announcements` | Filings, results, board meetings | Near-real-time during the day | Rolling window | Continuous | Same | **₹0** | Moderate; JSON shape changes | Same | RSS feeds | ❓ run probe |

### India VIX, market breadth
- **India VIX** — published in the indices close file and via broker APIs
  (Upstox exposes `NSE_INDEX|India VIX`).
- **Market breadth** (advances/declines) — derivable locally from the bhavcopy
  by counting `close > prev_close`, which is what this system does. No extra
  source needed.

---

## 2. Broker APIs — free, but require **your own** account

These are legitimate, documented APIs. They are free of charge, but you must
open an account and supply your own credentials. The system never ships with,
asks for, or stores anyone else's credentials.

| SOURCE | DATA AVAILABLE | REAL-TIME / DELAYED | HISTORICAL DEPTH | UPDATE FREQUENCY | RATE LIMIT | COST | RELIABILITY | LICENSING / TERMS CONCERNS | BACKUP SOURCE | VERIFIED |
|---|---|---|---|---|---|---|---|---|---|---|
| **Upstox API v3** | Daily + **intraday candles (1-min and up)**, quotes, index data, India VIX, option chain, websocket feed | Real-time via websocket (with token); historical REST | Varies by instrument; intraday depth limited | Live / on-demand | Published per-endpoint limits — respect them | **₹0** with an Upstox account | Good; actively maintained | Access token **expires daily** (SEBI). Static IP required for API trading from 01-Apr-2026 | Fyers / Dhan / Breeze | ❓ needs your token |
| **ICICI Breeze** | Historical **1-second and 1-minute** data, OHLC streaming, option chain with OI | Real-time with session | Documented as ~3 years (1-sec); longer for 1-min | Live | Per docs | **₹0** with an ICICIdirect account | Good | Daily session key required; resident Indians only | Upstox | ❓ needs account |
| **Fyers / Dhan / Angel One** | Similar broker-grade historical + live data | Real-time with token | Varies | Live | Per docs | **₹0** with account | Varies | Daily auth; T&Cs per broker | Each other | ❓ needs account |

> On broker choice: any one of these is enough. **Upstox** is the default in
> `config/sources.yaml` because its historical REST endpoints are the simplest
> to integrate. Switching is a config change, not a code change.

---

## 3. Convenience / cross-check sources

| SOURCE | DATA AVAILABLE | REAL-TIME / DELAYED | HISTORICAL DEPTH | UPDATE FREQUENCY | RATE LIMIT | COST | RELIABILITY | LICENSING / TERMS CONCERNS | BACKUP SOURCE | VERIFIED |
|---|---|---|---|---|---|---|---|---|---|---|
| **Yahoo Finance chart endpoint** (`.NS` symbols) | Daily & intraday OHLCV, indices (`^NSEI`) | ~15-min delayed | Many years daily | Continuous | Undocumented; throttles aggressively | **₹0** | Moderate. Undocumented endpoint, symbol quirks for India, adjusted-price surprises | **Not a licensed API.** Yahoo's ToS restricts redistribution and automated access. Use sparingly as a cross-check only | NSE archive | ❓ run probe |
| **Open-source libraries** — `jugaad-data`, `nse` (NseIndiaApi), `nsepython` | Wrappers over the same NSE endpoints | Same as NSE | Same as NSE | Same | Same | **₹0** (GPL/MIT) | They break when NSE changes URLs; actively patched | Library licence (some GPLv3 — matters if you redistribute) | Direct NSE fetch (what this project does) | ❓ optional |

**Why this project fetches NSE directly rather than depending on a wrapper:**
fewer moving parts, no GPL entanglement, and when NSE changes a URL you fix one
line in `sources.yaml` instead of waiting for an upstream release. The
`DataProvider` interface means you can still drop a library-backed provider in
later.

---

## 4. Role assignment (configured in `config/sources.yaml`)

| ROLE | PRIMARY | BACKUP | HISTORICAL | NOTES |
|---|---|---|---|---|
| Daily OHLC | NSE CM UDiFF bhavcopy | Upstox v3 → Yahoo | NSE archive | Cross-checked where practical |
| Index / sector OHLC | NSE `ind_close_all` | Upstox v3 → Yahoo | NSE archive | |
| Intraday | Upstox v3 | *(none free & reliable)* | — | See limitations |
| Quotes | Upstox v3 (websocket) | Yahoo (delayed) | — | Requires your token |
| Delivery | NSE `sec_bhavdata_full` | *(none)* | NSE archive | Single point of failure |
| Derivatives / OI | NSE F&O bhavcopy | Broker API | NSE archive | EOD only for free |
| Calendar | NSE holiday-master | Static fallback list | — | |
| News / events | NSE announcements | RSS | — | |

Cross-checking is implemented for daily closes: when two sources are available
for the same symbol-date, a disagreement beyond tolerance raises a data-quality
`WARN` and is written to `data_quality_log`.

---

## 5. Compliance position

- No CAPTCHA is solved or bypassed.
- No login, paywall, access control or rate limit is circumvented.
- Requests are self-throttled to ≥1 second per host and identify themselves.
- Only files NSE publishes for public download are fetched.
- Broker APIs are used only with your own account and your own credentials.
- Raw downloads are stored locally for personal research and **not
  redistributed**.
- If you intend to use this commercially, or to redistribute data, you need a
  **paid NSE data licence**. The free route does not cover that.
