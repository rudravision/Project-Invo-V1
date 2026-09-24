"""
Local web server powering the desktop interface.

Binds to 127.0.0.1 by default: the app is reachable only from your own
machine and nothing is ever uploaded. Every long operation is dispatched to
a background thread (see jobs.py) so the window never freezes.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from flask import Flask, jsonify, request, send_from_directory

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.alerts.telegram import TelegramNotifier
from app.analytics.indicators import add_indicator_set
from app.analytics.indices import (display as idx_display, is_broad,
                                   is_sector, norm as idx_norm, pick_row,
                                   sector_label)
from app.analytics.probability import Calibrator, MODEL_VERSION
from app.analytics.ranking import RankConfig, rank_stocks, sector_heatmap
from app.analytics.recommend import (RiskSettings, generate_candidates,
                                     portfolio_summary)
from app.core.config import load_settings
from app.data.calendar import MarketCalendar, SymbolLifecycle
from app.data.corporate_actions import (quarantine_summary,
                                        quarantined_symbols,
                                        symbols_with_extreme_jumps,
                                        unresolved_report)
from app.data.quality2 import explain_for_humans, validate_daily_v2
from app.data.repair import analyse_gaps
from app.db.database import Database, graceful_shutdown
from app.db.migrations import migrate
from app.gui import jobs as jobslib
from app.gui.pipeline import (build_calibration_job, full_update_job,
                              repair_job, run_backtest_job)

log = logging.getLogger(__name__)

STATIC = Path(__file__).parent / "static"


SETTING_DEFAULTS = {
    "capital": 1_000_000.0, "risk_per_trade_pct": 1.0, "max_positions": 5,
    "max_daily_loss_pct": 3.0, "direction": "both", "stop_method": "atr",
    "atr_multiple": 2.0, "stop_percent": 5.0, "reward_multiple": 2.0,
    "max_position_pct": 25.0, "history_period": "5y", "universe": "nifty200",
    "auto_backup": True, "telegram_enabled": False,
}


def _clean(o):
    """Make numpy/pandas types JSON-safe."""
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        f = float(o)
        return None if (np.isnan(f) or np.isinf(f)) else f
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, float):
        return None if (np.isnan(o) or np.isinf(o)) else o
    if isinstance(o, (pd.Timestamp, dt.date, dt.datetime)):
        return str(o)[:19]
    if o is pd.NaT:
        return None
    return o


def _quieten_request_log() -> None:
    """Stop the web server logging every single request.

    The interface polls /api/job roughly once a second while a job runs, so
    at INFO level werkzeug wrote a line per poll and buried every genuine
    message under thousands of '"GET /api/job HTTP/1.1" 200' lines. Real
    warnings and errors still come through at WARNING and above.
    """
    logging.getLogger("werkzeug").setLevel(logging.WARNING)


def _depth_note(start: str | None, end: str | None, requested: str
                ) -> str | None:
    """Say plainly how much history actually exists.

    The user can ask for 5 years, but NSE's public UDiFF archive only goes
    back so far. Reporting the request as though it were delivered would be
    dishonest, so the dashboard states the real span instead.
    """
    if not start or not end:
        return None
    want = {"3m": 0.25, "6m": 0.5, "1y": 1.0, "2y": 2.0, "3y": 3.0,
            "5y": 5.0}.get(requested)
    try:
        d0 = dt.date.fromisoformat(str(start)[:10])
        d1 = dt.date.fromisoformat(str(end)[:10])
    except ValueError:
        return None
    years = (d1 - d0).days / 365.25
    have = (f"{years:.1f} years of history "
            f"({start} to {end})")
    if want and years < want * 0.9:
        return (f"You asked for {requested}, but only {have} is available "
                f"from the free NSE archive. Everything shown uses the real "
                f"span, not the requested one.")
    return f"{have[0].upper()}{have[1:]}."


def _quarantine_note(q: dict) -> dict:
    """Describe the excluded stocks in words the user can act on."""
    return {"count": len(q), "symbols": sorted(q), "reasons": q,
            "note": (f"{len(q)} stock(s) are excluded from recommendations "
                     f"because of an unexplained large price move. The rest "
                     f"of the market is unaffected.") if q else
                    "No stocks are excluded."}


def _quarantine_payload(db, daily=None) -> dict:
    """Which stocks are excluded from recommendations, and why."""
    q = {}
    try:
        if daily is not None:
            q.update(symbols_with_extreme_jumps(daily))
        q.update(quarantined_symbols(db))
    except Exception:  # noqa: BLE001
        pass
    return {"count": len(q), "symbols": sorted(q), "reasons": q,
            "note": (f"{len(q)} stock(s) are excluded from recommendations "
                     f"because of an unexplained large price move. The rest "
                     f"of the market is unaffected.") if q else
                    "No stocks are excluded."}


def create_app(root: str | None = None) -> Flask:
    settings = load_settings(root)
    _quieten_request_log()
    db = Database(settings.db_path)
    migrate(db, settings.backups_dir)

    app = Flask(__name__, static_folder=str(STATIC), static_url_path="")
    app.config["SETTINGS"] = settings
    app.config["DB"] = db
    manager = jobslib.JobManager()
    app.config["JOBS"] = manager

    # ---------------------------------------------------------------- utils
    def get_setting(key, default=None):
        conn = db.connect()
        try:
            r = conn.execute("SELECT value FROM app_settings WHERE key=?",
                             (key,)).fetchone()
        finally:
            conn.close()
        if r is None:
            return SETTING_DEFAULTS.get(key, default)
        try:
            return json.loads(r["value"])
        except (ValueError, TypeError):
            return r["value"]

    def all_settings() -> dict:
        out = dict(SETTING_DEFAULTS)
        conn = db.connect()
        try:
            for r in conn.execute("SELECT key,value FROM app_settings"):
                try:
                    out[r["key"]] = json.loads(r["value"])
                except (ValueError, TypeError):
                    out[r["key"]] = r["value"]
        finally:
            conn.close()
        return out

    def save_settings(d: dict):
        with db.tx() as c:
            c.executemany(
                "INSERT INTO app_settings (key,value,updated_at)"
                " VALUES (?,?,datetime('now'))"
                " ON CONFLICT(key) DO UPDATE SET value=excluded.value,"
                " updated_at=datetime('now')",
                [(k, json.dumps(v)) for k, v in d.items()])

    def risk_settings() -> RiskSettings:
        s = all_settings()
        return RiskSettings(
            capital=float(s["capital"]),
            risk_per_trade_pct=float(s["risk_per_trade_pct"]),
            max_positions=int(s["max_positions"]),
            max_daily_loss_pct=float(s["max_daily_loss_pct"]),
            direction=str(s["direction"]),
            stop_method=str(s["stop_method"]),
            atr_multiple=float(s["atr_multiple"]),
            stop_percent=float(s["stop_percent"]),
            reward_multiple=float(s["reward_multiple"]),
            max_position_pct=float(s["max_position_pct"]))

    def load_frames(adjusted: bool = True):
        """Load prices. Uses the corporate-action adjusted series when one
        has been built, because indicators computed across an unadjusted
        split are simply wrong. Falls back to raw prices otherwise."""
        conn = db.connect()
        try:
            daily = pd.read_sql_query(
                "SELECT symbol,date,open,high,low,close,volume,is_synthetic"
                " FROM daily_ohlc ORDER BY symbol,date", conn)
            if adjusted:
                # Overlay the split-adjusted series for the stocks that have
                # one. Only an overlay, never a replacement: swapping the
                # whole table would silently drop every stock that never
                # needed an adjustment, which is nearly all of them.
                try:
                    adj = pd.read_sql_query(
                        "SELECT symbol,date,open,high,low,close,volume"
                        " FROM daily_ohlc_adjusted ORDER BY symbol,date",
                        conn)
                except Exception:  # noqa: BLE001
                    adj = pd.DataFrame()
                if not adj.empty:
                    adj["is_synthetic"] = 0
                    keep = daily[~daily["symbol"].isin(set(adj["symbol"]))]
                    daily = (pd.concat([keep, adj[daily.columns]],
                                       ignore_index=True)
                             .sort_values(["symbol", "date"])
                             .reset_index(drop=True))
            idx = pd.read_sql_query(
                "SELECT index_name,date,close,change_pct,is_synthetic"
                " FROM index_ohlc ORDER BY index_name,date", conn)
            sectors = dict(conn.execute(
                "SELECT symbol, COALESCE(sector,industry,'Unknown')"
                " FROM symbols").fetchall())
            deliv = dict(conn.execute(
                "SELECT symbol, delivery_pct FROM delivery WHERE date="
                "(SELECT MAX(date) FROM delivery)").fetchall())
        finally:
            conn.close()
        return daily, idx, sectors, deliv

    app.config["HELPERS"] = {
        "get_setting": get_setting, "all_settings": all_settings,
        "save_settings": save_settings, "risk_settings": risk_settings,
        "load_frames": load_frames}

    # --------------------------------------------------------------- static
    @app.route("/")
    def index():
        return send_from_directory(STATIC, "index.html")

    # ------------------------------------------------------------- overview
    @app.get("/api/status")
    def api_status():
        """Everything the home screen needs, in one call."""
        conn = db.connect()
        try:
            cov = conn.execute(
                "SELECT COUNT(*) n, MIN(date) mn, MAX(date) mx,"
                " COUNT(DISTINCT symbol) s FROM daily_ohlc WHERE is_synthetic=0"
            ).fetchone()
            synth = conn.execute(
                "SELECT COUNT(*) FROM daily_ohlc WHERE is_synthetic=1"
            ).fetchone()[0]
            idxn = conn.execute(
                "SELECT COUNT(*) n, COUNT(DISTINCT index_name) i"
                " FROM index_ohlc WHERE is_synthetic=0").fetchone()
            sess = conn.execute(
                "SELECT COUNT(*) FROM market_sessions WHERE status='SESSION'"
            ).fetchone()[0]
            last_dq = conn.execute(
                "SELECT checked_at FROM data_quality_log ORDER BY id DESC"
                " LIMIT 1").fetchone()
        finally:
            conn.close()

        ok_db, detail_db = db.integrity_check()
        has_real = bool(cov["n"])
        free = settings.free_space()

        # market snapshot
        nifty = market = breadth = None
        strongest = weakest = None
        daily = None
        heat = []
        if has_real:
            daily, idx, sectors, _ = load_frames()
            if not idx.empty:
                hm = sector_heatmap(idx[idx["is_synthetic"] == 0])
                if not hm.empty:
                    known = hm[hm["index_name"].map(
                        lambda n: is_sector(n) or is_broad(n))]
                    heat = _clean(known.to_dict("records"))
                    for h in heat:
                        h["label"] = idx_display(h["index_name"])
                else:
                    heat = []
                r = pick_row(hm, which="nifty50")
                if r is not None:
                    nifty = {"value": float(r["last_close"]),
                             "change_pct": (float(r["ret_1d"])
                                            if pd.notna(r["ret_1d"]) else None),
                             "as_of": r["as_of"]}
                    market = _market_label(r.get("ret_1d"), r.get("ret_21d"))
                sect = hm[hm["index_name"].map(is_sector)]
                sect = sect[sect["ret_21d"].notna()]
                if len(sect):
                    sect = sect.sort_values("ret_21d", ascending=False)
                    strongest = {"index_name": idx_display(
                        sect.iloc[0]["index_name"]),
                        "ret_21d": _clean(sect.iloc[0]["ret_21d"])}
                    weakest = {"index_name": idx_display(
                        sect.iloc[-1]["index_name"]),
                        "ret_21d": _clean(sect.iloc[-1]["ret_21d"])}
            if not daily.empty:
                breadth = _breadth(daily[daily["is_synthetic"] == 0])

        # data-quality gate
        gate = {"status": "unknown", "reasons": []}
        if has_real:
            daily, _, _, _ = load_frames()
            rep = validate_daily_v2(daily[daily["is_synthetic"] == 0], db,
                                    run_gap_analysis=True)
            issues = explain_for_humans(rep)
            gate = {"status": "ok" if rep.ok else "blocked",
                    "reasons": issues,
                    "errors": len(rep.errors), "warnings": len(rep.warnings)}
        elif synth:
            gate = {"status": "blocked", "reasons": [{
                "level": "ERROR", "title": "Practice data only",
                "detail": "The database holds demo data, not real market "
                          "data. Recommendations are disabled.",
                "action": "UPDATE NOW"}]}
        else:
            gate = {"status": "blocked", "reasons": [{
                "level": "ERROR", "title": "No market data yet",
                "detail": "Click UPDATE & ANALYZE MARKET to download it.",
                "action": "UPDATE NOW"}]}

        cal = Calibrator(db)
        job = manager.current()

        return jsonify(_clean({
            "has_data": has_real,
            "synthetic_rows": synth,
            "coverage": {"rows": cov["n"], "symbols": cov["s"],
                         "start": cov["mn"], "end": cov["mx"],
                         "sessions": sess,
                         "index_rows": idxn["n"], "indices": idxn["i"],
                         "requested_period": get_setting("history_period"),
                         "depth_note": _depth_note(cov["mn"], cov["mx"],
                                                   get_setting("history_period"))},
            "database": {"healthy": ok_db, "detail": detail_db,
                         "size_mb": round(settings.db_path.stat().st_size
                                          / 1024**2, 1)
                         if settings.db_path.exists() else 0},
            "disk": free,
            "nifty": nifty, "market": market, "breadth": breadth,
            "strongest_sector": strongest, "weakest_sector": weakest,
            "heatmap": heat,
            "gate": gate,
            "calibration": cal.summary(),
            "quarantined": _quarantine_payload(db, daily),
            "last_update": cov["mx"],
            "last_check": last_dq["checked_at"] if last_dq else None,
            "job": job.to_dict() if job else None,
            "root": str(settings.root),
        }))

    def _market_label(r1, r21):
        if r21 is None or pd.isna(r21):
            return "Unknown"
        if r21 > 4:
            return "Strong bullish"
        if r21 > 1:
            return "Bullish"
        if r21 < -4:
            return "Strong bearish"
        if r21 < -1:
            return "Bearish"
        return "Neutral"

    def _breadth(daily: pd.DataFrame):
        if daily.empty:
            return None
        d = daily.copy()
        d["date"] = pd.to_datetime(d["date"])
        last = d["date"].max()
        cur = d[d["date"] == last]
        prev_dates = sorted(d["date"].unique())
        if len(prev_dates) < 2:
            return None
        prev = d[d["date"] == prev_dates[-2]][["symbol", "close"]] \
            .rename(columns={"close": "pc"})
        m = cur.merge(prev, on="symbol", how="inner")
        if m.empty:
            return None
        adv = int((m["close"] > m["pc"]).sum())
        dec = int((m["close"] < m["pc"]).sum())
        unch = int(len(m) - adv - dec)
        return {"advances": adv, "declines": dec, "unchanged": unch,
                "total": int(len(m)),
                "ratio": round(adv / dec, 2) if dec else None,
                "pct_advancing": round(adv / len(m) * 100, 1)}

    # ------------------------------------------------------------- heatmap
    @app.get("/api/heatmap")
    def api_heatmap():
        _, idx, _, _ = load_frames()
        idx = idx[idx["is_synthetic"] == 0]
        if idx.empty:
            return jsonify({"sectors": [], "broad": [],
                            "message": "No index data yet. Run an update."})
        hm = sector_heatmap(idx)
        recs = _clean(hm.to_dict("records"))
        for r in recs:
            r["band"] = _band(r.get("ret_21d"))
            r["label"] = idx_display(r["index_name"])
        sectors = [r for r in recs if is_sector(r["index_name"])]
        broad = [r for r in recs if is_broad(r["index_name"])]
        other = [r for r in recs
                 if not is_sector(r["index_name"])
                 and not is_broad(r["index_name"])]
        msg = None
        if not sectors:
            msg = ("No sector indices have been downloaded yet. Run "
                   "UPDATE & ANALYZE MARKET.")
        return jsonify({"sectors": sectors, "broad": broad,
                        "other_count": len(other), "message": msg})

    def _band(v):
        if v is None:
            return "unknown"
        if v >= 5:
            return "strong_bull"
        if v >= 1.5:
            return "bull"
        if v > -1.5:
            return "neutral"
        if v > -5:
            return "bear"
        return "strong_bear"

    @app.get("/api/sector/<path:name>/stocks")
    def api_sector_stocks(name):
        daily, idx, sectors, _ = load_frames()
        daily = daily[daily["is_synthetic"] == 0]
        if daily.empty:
            return jsonify({"stocks": []})
        ranked = rank_stocks(daily, RankConfig(), sectors=sectors)
        if ranked.empty:
            return jsonify({"stocks": [],
                            "message": "Not enough history to rank yet."})
        key = name.replace("NIFTY ", "").strip().lower()
        sel = ranked[ranked["sector"].fillna("").str.lower().str.contains(
            key, regex=False)]
        if sel.empty:
            sel = ranked
        cols = [c for c in ("rank", "symbol", "sector", "score", "close",
                            "ret_21", "ret_63", "rsi14", "vol20",
                            "above_sma50", "above_sma200") if c in sel]
        return jsonify({"sector": name,
                        "stocks": _clean(sel[cols].head(60).to_dict("records"))})

    # ----------------------------------------------------- recommendations
    @app.get("/api/recommendations")
    def api_recommendations():
        daily, idx, sectors, deliv = load_frames()
        total_rows = len(daily)
        daily = daily[daily["is_synthetic"] == 0]
        idx = idx[idx["is_synthetic"] == 0]
        if daily.empty:
            # Say WHY there is nothing, so a full database and an empty one
            # never produce the same unhelpful message.
            if total_rows:
                reason = (f"The database holds {total_rows:,} rows but all of "
                          f"them are test data, which is never used for real "
                          f"recommendations.")
            else:
                reason = ("No price data has been downloaded yet. Press "
                          "UPDATE & ANALYZE MARKET.")
            return jsonify({"blocked": True, "reason": reason,
                            "rows_total": total_rows, "rows_usable": 0,
                            "long": [], "short": []})

        rep = validate_daily_v2(daily, db, run_gap_analysis=True)
        if not rep.ok:
            return jsonify({
                "blocked": True,
                "quarantined": _quarantine_payload(db, daily),
                "reason": "SIGNAL DISABLED - DATA QUALITY FAILURE",
                "issues": explain_for_humans(rep), "long": [], "short": []})

        # Drop stocks whose history we cannot trust. Their indicators would
        # be computed across an unadjusted split, so any signal is garbage.
        bad = dict(symbols_with_extreme_jumps(daily))
        bad.update(quarantined_symbols(db))
        quarantined = _quarantine_note(bad)
        if bad:
            daily = daily[~daily["symbol"].isin(bad)]

        ranked = rank_stocks(daily, RankConfig(), sectors=sectors)
        if ranked.empty:
            return jsonify({"blocked": True,
                            "reason": "Not enough price history to rank "
                                      "stocks yet. Download more history.",
                            "quarantined": quarantined,
                            "long": [], "short": []})

        hm = sector_heatmap(idx) if not idx.empty else pd.DataFrame()
        sector_ranks = {}
        market_trend = "Unknown"
        if not hm.empty:
            for r in hm.itertuples():
                lbl = sector_label(r.index_name)
                if lbl:
                    sector_ranks[lbl] = float(r.momentum_rank)
            n50 = pick_row(hm, which="nifty50")
            if n50 is not None:
                market_trend = _market_label(n50.get("ret_1d"),
                                             n50.get("ret_21d"))

        rs = risk_settings()
        cal = Calibrator(db)
        cands = generate_candidates(
            daily, ranked, sectors=sectors, sector_ranks=sector_ranks,
            market_trend=market_trend, rs=rs, calibrator=cal,
            delivery=deliv, top_n=5)

        return jsonify(_clean({
            "blocked": False,
            "market_trend": market_trend,
            "long": [c.to_dict() for c in cands["long"]],
            "short": [c.to_dict() for c in cands["short"]],
            "portfolio": portfolio_summary(cands, rs),
            "risk": rs.to_dict(),
            "calibration": cal.summary(),
            "quarantined": quarantined,
        }))

    # -------------------------------------------------------------- charts
    @app.get("/api/chart/<symbol>")
    def api_chart(symbol):
        rng = request.args.get("range", "1Y").upper()
        days = {"1M": 31, "3M": 92, "6M": 183, "1Y": 366, "3Y": 1096,
                "5Y": 1827}.get(rng, 366)
        conn = db.connect()
        adjusted = False
        try:
            # Chart the split-adjusted series when we have one: moving
            # averages drawn across an unadjusted split are meaningless.
            try:
                df = pd.read_sql_query(
                    "SELECT date,open,high,low,close,volume FROM"
                    " daily_ohlc_adjusted WHERE symbol=? ORDER BY date",
                    conn, params=[symbol.upper()])
                adjusted = not df.empty
            except Exception:  # noqa: BLE001
                df = pd.DataFrame()
            if df.empty:
                df = pd.read_sql_query(
                    "SELECT date,open,high,low,close,volume FROM daily_ohlc"
                    " WHERE symbol=? AND is_synthetic=0 ORDER BY date",
                    conn, params=[symbol.upper()])
        finally:
            conn.close()
        if df.empty:
            return jsonify({"error": f"No data for {symbol}"}), 404

        ind = add_indicator_set(df.assign(date=pd.to_datetime(df["date"])))
        ind = ind.tail(days)
        sup, res = _support_resistance(ind)

        rs = risk_settings()
        from app.analytics.recommend import compute_levels
        last = ind.iloc[-1]
        entry, stop, target = compute_levels(
            float(last["close"]), float(last.get("atr14") or 0), "LONG", rs)

        def col(c):
            return [None if pd.isna(v) else round(float(v), 4)
                    for v in ind[c]] if c in ind else []

        return jsonify(_clean({
            "symbol": symbol.upper(), "range": rng,
            "adjusted": adjusted,
            "price_note": ("Prices adjusted for splits and bonuses."
                           if adjusted else "Prices as reported by NSE."),
            "dates": [d.strftime("%Y-%m-%d") for d in ind["date"]],
            "open": col("open"), "high": col("high"), "low": col("low"),
            "close": col("close"), "volume": col("volume"),
            "ema20": col("ema20"), "sma50": col("sma50"),
            "sma200": col("sma200"), "rsi": col("rsi14"),
            "macd": col("macd"), "macd_signal": col("macd_signal"),
            "macd_hist": col("macd_hist"), "atr": col("atr14"),
            "support": sup, "resistance": res,
            "entry": round(entry, 2), "stop": round(stop, 2),
            "target": round(target, 2),
        }))

    def _support_resistance(ind, lookback=120, n=3):
        tail = ind.tail(lookback)
        if tail.empty:
            return [], []
        lows = sorted(tail["low"].dropna().values)
        highs = sorted(tail["high"].dropna().values, reverse=True)
        sup = [round(float(x), 2) for x in lows[:n]]
        res = [round(float(x), 2) for x in highs[:n]]
        return sup, res

    # ------------------------------------------------------------- actions
    @app.post("/api/run/<action>")
    def api_run(action):
        body = request.get_json(silent=True) or {}
        try:
            if action == "update":
                job = manager.start(
                    "Update & Analyze Market",
                    lambda j: full_update_job(
                        j, db, settings,
                        period=body.get("period") or get_setting("history_period"),
                        universe=get_setting("universe"),
                        risk=risk_settings()))
            elif action == "repair":
                job = manager.start("Repair Data",
                                    lambda j: repair_job(j, db, settings))
            elif action == "backtest":
                job = manager.start(
                    "Backtest",
                    lambda j: run_backtest_job(j, db, settings, body))
            elif action == "calibrate":
                job = manager.start(
                    "Build Probability Calibration",
                    lambda j: build_calibration_job(j, db, settings))
            elif action == "backup":
                job = manager.start("Backup", lambda j: _backup_job(j))
            else:
                return jsonify({"error": f"Unknown action '{action}'"}), 400
        except RuntimeError as e:
            return jsonify({"error": str(e)}), 409
        return jsonify(job.to_dict())

    def _backup_job(job):
        cb = jobslib.progress_adapter(job)
        cb("Creating verified backup...", 0, 2)
        p = db.backup(settings.backups_dir, keep=int(get_setting("keep_backups", 10)))
        cb("Verifying checksum...", 1, 2)
        v = [b for b in db.verify_backups(settings.backups_dir)
             if b["file"] == p.name]
        cb("Backup complete.", 2, 2)
        return {"file": p.name, "verified": bool(v and v[0]["ok"])}

    @app.get("/api/job")
    def api_job():
        j = manager.current()
        return jsonify(j.to_dict() if j else {"status": "idle"})

    @app.get("/api/jobs")
    def api_jobs():
        return jsonify(manager.recent())

    @app.post("/api/job/<job_id>/cancel")
    def api_cancel(job_id):
        return jsonify({"cancelled": manager.cancel(job_id)})

    # ------------------------------------------------------------ backtest
    @app.get("/api/backtest/latest")
    def api_backtest_latest():
        files = sorted((settings.root / "backtests").glob("*_stats.json"))
        if not files:
            return jsonify({"available": False,
                            "message": "No backtest has been run yet."})
        data = json.loads(files[-1].read_text())
        eq = files[-1].with_name(
            files[-1].name.replace("_stats.json", "_equity.csv"))
        curve = []
        if eq.exists():
            e = pd.read_csv(eq)
            e.columns = ["date", "equity"][:len(e.columns)]
            curve = _clean(e.to_dict("records"))
        return jsonify(_clean({"available": True, **data, "equity": curve,
                               "file": files[-1].name}))

    # --------------------------------------------------------- data sources
    @app.get("/api/sources")
    def api_sources():
        probes = sorted((settings.root / "reports").glob("source_probe_*.json"))
        latest = {}
        if probes:
            try:
                latest = json.loads(probes[-1].read_text())
            except (OSError, ValueError):
                latest = {}
        roles = settings.roles()
        purpose = {}
        fallback = {}
        for role, cfg in roles.items():
            p = cfg.get("primary")
            if p:
                purpose.setdefault(p, []).append(role)
                fallback[p] = ", ".join(cfg.get("backups") or []) or "none"
            for b in cfg.get("backups") or []:
                purpose.setdefault(b, []).append(f"{role} (backup)")

        conn = db.connect()
        try:
            fails = [dict(r) for r in conn.execute(
                "SELECT time_utc,source,capability,error,fallback_used"
                " FROM source_failures ORDER BY id DESC LIMIT 25")]
        finally:
            conn.close()

        # The probe reports WORKING / FAILED / BLOCKED / NOT_PUBLISHED /
        # RATE_LIMITED / SKIPPED / UNKNOWN. Roll those into the four counters
        # the page shows.
        raw = latest.get("summary", {}) or {}
        summary = {
            "ok": raw.get("WORKING", 0),
            "fail": (raw.get("FAILED", 0) + raw.get("UNKNOWN", 0)
                     + raw.get("REACHABLE_BUT_UNEXPECTED", 0)),
            "blocked": (raw.get("BLOCKED", 0) + raw.get("RATE_LIMITED", 0)),
            "skipped": (raw.get("SKIPPED", 0) + raw.get("NOT_PUBLISHED", 0)),
            "raw": raw,
        }

        rows = []
        for r in latest.get("results", []):
            rows.append({
                "source": r["source"], "status": r["status"],
                "latency_ms": r.get("latency_ms"),
                "http": r.get("http_status"), "detail": r.get("detail"),
                "checked_at": r.get("checked_at_utc"),
                "purpose": ", ".join(purpose.get(r["source"].split(":")[0], []))
                or _guess_purpose(r["source"]),
                "fallback": fallback.get(r["source"].split(":")[0], "-"),
            })
        # Tell the user how old this snapshot is. A source test from
        # yesterday can say FAILED while today's download is working fine,
        # which is confusing unless the staleness is stated plainly.
        age_hours = None
        gen = latest.get("generated_at_utc")
        if gen:
            try:
                then = dt.datetime.fromisoformat(gen.replace("Z", "+00:00"))
                if then.tzinfo is None:
                    then = then.replace(tzinfo=dt.timezone.utc)
                age_hours = round(
                    (dt.datetime.now(dt.timezone.utc) - then).total_seconds()
                    / 3600, 1)
            except ValueError:
                pass

        return jsonify({"generated_at": gen,
                        "age_hours": age_hours,
                        "stale": bool(age_hours is not None and age_hours > 12),
                        "summary": summary,
                        "sources": rows, "failures": fails})

    def _guess_purpose(name):
        n = name.lower()
        for key, val in (("bhavcopy", "Daily prices"),
                         ("index", "Index & sector data"),
                         ("delivery", "Delivery %"),
                         ("holiday", "Trading calendar"),
                         ("announce", "Corporate news"),
                         ("quote", "Live quotes"),
                         ("constituents", "Index membership"),
                         ("fo", "Futures & options")):
            if key in n:
                return val
        return "Market data"

    @app.post("/api/sources/probe")
    def api_probe():
        def run(job):
            cb = jobslib.progress_adapter(job)
            cb("Testing data sources...", 0, 1)
            import subprocess
            r = subprocess.run(
                [sys.executable,
                 str(settings.root / "scripts" / "probe_sources.py")],
                capture_output=True, text=True, timeout=600)
            cb("Done.", 1, 1)
            return {"output": (r.stdout or "")[-4000:]}
        try:
            job = manager.start("Test Data Sources", run)
        except RuntimeError as e:
            return jsonify({"error": str(e)}), 409
        return jsonify(job.to_dict())

    # ------------------------------------------------------------ settings
    @app.get("/api/settings")
    def api_get_settings():
        return jsonify(_clean({"settings": all_settings(),
                               "defaults": SETTING_DEFAULTS}))

    @app.post("/api/settings")
    def api_post_settings():
        body = request.get_json(silent=True) or {}
        clean, errors = {}, []
        for k, v in body.items():
            if k not in SETTING_DEFAULTS:
                continue
            try:
                if k in ("capital", "risk_per_trade_pct", "max_daily_loss_pct",
                         "atr_multiple", "stop_percent", "reward_multiple",
                         "max_position_pct"):
                    v = float(v)
                    if v <= 0:
                        errors.append(f"{k} must be greater than zero")
                        continue
                elif k == "max_positions":
                    v = int(v)
                elif k in ("auto_backup", "telegram_enabled"):
                    v = bool(v)
            except (TypeError, ValueError):
                errors.append(f"{k} is not a valid number")
                continue
            clean[k] = v
        if clean.get("risk_per_trade_pct", 0) > 10:
            errors.append("Risk per trade above 10% is dangerous; capped at 10%")
            clean["risk_per_trade_pct"] = 10.0
        if errors and not clean:
            return jsonify({"ok": False, "errors": errors}), 400
        save_settings(clean)
        return jsonify({"ok": True, "saved": clean, "warnings": errors,
                        "settings": all_settings()})

    @app.post("/api/settings/reset")
    def api_reset_settings():
        save_settings(SETTING_DEFAULTS)
        return jsonify({"ok": True, "settings": all_settings()})

    # ------------------------------------------------------------ telegram
    @app.post("/api/telegram/save")
    def api_tg_save():
        body = request.get_json(silent=True) or {}
        tok = (body.get("token") or "").strip()
        chat = (body.get("chat_id") or "").strip()
        env = settings.root / "config" / ".env"
        env.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        if env.exists():
            lines = [l for l in env.read_text(encoding="utf-8").splitlines()
                     if not l.startswith(("TELEGRAM_BOT_TOKEN=",
                                          "TELEGRAM_CHAT_ID="))]
        lines += [f"TELEGRAM_BOT_TOKEN={tok}", f"TELEGRAM_CHAT_ID={chat}"]
        env.write_text("\n".join(lines) + "\n", encoding="utf-8")
        try:
            env.chmod(0o600)
        except OSError:
            pass
        save_settings({"telegram_enabled": bool(tok and chat)})
        # Never echo the token back.
        return jsonify({"ok": True, "configured": bool(tok and chat)})

    @app.get("/api/telegram/status")
    def api_tg_status():
        from app.core.config import load_credentials
        c = load_credentials(settings.root)
        tok, chat = c.get("TELEGRAM_BOT_TOKEN"), c.get("TELEGRAM_CHAT_ID")
        return jsonify({"configured": bool(tok and chat),
                        "chat_id_masked": (chat[:3] + "***") if chat else None})

    @app.post("/api/telegram/test")
    def api_tg_test():
        from app.core.config import load_credentials
        c = load_credentials(settings.root)
        n = TelegramNotifier(c.get("TELEGRAM_BOT_TOKEN"),
                             c.get("TELEGRAM_CHAT_ID"))
        ok, detail = n.health_check()
        sent = n.send("TRADING_AI test message - your alerts are working.") \
            if ok else False
        return jsonify({"ok": bool(ok and sent),
                        "detail": detail if ok else detail,
                        "message": "Test message sent - check Telegram."
                        if sent else "Could not send. " + detail})

    # ------------------------------------------------------------- backups
    @app.get("/api/backups")
    def api_backups():
        out = []
        for b in db.verify_backups(settings.backups_dir):
            p = settings.backups_dir / b["file"]
            out.append({**b,
                        "created": dt.datetime.fromtimestamp(
                            p.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
                        "checksum_short": (b["actual"] or "")[:16]})
        out.sort(key=lambda x: x["created"], reverse=True)
        return jsonify({"backups": out, "dir": str(settings.backups_dir)})

    @app.post("/api/backups/restore")
    def api_restore():
        body = request.get_json(silent=True) or {}
        name = body.get("file")
        src = settings.backups_dir / str(name)
        if not name or not src.exists():
            return jsonify({"ok": False, "error": "Backup not found"}), 404
        v = [b for b in db.verify_backups(settings.backups_dir)
             if b["file"] == name]
        if not v or v[0]["ok"] is not True:
            return jsonify({"ok": False,
                            "error": "That backup fails its checksum and will "
                                     "not be restored."}), 400
        # Never destroy the current database: snapshot it first.
        safety = db.backup(settings.backups_dir, keep=20)
        graceful_shutdown(db)
        import shutil
        shutil.copy2(src, settings.db_path)
        return jsonify({"ok": True, "restored": name,
                        "previous_saved_as": safety.name})

    # ---------------------------------------------------------------- logs
    @app.get("/api/logs")
    def api_logs():
        kind = request.args.get("kind", "app")
        if kind == "quality":
            conn = db.connect()
            try:
                rows = [dict(r) for r in conn.execute(
                    "SELECT checked_at,dataset,check_name,severity,affected,"
                    "detail FROM data_quality_log ORDER BY id DESC LIMIT 300")]
            finally:
                conn.close()
            return jsonify({"rows": rows})
        if kind == "gaps":
            conn = db.connect()
            try:
                rows = [dict(r) for r in conn.execute(
                    "SELECT symbol,date,classification,detail,resolved"
                    " FROM data_gaps ORDER BY date DESC LIMIT 300")]
            finally:
                conn.close()
            return jsonify({"rows": rows})
        if kind == "corporate":
            df = unresolved_report(db)
            return jsonify({"rows": _clean(df.to_dict("records"))})
        f = settings.logs_dir / "trading_ai.log"
        text = ""
        if f.exists():
            text = f.read_text(encoding="utf-8", errors="replace")[-60_000:]
        return jsonify({"text": text})

    @app.get("/api/health")
    def api_health():
        return jsonify({"ok": True, "version": MODEL_VERSION})

    return app


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8777)
    ap.add_argument("--debug", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO)
    app = create_app(a.root)
    app.run(host=a.host, port=a.port, debug=a.debug, threaded=True,
            use_reloader=False)


if __name__ == "__main__":
    main()
