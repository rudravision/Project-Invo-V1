"""
The work behind the buttons (spec item 13).

UPDATE & ANALYZE MARKET runs one chain end to end:
  backup -> migrate -> calendar -> download -> indices/sectors -> delivery
  -> validate -> corporate actions -> indicators -> rank -> heatmap
  -> probabilities -> levels -> report

Every step publishes progress. If validation fails, ranking still runs for
inspection but recommendations stay disabled - that decision lives in the
API layer, which re-validates before returning any trade idea.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.analytics.confirmations import evaluate_checks
from app.analytics.indicators import add_indicator_set
from app.analytics.indices import pick_row, sector_label
from app.data.frames import exclusion_note, load_daily
from app.analytics.probability import (Calibrator, build_calibration,
                                       persist_calibration)
from app.analytics.ranking import RankConfig, rank_stocks, sector_heatmap
from app.analytics.recommend import (RiskSettings, generate_candidates,
                                     portfolio_summary)
from app.backtest.engine import BacktestConfig, CostModel, run_backtest
from app.data.calendar import MarketCalendar, SymbolLifecycle
from app.data.corporate_actions import run_corporate_action_pass
from app.data.quality2 import explain_for_humans, validate_daily_v2
from app.data.repair import DownloadQueue, analyse_gaps, plan_repair
from app.db.migrations import migrate
from app.gui.jobs import progress_adapter, should_stop

log = logging.getLogger(__name__)

STEPS = [
    "Backing up the database",
    "Applying database updates",
    "Checking the trading calendar",
    "Downloading missing price data",
    "Updating indices and sectors",
    "Checking data quality",
    "Checking corporate actions",
    "Calculating indicators and ranking",
    "Building the sector heatmap",
    "Applying calibrated probabilities",
    "Saving the report",
]


def _load(db, *, clean: bool = True):
    """Prices for analysis, plus the index/sector context.

    `clean` applies the shared rules in app/data/frames.py: adjusted series
    preferred, quarantined stocks dropped. The excluded stocks are returned
    so the caller can report them.
    """
    daily, excluded = load_daily(db, adjusted=clean,
                                 exclude_quarantined=clean, real_only=True)
    conn = db.connect()
    try:
        idx = pd.read_sql_query(
            "SELECT index_name,date,close,is_synthetic FROM index_ohlc"
            " WHERE is_synthetic=0 ORDER BY index_name,date", conn)
        sectors = dict(conn.execute(
            "SELECT symbol, COALESCE(sector,industry,'Unknown') FROM symbols"
        ).fetchall())
        deliv = dict(conn.execute(
            "SELECT symbol, delivery_pct FROM delivery WHERE date="
            "(SELECT MAX(date) FROM delivery)").fetchall())
    finally:
        conn.close()
    _load.last_excluded = excluded
    return daily, idx, sectors, deliv


# --------------------------------------------------------------------------- #
def full_update_job(job, db, settings, *, period="5y", universe="nifty200",
                    risk: RiskSettings | None = None) -> dict:
    cb = progress_adapter(job)
    stop = should_stop(job)
    risk = risk or RiskSettings()
    job.total = len(STEPS)
    out: dict = {"period": period, "started": job.started_at}
    step = 0

    def advance(text):
        nonlocal step
        step += 1
        cb(text, step, len(STEPS))

    # 1 backup
    advance(STEPS[0])
    try:
        bpath = db.backup(settings.backups_dir, keep=10)
        out["backup"] = bpath.name
    except Exception as e:  # noqa: BLE001
        out["backup_error"] = str(e)

    # 2 migrate
    advance(STEPS[1])
    out["migrations"] = migrate(db, settings.backups_dir)

    # 3 calendar
    advance(STEPS[2])
    cal = MarketCalendar(db)
    today = dt.date.today()
    cal_start = today - dt.timedelta(days=366 * 6)
    cal.seed_weekends(cal_start, today)
    cal.infer_sessions_from_data()
    out["calendar"] = cal.summary(cal_start, today)
    if stop():
        return out

    # 4+5 download (sync handles prices, indices, membership, delivery)
    advance(STEPS[3])

    def sync_progress(msg, cur=None, tot=None):
        job.message = msg
        if cur is not None and tot:
            # keep the outer step bar meaningful while the inner loop runs
            job.current = step
            job.total = len(STEPS)
            job.steps.append(f"{msg} ({cur}/{tot})")
        elif not job.steps or job.steps[-1] != msg:
            job.steps.append(msg)

    try:
        from scripts.sync_data import run_sync
        out["sync"] = run_sync(db, settings, period=period, universe=universe,
                               progress=sync_progress, should_stop=stop)
    except Exception as e:  # noqa: BLE001
        log.exception("sync failed")
        out["sync_error"] = str(e)
        job.steps.append(f"Download step failed: {e}")

    advance(STEPS[4])
    SymbolLifecycle(db).rebuild()
    if stop():
        return out

    # 6 validate
    advance(STEPS[5])
    daily, idx, sectors, deliv = _load(db)
    out["rows"] = int(len(daily))
    out["symbols"] = int(daily["symbol"].nunique()) if len(daily) else 0
    if daily.empty:
        job.message = ("No real market data could be downloaded. "
                       "Check the Data Sources page.")
        out["blocked"] = True
        return out

    rep = validate_daily_v2(daily, db, run_gap_analysis=True)
    out["quality_ok"] = rep.ok
    out["quality"] = explain_for_humans(rep)

    # 7 corporate actions
    advance(STEPS[6])
    try:
        out["corporate_actions"] = run_corporate_action_pass(db, progress=cb)
    except Exception as e:  # noqa: BLE001
        out["corporate_actions_error"] = str(e)

    # 8 rank
    advance(STEPS[7])
    ranked = rank_stocks(daily, RankConfig(), sectors=sectors)
    out["ranked"] = int(len(ranked))
    if ranked.empty:
        out["rank_note"] = (
            "No stock has enough continuous history to be ranked yet "
            "(130 sessions needed). Download more history.")

    # 9 heatmap
    advance(STEPS[8])
    hm = sector_heatmap(idx) if not idx.empty else pd.DataFrame()
    out["indices"] = int(len(hm))

    # 10 probabilities + levels
    advance(STEPS[9])
    cal_ = Calibrator(db)
    out["calibration"] = cal_.summary()
    recs = {"long": [], "short": []}
    if not ranked.empty and rep.ok:
        sector_ranks = {}
        market_trend = "Unknown"
        if not hm.empty:
            for r in hm.itertuples():
                lbl = sector_label(r.index_name)
                if lbl:
                    sector_ranks[lbl] = float(r.momentum_rank)
            n50 = pick_row(hm, which="nifty50")
            if n50 is not None:
                v = n50.get("ret_21d")
                market_trend = ("Bullish" if (v or 0) > 1 else
                                "Bearish" if (v or 0) < -1 else "Neutral")
        cands = generate_candidates(daily, ranked, sectors=sectors,
                                    sector_ranks=sector_ranks,
                                    market_trend=market_trend, rs=risk,
                                    calibrator=cal_, delivery=deliv, top_n=5)
        recs = {k: [c.to_dict() for c in v] for k, v in cands.items()}
        out["portfolio"] = portfolio_summary(cands, risk)
    elif not rep.ok:
        out["recommendations_disabled"] = (
            "Recommendations are switched off because the data quality "
            "check failed. Use REPAIR DATA first.")

    out["recommendations"] = recs

    # 11 report
    advance(STEPS[10])
    rdir = settings.reports_dir
    rdir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = rdir / f"market_update_{stamp}.json"
    path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    out["report_file"] = path.name
    job.message = "Market update complete."
    return out


# --------------------------------------------------------------------------- #
def repair_job(job, db, settings) -> dict:
    cb = progress_adapter(job)
    stop = should_stop(job)
    job.total = 6
    cb("Backing up before repair...", 0, 6)
    db.backup(settings.backups_dir, keep=10)

    cb("Applying database updates...", 1, 6)
    migrate(db, settings.backups_dir)

    cb("Rebuilding the trading calendar...", 2, 6)
    cal = MarketCalendar(db)
    today = dt.date.today()
    cal_start = today - dt.timedelta(days=366 * 6)
    cal.seed_weekends(cal_start, today)
    cal.infer_sessions_from_data()
    SymbolLifecycle(db).rebuild()

    cb("Finding the gaps...", 3, 6)
    gap = analyse_gaps(db)
    before = gap.summary()

    cb("Downloading what is genuinely missing...", 4, 6)
    plan = plan_repair(db, gap, cal_start, today)
    q = DownloadQueue(db)
    for dataset, keys, prio in (("cm_bhavcopy", plan.refetch_sessions, 10),
                                ("cm_bhavcopy", plan.verify_dates, 50),
                                ("index_close", plan.need_index, 20)):
        q.enqueue(dataset, keys, priority=prio)
        q.requeue(dataset, keys)      # override stale DONE markers
    q.reset_failed("cm_bhavcopy")
    q.reset_failed("index_close")
    out_plan = {"refetch_sessions": len(plan.refetch_sessions),
                "verify_dates": len(plan.verify_dates),
                "need_index": len(plan.need_index)}
    try:
        from scripts.sync_data import run_sync
        run_sync(db, settings, period="max",
                 progress=lambda m, c=None, t=None: cb(m, c, t),
                 should_stop=stop)
    except Exception as e:  # noqa: BLE001
        job.steps.append(f"Download step failed: {e}")

    cb("Re-checking...", 5, 6)
    after = analyse_gaps(db).summary()
    daily, *_ = _load(db)
    rep = validate_daily_v2(daily, db, run_gap_analysis=True) \
        if not daily.empty else None
    cb("Repair finished.", 6, 6)
    return {"before": before, "after": after, "plan": out_plan,
            "quality_ok": bool(rep and rep.ok),
            "quality": explain_for_humans(rep) if rep else []}


# --------------------------------------------------------------------------- #
def run_backtest_job(job, db, settings, body: dict) -> dict:
    cb = progress_adapter(job)
    job.total = 4
    cb("Loading price history...", 0, 4)
    daily, idx, sectors, _ = _load(db)
    excluded = getattr(_load, "last_excluded", {})
    if daily.empty:
        raise ValueError("There is no real market data to backtest.")

    daily["date"] = pd.to_datetime(daily["date"])
    dates = sorted(daily["date"].unique())
    warmup = int(body.get("warmup", 130))
    if len(dates) < warmup + 40:
        raise ValueError(
            f"Only {len(dates)} sessions available. A backtest needs at least "
            f"{warmup + 40}. Download more history first.")

    start = pd.Timestamp(dates[warmup]).date()
    end = pd.Timestamp(dates[-1]).date()
    cfg = BacktestConfig(start=start, end=end,
                         rebalance_days=int(body.get("rebalance_days", 5)),
                         top_n=int(body.get("top_n", 5)),
                         initial_capital=float(body.get("capital", 1_000_000)),
                         warmup_bars=warmup)

    bench = None
    if not idx.empty:
        from app.analytics.indices import is_nifty50
        b = idx[idx["index_name"].map(is_nifty50)][["date", "close"]]
        if len(b) > 20:
            bench = b

    cb("Running the walk-forward backtest (this takes a while)...", 1, 4)
    res = run_backtest(daily, cfg, RankConfig(), CostModel(), benchmark=bench)

    cb("Saving results...", 2, 4)
    bdir = settings.root / "backtests"
    bdir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    (bdir / f"{stamp}_stats.json").write_text(
        json.dumps(res.stats, indent=2, default=str), encoding="utf-8")
    res.equity.to_csv(bdir / f"{stamp}_equity.csv", header=["equity"])
    if not res.trades.empty:
        res.trades.to_csv(bdir / f"{stamp}_trades.csv", index=False)

    cb("Done.", 4, 4)
    stats = dict(res.stats)
    stats["excluded_symbols"] = sorted(excluded)
    stats["excluded_note"] = exclusion_note(excluded)
    return {"stats": stats, "file": f"{stamp}_stats.json",
            "excluded": stats["excluded_note"],
            "is_synthetic": res.is_synthetic, "report": res.report()}


# --------------------------------------------------------------------------- #
def build_calibration_job(job, db, settings) -> dict:
    """Walk-forward calibration of score -> observed hit rate."""
    cb = progress_adapter(job)
    job.total = 4
    cb("Loading history...", 0, 4)
    daily, idx, sectors, _ = _load(db)
    if daily.empty:
        raise ValueError("No real market data to calibrate against.")

    cfg = RankConfig()

    def score_fn(hist, as_of):
        r = rank_stocks(hist, cfg, as_of=as_of, sectors=sectors)
        return r[["symbol", "score"]] if len(r) else None

    cb("Running walk-forward folds...", 1, 4)
    cal = build_calibration(daily, score_fn,
                            progress=lambda m: cb(m, 1, 4))
    if cal.empty:
        return {"built": False,
                "message": ("Not enough history yet to calibrate honestly. "
                            "Download more data and try again. Until then "
                            "probabilities will show 'Insufficient data'.")}

    cb("Saving calibration...", 2, 4)
    n = persist_calibration(db, cal)
    summary = Calibrator(db).summary()

    # Measure whether each confirmation check is worth anything. This is the
    # part that stops "add more confirmations" from becoming superstition:
    # a check earns its place by improving the next-session hit rate on a
    # large sample, or it is reported as having no measurable effect.
    cb("Measuring the confirmation checks...", 3, 4)
    conf = {}
    try:
        conf = measure_confirmations(db, daily, sectors, idx=idx)
    except Exception as e:  # noqa: BLE001
        conf = {"error": f"Could not measure the checks: {e}"}

    cb("Calibration complete.", 4, 4)
    return {"built": True, "buckets": n, "summary": summary,
            "confirmations": conf, "table": cal.to_dict("records")}


def _market_trend_by_date(idx: pd.DataFrame) -> pd.Series:
    """Bullish/Bearish per date, from NIFTY 50 against its 50-day average.

    Computed only from data available on that date, so the evaluation
    cannot see the future.
    """
    if idx is None or idx.empty:
        return pd.Series(dtype=object)
    from app.analytics.indices import is_nifty50
    n = idx[idx["index_name"].map(is_nifty50)].copy()
    if n.empty:
        return pd.Series(dtype=object)
    n["date"] = pd.to_datetime(n["date"])
    n = n.sort_values("date")
    sma = n["close"].rolling(50, min_periods=20).mean()
    lab = pd.Series("Unknown", index=n.index, dtype=object)
    lab[n["close"] > sma] = "Bullish"
    lab[n["close"] <= sma] = "Bearish"
    lab[sma.isna()] = "Unknown"
    return pd.Series(lab.values, index=n["date"].values)


def _sector_strength_by_date(idx: pd.DataFrame) -> dict:
    """For each date, each sector's momentum rank turned into a label."""
    if idx is None or idx.empty:
        return {}
    from app.analytics.indices import sector_label
    d = idx.copy()
    d["date"] = pd.to_datetime(d["date"])
    d["sector"] = d["index_name"].map(sector_label)
    d = d[d["sector"].notna()]
    if d.empty:
        return {}
    d = d.sort_values(["sector", "date"])
    d["ret21"] = d.groupby("sector")["close"].pct_change(21)
    d = d.dropna(subset=["ret21"])
    if d.empty:
        return {}
    d["pct"] = d.groupby("date")["ret21"].rank(pct=True)

    def lab(p):
        return ("Strong" if p >= 0.8 else "Firm" if p >= 0.6 else
                "Neutral" if p >= 0.4 else "Weak" if p >= 0.2 else
                "Very weak")

    d["label"] = d["pct"].map(lab)
    return {(r.date, r.sector): r.label for r in d.itertuples()}


