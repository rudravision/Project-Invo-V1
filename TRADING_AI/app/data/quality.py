"""
Data-quality validation (spec 22, 26).

Checks performed on daily OHLCV:
  duplicates, missing candles, impossible prices, corporate-action distortions,
  timestamp sanity, trading-holiday alignment, staleness.

The public entry point is `validate_daily()`. Its verdict decides whether the
system may emit a trading signal at all. If the verdict fails, the caller MUST
print the SIGNAL DISABLED banner instead of a recommendation.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import logging
from typing import Any

log = logging.getLogger(__name__)

SIGNAL_DISABLED_BANNER = "WARNING: SIGNAL DISABLED - DATA QUALITY FAILURE"


@dataclasses.dataclass
class Issue:
    check: str
    severity: str          # INFO / WARN / ERROR
    affected: int
    detail: str

    def __str__(self) -> str:
        return f"[{self.severity}] {self.check}: {self.affected} - {self.detail}"


@dataclasses.dataclass
class QualityReport:
    dataset: str
    rows: int
    issues: list[Issue] = dataclasses.field(default_factory=list)
    checked_at: str = dataclasses.field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc)
        .isoformat(timespec="seconds"))

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "ERROR"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "WARN"]

    @property
    def ok(self) -> bool:
        """True only when there are no ERROR-level issues."""
        return not self.errors

    def add(self, check: str, severity: str, affected: int, detail: str):
        if affected > 0 or severity == "ERROR":
            self.issues.append(Issue(check, severity, affected, detail))

    def summary(self) -> str:
        head = (f"Data quality: {self.dataset} | rows={self.rows} | "
                f"{'PASS' if self.ok else 'FAIL'} | "
                f"{len(self.errors)} errors, {len(self.warnings)} warnings")
        if not self.issues:
            return head + "\n  (no issues found)"
        return head + "\n" + "\n".join("  " + str(i) for i in self.issues)

    def persist(self, db) -> None:
        for i in self.issues:
            db.log_quality(self.dataset, i.check, i.severity, i.affected,
                           i.detail)
        if not self.issues:
            db.log_quality(self.dataset, "all_checks", "INFO", 0,
                           f"Clean: {self.rows} rows validated")


# --------------------------------------------------------------------------- #
def validate_daily(df: Any, *, max_staleness_days: int = 5,
                   holidays: set[str] | None = None,
                   dataset: str = "daily_ohlc") -> QualityReport:
    """Validate a canonical daily OHLCV DataFrame.

    Expects columns: date, symbol, open, high, low, close, volume.
    """
    import pandas as pd

    rep = QualityReport(dataset=dataset, rows=int(len(df)))

    if len(df) == 0:
        rep.add("empty_dataset", "ERROR", 1, "No rows at all - nothing to trade on")
        return rep

    required = {"date", "symbol", "open", "high", "low", "close", "volume"}
    missing_cols = required - set(df.columns)
    if missing_cols:
        rep.add("schema", "ERROR", len(missing_cols),
                f"Missing required columns: {sorted(missing_cols)}")
        return rep

    d = df.copy()
    d["date"] = pd.to_datetime(d["date"], errors="coerce")

    # 1. timestamps -------------------------------------------------------
    bad_ts = int(d["date"].isna().sum())
    rep.add("bad_timestamps", "ERROR" if bad_ts else "INFO", bad_ts,
            "Unparseable dates" if bad_ts else "All dates parsed")

    future = int((d["date"].dt.date > dt.date.today()).sum())
    rep.add("future_timestamps", "ERROR" if future else "INFO", future,
            "Rows dated in the future - clock or source error")

    # 2. duplicates -------------------------------------------------------
    dups = int(d.duplicated(subset=["symbol", "date"]).sum())
    rep.add("duplicates", "ERROR" if dups else "INFO", dups,
            "Duplicate (symbol,date) rows")

    # 3. impossible prices -------------------------------------------------
    px = ["open", "high", "low", "close"]
    nonpos = int((d[px] <= 0).any(axis=1).sum())
    rep.add("non_positive_prices", "ERROR" if nonpos else "INFO", nonpos,
            "Rows with a price <= 0")

    nulls = int(d[px].isna().any(axis=1).sum())
    rep.add("null_prices", "ERROR" if nulls else "INFO", nulls,
            "Rows with a missing OHLC value")

    valid = d[px].notna().all(axis=1)
    bad_hl = int((valid & (d["high"] < d["low"])).sum())
    rep.add("high_below_low", "ERROR" if bad_hl else "INFO", bad_hl,
            "high < low")

    out_of_range = int((valid & (
        (d["open"] > d["high"]) | (d["open"] < d["low"]) |
        (d["close"] > d["high"]) | (d["close"] < d["low"]))).sum())
    rep.add("ohlc_out_of_range", "ERROR" if out_of_range else "INFO",
            out_of_range, "open/close outside the high-low band")

    neg_vol = int((d["volume"] < 0).sum())
    rep.add("negative_volume", "ERROR" if neg_vol else "INFO", neg_vol,
            "Negative traded volume")

    zero_vol = int((d["volume"] == 0).sum())
    rep.add("zero_volume", "WARN" if zero_vol else "INFO", zero_vol,
            "Zero-volume bars (illiquid or a data gap)")

    # 4. corporate-action distortions -------------------------------------
    # An unadjusted split shows up as a large overnight gap with no matching
    # intraday range. Flag, never silently "fix".
    d = d.sort_values(["symbol", "date"])
    d["prev_c"] = d.groupby("symbol")["close"].shift(1)
    d["gap"] = (d["close"] / d["prev_c"]) - 1
    susp = d[(d["prev_c"].notna()) & (d["gap"].abs() > 0.20)]
    if len(susp):
        ex = susp.nlargest(min(5, len(susp)), "gap", keep="all")
        sample = ", ".join(
            f"{r.symbol}@{r.date:%Y-%m-%d} {r.gap:+.1%}"
            for r in ex.itertuples())
        rep.add("possible_corporate_action", "WARN", int(len(susp)),
                f"Overnight moves >20% - verify split/bonus adjustment. {sample}")

    extreme = d[(d["prev_c"].notna()) & (d["gap"].abs() > 0.60)]
    rep.add("extreme_price_jump", "ERROR" if len(extreme) else "INFO",
            int(len(extreme)),
            "Overnight moves >60% - almost certainly unadjusted or corrupt")

    # 5. missing candles ---------------------------------------------------
    holidays = holidays or set()
    total_missing = 0
    details = []
    for sym, g in d.groupby("symbol"):
        have = set(g["date"].dt.date)
        if not have:
            continue
        lo, hi = min(have), max(have)
        expect = set()
        cur = lo
        while cur <= hi:
            if cur.weekday() < 5 and cur.isoformat() not in holidays:
                expect.add(cur)
            cur += dt.timedelta(days=1)
        gaps = expect - have
        if gaps:
            total_missing += len(gaps)
            if len(details) < 5:
                details.append(f"{sym}:{len(gaps)}")
    sev = "WARN" if total_missing else "INFO"
    if total_missing > max(10, 0.1 * len(d)):
        sev = "ERROR"
    rep.add("missing_candles", sev, total_missing,
            f"Absent weekday bars (holidays excluded). e.g. {', '.join(details)}")

    # 6. staleness ---------------------------------------------------------
    latest = d["date"].max()
    if pd.notna(latest):
        age = (dt.date.today() - latest.date()).days
        # Discount weekends so a Monday-morning run is not a false alarm.
        sev = "ERROR" if age > max_staleness_days else "INFO"
        rep.add("stale_data", sev, age if age > max_staleness_days else 0,
                f"Newest bar is {latest.date()} ({age} days old); "
                f"limit is {max_staleness_days}")

    return rep


def gate_signal(report: QualityReport, *, allow_synthetic: bool = False,
                is_synthetic: bool = False) -> tuple[bool, str]:
    """Decide whether a trading signal may be emitted.

    Returns (allowed, message). When not allowed the message is the banner
    plus the reasons, ready to print or send to Telegram.
    """
    reasons = []
    if is_synthetic and not allow_synthetic:
        reasons.append("Dataset is SYNTHETIC/demo data - not real market data")
    reasons.extend(str(i) for i in report.errors)

    if reasons:
        return False, (SIGNAL_DISABLED_BANNER + "\n" +
                       "\n".join(f"  - {r}" for r in reasons))
    msg = "Data quality OK"
    if report.warnings:
        msg += f" ({len(report.warnings)} warnings - review before acting)"
    return True, msg
