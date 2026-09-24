"""
Additive schema migrations.

Rules:
  * Every migration is ADDITIVE. No column is dropped, no table is deleted,
    no existing row is rewritten.
  * A verified backup is taken before any migration runs.
  * Migrations are idempotent and tracked in schema_migrations, so running
    them twice is harmless.
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Migration 001: session calendar, symbol lifecycle, gap ledger, download
# queue, corporate-action adjustment factors.
#
# These are the tables the old system lacked, which is why it could not tell
# "NSE was closed" apart from "our download failed".
# ---------------------------------------------------------------------------
M001 = """
-- Authoritative record of what each calendar date actually WAS.
-- status: SESSION | WEEKEND | HOLIDAY | UNKNOWN
-- UNKNOWN is the honest default: a weekday we have not yet confirmed.
CREATE TABLE IF NOT EXISTS market_sessions (
    date               TEXT PRIMARY KEY,
    status             TEXT NOT NULL DEFAULT 'UNKNOWN',
    bhavcopy_available INTEGER NOT NULL DEFAULT 0,
    index_available    INTEGER NOT NULL DEFAULT 0,
    delivery_available INTEGER NOT NULL DEFAULT 0,
    symbol_count       INTEGER DEFAULT 0,
    evidence           TEXT,
    source             TEXT,
    confirmed_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON market_sessions(status);

-- When each symbol was actually tradeable. Prevents counting pre-listing
-- or post-delisting dates as "missing data".
CREATE TABLE IF NOT EXISTS symbol_lifecycle (
    symbol         TEXT PRIMARY KEY,
    status         TEXT NOT NULL DEFAULT 'ACTIVE',  -- ACTIVE|SUSPENDED|DELISTED|UNKNOWN
    first_session  TEXT,
    last_session   TEXT,
    listing_date   TEXT,
    delisting_date TEXT,
    sessions_seen  INTEGER DEFAULT 0,
    note           TEXT,
    updated_at     TEXT DEFAULT (datetime('now'))
);

-- Symbol renames, so history can be stitched across a ticker change.
CREATE TABLE IF NOT EXISTS symbol_aliases (
    old_symbol  TEXT NOT NULL,
    new_symbol  TEXT NOT NULL,
    change_date TEXT,
    source      TEXT,
    PRIMARY KEY (old_symbol, new_symbol)
);

-- Every hole found by the validator, with WHY it is a hole.
CREATE TABLE IF NOT EXISTS data_gaps (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol         TEXT NOT NULL,
    date           TEXT NOT NULL,
    classification TEXT NOT NULL,
    detail         TEXT,
    resolved       INTEGER NOT NULL DEFAULT 0,
    detected_at    TEXT DEFAULT (datetime('now')),
    resolved_at    TEXT,
    UNIQUE(symbol, date)
);
CREATE INDEX IF NOT EXISTS idx_gaps_class ON data_gaps(classification, resolved);

-- Resumable work queue. An interrupted download picks up here.
CREATE TABLE IF NOT EXISTS download_queue (
    dataset     TEXT NOT NULL,
    key         TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING|DONE|FAILED|SKIPPED
    attempts    INTEGER NOT NULL DEFAULT 0,
    last_error  TEXT,
    priority    INTEGER NOT NULL DEFAULT 100,
    updated_at  TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (dataset, key)
);
CREATE INDEX IF NOT EXISTS idx_queue_status ON download_queue(status, priority);

-- Corporate-action price adjustment factors, derived and auditable.
CREATE TABLE IF NOT EXISTS adjustment_factors (
    symbol     TEXT NOT NULL,
    ex_date    TEXT NOT NULL,
    factor     REAL NOT NULL,
    reason     TEXT,
    ratio_text TEXT,
    confidence TEXT,          -- CONFIRMED | INFERRED | UNRESOLVED
    source     TEXT,
    detected_gap REAL,
    created_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (symbol, ex_date, reason)
);

-- Adjusted price series, derived from raw. Raw is never modified.
CREATE TABLE IF NOT EXISTS daily_ohlc_adjusted (
    symbol TEXT NOT NULL,
    date   TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL, volume REAL,
    adj_factor REAL NOT NULL DEFAULT 1.0,
    built_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (symbol, date)
);

-- Index membership over time, for sector mapping and survivorship control.
CREATE TABLE IF NOT EXISTS index_membership (
    index_slug TEXT NOT NULL,
    symbol     TEXT NOT NULL,
    sector     TEXT,
    added_on   TEXT,
    removed_on TEXT,
    source     TEXT,
    PRIMARY KEY (index_slug, symbol)
);
CREATE INDEX IF NOT EXISTS idx_membership_sym ON index_membership(symbol);
"""

# ---------------------------------------------------------------------------
# Migration 002: settings + calibrated probability evidence.
# ---------------------------------------------------------------------------
M002 = """
CREATE TABLE IF NOT EXISTS app_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Out-of-sample calibration bins. A displayed probability MUST come from
-- here, with n_observations attached, or it is not displayed at all.
CREATE TABLE IF NOT EXISTS probability_calibration (
    model_version  TEXT NOT NULL,
    horizon_days   INTEGER NOT NULL,
    bucket         INTEGER NOT NULL,
    score_lo       REAL,
    score_hi       REAL,
    n_observations INTEGER NOT NULL,
    n_positive     INTEGER NOT NULL,
    hit_rate       REAL,
    mean_return    REAL,
    built_at       TEXT DEFAULT (datetime('now')),
    fold           TEXT,
    PRIMARY KEY (model_version, horizon_days, bucket, fold)
);

CREATE TABLE IF NOT EXISTS model_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    model_version TEXT,
    trained_at    TEXT DEFAULT (datetime('now')),
    train_start   TEXT, train_end TEXT,
    test_start    TEXT, test_end  TEXT,
    n_train       INTEGER, n_test INTEGER,
    metrics       TEXT,
    features      TEXT,
    notes         TEXT
);
"""

MIGRATIONS: list[tuple[str, str]] = [
    ("001_sessions_lifecycle_gaps", M001),
    ("002_settings_calibration", M002),
]


def applied(conn) -> set[str]:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " name TEXT PRIMARY KEY, applied_at TEXT DEFAULT (datetime('now')))"
    )
    return {r[0] for r in conn.execute("SELECT name FROM schema_migrations")}


def pending(db) -> list[str]:
    conn = db.connect()
    try:
        done = applied(conn)
    finally:
        conn.close()
    return [n for n, _ in MIGRATIONS if n not in done]


def migrate(db, backup_dir: Path | None = None,
            progress=None) -> dict:
    """Apply pending migrations. Takes a verified backup first.

    Returns a summary dict. Raises only if a migration genuinely fails, in
    which case the pre-migration backup is the recovery point.
    """
    def say(msg):
        log.info(msg)
        if progress:
            progress(msg)

    todo = pending(db)
    if not todo:
        return {"applied": [], "backup": None,
                "detail": "Database schema already up to date."}

    backup_path = None
    if backup_dir is not None:
        say(f"Backing up before migrating ({len(todo)} change(s))...")
        backup_path = db.backup(backup_dir, keep=20)
        verified = [b for b in db.verify_backups(backup_dir)
                    if b["file"] == backup_path.name]
        if not verified or verified[0]["ok"] is not True:
            raise RuntimeError(
                "Pre-migration backup failed its checksum. Refusing to "
                "migrate without a verified recovery point.")
        say(f"Verified backup: {backup_path.name}")

    done = []
    for name, sql in MIGRATIONS:
        if name not in todo:
            continue
        say(f"Applying {name}...")
        conn = db.connect()
        try:
            conn.executescript("BEGIN;" + sql + "\nCOMMIT;")
            conn.execute("INSERT OR IGNORE INTO schema_migrations (name)"
                         " VALUES (?)", (name,))
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise
        finally:
            conn.close()
        done.append(name)

    say(f"Schema updated ({len(done)} migration(s)).")
    return {"applied": done,
            "backup": str(backup_path) if backup_path else None,
            "detail": f"Applied {len(done)} migration(s)."}
