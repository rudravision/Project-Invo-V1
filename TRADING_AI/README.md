# TRADING_AI

A portable, low-cost NSE trading **research and alert** system designed to run
entirely from an external SSD, on free and public data, at **₹0/month**.

> **Not investment advice.** This is a research tool. It produces rankings and
> statistics, not instructions. Verify everything before risking money.

---

## Read this first — what is and isn't real

This project was built in a Linux cloud sandbox that had **no SanDisk SSD
attached** and **no network route to NSE, Upstox or Yahoo**. Two consequences:

1. **SSD detection was written and tested, but never run against your actual
   drive.** It auto-detects at runtime and never hardcodes `E:`. On first run it
   will tell you exactly what it found.
2. **No data source has been confirmed working.** The probe script was run and
   every endpoint returned `FAILED — SSLError` (blocked egress). That real
   result is saved in `reports/source_probe_20260923_175958.json`.

Anything that could not be verified is marked ❓ rather than asserted.
**Run `python scripts/probe_sources.py` on your own machine** — that is the
only source of truth about what works.

The dataset currently in the database is **synthetic random numbers**, clearly
flagged, and the signal gate **blocks all recommendations** derived from it.

---

## Quick start (Windows, from the SSD)

```
1. Copy the TRADING_AI folder to your SanDisk SSD
2. INSTALL.bat            # creates the Python env ON THE SSD
3. SYSTEM_CHECK.bat       # verifies SSD, internet, DB, credentials, space
4. python scripts\probe_sources.py      # find out what actually works
5. python scripts\bootstrap_data.py     # download a small real sample
6. START_TRADING_AI.bat   # run the pipeline
```

Linux/macOS: `./install.sh`, `./system_check.sh`, `./start_trading_ai.sh`.

---

## Scripts

| Script | Purpose |
|---|---|
| `INSTALL.bat` / `install.sh` | Create the Python environment **on the SSD**, build folders, write a `.env` template |
| `START_TRADING_AI.bat` / `start_trading_ai.sh` | Pre-flight check, then run the full pipeline |
| `STOP.bat` / `stop.sh` | Graceful shutdown: WAL checkpoint, stop dashboard |
| `UPDATE.bat` / `update.sh` | Upgrade packages, re-probe sources, fetch **only missing** data, refresh reports |
| `BACKUP.bat` / `backup.sh` | Checksummed backup of DB, config and models, with rotation |
| `SYSTEM_CHECK.bat` / `system_check.sh` | All eight pre-flight checks |

Launchers use `%~dp0` / `$BASH_SOURCE` to locate themselves, so **the SSD drive
letter can change** and nothing breaks.

---

## Layout

```
TRADING_AI/
├── app/
│   ├── core/          ssd.py (detection), config.py (settings, secrets)
│   ├── data/          base.py (DataProvider + Router), quality.py
│   │   └── providers/ nse_archive.py
│   ├── db/            database.py, schema.sql
│   ├── analytics/     indicators.py, ranking.py
│   ├── backtest/      engine.py
│   └── alerts/        telegram.py
├── config/            paths.yaml, sources.yaml, .env (untracked)
├── data/              raw/ (immutable) processed/ historical/ intraday/ backup/
├── database/          trading_ai.sqlite
├── models/            production/ experimental/ archived/
├── backtests/ reports/ logs/ backups/ dashboard/ notebooks/ tests/ docs/
└── scripts/           probe_sources, bootstrap_data, run_pipeline,
                       system_check, backup, shutdown, cost_tracker,
                       make_demo_dataset
```

---

## How the data layer protects you

**Swappable sources.** Everything talks to `DataRouter`, never to a concrete
provider. Replacing NSE with a broker API is a `sources.yaml` edit.

**Automatic fallback.** Primary fails → backup is tried → the failure is logged
with `SOURCE / TIME / ERROR / FALLBACK USED` to `logs/source_failures.jsonl` and
the `source_failures` table. One dead source never takes the system down.

**The signal gate.** Before any recommendation, `validate_daily()` checks
duplicates, missing candles, impossible prices, corporate-action distortions,
timestamps, holidays and staleness. Any `ERROR`, or any synthetic data, and the
system prints

```
WARNING: SIGNAL DISABLED - DATA QUALITY FAILURE
```

instead of a recommendation. This is enforced in the pipeline, the dashboard
and the Telegram notifier.

**Immutable raw data.** Downloads are written once, `chmod 444`, SHA-256
recorded in `raw_files`. A re-download with different content **keeps the
original** and logs the discrepancy. Processed tables are always rebuildable
from raw.

**Incremental cache.** `bootstrap_data.py` queries what's already stored and
downloads only missing dates. Re-running it after a gap costs a handful of
requests, not a full re-download.

**Storage estimate before download.** Prints projected MB and request count and
requires confirmation. Aborts if free space lacks a 3× safety margin.

---

## Data safety

- SQLite in **WAL** mode, `synchronous=FULL`
- Atomic writes (temp file → `fsync` → `os.replace`) — never a partial file
- `PRAGMA integrity_check` + `foreign_key_check` on every system check
- Online backups via SQLite's backup API, SHA-256 sidecars, rotation (keep 10)
- Graceful shutdown checkpoints WAL so the SSD is safe to unplug
- `config/.env` is gitignored and **excluded from backups** — secrets are never
  archived

---

## Current status

| Step | Status |
|---|---|
| 1. Detect SanDisk SSD | ✅ Built, cross-platform. ❌ No SSD present here — reports honestly |
| 2. Report free space | ✅ Working (`system_check.py`) |
| 3. Create TRADING_AI dir | ✅ Additive only; verified it never deletes existing files |
| 4. Research free sources | ✅ `docs/DATA_SOURCES.md` |
| 5. Test which sources work | ✅ Probe built and run. **All blocked in sandbox** — re-run on your machine |
| 6. DataProvider abstraction | ✅ Interface + router + fallback, tested |
| 7. Local database | ✅ SQLite, 14 tables, integrity + backups |
| 8. Sample dataset | ⚠️ **Synthetic only** — real download blocked |
| 9. Validate dataset | ✅ 7 check families, gate enforced |
| 10. NIFTY + sector heatmap | ✅ Running |
| 11. Stock ranking prototype | ✅ Running |
| 12. Backtest | ✅ Walk-forward, no look-ahead, full Indian cost model |
| 13. ML + Telegram | 🔜 Telegram client built; ML deferred until real data exists |

**34/34 tests pass** (`python -m pytest tests/ -q`).

---

## Why no ML yet

ML on synthetic random walks learns nothing and would produce fake probability
numbers. The correct order is: real data → honest rule-based baseline → then ML
that has to *beat* that baseline out-of-sample. The rule-based ranker in
`app/analytics/ranking.py` is that baseline.

---

## Cost

```
python scripts/cost_tracker.py
```

Currently **₹0/month**. See `docs/FREE_DATA_LIMITATIONS.md` for exactly where
free data falls short, what a fix costs, and whether it's worth it. Nothing is
ever purchased automatically.
