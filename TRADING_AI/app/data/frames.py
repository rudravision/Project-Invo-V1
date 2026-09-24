"""One place that decides which prices analysis is allowed to see.

Three rules, applied everywhere - dashboard, recommendations, charts and
backtest - so the screens cannot disagree with each other:

1. Practice (synthetic) rows are never used for real output.
2. Where a corporate-action adjusted series exists, it wins. Indicators
   computed across an unadjusted split are wrong.
3. Stocks with an unexplained large overnight move are dropped. They are
   either carrying an unadjusted corporate action or bad vendor data; in a
   backtest they show up as a fake 60% crash and wreck the equity curve.

The backtest used to skip rules 2 and 3, which is why its results were
distorted by a handful of old stock splits.
"""
from __future__ import annotations

import pandas as pd

from .corporate_actions import quarantined_symbols, symbols_with_extreme_jumps

COLUMNS = ["symbol", "date", "open", "high", "low", "close", "volume",
           "is_synthetic"]


def load_daily(db, *, adjusted: bool = True, exclude_quarantined: bool = True,
               real_only: bool = False) -> tuple[pd.DataFrame, dict[str, str]]:
    """Return (prices, excluded) ready for analysis.

    `excluded` maps symbol -> plain-language reason, so callers can tell the
    user which stocks were left out instead of silently dropping them.
    """
    conn = db.connect()
    try:
        where = " WHERE is_synthetic=0" if real_only else ""
        daily = pd.read_sql_query(
            "SELECT symbol,date,open,high,low,close,volume,is_synthetic"
            f" FROM daily_ohlc{where} ORDER BY symbol,date", conn)

        if adjusted and not daily.empty:
            try:
                adj = pd.read_sql_query(
                    "SELECT symbol,date,open,high,low,close,volume"
                    " FROM daily_ohlc_adjusted ORDER BY symbol,date", conn)
            except Exception:  # noqa: BLE001  (table may predate migration)
                adj = pd.DataFrame()
            if not adj.empty:
                # Overlay, never replace: swapping the whole table would drop
                # every stock that never needed an adjustment.
                adj["is_synthetic"] = 0
                keep = daily[~daily["symbol"].isin(set(adj["symbol"]))]
                daily = (pd.concat([keep, adj[COLUMNS]], ignore_index=True)
                         .sort_values(["symbol", "date"])
                         .reset_index(drop=True))
    finally:
        conn.close()

    excluded: dict[str, str] = {}
    if exclude_quarantined and not daily.empty:
        real = daily[daily["is_synthetic"] == 0]
        excluded.update(symbols_with_extreme_jumps(real))
        try:
            excluded.update(quarantined_symbols(db))
        except Exception:  # noqa: BLE001
            pass
        if excluded:
            daily = daily[~daily["symbol"].isin(excluded)]

    return daily, excluded


def exclusion_note(excluded: dict[str, str]) -> str:
    if not excluded:
        return "No stocks were excluded."
    return (f"{len(excluded)} stock(s) excluded because of an unexplained "
            f"large price move: {', '.join(sorted(excluded))}.")
