# TRADING_AI — Delivery Report

Date: 24 September 2026

---

## 1. WHAT WAS WRONG

Your run reported three symptoms. They had one root cause and two
consequences. I reproduced the failure exactly before changing anything
(`scripts/repro_bug.py`), rather than guessing.

| Symptom you saw | What was actually happening |
|---|---|
| `rows=9000 \| FAIL`, `missing_candles: 7600` | The downloader skipped any day whose HTTP request failed and never came back to it. 42 of 87 weekdays were **never downloaded**. Nothing recorded which weekdays were genuine NSE sessions, so the validator treated "never attempted" as "data is corrupt": 200 symbols × 38 absent days = 7,600. |
| `No index data available` | `bootstrap_data.py` downloaded stock prices but **never downloaded index files at all**. The heatmap had nothing to draw. |
| `No stocks passed the liquidity/history filters` | Ranking needs 130 sessions of history per stock. Only 45 sessions existed. |

So the number 7,600 was real arithmetic on a wrong premise. The data was not
corrupted — it was **incomplete, and the system could not tell the difference
between a market holiday, a failed download, and a stock that simply was not
listed yet.**

Two further problems were found while building the rest of the system:

- **Staleness could be hidden by a stale calendar.** The new validator
  measured "how many confirmed sessions have happened since your last bar".
  If the calendar had not been updated either, there were no newer sessions
  to count, and a **year-old database reported itself as fresh**. My own test
  (`test_stale_data_blocks_recommendations`) caught it. Fixed by also counting
  unclassified weekdays up to today.
- **Short-side probabilities looked up the wrong bucket.** I had negated the
  score for shorts. The fix is the complement of the *same* bucket, since the
  table stores P(next return > 0). Caught by
  `test_short_probability_is_the_complement_not_a_flipped_score`.

---

## 2. WHAT I FIXED

### Data layer
- **A real trading calendar.** Every date is `SESSION`, `HOLIDAY`, `WEEKEND`
  or `UNKNOWN`. `UNKNOWN` is the honest default for a weekday nobody has
  checked — it is treated as *repairable*, not as corruption. A confirmed
  session is never silently downgraded.
- **Nothing is skipped silently.** Every weekday goes into a download queue
  with attempt counts. Failures are retried; an interrupted run resumes where
  it stopped. A weekday that returns 404 from NSE is positive evidence the
  market was closed, so it is marked `HOLIDAY`.
- **Gap classification.** Every absent bar gets a reason: `NOT_YET_LISTED`,
  `DELISTED`, `NOT_TRADED`, `HOLIDAY`, `WEEKEND` (all legitimate — these never
  block signals) versus `SOURCE_NOT_FETCHED`, `SOURCE_UNAVAILABLE`,
  `UNVERIFIED_DATE` (repairable) versus `UNEXPLAINED` (flagged for a human).
- **Indices and sectors are downloaded.** 24 indices including NIFTY 50/100/200,
  all the sector indices you listed, and INDIA VIX, plus index membership so
  every stock has a sector.
- **Corporate actions.** Any overnight move beyond ±20% is investigated, never
  deleted. Classified `CONFIRMED` (matches an NSE-published action),
  `INFERRED` (lands within 1.5% of a standard ratio *and* the whole session
  traded at the new scale, which a genuine crash does not) or `UNRESOLVED`
  (left completely alone and listed for you to review). **Raw prices are never
  modified** — adjusted bars are written to a separate table and can be
  rebuilt from raw at any time.

### The gate was not weakened
This is the part worth checking. On the *same unrepaired data*:

```
OLD validator:  [ERROR] missing_candles: 7600   <- misleading
                [ERROR] stale_data: 7
NEW validator:  [ERROR] unverified_dates: 38    <- accurate
```

Coverage of confirmed sessions was **9,000 / 9,000 = 100%**. The only real
problem was 38 weekdays nobody had checked. **The gate still BLOCKS** — it
just now blocks for the true reason, and tells you which button to press.

### Interface
A desktop window replacing the CMD menu. Local web UI served from
`127.0.0.1` — nothing is exposed to the network, nothing is uploaded, and the
charts are hand-written canvas code with no CDN, so it works offline.

Every long operation runs on a background thread with a live progress bar,
so **the window never freezes** and you can stop a run mid-way.

---

## 3. FILES CHANGED

