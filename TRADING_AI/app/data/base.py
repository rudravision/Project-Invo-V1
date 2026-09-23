"""
The DataProvider abstraction.

Every source -- exchange file archive, broker API, CSV dump -- implements this
one interface. The rest of the trading system talks only to `DataRouter` and
never imports a concrete provider, so a source can be swapped out without
touching strategy, backtest or alert code.

Key guarantees:
  * A provider that cannot serve a capability raises NotSupportedError; the
    router moves on to the next provider instead of crashing (spec 26).
  * Every failure is recorded with SOURCE / TIME / ERROR / FALLBACK USED.
  * Providers return a canonical DataFrame schema so downstream code is
    source-agnostic.
"""

from __future__ import annotations

import abc
import dataclasses
import datetime as dt
import enum
import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Iterable

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Capabilities & canonical schema
# --------------------------------------------------------------------------- #
class Capability(str, enum.Enum):
    DAILY_OHLC = "daily_ohlc"
    INTRADAY = "intraday"
    INDEX_OHLC = "index_ohlc"
    QUOTES = "quotes"
    DELIVERY = "delivery"
    DERIVATIVES = "derivatives"
    OPEN_INTEREST = "open_interest"
    INDIA_VIX = "india_vix"
    BREADTH = "breadth"
    CALENDAR = "calendar"
    ANNOUNCEMENTS = "announcements"
    CORPORATE_ACTIONS = "corporate_actions"
    NEWS = "news"
    INDEX_MEMBERSHIP = "index_membership"


# Canonical OHLCV column names. Providers MUST map their native names to these.
OHLCV_COLUMNS = ["date", "symbol", "open", "high", "low", "close", "volume"]


class Freshness(str, enum.Enum):
    REALTIME = "realtime"
    DELAYED = "delayed"
    END_OF_DAY = "end_of_day"
    HISTORICAL = "historical"


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
class ProviderError(Exception):
    """Base class for all provider failures."""


class NotSupportedError(ProviderError):
    """This provider does not offer the requested capability."""


class NotAvailableError(ProviderError):
    """Source reachable but has no data for this request (e.g. holiday)."""


class CredentialsMissingError(ProviderError):
    """Provider needs credentials the user has not supplied."""


class RateLimitedError(ProviderError):
    """Source signalled a rate limit. Back off; do not hammer."""


class DataQualityError(ProviderError):
    """Data arrived but failed validation and must not be traded on."""


# --------------------------------------------------------------------------- #
# Failure ledger (spec 26)
# --------------------------------------------------------------------------- #
@dataclasses.dataclass
class FailureRecord:
    time_utc: str
    source: str
    capability: str
    error: str
    fallback_used: str | None

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


