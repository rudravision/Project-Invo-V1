"""
Walk-forward backtester for the ranking prototype (spec step 12).

Correctness rules enforced here:
  * NO LOOK-AHEAD. Ranks are computed using data up to and including day T,
    positions are entered at day T+1's OPEN, and returns accrue from there.
  * Costs are explicit: brokerage, STT, exchange fees, GST, stamp duty and
    slippage are all charged. A "free" backtest is a fantasy.
  * Results are reported honestly, including the losing cases.
  * If the input is synthetic, every output is stamped SYNTHETIC.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..analytics.indicators import max_drawdown
from ..analytics.ranking import RankConfig, rank_stocks


@dataclasses.dataclass
class CostModel:
    """Indian equity delivery/intraday cost approximation, in fractions.

    Defaults are deliberately conservative. Verify against your own broker's
    contract notes before believing any net return.
    """
    brokerage_pct: float = 0.0003      # 0.03% or flat-fee equivalent
    brokerage_cap: float = 20.0        # INR per order
    stt_sell_pct: float = 0.001        # 0.1% on sell (delivery)
    exchange_pct: float = 0.0000345
    gst_pct: float = 0.18              # on brokerage + exchange
    stamp_buy_pct: float = 0.00015
    slippage_pct: float = 0.0010       # 10 bps each way -- be pessimistic

    def buy_cost(self, value: float) -> float:
        b = min(value * self.brokerage_pct, self.brokerage_cap)
        ex = value * self.exchange_pct
        gst = (b + ex) * self.gst_pct
        stamp = value * self.stamp_buy_pct
        slip = value * self.slippage_pct
        return b + ex + gst + stamp + slip

    def sell_cost(self, value: float) -> float:
        b = min(value * self.brokerage_pct, self.brokerage_cap)
        ex = value * self.exchange_pct
        gst = (b + ex) * self.gst_pct
        stt = value * self.stt_sell_pct
        slip = value * self.slippage_pct
        return b + ex + gst + stt + slip


@dataclasses.dataclass
class BacktestConfig:
    start: dt.date
    end: dt.date
    rebalance_days: int = 5
    top_n: int = 5
    initial_capital: float = 1_000_000.0
    max_weight: float = 0.25
    warmup_bars: int = 130


@dataclasses.dataclass
class BacktestResult:
    equity: pd.Series
    trades: pd.DataFrame
    stats: dict
    is_synthetic: bool

    def report(self) -> str:
        s = self.stats
        lines = []
        if self.is_synthetic:
            lines += ["!" * 78,
                      "! RESULTS FROM SYNTHETIC DATA - THESE NUMBERS ARE MEANINGLESS !",
                      "! They prove the engine runs. They say NOTHING about the market !",
                      "!" * 78, ""]
        lines.append("BACKTEST RESULT (walk-forward, costs included)")
        lines.append("-" * 62)
        for k in ["period", "trading_days", "rebalances", "trades",
                  "initial_capital", "final_equity", "total_return_pct",
                  "cagr_pct", "ann_vol_pct", "sharpe", "sortino",
                  "max_drawdown_pct", "win_rate_pct", "avg_win_pct",
                  "avg_loss_pct", "profit_factor", "total_costs",
                  "cost_drag_pct", "benchmark_return_pct", "excess_vs_bench_pct"]:
            if k in s:
                v = s[k]
                v = f"{v:,.2f}" if isinstance(v, float) else v
                lines.append(f"  {k.replace('_', ' ').title():<26} {v}")
        lines.append("-" * 62)
        lines.append("Sharpe assumes 0% risk-free rate. Past performance, even "
                     "on real data, does not predict future returns.")
        return "\n".join(lines)


def run_backtest(daily: pd.DataFrame, cfg: BacktestConfig,
                 rank_cfg: RankConfig | None = None,
                 costs: CostModel | None = None,
                 benchmark: pd.DataFrame | None = None) -> BacktestResult:
    """Run the walk-forward backtest.

    daily: long-format OHLCV for the universe.
    benchmark: optional index frame (date, close) for comparison.
    """
    rank_cfg = rank_cfg or RankConfig()
    costs = costs or CostModel()

    d = daily.copy()
    d["date"] = pd.to_datetime(d["date"])
    is_synth = bool(d["is_synthetic"].max()) if "is_synthetic" in d else False

    # Wide price panels for fast lookups.
    close = d.pivot_table(index="date", columns="symbol", values="close")
    open_ = d.pivot_table(index="date", columns="symbol", values="open")
    close = close.sort_index()
    open_ = open_.sort_index().reindex(close.index)

    all_dates = close.index
    mask = (all_dates >= pd.Timestamp(cfg.start)) & (all_dates <= pd.Timestamp(cfg.end))
    test_dates = all_dates[mask]
    if len(test_dates) < 20:
        raise ValueError(
            f"Only {len(test_dates)} bars in the backtest window. "
            f"Need at least 20. Widen the date range or load more history.")

    cash = cfg.initial_capital
    holdings: dict[str, float] = {}          # symbol -> shares
    equity_curve, trade_log = [], []
    total_costs = 0.0
    rebalances = 0

    for i, today in enumerate(test_dates):
        # ---- mark to market at today's close ----
        pos_val = sum(sh * _px(close, today, sym)
                      for sym, sh in holdings.items())
        equity = cash + pos_val
        equity_curve.append((today, equity))

        # ---- decide on rebalance days, execute NEXT open (no look-ahead) ----
        if i % cfg.rebalance_days != 0:
            continue
        if i + 1 >= len(test_dates):
            continue
        exec_date = test_dates[i + 1]

        hist = d[d["date"] <= today]
        ranked = rank_stocks(hist, rank_cfg, as_of=today.date())
        if ranked.empty:
            continue

        targets = list(ranked.head(cfg.top_n)["symbol"])
        rebalances += 1

        # ---- sell what is no longer wanted ----
        for sym in list(holdings):
            if sym in targets:
                continue
            px = _px(open_, exec_date, sym)
            if not np.isfinite(px):
                continue
            val = holdings[sym] * px
            c = costs.sell_cost(val)
            cash += val - c
            total_costs += c
            trade_log.append({"date": exec_date, "symbol": sym, "side": "SELL",
                              "shares": holdings[sym], "price": px,
                              "value": val, "cost": c})
            del holdings[sym]

        # ---- size and buy targets equally, capped ----
        equity_now = cash + sum(sh * _px(open_, exec_date, s)
                                for s, sh in holdings.items())
        if not np.isfinite(equity_now) or equity_now <= 0:
            continue
        target_w = min(1.0 / max(len(targets), 1), cfg.max_weight)

        for sym in targets:
            px = _px(open_, exec_date, sym)
            if not np.isfinite(px) or px <= 0:
                continue
            want_val = equity_now * target_w
            have_val = holdings.get(sym, 0.0) * px
            delta = want_val - have_val
            if delta <= px:            # too small to bother
                continue
            shares = int(delta // px)
            if shares <= 0:
                continue
            val = shares * px
            c = costs.buy_cost(val)
            if val + c > cash:
                shares = int(max(cash - c, 0) // px)
                if shares <= 0:
                    continue
                val = shares * px
                c = costs.buy_cost(val)
            cash -= val + c
            total_costs += c
            holdings[sym] = holdings.get(sym, 0.0) + shares
            trade_log.append({"date": exec_date, "symbol": sym, "side": "BUY",
                              "shares": shares, "price": px, "value": val,
                              "cost": c})

    eq = pd.Series(dict(equity_curve)).sort_index()
    trades = pd.DataFrame(trade_log)
    stats = _stats(eq, trades, cfg, total_costs, rebalances, benchmark)
    return BacktestResult(eq, trades, stats, is_synth)


def _px(panel: pd.DataFrame, date, sym: str) -> float:
    try:
        v = panel.at[date, sym]
        return float(v) if pd.notna(v) else float("nan")
    except (KeyError, ValueError):
        return float("nan")


def _stats(eq: pd.Series, trades: pd.DataFrame, cfg: BacktestConfig,
           total_costs: float, rebalances: int,
           benchmark: pd.DataFrame | None) -> dict:
    if eq.empty:
        return {"error": "empty equity curve"}

    rets = eq.pct_change().dropna()
    years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    total_ret = float(eq.iloc[-1] / eq.iloc[0] - 1)
    cagr = float((eq.iloc[-1] / eq.iloc[0]) ** (1 / years) - 1) if years > 0 else 0.0
    vol = float(rets.std(ddof=0) * np.sqrt(252)) if len(rets) > 1 else 0.0
    sharpe = float(rets.mean() / rets.std(ddof=0) * np.sqrt(252)) \
        if len(rets) > 1 and rets.std(ddof=0) > 0 else 0.0
    downside = rets[rets < 0]
    sortino = float(rets.mean() / downside.std(ddof=0) * np.sqrt(252)) \
        if len(downside) > 1 and downside.std(ddof=0) > 0 else 0.0

    # Round-trip P&L per symbol (FIFO-lite: pair each sell against avg cost).
    wins, losses = [], []
    if not trades.empty:
        book: dict[str, list[tuple[float, float]]] = {}
        for t in trades.itertuples():
            if t.side == "BUY":
                book.setdefault(t.symbol, []).append((t.shares, t.price))
            else:
                lots = book.get(t.symbol, [])
                if not lots:
                    continue
                tot_sh = sum(s for s, _ in lots)
                avg = sum(s * p for s, p in lots) / tot_sh if tot_sh else t.price
                pnl_pct = (t.price / avg - 1) if avg else 0.0
                (wins if pnl_pct > 0 else losses).append(pnl_pct)
                book[t.symbol] = []

    n_rt = len(wins) + len(losses)
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))

    out = {
        "period": f"{eq.index[0].date()} to {eq.index[-1].date()}",
        "trading_days": int(len(eq)),
        "rebalances": rebalances,
        "trades": int(len(trades)),
        "initial_capital": float(cfg.initial_capital),
        "final_equity": float(eq.iloc[-1]),
        "total_return_pct": total_ret * 100,
        "cagr_pct": cagr * 100,
        "ann_vol_pct": vol * 100,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown_pct": max_drawdown(eq) * 100,
        "round_trips": n_rt,
        "win_rate_pct": (len(wins) / n_rt * 100) if n_rt else 0.0,
        "avg_win_pct": (float(np.mean(wins)) * 100) if wins else 0.0,
        "avg_loss_pct": (float(np.mean(losses)) * 100) if losses else 0.0,
        "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else float("inf"),
        "worst_day_pct": float(eq.pct_change().min() * 100)
                         if len(eq) > 1 else 0.0,
        "worst_day_date": (str(eq.pct_change().idxmin().date())
                           if len(eq) > 1 else None),
        "total_costs": float(total_costs),
        "cost_drag_pct": float(total_costs / cfg.initial_capital * 100),
    }

    if benchmark is not None and not benchmark.empty:
        b = benchmark.copy()
        b["date"] = pd.to_datetime(b["date"])
        b = b.set_index("date")["close"].sort_index()
        b = b[(b.index >= eq.index[0]) & (b.index <= eq.index[-1])]
        if len(b) > 1:
            bret = float(b.iloc[-1] / b.iloc[0] - 1)
            out["benchmark_return_pct"] = bret * 100
            out["excess_vs_bench_pct"] = (total_ret - bret) * 100
    return out


def save_result(res: BacktestResult, outdir: Path, name: str) -> dict:
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    base = outdir / f"{name}_{stamp}"
    res.equity.to_csv(f"{base}_equity.csv", header=["equity"])
    if not res.trades.empty:
        res.trades.to_csv(f"{base}_trades.csv", index=False)
    payload = {"stats": res.stats, "is_synthetic": res.is_synthetic,
               "generated_at": dt.datetime.now().isoformat(timespec="seconds")}
    Path(f"{base}_stats.json").write_text(json.dumps(payload, indent=2, default=str))
    Path(f"{base}_report.txt").write_text(res.report(), encoding="utf-8")
    return {"base": str(base)}
