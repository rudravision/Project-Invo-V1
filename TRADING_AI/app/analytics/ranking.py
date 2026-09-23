"""
Sector heatmap + stock-ranking prototype (spec steps 10 & 11).

Deliberately simple and fully transparent: a cross-sectional multi-factor
score with published weights. No ML yet -- ML only makes sense once there is
real data and an honest baseline to beat.

Every output carries an `is_synthetic` flag that propagates from the database.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
from typing import Any

import numpy as np
import pandas as pd

from .indicators import add_indicator_set


# --------------------------------------------------------------------------- #
# Sector heatmap
# --------------------------------------------------------------------------- #
def sector_heatmap(index_df: pd.DataFrame,
                   periods: tuple[int, ...] = (1, 5, 21, 63)) -> pd.DataFrame:
    """Returns over several lookbacks for every index, plus a momentum rank.

    index_df columns: index_name, date, close
    """
    if index_df.empty:
        return pd.DataFrame()

    d = index_df.copy()
    d["date"] = pd.to_datetime(d["date"])
    d = d.sort_values(["index_name", "date"])

    rows = []
    for name, g in d.groupby("index_name"):
        g = g.sort_values("date")
        c = g["close"]
        rec: dict[str, Any] = {"index_name": name,
                               "last_close": float(c.iloc[-1]),
                               "as_of": g["date"].iloc[-1].date().isoformat()}
        for p in periods:
            rec[f"ret_{p}d"] = (float(c.iloc[-1] / c.iloc[-1 - p] - 1) * 100
                                if len(c) > p else np.nan)
        rec["vol_20d"] = float(c.pct_change().tail(20).std(ddof=0) *
                               np.sqrt(252) * 100) if len(c) > 21 else np.nan
        above = c.rolling(50, min_periods=20).mean()
        rec["above_sma50"] = (bool(c.iloc[-1] > above.iloc[-1])
                              if pd.notna(above.iloc[-1]) else None)
        rows.append(rec)

    hm = pd.DataFrame(rows)
    # Composite momentum: equally weighted rank across lookbacks.
    rank_cols = [f"ret_{p}d" for p in periods if f"ret_{p}d" in hm.columns]
    hm["momentum_rank"] = hm[rank_cols].rank(pct=True).mean(axis=1)
    return hm.sort_values("momentum_rank", ascending=False).reset_index(drop=True)


def render_heatmap_text(hm: pd.DataFrame, synthetic: bool = False) -> str:
    """ASCII heatmap so it works in a terminal, a log file or Telegram."""
    if hm.empty:
        return "No index data available to build a heatmap."

    def cell(v: float) -> str:
        if pd.isna(v):
            return "    n/a"
        return f"{v:+6.2f}%"

    def bar(v: float) -> str:
        if pd.isna(v):
            return " " * 11
        n = int(min(abs(v), 5.0) / 5.0 * 5)
        return ("[" + ("-" * n).rjust(5) + "|" + " " * 5 + "]") if v < 0 else \
               ("[" + " " * 5 + "|" + ("+" * n).ljust(5) + "]")

    lines = []
    if synthetic:
        lines += ["!" * 74,
                  "! SYNTHETIC DEMO DATA - NOT REAL MARKET DATA - DO NOT TRADE !",
                  "!" * 74]
    lines.append(f"SECTOR / INDEX HEATMAP           as of {hm['as_of'].iloc[0]}")
    lines.append("-" * 88)
    lines.append(f"{'INDEX':<26}{'1D':>8}{'5D':>8}{'21D':>8}{'63D':>8}"
                 f"{'VOL':>8}   {'21D MOMENTUM':<13}")
    lines.append("-" * 88)
    for r in hm.itertuples():
        lines.append(
            f"{r.index_name:<26}"
            f"{cell(getattr(r, 'ret_1d', np.nan)):>8}"
            f"{cell(getattr(r, 'ret_5d', np.nan)):>8}"
            f"{cell(getattr(r, 'ret_21d', np.nan)):>8}"
            f"{cell(getattr(r, 'ret_63d', np.nan)):>8}"
            f"{cell(getattr(r, 'vol_20d', np.nan)):>8}   "
            f"{bar(getattr(r, 'ret_21d', np.nan))}"
        )
    lines.append("-" * 88)
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Stock ranking
# --------------------------------------------------------------------------- #
@dataclasses.dataclass
class RankConfig:
    """Factor weights. Documented and tunable -- no hidden magic."""
    w_momentum_21: float = 0.20
    w_momentum_63: float = 0.25
    w_momentum_126: float = 0.15
    w_trend: float = 0.15          # above 50/200 DMA
    w_volume: float = 0.10         # volume expansion z-score
    w_lowvol: float = 0.10         # prefer lower realised vol
    w_pullback: float = 0.05       # small pullback from highs preferred
    min_price: float = 20.0
    min_adv: float = 100_000.0     # min 20d average daily volume
    min_history: int = 130         # bars needed before a stock is rankable
    top_n: int = 20


def _zc(s: pd.Series) -> pd.Series:
    """Cross-sectional z-score, outlier-clipped."""
    m, sd = s.mean(), s.std(ddof=0)
    if not np.isfinite(sd) or sd == 0:
        return pd.Series(0.0, index=s.index)
    return ((s - m) / sd).clip(-3, 3)


def rank_stocks(daily: pd.DataFrame, cfg: RankConfig | None = None,
                as_of: dt.date | None = None,
                sectors: dict[str, str] | None = None) -> pd.DataFrame:
    """Cross-sectional ranking of every liquid symbol on one date.

    daily: canonical OHLCV for all symbols (long format).
    Returns one row per ranked symbol, best first.
    """
    cfg = cfg or RankConfig()
    if daily.empty:
        return pd.DataFrame()

    d = daily.copy()
    d["date"] = pd.to_datetime(d["date"])
    if as_of is not None:
        d = d[d["date"] <= pd.Timestamp(as_of)]

    feats = []
    for sym, g in d.groupby("symbol"):
        if len(g) < cfg.min_history:
            continue
        ind = add_indicator_set(g)
        last = ind.iloc[-1]
        if not np.isfinite(last["close"]) or last["close"] < cfg.min_price:
            continue
        if not np.isfinite(last.get("adv20", np.nan)) or last["adv20"] < cfg.min_adv:
            continue
        feats.append({
            "symbol": sym,
            "date": last["date"],
            "close": float(last["close"]),
            "ret_21": last["ret_21"], "ret_63": last["ret_63"],
            "ret_126": last["ret_126"],
            "above_sma50": last["above_sma50"],
            "above_sma200": last["above_sma200"],
            "vol_z": last["vol_z"], "vol20": last["vol20"],
            "rsi14": last["rsi14"], "atr_pct": last["atr_pct"],
            "dist_252h": last["dist_252h"],
            "adv20": last["adv20"],
            "is_synthetic": int(g["is_synthetic"].max())
                            if "is_synthetic" in g else 0,
        })

    if not feats:
        return pd.DataFrame()

    f = pd.DataFrame(feats).set_index("symbol")
    f = f.replace([np.inf, -np.inf], np.nan)

    trend = (f["above_sma50"].fillna(0) + f["above_sma200"].fillna(0)) / 2.0
    # Mild pullback preferred: penalise both extended and deeply broken names.
    pull = -(f["dist_252h"].fillna(-0.5) + 0.07).abs()

    f["score"] = (
        cfg.w_momentum_21 * _zc(f["ret_21"].fillna(0))
        + cfg.w_momentum_63 * _zc(f["ret_63"].fillna(0))
        + cfg.w_momentum_126 * _zc(f["ret_126"].fillna(0))
        + cfg.w_trend * _zc(trend)
        + cfg.w_volume * _zc(f["vol_z"].fillna(0))
        + cfg.w_lowvol * _zc(-f["vol20"].fillna(f["vol20"].median()))
        + cfg.w_pullback * _zc(pull)
    )

    f = f.sort_values("score", ascending=False)
    f["rank"] = range(1, len(f) + 1)
    if sectors:
        f["sector"] = [sectors.get(s, "Unknown") for s in f.index]
    return f.reset_index()


def render_ranking_text(r: pd.DataFrame, top_n: int = 15,
                        synthetic: bool = False) -> str:
    if r.empty:
        return "No stocks passed the liquidity/history filters."
    lines = []
    if synthetic:
        lines += ["!" * 74,
                  "! SYNTHETIC DEMO DATA - NOT REAL MARKET DATA - DO NOT TRADE !",
                  "!" * 74]
    as_of = pd.to_datetime(r["date"].iloc[0]).date()
    lines.append(f"STOCK RANKING (prototype, rule-based)   as of {as_of}")
    lines.append("-" * 100)
    lines.append(f"{'#':>3} {'SYMBOL':<13}{'SCORE':>7}{'CLOSE':>10}"
                 f"{'21D':>8}{'63D':>8}{'RSI':>6}{'VOL%':>7}{'>50D':>6}"
                 f"{'>200D':>7}  {'SECTOR':<22}")
    lines.append("-" * 100)
    for row in r.head(top_n).itertuples():
        lines.append(
            f"{row.rank:>3} {row.symbol:<13}{row.score:>7.2f}"
            f"{row.close:>10.2f}"
            f"{(row.ret_21 * 100 if pd.notna(row.ret_21) else 0):>7.1f}%"
            f"{(row.ret_63 * 100 if pd.notna(row.ret_63) else 0):>7.1f}%"
            f"{(row.rsi14 if pd.notna(row.rsi14) else 0):>6.0f}"
            f"{(row.vol20 * 100 if pd.notna(row.vol20) else 0):>7.1f}"
            f"{'Y' if row.above_sma50 else 'n':>6}"
            f"{'Y' if row.above_sma200 else 'n':>7}  "
            f"{getattr(row, 'sector', 'Unknown'):<22}"
        )
    lines.append("-" * 100)
    lines.append("Score = weighted cross-sectional z-scores of momentum, "
                 "trend, volume, low-vol and pullback factors.")
    return "\n".join(lines)


def components_json(row: pd.Series) -> str:
    keys = ["ret_21", "ret_63", "ret_126", "above_sma50", "above_sma200",
            "vol_z", "vol20", "rsi14", "dist_252h"]
    return json.dumps({k: (None if pd.isna(row.get(k)) else round(float(row[k]), 6))
                       for k in keys if k in row})
