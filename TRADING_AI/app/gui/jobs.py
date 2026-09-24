"""
Background job runner.

Long operations (downloading five years of data, backtesting) must never
block the interface. Each job runs on its own thread and publishes progress
that the front end polls. The UI stays responsive throughout and shows a
live progress bar.
"""

from __future__ import annotations

import datetime as dt
import logging
import threading
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger(__name__)


@dataclass
class Job:
    id: str
    name: str
    status: str = "running"        # running | done | error | cancelled
    message: str = "Starting..."
    current: int = 0
    total: int = 0
    started_at: str = field(
        default_factory=lambda: dt.datetime.now().isoformat(timespec="seconds"))
    finished_at: str | None = None
    result: Any = None
    error: str | None = None
    steps: list[str] = field(default_factory=list)
    _cancel: threading.Event = field(default_factory=threading.Event,
                                     repr=False)

    @property
    def percent(self) -> int:
        if self.status == "done":
            return 100
        if not self.total:
            return 0
        return max(0, min(100, int(self.current / self.total * 100)))

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "status": self.status,
                "message": self.message, "current": self.current,
                "total": self.total, "percent": self.percent,
                "started_at": self.started_at, "finished_at": self.finished_at,
                "error": self.error, "steps": self.steps[-40:],
                "result": self.result if isinstance(
                    self.result, (dict, list, str, int, float, type(None)))
                else str(self.result)}


class JobManager:
    """Runs one job at a time (they all hit the same SQLite file)."""

    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._current: str | None = None

    @property
    def busy(self) -> bool:
        with self._lock:
            j = self._jobs.get(self._current or "")
            return bool(j and j.status == "running")

    def current(self) -> Job | None:
        with self._lock:
            return self._jobs.get(self._current or "")

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def recent(self, n: int = 10) -> list[dict]:
        with self._lock:
            js = sorted(self._jobs.values(), key=lambda j: j.started_at,
                        reverse=True)
        return [j.to_dict() for j in js[:n]]

    def start(self, name: str, fn: Callable[[Job], Any]) -> Job:
        """Start `fn` on a worker thread. Rejects if a job is already running."""
        with self._lock:
            cur = self._jobs.get(self._current or "")
            if cur and cur.status == "running":
                raise RuntimeError(
                    f"'{cur.name}' is already running. Please wait for it to "
                    f"finish.")
            job = Job(id=uuid.uuid4().hex[:12], name=name)
            self._jobs[job.id] = job
            self._current = job.id

        def runner():
            try:
                job.result = fn(job)
                if job.status != "cancelled":
                    job.status = "done"
                    job.message = "Finished."
                    if job.total:
                        job.current = job.total
            except Exception as e:  # noqa: BLE001
                job.status = "error"
                job.error = str(e)
                job.message = friendly_error(e)
                log.exception("Job %s failed", job.name)
                job.steps.append(f"ERROR: {e}")
                job.steps.append(traceback.format_exc()[-1500:])
            finally:
                job.finished_at = dt.datetime.now().isoformat(timespec="seconds")

        threading.Thread(target=runner, name=f"job-{job.name}",
                         daemon=True).start()
        return job

    def cancel(self, job_id: str) -> bool:
        j = self.get(job_id)
        if j and j.status == "running":
            j._cancel.set()
            j.status = "cancelled"
            j.message = "Stopped at your request."
            return True
        return False


def progress_adapter(job: Job):
    """Adapts our various progress callback shapes onto a Job."""
    def cb(message: str, current: int | None = None,
           total: int | None = None):
        job.message = str(message)
        if current is not None:
            job.current = current
        if total is not None:
            job.total = total
        if not job.steps or job.steps[-1] != job.message:
            job.steps.append(job.message)
    return cb


def should_stop(job: Job):
    return lambda: job._cancel.is_set()


# --------------------------------------------------------------------------- #
def friendly_error(e: Exception) -> str:
    """Turn a Python exception into something a human can act on."""
    name = type(e).__name__
    text = str(e)
    low = text.lower()

    if name in ("ConnectionError", "ConnectTimeout", "ReadTimeout",
                "Timeout", "SSLError", "NewConnectionError",
                "MaxRetryError", "ConnectionResetError"):
        return ("Could not reach the market-data source. Check your internet "
                "connection and try again. If you are on office Wi-Fi or a "
                "VPN, that may be blocking it.")
    if "403" in text or "forbidden" in low:
        return ("The data source refused the request (HTTP 403). We will not "
                "try to work around that. Try again later or use a broker "
                "account instead.")
    if "429" in text or "rate limit" in low:
        return ("The data source asked us to slow down. Wait a few minutes "
                "and try again.")
    if "404" in text:
        return "That day's file is not published by NSE."
    if name in ("DatabaseError", "OperationalError", "IntegrityError"):
        if "locked" in low:
            return ("The database is busy. Close any other copy of "
                    "TRADING_AI and try again.")
        return ("There is a problem with the database file. Use Backups -> "
                "Restore to recover the last good copy.")
    if name in ("PermissionError",):
        return ("Windows refused access to a file on the SSD. Make sure the "
                "drive is not write-protected and no other program has the "
                "file open.")
    if name in ("FileNotFoundError",):
        return f"A required file is missing: {text}"
    if "no space" in low or name == "OSError" and "space" in low:
        return "The SSD is full. Free up some space and try again."
    return f"{name}: {text}"