class FailureLog:
    """Append-only JSONL ledger of source failures and fallbacks."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.records: list[FailureRecord] = []

    def record(self, source: str, capability: str, error: str,
               fallback_used: str | None = None) -> FailureRecord:
        rec = FailureRecord(
            time_utc=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            source=source, capability=capability,
            error=str(error)[:500], fallback_used=fallback_used,
        )
        self.records.append(rec)
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec.to_dict()) + "\n")
        log.warning("SOURCE FAILED source=%s cap=%s err=%s fallback=%s",
                    source, capability, rec.error, fallback_used)
        return rec


# --------------------------------------------------------------------------- #
# Rate limiting
# --------------------------------------------------------------------------- #
class RateLimiter:
    """Simple per-host minimum-interval limiter.

    This exists to RESPECT published limits and be a polite client, not to
    evade anything.
    """

    def __init__(self, min_interval: float = 1.0):
        self.min_interval = float(min_interval)
        self._last = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            delta = time.monotonic() - self._last
            if delta < self.min_interval:
                time.sleep(self.min_interval - delta)
            self._last = time.monotonic()


# --------------------------------------------------------------------------- #
# Provider metadata -- feeds the source comparison table in docs
# --------------------------------------------------------------------------- #
@dataclasses.dataclass
class ProviderInfo:
    name: str
    data_available: str
    freshness: Freshness
    historical_depth: str
    update_frequency: str
    rate_limit: str
    cost: str
    reliability: str
    licensing_concerns: str
    backup_source: str
    requires_credentials: bool = False
    verified: bool | None = None       # set by the probe script, never guessed
    verified_at: str | None = None


# --------------------------------------------------------------------------- #
# The interface
# --------------------------------------------------------------------------- #
class DataProvider(abc.ABC):
    """Abstract base every data source implements."""

    name: str = "unnamed"

    def __init__(self, config: dict | None = None,
                 rate_limiter: RateLimiter | None = None):
        self.config = config or {}
        self.rate_limiter = rate_limiter or RateLimiter(
            self.config.get("min_interval_seconds", 1.0)
        )

    # -- metadata ----------------------------------------------------------
    @abc.abstractmethod
    def info(self) -> ProviderInfo:
        """Static description of this source for the comparison table."""

    @abc.abstractmethod
    def capabilities(self) -> set[Capability]:
        """What this provider can actually serve."""

    def supports(self, cap: Capability) -> bool:
        return cap in self.capabilities()

    # -- health ------------------------------------------------------------
    @abc.abstractmethod
    def health_check(self) -> tuple[bool, str]:
        """Cheap liveness probe. Returns (ok, human_readable_detail).

        Must make a REAL request. Never return True optimistically.
        """

    # -- data methods: default to NotSupported so subclasses opt in ---------
    def get_daily_ohlc(self, symbols: Iterable[str], start: dt.date,
                       end: dt.date) -> Any:
        raise NotSupportedError(f"{self.name} does not provide daily OHLC")

    def get_intraday(self, symbol: str, interval: str, start: dt.date,
                     end: dt.date) -> Any:
        raise NotSupportedError(f"{self.name} does not provide intraday data")

    def get_index_ohlc(self, index_names: Iterable[str], start: dt.date,
                       end: dt.date) -> Any:
        raise NotSupportedError(f"{self.name} does not provide index OHLC")

    def get_quote(self, symbols: Iterable[str]) -> Any:
        raise NotSupportedError(f"{self.name} does not provide quotes")

    def get_delivery(self, date: dt.date) -> Any:
        raise NotSupportedError(f"{self.name} does not provide delivery data")

    def get_derivatives(self, date: dt.date) -> Any:
        raise NotSupportedError(f"{self.name} does not provide F&O data")

    def get_trading_calendar(self, year: int) -> Any:
        raise NotSupportedError(f"{self.name} does not provide a calendar")

    def get_announcements(self, since: dt.date) -> Any:
        raise NotSupportedError(f"{self.name} does not provide announcements")

    def get_index_membership(self, index_slug: str) -> Any:
        raise NotSupportedError(f"{self.name} does not provide membership")

    def __repr__(self) -> str:
        return f"<{type(self).__name__} name={self.name!r}>"


# --------------------------------------------------------------------------- #
# Router: primary -> backup chain with failure logging (spec 18 & 26)
# --------------------------------------------------------------------------- #
class DataRouter:
    """Routes a capability request across primary and backup providers.

    The rest of the system depends on THIS, not on any concrete provider.
    """

    def __init__(self, providers: dict[str, DataProvider],
                 roles: dict[str, dict], failure_log: FailureLog):
        self.providers = providers
        self.roles = roles
        self.failure_log = failure_log

    def chain_for(self, role: str) -> list[DataProvider]:
        cfg = self.roles.get(role, {})
        names = [cfg.get("primary")] + list(cfg.get("backups") or [])
        return [self.providers[n] for n in names
                if n and n in self.providers]

    def fetch(self, role: str, method: str, *args, **kwargs) -> Any:
        """Call `method` on each provider in the role chain until one succeeds.

        Raises ProviderError only if EVERY provider in the chain fails, so a
        single dead source can never take the whole system down.
        """
        chain = self.chain_for(role)
        if not chain:
            raise ProviderError(
                f"No provider configured for role '{role}'. "
                f"Check config/sources.yaml -> roles.{role}"
            )

        last_error: Exception | None = None
        for i, provider in enumerate(chain):
            try:
                result = getattr(provider, method)(*args, **kwargs)
                if i > 0:
                    log.info("Role %s served by FALLBACK %s", role, provider.name)
                return result
            except NotSupportedError as e:
                last_error = e
                continue
            except Exception as e:  # noqa: BLE001 - deliberately broad
                last_error = e
                nxt = chain[i + 1].name if i + 1 < len(chain) else None
                self.failure_log.record(provider.name, role, str(e), nxt)

        raise ProviderError(
            f"All providers failed for role '{role}'. "
            f"Tried: {[p.name for p in chain]}. Last error: {last_error}"
        )

    def health_report(self) -> dict[str, tuple[bool, str]]:
        out: dict[str, tuple[bool, str]] = {}
        for name, p in self.providers.items():
            try:
                out[name] = p.health_check()
            except Exception as e:  # noqa: BLE001
                out[name] = (False, f"health_check raised: {e}")
        return out
