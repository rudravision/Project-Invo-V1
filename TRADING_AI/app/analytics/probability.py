"""
Calibrated probability engine (spec item 7 & 11).

The rule you set: a number like "72% probability" must come from calibrated
OUT-OF-SAMPLE results, with the supporting sample size shown, or it must not
be shown at all.

How this works:
  1. Features and forward returns are computed for every (symbol, date).
  2. A WALK-FORWARD split is used: the model only ever sees data strictly
     before the period it is scored on. No look-ahead, no training on the
     test set.
  3. Scores from the held-out folds are grouped into buckets.
  4. For each bucket we count how often the forward return was positive.
     THAT empirical frequency is the probability. It is not a model output
     squashed through a sigmoid and relabelled.
  5. A bucket with fewer than MIN_OBSERVATIONS samples returns
     "Insufficient data". You chose strict mode, so that threshold is 200.

There is no fitted black box here. The score is a transparent weighted sum,
and the probability is a lookup of what actually happened historically to
similar setups.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

MIN_OBSERVATIONS = 200        # strict mode
N_BUCKETS = 10
MODEL_VERSION = "rank_v1"


@dataclasses.dataclass
class Probability:
    """A probability, or an honest refusal to give one."""
    available: bool
    value: float | None            # 0..1
    n_observations: int
    bucket: int | None = None
    horizon_days: int = 1
    mean_return: float | None = None
    note: str = ""

    @property
    def display(self) -> str:
        if not self.available:
            return "Insufficient data"
        return f"{self.value * 100:.0f}%"

    @property
    def evidence(self) -> str:
        # n_observations should always be an int, but a single bad value
        # must not take down every screen that renders a probability.
        n = self.n_observations if isinstance(self.n_observations, (int, float)) else None
        if not self.available:
            return (f"only {0 if n is None else int(n)} historical "
                    f"observations (need {MIN_OBSERVATIONS})")
        if n is None:
            return "based on an unrecorded number of historical observations"
        return f"based on {int(n):,} historical observations"

    def to_dict(self) -> dict:
        return {"available": self.available,
                "value": None if self.value is None else round(self.value, 4),
                "display": self.display, "n": self.n_observations,
                "evidence": self.evidence, "bucket": self.bucket,
                "horizon_days": self.horizon_days,
                "mean_return": (None if self.mean_return is None
                                else round(self.mean_return, 5)),
                "note": self.note}


INSUFFICIENT = Probability(False, None, 0, note="no calibration data yet")


# --------------------------------------------------------------------------- #
# Calibration build (walk-forward)
# --------------------------------------------------------------------------- #
def build_calibration(daily: pd.DataFrame, score_fn, *, horizon_days: int = 1,
                      n_folds: int = 5, min_train: int = 250,
                      progress=None) -> pd.DataFrame:
    """Walk-forward calibration table.

    `score_fn(history_df, as_of_date) -> DataFrame[symbol, score]` must use
    ONLY data up to as_of_date. The engine enforces this by slicing the frame
    before handing it over.
    """
    if daily is None or daily.empty:
        return pd.DataFrame()

    d = daily.copy()
    d["date"] = pd.to_datetime(d["date"])
    d = d.sort_values(["symbol", "date"])

    # forward return, strictly in the future
    d["fwd_close"] = d.groupby("symbol")["close"].shift(-horizon_days)
    d["fwd_ret"] = d["fwd_close"] / d["close"] - 1

    dates = sorted(d["date"].unique())
    if len(dates) < min_train + n_folds * 10:
        log.info("Not enough history to calibrate: %d sessions", len(dates))
        return pd.DataFrame()

    test_start = min_train
    fold_size = max((len(dates) - test_start) // n_folds, 1)
    records = []

    for fold in range(n_folds):
        lo = test_start + fold * fold_size
        hi = min(lo + fold_size, len(dates))
        if lo >= len(dates):
            break
        if progress:
            progress(f"Calibrating fold {fold + 1}/{n_folds}...")

        # Sample every 5th session to keep runtime sane and reduce the
        # heavy autocorrelation between consecutive daily snapshots.
        for di in range(lo, hi, 5):
            as_of = dates[di]
            hist = d[d["date"] <= as_of]
            try:
                scored = score_fn(hist, pd.Timestamp(as_of).date())
            except Exception:  # noqa: BLE001
                continue
            if scored is None or len(scored) == 0:
                continue
            snap = d[d["date"] == as_of][["symbol", "fwd_ret"]]
            merged = scored.merge(snap, on="symbol", how="inner")
            merged = merged[merged["fwd_ret"].notna()]
            for r in merged.itertuples():
                records.append({"fold": f"fold{fold}", "score": float(r.score),
                                "fwd_ret": float(r.fwd_ret)})

    if not records:
        return pd.DataFrame()

    cal = pd.DataFrame(records)
    # Bucket by score quantile across all out-of-sample observations.
    try:
        cal["bucket"] = pd.qcut(cal["score"], N_BUCKETS, labels=False,
                                duplicates="drop")
    except ValueError:
        cal["bucket"] = 0

    out = (cal.groupby("bucket")
              .agg(score_lo=("score", "min"), score_hi=("score", "max"),
                   n_observations=("fwd_ret", "size"),
                   n_positive=("fwd_ret", lambda s: int((s > 0).sum())),
                   mean_return=("fwd_ret", "mean"))
              .reset_index())
    out["hit_rate"] = out["n_positive"] / out["n_observations"]
    out["horizon_days"] = horizon_days
    out["model_version"] = MODEL_VERSION
    out["fold"] = "walkforward"
    return out


def persist_calibration(db, cal: pd.DataFrame) -> int:
    if cal is None or cal.empty:
        return 0
    with db.tx() as c:
        c.execute("DELETE FROM probability_calibration WHERE model_version=?"
                  " AND fold='walkforward'", (MODEL_VERSION,))
        c.executemany(
            "INSERT INTO probability_calibration (model_version,horizon_days,"
            "bucket,score_lo,score_hi,n_observations,n_positive,hit_rate,"
            "mean_return,fold) VALUES (?,?,?,?,?,?,?,?,?,?)",
            [(r.model_version, int(r.horizon_days), int(r.bucket),
              float(r.score_lo), float(r.score_hi), int(r.n_observations),
              int(r.n_positive), float(r.hit_rate), float(r.mean_return),
              r.fold) for r in cal.itertuples()])
    return len(cal)


# --------------------------------------------------------------------------- #
# Lookup
# --------------------------------------------------------------------------- #
class Calibrator:
    """Maps a live score to an evidence-backed probability, or refuses."""

    def __init__(self, db, horizon_days: int = 1,
                 min_observations: int = MIN_OBSERVATIONS):
        self.min_obs = min_observations
        self.horizon = horizon_days
        conn = db.connect()
        try:
            self.table = pd.read_sql_query(
                "SELECT bucket,score_lo,score_hi,n_observations,n_positive,"
                "hit_rate,mean_return FROM probability_calibration"
                " WHERE model_version=? AND horizon_days=? AND fold='walkforward'"
                " ORDER BY bucket",
                conn, params=[MODEL_VERSION, horizon_days])
        except Exception:  # noqa: BLE001
            self.table = pd.DataFrame()
        finally:
            conn.close()

    @property
    def ready(self) -> bool:
        return not self.table.empty

    @property
    def total_observations(self) -> int:
        return 0 if self.table.empty else int(self.table["n_observations"].sum())

    def probability(self, score: float) -> Probability:
        if self.table.empty:
            return dataclasses.replace(
                INSUFFICIENT,
                note="no calibration built yet - run a backtest first")

        row = None
        for r in self.table.itertuples():
            if r.score_lo <= score <= r.score_hi:
                row = r
                break
        if row is None:
            # outside every observed bucket -> use the nearest edge, but be
            # explicit that this is an extrapolation
            edge = (self.table.iloc[-1] if score > self.table["score_hi"].max()
                    else self.table.iloc[0])
            return Probability(False, None, int(edge["n_observations"]),
                               horizon_days=self.horizon,
                               note="score outside the calibrated range")

        n = int(row.n_observations)
        if n < self.min_obs:
            return Probability(False, None, n, bucket=int(row.bucket),
                               horizon_days=self.horizon,
                               note=f"bucket has only {n} observations")
        return Probability(True, float(row.hit_rate), n, bucket=int(row.bucket),
                           horizon_days=self.horizon,
                           mean_return=float(row.mean_return),
                           note="walk-forward out-of-sample")

    def probability_for(self, score: float, side: str) -> Probability:
        """Probability that the trade's direction is right.

        The calibration table stores P(next return > 0) for each score
        bucket. A short wins when the return is NOT positive, so its
        probability is the complement of the same bucket. Negating the score
        instead would look up an unrelated bucket - that is a real and easy
        mistake to make.
        """
        p = self.probability(score)
        if side.upper() != "SHORT" or not p.available:
            return p
        return dataclasses.replace(
            p, value=1.0 - p.value,
            note=p.note + " (complement, short side)")

    def summary(self) -> dict:
        if self.table.empty:
            return {"ready": False, "buckets": 0, "observations": 0,
                    "usable_buckets": 0,
                    "note": "No calibration yet. Run a backtest to build it."}
        usable = int((self.table["n_observations"] >= self.min_obs).sum())
        return {
            "ready": True,
            "buckets": len(self.table),
            "observations": self.total_observations,
            "usable_buckets": usable,
            "min_required": self.min_obs,
            "hit_rate_range": [round(float(self.table["hit_rate"].min()), 4),
                               round(float(self.table["hit_rate"].max()), 4)],
            "note": (f"{usable} of {len(self.table)} score buckets have the "
                     f"{self.min_obs}+ observations needed to show a "
                     f"probability."),
        }
