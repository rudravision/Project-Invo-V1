"""
Local SQLite database with integrity, atomic writes and backup rotation.

Implements spec 24:
  * WAL journalling + synchronous=FULL -> survives power loss
  * integrity_check / corruption detection
  * atomic file writes via temp-file + os.replace
  * online backups with rotation
  * SHA-256 checksums for raw files, which are never modified after write
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import os
import shutil
import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator

log = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


class Database:
    """Thin, safe wrapper around the project's SQLite file."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # -- connections -------------------------------------------------------
    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=30.0,
                               isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")   # durability over speed
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        """Transaction context: commits on success, rolls back on error."""
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        sql = SCHEMA_PATH.read_text(encoding="utf-8")
        conn = self.connect()
        try:
            conn.executescript(sql)
        finally:
            conn.close()

    # -- integrity ---------------------------------------------------------
    def integrity_check(self) -> tuple[bool, str]:
        """Detect corruption. Returns (ok, detail)."""
        try:
            conn = self.connect()
            try:
                rows = conn.execute("PRAGMA integrity_check").fetchall()
                detail = "; ".join(r[0] for r in rows)
                ok = detail.strip().lower() == "ok"
                fk = conn.execute("PRAGMA foreign_key_check").fetchall()
                if fk:
                    ok = False
                    detail += f"; {len(fk)} foreign-key violations"
                return ok, detail
            finally:
                conn.close()
        except sqlite3.DatabaseError as e:
            return False, f"DatabaseError (likely corrupt): {e}"

    # -- backups (spec 24) -------------------------------------------------
    def backup(self, backup_dir: str | Path, keep: int = 10) -> Path:
        """Consistent online backup, then rotate old ones.

        Uses SQLite's backup API so it is safe while the DB is in use.
        Old backups are pruned oldest-first; the current DB is never touched.
        """
        backup_dir = Path(backup_dir)
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        target = backup_dir / f"{self.path.stem}_{stamp}.sqlite"

        src = self.connect()
        try:
            dst = sqlite3.connect(str(target))
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()

        # checksum sidecar so corruption in the backup itself is detectable
        digest = sha256_file(target)
        target.with_suffix(".sqlite.sha256").write_text(
            f"{digest}  {target.name}\n", encoding="utf-8")

        self._rotate(backup_dir, keep)
        log.info("DB backup written: %s (sha256=%s)", target, digest[:12])
        return target

    @staticmethod
    def _rotate(backup_dir: Path, keep: int) -> None:
        backups = sorted(backup_dir.glob("*.sqlite"),
                         key=lambda p: p.stat().st_mtime, reverse=True)
        for old in backups[keep:]:
            sidecar = old.with_suffix(".sqlite.sha256")
            try:
                old.unlink()
                if sidecar.exists():
                    sidecar.unlink()
                log.info("Rotated out old backup %s", old.name)
            except OSError as e:
                log.warning("Could not rotate %s: %s", old, e)

    def verify_backups(self, backup_dir: str | Path) -> list[dict]:
        """Re-check every backup against its stored checksum."""
        out = []
        for b in sorted(Path(backup_dir).glob("*.sqlite")):
            sidecar = b.with_suffix(".sqlite.sha256")
            expected = (sidecar.read_text().split()[0]
                        if sidecar.exists() else None)
            actual = sha256_file(b)
            out.append({
                "file": b.name,
                "expected": expected,
                "actual": actual,
                "ok": (expected == actual) if expected else None,
                "size_mb": round(b.stat().st_size / 1024**2, 2),
            })
        return out

    # -- convenience -------------------------------------------------------
    def log_quality(self, dataset: str, check_name: str, severity: str,
                    affected: int, detail: str) -> None:
        with self.tx() as c:
            c.execute(
                "INSERT INTO data_quality_log"
                " (dataset, check_name, severity, affected, detail)"
                " VALUES (?,?,?,?,?)",
                (dataset, check_name, severity, affected, detail[:2000]),
            )

    def log_failure(self, rec: dict) -> None:
        with self.tx() as c:
            c.execute(
                "INSERT INTO source_failures"
                " (time_utc, source, capability, error, fallback_used)"
                " VALUES (?,?,?,?,?)",
                (rec.get("time_utc"), rec.get("source"),
                 rec.get("capability"), rec.get("error"),
                 rec.get("fallback_used")),
            )

    def upsert_daily(self, rows: Iterable[dict]) -> int:
        """Insert-or-replace daily bars. Idempotent -- safe to re-run."""
        rows = list(rows)
        if not rows:
            return 0
        with self.tx() as c:
            c.executemany(
                """INSERT INTO daily_ohlc
                   (symbol,date,open,high,low,close,prev_close,volume,
                    turnover,trades,source,is_synthetic)
                   VALUES (:symbol,:date,:open,:high,:low,:close,:prev_close,
                           :volume,:turnover,:trades,:source,:is_synthetic)
                   ON CONFLICT(symbol,date) DO UPDATE SET
                     open=excluded.open, high=excluded.high, low=excluded.low,
                     close=excluded.close, prev_close=excluded.prev_close,
                     volume=excluded.volume, turnover=excluded.turnover,
                     trades=excluded.trades, source=excluded.source,
                     is_synthetic=excluded.is_synthetic,
                     ingested_at=datetime('now')""",
                [_defaults(r) for r in rows],
            )
        return len(rows)

    def upsert_index(self, rows: Iterable[dict]) -> int:
        rows = list(rows)
        if not rows:
            return 0
        with self.tx() as c:
            c.executemany(
                """INSERT INTO index_ohlc
                   (index_name,date,open,high,low,close,change_pct,volume,
                    pe,pb,div_yield,source,is_synthetic)
                   VALUES (:index_name,:date,:open,:high,:low,:close,
                           :change_pct,:volume,:pe,:pb,:div_yield,:source,
                           :is_synthetic)
                   ON CONFLICT(index_name,date) DO UPDATE SET
                     open=excluded.open, high=excluded.high, low=excluded.low,
                     close=excluded.close, change_pct=excluded.change_pct,
                     volume=excluded.volume, source=excluded.source,
                     is_synthetic=excluded.is_synthetic""",
                [_index_defaults(r) for r in rows],
            )
        return len(rows)

    def coverage(self, dataset: str = "daily_ohlc") -> dict:
        """What we already have -- drives incremental downloads (spec 22)."""
        conn = self.connect()
        try:
            if dataset == "daily_ohlc":
                r = conn.execute(
                    "SELECT COUNT(*) n, MIN(date) mn, MAX(date) mx,"
                    " COUNT(DISTINCT symbol) syms FROM daily_ohlc"
                ).fetchone()
            else:
                r = conn.execute(
                    "SELECT COUNT(*) n, MIN(date) mn, MAX(date) mx,"
                    " COUNT(DISTINCT index_name) syms FROM index_ohlc"
                ).fetchone()
            return {"rows": r["n"], "min_date": r["mn"],
                    "max_date": r["mx"], "symbols": r["syms"]}
        finally:
            conn.close()

    def missing_dates(self, symbol: str, start: str, end: str) -> list[str]:
        """Dates in [start,end] with no row for `symbol`, weekdays only."""
        conn = self.connect()
        try:
            have = {r["date"] for r in conn.execute(
                "SELECT date FROM daily_ohlc WHERE symbol=?"
                " AND date BETWEEN ? AND ?", (symbol, start, end))}
            holidays = {r["date"] for r in conn.execute(
                "SELECT date FROM trading_calendar WHERE is_holiday=1")}
        finally:
            conn.close()
        out = []
        d = dt.date.fromisoformat(start)
        e = dt.date.fromisoformat(end)
        while d <= e:
            iso = d.isoformat()
            if d.weekday() < 5 and iso not in have and iso not in holidays:
                out.append(iso)
            d += dt.timedelta(days=1)
        return out


