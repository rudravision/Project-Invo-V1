"""Local technical indicators. Pure pandas/numpy -- no cloud, no API calls."""

from __future__ import annotations

import numpy as np
import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    """Wilder's RSI."""
    delta = s.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    ag = gain.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    al = loss.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = ag / al.replace(0.0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.fillna(100.0).where(al.notna())


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """Average True Range from high/low/close."""
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def macd(s: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    line = ema(s, fast) - ema(s, slow)
    sig = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return line, sig, line - sig


def roc(s: pd.Series, n: int) -> pd.Series:
    """Rate of change over n periods, as a fraction."""
    return s.pct_change(n)


def rolling_zscore(s: pd.Series, n: int) -> pd.Series:
    m = s.rolling(n, min_periods=max(5, n // 3)).mean()
    sd = s.rolling(n, min_periods=max(5, n // 3)).std(ddof=0)
    return (s - m) / sd.replace(0.0, np.nan)


def realised_vol(s: pd.Series, n: int = 20) -> pd.Series:
    """Annualised realised volatility from daily closes."""
    return s.pct_change().rolling(n, min_periods=max(5, n // 2)) \
            .std(ddof=0) * np.sqrt(252)


def max_drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    peak = equity.cummax()
    return float(((equity / peak) - 1.0).min())


def distance_from_high(s: pd.Series, n: int = 252) -> pd.Series:
    """How far below the rolling n-day high, as a negative fraction."""
    hi = s.rolling(n, min_periods=max(20, n // 5)).max()
    return (s / hi) - 1.0


def add_indicator_set(df: pd.DataFrame) -> pd.DataFrame:
    """Attach the standard indicator set to one symbol's OHLCV frame.

    Input must be a single symbol, sorted by date ascending.
    """
    d = df.sort_values("date").copy()
    c = d["close"]
    d["sma20"] = sma(c, 20)
    d["sma50"] = sma(c, 50)
    d["sma200"] = sma(c, 200)
    d["ema20"] = ema(c, 20)
    d["rsi14"] = rsi(c, 14)
    d["atr14"] = atr(d, 14)
    d["atr_pct"] = d["atr14"] / c
    d["macd"], d["macd_signal"], d["macd_hist"] = macd(c)
    d["ret_5"] = roc(c, 5)
    d["ret_21"] = roc(c, 21)
    d["ret_63"] = roc(c, 63)
    d["ret_126"] = roc(c, 126)
    d["vol20"] = realised_vol(c, 20)
    d["vol_z"] = rolling_zscore(d["volume"], 20)
    d["adv20"] = d["volume"].rolling(20, min_periods=5).mean()
    d["turnover20"] = (d["close"] * d["volume"]).rolling(20, min_periods=5).mean()
    d["dist_252h"] = distance_from_high(c, 252)
    d["above_sma50"] = (c > d["sma50"]).astype(float)
    d["above_sma200"] = (c > d["sma200"]).astype(float)
    return d