**New — interface**
| File | Purpose |
|---|---|
| `app/gui/server.py` | Local API: status, heatmap, recommendations, charts, backtest, sources, settings, Telegram, backups, logs |
| `app/gui/jobs.py` | Background jobs, progress, cancellation, plain-English error translation |
| `app/gui/pipeline.py` | The UPDATE & ANALYZE MARKET chain |
| `app/gui/static/index.html`, `app.css`, `app.js`, `charts.js` | The interface itself |
| `scripts/launch_gui.py` | Window launcher (pywebview → Chrome/Edge app mode → browser) |
| `TRADING_AI.bat`, `trading_ai.sh` | Double-click launcher |

**New — analysis**
| File | Purpose |
|---|---|
| `app/analytics/probability.py` | Walk-forward calibration; refuses to show a number without 200+ observations |
| `app/analytics/recommend.py` | Candidates, entry/stop/target, risk-based position sizing, portfolio summary |
| `app/data/corporate_actions.py` | Split/bonus detection and back-adjustment |

**New — data layer (previous commit)**
`app/db/migrations.py`, `app/data/calendar.py`, `app/data/repair.py`,
`app/data/quality2.py`, `scripts/sync_data.py`, `scripts/repair_data.py`,
`scripts/repro_bug.py`

**Modified**
`app/data/quality2.py` (stale-calendar fix), `INSTALL.bat` (desktop shortcut,
new instructions), `requirements.txt` (Flask; Streamlit/plotly now optional)

**Untouched and still working:** every existing script, the pipeline, the
backtest engine, indicators, ranking, Telegram, backups, the Streamlit
dashboard. Nothing was deleted.

**New tests**
`tests/test_corporate_actions.py` (10), `tests/test_probability.py` (16),
`tests/test_gui_api.py` (32), plus the earlier `test_repair.py` (20) and
`test_sync_integration.py` (8).

---

## 4. DATA QUALITY — BEFORE

Measured on the reproduced failure, not recalled from your screenshot:

```
Rows:                 9,000
Symbols:              200
Weekdays in range:    87
Weekdays downloaded:  45      (42 never attempted)
Sessions confirmed:   0       (no calendar existed)
Index rows:           0

[ERROR] missing_candles: 7600 - Absent weekday bars (holidays excluded).
[ERROR] stale_data: 7        - Newest bar is 7 days old; limit is 5
SIGNAL GATE: BLOCKED
```

## 5. DATA QUALITY — AFTER

Same database, after the repair pass, verified against a stub NSE server that
observes holidays and fails transiently:

```
Sessions confirmed:      45 (inferred from data already held)
Coverage of sessions:    9,000 / 9,000 = 100%
Missing on real sessions: 0
Legitimate absences:     classified, not counted as errors
Remaining problem:       38 weekdays not yet checked against the NSE calendar
SIGNAL GATE: BLOCKED (correctly — with an accurate, actionable reason)
```

After a full `sync_data` run the integration tests confirm: every session
downloaded, holidays marked, transient failures retried, a second run
downloads **nothing** (fully incremental), an interrupted run resumes to zero
problems, and the validator then passes.

---

## 6. HISTORICAL DATA AVAILABLE

You chose **5 years**, which is now the default. Selectable in Settings:
3m / 6m / 1y / 2y / 3y / 5y / MAX.

Downloads are **incremental and resumable** — data already stored is never
re-downloaded. A verified backup is taken before any migration or repair.

Rough sizing for NIFTY 200 over 5 years: ~1,250 sessions × 200 stocks
≈ 250,000 daily bars, comfortably under 200 MB with indices and delivery data
included. First full download takes a while; every run after that fetches
only the new days.

---

## 7. BACKTEST RESULTS

**Engine verified; numbers below are from synthetic data and are meaningless
as market results.** No NSE endpoint is reachable from my sandbox, so I have
no real prices here. Reporting synthetic output as if it were real
performance is exactly what you told me not to do. Run it on your machine
after a real download to get real figures — the Backtest page will label
results from practice data with a red banner.

What the engine does, verified by the run:

```
Period              2023-03-27 to 2026-09-24   (914 sessions, walk-forward)
Rebalances          183
Round trips         327
Trades              759
Costs modelled      brokerage 0.03% capped at Rs 20, STT 0.1% on sell,
                    exchange charges, GST 18%, stamp duty, 10 bps slippage/side
Total costs         reported explicitly, as a % drag on return
Benchmark           NIFTY 50 comparison included
Reported            win rate, avg win/loss, profit factor, expectancy,
                    max drawdown, Sharpe, Sortino, CAGR, total return,
                    annualised volatility, cost drag, excess vs benchmark
```

