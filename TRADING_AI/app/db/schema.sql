-- TRADING_AI local database (SQLite).
--
-- Design notes:
--   * Raw downloaded files stay immutable on disk; this DB holds the
--     PROCESSED, reproducible view of them (spec 24).
--   * Every price row carries `source` and `ingested_at` so a bad provider
--     can be identified and its rows recomputed from raw.
--   * `data_quality_log` is the audit trail required by spec 22.
--   * WAL mode + atomic writes are configured in app/db/database.py.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------- symbols --
CREATE TABLE IF NOT EXISTS symbols (
    symbol        TEXT PRIMARY KEY,
    name          TEXT,
    isin          TEXT,
    series        TEXT,
    sector        TEXT,
    industry      TEXT,
    is_fno        INTEGER DEFAULT 0,
    in_nifty50    INTEGER DEFAULT 0,
    in_nifty200   INTEGER DEFAULT 0,
    first_seen    TEXT,
    last_seen     TEXT,
    updated_at    TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_symbols_sector ON symbols(sector);

-- ------------------------------------------------------------ daily OHLC --
CREATE TABLE IF NOT EXISTS daily_ohlc (
    symbol        TEXT NOT NULL,
    date          TEXT NOT NULL,          -- ISO YYYY-MM-DD
    open          REAL,
    high          REAL,
    low           REAL,
    close         REAL,
    prev_close    REAL,
    volume        REAL,
    turnover      REAL,
    trades        REAL,
    source        TEXT NOT NULL,
    is_synthetic  INTEGER NOT NULL DEFAULT 0,  -- 1 = demo data, NEVER tradeable
    ingested_at   TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (symbol, date)
);
CREATE INDEX IF NOT EXISTS idx_daily_date ON daily_ohlc(date);
CREATE INDEX IF NOT EXISTS idx_daily_symbol ON daily_ohlc(symbol);
CREATE INDEX IF NOT EXISTS idx_daily_synth ON daily_ohlc(is_synthetic);

-- ----------------------------------------------------------- index OHLC ---
CREATE TABLE IF NOT EXISTS index_ohlc (
    index_name    TEXT NOT NULL,
    date          TEXT NOT NULL,
    open          REAL, high REAL, low REAL, close REAL,
    change_pct    REAL,
    volume        REAL,
    pe REAL, pb REAL, div_yield REAL,
    source        TEXT NOT NULL,
    is_synthetic  INTEGER NOT NULL DEFAULT 0,
    ingested_at   TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (index_name, date)
);
CREATE INDEX IF NOT EXISTS idx_index_date ON index_ohlc(date);

-- -------------------------------------------------------------- intraday --
CREATE TABLE IF NOT EXISTS intraday_ohlc (
    symbol        TEXT NOT NULL,
    ts            TEXT NOT NULL,          -- ISO datetime with tz
    interval      TEXT NOT NULL,          -- '1m','5m','15m'
    open REAL, high REAL, low REAL, close REAL, volume REAL,
    source        TEXT NOT NULL,
    is_synthetic  INTEGER NOT NULL DEFAULT 0,
    ingested_at   TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (symbol, ts, interval)
);
CREATE INDEX IF NOT EXISTS idx_intraday_sym_int ON intraday_ohlc(symbol, interval);

-- -------------------------------------------------------------- delivery --
CREATE TABLE IF NOT EXISTS delivery (
    symbol TEXT NOT NULL,
    date   TEXT NOT NULL,
    deliverable_qty REAL,
    delivery_pct    REAL,
    traded_qty      REAL,
    source TEXT NOT NULL,
    is_synthetic INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (symbol, date)
);

-- ------------------------------------------------------------ derivatives --
CREATE TABLE IF NOT EXISTS derivatives (
    symbol TEXT NOT NULL,
    date   TEXT NOT NULL,
    expiry TEXT,
    instrument TEXT,          -- FUTSTK / OPTIDX ...
    option_type TEXT,         -- CE / PE / NULL
    strike REAL,
    open REAL, high REAL, low REAL, close REAL,
    settle REAL,
    contracts REAL,
    open_interest REAL,
    change_in_oi REAL,
    source TEXT NOT NULL,
    is_synthetic INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (symbol, date, expiry, instrument, option_type, strike)
);

-- --------------------------------------------------------------- calendar --
CREATE TABLE IF NOT EXISTS trading_calendar (
    date        TEXT PRIMARY KEY,
    is_holiday  INTEGER NOT NULL DEFAULT 0,
    description TEXT,
    segment     TEXT,
    source      TEXT
);

-- ---------------------------------------------------- corporate actions ---
CREATE TABLE IF NOT EXISTS corporate_actions (
    symbol TEXT NOT NULL,
    ex_date TEXT NOT NULL,
    action_type TEXT,         -- SPLIT / BONUS / DIVIDEND / RIGHTS
    ratio_from REAL,
    ratio_to REAL,
    details TEXT,
    source TEXT,
    PRIMARY KEY (symbol, ex_date, action_type)
);

-- ------------------------------------------------------- announcements ----
CREATE TABLE IF NOT EXISTS announcements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT,
    published_at TEXT,
    subject TEXT,
    detail TEXT,
    url TEXT,
    source TEXT,
    UNIQUE(symbol, published_at, subject)
);