def _delivery_by_symbol_date(db) -> dict:
    conn = db.connect()
    try:
        try:
            rows = conn.execute(
                "SELECT symbol, date, delivery_pct FROM delivery"
            ).fetchall()
        except Exception:  # noqa: BLE001
            return {}
    finally:
        conn.close()
    return {(r["symbol"], str(r["date"])[:10]): r["delivery_pct"]
            for r in rows if r["delivery_pct"] is not None}


def measure_confirmations(db, daily: pd.DataFrame, sectors: dict,
                          idx: pd.DataFrame | None = None,
                          horizon: int = 1) -> dict:
    """Build the evidence table for every confirmation check.

    Every row of history is scored with the same checks the trade cards
    use, then compared against what price actually did next. Nothing here
    is fitted - it is a straight count of what happened.
    """
    d = daily.copy()
    d["date"] = pd.to_datetime(d["date"])
    mkt = _market_trend_by_date(idx)
    sect = _sector_strength_by_date(idx)
    deliv = _delivery_by_symbol_date(db)

    frames = []
    for sym, g in d.groupby("symbol"):
        if len(g) < 220:
            continue
        f = add_indicator_set(g)
        f["relative_volume"] = f["volume"] / f["adv20"]
        sec = sectors.get(sym, "Unknown")
        f["market_trend"] = (f["date"].map(mkt).fillna("Unknown")
                             if len(mkt) else "Unknown")
        f["market_alignment"] = "Unknown"
        f["sector_strength"] = [sect.get((dd, sec), "Unknown")
                                for dd in f["date"]] if sect else "Unknown"
        f["delivery_pct"] = ([deliv.get((sym, dd.strftime("%Y-%m-%d")))
                              for dd in f["date"]] if deliv else None)
        f["announcements_7d"] = None
        f["fwd_ret"] = f["close"].shift(-horizon) / f["close"] - 1
        frames.append(f.dropna(subset=["fwd_ret"]))
    if not frames:
        return {"available": False,
                "message": "Not enough history to measure the checks yet."}

    feat = pd.concat(frames, ignore_index=True)
    out = {"available": True, "rows": int(len(feat)), "sides": {}}
    with db.tx() as conn:
        for side in ("LONG", "SHORT"):
            tbl = evaluate_checks(feat, side=side, horizon=horizon)
            out["sides"][side] = tbl.to_dict("records")
            for r in tbl.itertuples():
                conn.execute(
                    "INSERT OR REPLACE INTO confirmation_stats"
                    " (check_key,label,side,horizon_days,n_pass,n_fail,"
                    "  hit_pass_pct,hit_fail_pct,edge_pct,verdict,built_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,datetime('now'))",
                    (r.check, r.label, side, horizon, int(r.n_pass),
                     int(r.n_fail),
                     None if pd.isna(r.hit_pass_pct) else float(r.hit_pass_pct),
                     None if pd.isna(r.hit_fail_pct) else float(r.hit_fail_pct),
                     None if pd.isna(r.edge_pct) else float(r.edge_pct),
                     r.verdict))
    return out