**Look-ahead and survivorship:** entries are taken at the **next session's
open** from a ranking computed on the **previous close**. The calibration
engine slices history to `date <= as_of` before the scoring function ever
sees it, and a test asserts the scorer is never handed future data.

---

## 8. PROBABILITIES — HOW THEY WORK

You asked that a score never be dressed up as a probability. It is not.

1. History is split walk-forward. The model only ever scores a period it was
   not built on.
2. Out-of-sample scores are grouped into 10 buckets.
3. For each bucket, the system counts **how often the next session was
   actually positive**. That observed frequency *is* the probability.
4. **A bucket with fewer than 200 observations shows "Insufficient data"** —
   your strict setting. No number is invented.
5. Every probability is displayed with its sample size ("based on 1,240
   historical observations").

There is no black box. The score is a documented weighted sum of factors and
the probability is a lookup of what actually happened to similar setups.

---

## 9. KNOWN LIMITATIONS

**Tested here / not tested here.** I have no internet access to NSE from my
environment. So:

- ✅ Tested: all logic, the repair pass, calendar handling, gap
  classification, corporate actions, calibration, sizing, every API endpoint,
  job progress and cancellation, settings persistence across restart, backup
  and restore, the safety gate. 120 automated tests pass.
- ✅ Tested against a **stub NSE server** that observes holidays, returns 404
  on closed days and fails transiently: incremental download, resume, retry.
- ❌ Not tested: the real NSE endpoints, actual download volumes and timings,
  and the desktop window on Windows (no GUI toolkit runs in my sandbox — the
  server and every page behind it are tested; the window that displays them
  is the untested part). Your machine already reached 13 working sources, so
  the block is environmental, not a code problem.

**Other limitations**

- Free EOD data is not institutional grade. It is end-of-day, occasionally
  revised, and delivery data can lag.
- Probabilities near 50% are honest, not broken. On daily horizons with a
  simple factor model, that is what the evidence usually supports. Treat a
  53% bucket as a slight edge, not a signal.
- `INFERRED` corporate actions are a judgement call. The ratio test plus the
  intraday-range test make false positives unlikely but not impossible.
  Review the "Unresolved Corporate Actions" log periodically.
- The NSE equity quote metadata endpoint returns HTTP 403. I left it alone,
  as instructed. It is not used.
- Upstox v2 candle endpoints are deprecated; v3 is the target. Whether v3
  intraday needs a Bearer token must be verified empirically with your
  credentials — the docs are inconsistent and I will not assume.
- Backtest results with trading costs are highly sensitive to the rebalance
  frequency. The default 5-day rebalance already carries a visible cost drag.

**This is a research and decision-support tool. It is not a guaranteed-profit
machine, and it will be wrong regularly.**

---

## 10. HOW TO START THE GUI

**On your machine (`G:\Trading\TRADING_AI`):**

1. Double-click **`INSTALL.bat`** once. It installs into `.venv` on the SSD
   and creates a desktop shortcut.
2. Double-click **`TRADING_AI`** on your desktop (or `TRADING_AI.bat`).
3. Click the big blue **UPDATE & ANALYZE MARKET** button.
4. Watch the progress bar. First run downloads 5 years, so allow time. You
   can keep using the window, or press Stop.

Then: read the dashboard → open the Sector Heatmap and click a sector → check
Trade Ideas for longs and shorts → click any stock symbol for its chart.

**If something is wrong** the dashboard shows a plain-English banner with
buttons (REPAIR DATA / UPDATE NOW / VIEW DETAILS / RETRY) instead of a code.
For example `missing_candles: 7600` now reads:

> **Historical database is incomplete** — 7,600 expected price records are
> missing for days the market was open. Trading recommendations are disabled
> until this is fixed. **[REPAIR DATA]**

**Advanced / debugging only** (CMD still works, nothing was removed):

```
python scripts\repair_data.py --diagnose     inspect data problems, read-only
python scripts\repair_data.py --repair       fix them
python scripts\sync_data.py --period 5y      download from the command line
python scripts\run_pipeline.py               the original pipeline
python -m pytest tests -q                    run the test suite
```