def _defaults(r: dict) -> dict:
    base = {"symbol": None, "date": None, "open": None, "high": None,
            "low": None, "close": None, "prev_close": None, "volume": None,
            "turnover": None, "trades": None, "source": "unknown",
            "is_synthetic": 0}
    base.update(r)
    return base


def _index_defaults(r: dict) -> dict:
    base = {"index_name": None, "date": None, "open": None, "high": None,
            "low": None, "close": None, "change_pct": None, "volume": None,
            "pe": None, "pb": None, "div_yield": None, "source": "unknown",
            "is_synthetic": 0}
    base.update(r)
    return base


# --------------------------------------------------------------------------- #
# Atomic file helpers (spec 24)
# --------------------------------------------------------------------------- #
def sha256_file(path: str | Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def atomic_write_bytes(path: str | Path, data: bytes) -> Path:
    """Write via temp file + fsync + os.replace. Never leaves a partial file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return path


def atomic_write_text(path: str | Path, text: str) -> Path:
    return atomic_write_bytes(path, text.encode("utf-8"))


def write_raw_immutable(path: str | Path, data: bytes,
                        db: Database | None = None, dataset: str = "",
                        for_date: str = "", source: str = "") -> dict:
    """Write a raw download once and never overwrite it (spec 24).

    If the file already exists, its checksum is verified and the existing file
    is kept. The original dataset is never modified in place.
    """
    path = Path(path)
    digest = hashlib.sha256(data).hexdigest()

    if path.exists():
        existing = sha256_file(path)
        status = "exists_identical" if existing == digest else "exists_different"
        if status == "exists_different":
            log.warning(
                "Raw file %s already exists with a DIFFERENT checksum. "
                "Keeping the original (immutable). New copy not written.", path)
        return {"path": str(path), "sha256": existing, "status": status}

    atomic_write_bytes(path, data)
    try:
        os.chmod(path, 0o444)   # read-only: guards against accidental edits
    except OSError:
        pass

    if db is not None:
        with db.tx() as c:
            c.execute(
                "INSERT OR REPLACE INTO raw_files"
                " (path,dataset,for_date,sha256,bytes,source)"
                " VALUES (?,?,?,?,?,?)",
                (str(path), dataset, for_date, digest, len(data), source),
            )
    return {"path": str(path), "sha256": digest, "status": "written"}


def graceful_shutdown(db: Database) -> None:
    """Checkpoint WAL and leave the DB in a clean, consistent state."""
    try:
        conn = db.connect()
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.execute("PRAGMA optimize")
        finally:
            conn.close()
        log.info("Database checkpointed and closed cleanly.")
    except sqlite3.Error as e:
        log.error("Graceful shutdown had a problem: %s", e)