-- --------------------------------------------------- data quality log -----
CREATE TABLE IF NOT EXISTS data_quality_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    checked_at TEXT DEFAULT (datetime('now')),
    dataset    TEXT NOT NULL,      -- 'daily_ohlc' etc
    check_name TEXT NOT NULL,      -- 'duplicates','impossible_prices',...
    severity   TEXT NOT NULL,      -- INFO / WARN / ERROR
    affected   INTEGER DEFAULT 0,
    detail     TEXT
);
CREATE INDEX IF NOT EXISTS idx_dq_time ON data_quality_log(checked_at);

-- ------------------------------------------------------ source failures ---
CREATE TABLE IF NOT EXISTS source_failures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    time_utc TEXT,
    source TEXT,
    capability TEXT,
    error TEXT,
    fallback_used TEXT
);

-- ------------------------------------------------------- cache manifest ---
-- Lets the downloader fetch ONLY missing observations (spec 22).
CREATE TABLE IF NOT EXISTS cache_manifest (
    dataset   TEXT NOT NULL,       -- 'daily_ohlc','intraday_5m',...
    key       TEXT NOT NULL,       -- symbol or 'ALL'
    from_date TEXT,
    to_date   TEXT,
    rows      INTEGER,
    checksum  TEXT,
    source    TEXT,
    updated_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (dataset, key)
);

-- -------------------------------------------------------- raw file index --
-- Immutable raw downloads: path + checksum, never modified after write.
CREATE TABLE IF NOT EXISTS raw_files (
    path       TEXT PRIMARY KEY,
    dataset    TEXT,
    for_date   TEXT,
    sha256     TEXT NOT NULL,
    bytes      INTEGER,
    source     TEXT,
    downloaded_at TEXT DEFAULT (datetime('now'))
);

-- ------------------------------------------------------------ cost ledger --
CREATE TABLE IF NOT EXISTS cost_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month     TEXT NOT NULL,       -- YYYY-MM
    category  TEXT NOT NULL,       -- api / server / data / other
    item      TEXT,
    amount_inr REAL NOT NULL DEFAULT 0,
    note      TEXT
);

-- ---------------------------------------------------------- signals -------
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    generated_at TEXT DEFAULT (datetime('now')),
    as_of_date TEXT,
    symbol TEXT,
    rank INTEGER,
    score REAL,
    components TEXT,          -- JSON
    data_quality_ok INTEGER,
    is_synthetic INTEGER NOT NULL DEFAULT 0,
    notes TEXT
);
