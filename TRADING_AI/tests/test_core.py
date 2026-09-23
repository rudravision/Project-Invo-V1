"""Tests for the pieces that must not silently break."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analytics.indicators import atr, max_drawdown, rsi, sma
from app.analytics.ranking import RankConfig, rank_stocks, sector_heatmap
from app.data.base import (Capability, DataProvider, DataRouter, FailureLog,
                           NotSupportedError, ProviderError, ProviderInfo,
                           Freshness)
from app.data.quality import gate_signal, validate_daily
from app.db.database import (Database, atomic_write_bytes, sha256_file,
                             write_raw_immutable)


# ---------------------------------------------------------------- fixtures --
def make_daily(n=300, symbols=("AAA", "BBB", "CCC"), seed=7, synthetic=0):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=dt.date.today() - dt.timedelta(days=1), periods=n)
    rows = []
    for s in symbols:
        px = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.015, n)))
        for i, d in enumerate(dates):
            o = px[i] * (1 + rng.normal(0, 0.002))
            rows.append({"symbol": s, "date": d, "open": o,
                         "high": max(o, px[i]) * 1.01,
                         "low": min(o, px[i]) * 0.99,
                         "close": px[i], "volume": float(rng.integers(1e5, 1e6)),
                         "is_synthetic": synthetic})
    return pd.DataFrame(rows)


# ------------------------------------------------------------- indicators --
def test_sma_matches_manual():
    s = pd.Series([1.0, 2, 3, 4, 5])
    assert sma(s, 3).iloc[-1] == pytest.approx(4.0)


def test_rsi_bounds():
    s = pd.Series(np.cumsum(np.random.default_rng(1).normal(0, 1, 200)) + 100)
    r = rsi(s, 14).dropna()
    assert ((r >= 0) & (r <= 100)).all()


def test_rsi_all_gains_is_high():
    s = pd.Series(np.arange(1, 60, dtype=float))
    assert rsi(s, 14).iloc[-1] > 95


def test_atr_positive():
    d = make_daily(60, ("X",))
    a = atr(d, 14).dropna()
    assert (a > 0).all()


def test_max_drawdown_known():
    eq = pd.Series([100.0, 120, 60, 90])
    assert max_drawdown(eq) == pytest.approx(-0.5)


# ---------------------------------------------------------------- quality --
def test_validate_clean_data_passes():
    rep = validate_daily(make_daily(200))
    assert rep.ok, rep.summary()


def test_detects_duplicates():
    d = make_daily(120, ("AAA",))
    d = pd.concat([d, d.tail(1)], ignore_index=True)
    rep = validate_daily(d)
    assert not rep.ok
    assert any(i.check == "duplicates" for i in rep.errors)


def test_detects_negative_price():
    d = make_daily(120, ("AAA",))
    d.loc[d.index[-1], "close"] = -5.0
    rep = validate_daily(d)
    assert not rep.ok
    assert any(i.check == "non_positive_prices" for i in rep.errors)


def test_detects_high_below_low():
    d = make_daily(120, ("AAA",))
    i = d.index[-1]
    d.loc[i, "high"], d.loc[i, "low"] = 10.0, 99.0
    rep = validate_daily(d)
    assert any(i_.check == "high_below_low" for i_ in rep.errors)


def test_detects_stale_data():
    d = make_daily(120, ("AAA",))
    d["date"] = d["date"] - pd.Timedelta(days=90)
    rep = validate_daily(d)
    assert any(i.check == "stale_data" for i in rep.errors)


def test_flags_corporate_action_gap():
    d = make_daily(150, ("AAA",)).sort_values("date").reset_index(drop=True)
    d.loc[d.index[-1], "close"] = d.loc[d.index[-2], "close"] * 0.5
    d.loc[d.index[-1], "low"] = d.loc[d.index[-1], "close"] * 0.99
    d.loc[d.index[-1], "open"] = d.loc[d.index[-1], "close"]
    d.loc[d.index[-1], "high"] = d.loc[d.index[-1], "close"] * 1.01
    rep = validate_daily(d)
    assert any("corporate_action" in i.check for i in rep.issues)


def test_empty_dataset_is_error():
    rep = validate_daily(pd.DataFrame())
    assert not rep.ok


def test_gate_blocks_synthetic():
    rep = validate_daily(make_daily(200))
    allowed, msg = gate_signal(rep, is_synthetic=True)
    assert not allowed
    assert "SIGNAL DISABLED" in msg


def test_gate_allows_clean_real_data():
    rep = validate_daily(make_daily(200))
    allowed, _ = gate_signal(rep, is_synthetic=False)
    assert allowed


# ---------------------------------------------------------------- ranking --
def test_ranking_produces_ordered_scores():
    r = rank_stocks(make_daily(300), RankConfig(min_history=130))
    assert not r.empty
    assert list(r["rank"]) == sorted(r["rank"])
    assert r["score"].is_monotonic_decreasing


def test_ranking_respects_min_history():
    r = rank_stocks(make_daily(50), RankConfig(min_history=130))
    assert r.empty


def test_ranking_no_lookahead():
    """Ranking as of date T must ignore everything after T."""
    d = make_daily(300, ("AAA", "BBB", "CCC"))
    cut = pd.to_datetime(d["date"]).sort_values().iloc[-30].date()
    full = rank_stocks(d, RankConfig(), as_of=cut)
    truncated = rank_stocks(d[pd.to_datetime(d["date"]).dt.date <= cut],
                            RankConfig(), as_of=cut)
    pd.testing.assert_series_equal(full["score"].reset_index(drop=True),
                                   truncated["score"].reset_index(drop=True))


def test_heatmap():
    idx = pd.DataFrame([
        {"index_name": n, "date": d, "close": 100 + i + hash(n) % 7}
        for n in ("NIFTY 50", "NIFTY IT")
        for i, d in enumerate(pd.bdate_range(end=dt.date.today(), periods=100))
    ])
    hm = sector_heatmap(idx)
    assert len(hm) == 2
    assert "ret_21d" in hm.columns


# --------------------------------------------------------------- database --
def test_db_roundtrip_and_integrity(tmp_path):
    db = Database(tmp_path / "t.sqlite")
    rows = [{"symbol": "AAA", "date": "2026-01-01", "open": 1, "high": 2,
             "low": 0.5, "close": 1.5, "volume": 100, "source": "test"}]
    assert db.upsert_daily(rows) == 1
    ok, _ = db.integrity_check()
    assert ok
    assert db.coverage()["rows"] == 1


def test_db_upsert_is_idempotent(tmp_path):
    db = Database(tmp_path / "t.sqlite")
    row = [{"symbol": "AAA", "date": "2026-01-01", "close": 1.5,
            "source": "test"}]
    db.upsert_daily(row)
    db.upsert_daily(row)
    assert db.coverage()["rows"] == 1


def test_db_backup_and_checksum(tmp_path):
    db = Database(tmp_path / "t.sqlite")
    db.upsert_daily([{"symbol": "A", "date": "2026-01-01", "close": 1,
                      "source": "t"}])
    b = db.backup(tmp_path / "bk", keep=3)
    assert b.exists()
    v = db.verify_backups(tmp_path / "bk")
    assert v and v[0]["ok"] is True


def test_backup_rotation(tmp_path):
    db = Database(tmp_path / "t.sqlite")
    for _ in range(5):
        db.backup(tmp_path / "bk", keep=2)
    assert len(list((tmp_path / "bk").glob("*.sqlite"))) <= 2


def test_missing_dates(tmp_path):
    db = Database(tmp_path / "t.sqlite")
    db.upsert_daily([{"symbol": "A", "date": "2026-01-05", "close": 1,
                      "source": "t"}])
    miss = db.missing_dates("A", "2026-01-05", "2026-01-09")
    assert "2026-01-05" not in miss
    assert "2026-01-06" in miss


# ---------------------------------------------------------- atomic writes --
def test_atomic_write(tmp_path):
    p = atomic_write_bytes(tmp_path / "a" / "b.bin", b"hello")
    assert p.read_bytes() == b"hello"
    assert not list(tmp_path.rglob("*.tmp"))


def test_raw_files_are_immutable(tmp_path):
    p = tmp_path / "raw.json"
    r1 = write_raw_immutable(p, b"original")
    assert r1["status"] == "written"
    r2 = write_raw_immutable(p, b"DIFFERENT")
    assert r2["status"] == "exists_different"
    assert p.read_bytes() == b"original"   # original preserved


def test_sha256(tmp_path):
    p = tmp_path / "f"
    p.write_bytes(b"abc")
    assert sha256_file(p) == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")


# ----------------------------------------------------------------- router --
class _Good(DataProvider):
    name = "good"
    def info(self): return ProviderInfo("good", "", Freshness.END_OF_DAY,
                                        "", "", "", "free", "", "", "")
    def capabilities(self): return {Capability.DAILY_OHLC}
    def health_check(self): return True, "ok"
    def get_daily_ohlc(self, s, a, b): return "GOOD_DATA"


class _Broken(DataProvider):
    name = "broken"
    def info(self): return ProviderInfo("broken", "", Freshness.END_OF_DAY,
                                        "", "", "", "free", "", "", "")
    def capabilities(self): return {Capability.DAILY_OHLC}
    def health_check(self): return False, "down"
    def get_daily_ohlc(self, s, a, b): raise ConnectionError("source is down")


def test_router_falls_back(tmp_path):
    flog = FailureLog(tmp_path / "f.jsonl")
    router = DataRouter({"broken": _Broken(), "good": _Good()},
                        {"daily_ohlc": {"primary": "broken",
                                        "backups": ["good"]}}, flog)
    out = router.fetch("daily_ohlc", "get_daily_ohlc", ["A"], None, None)
    assert out == "GOOD_DATA"
    assert len(flog.records) == 1
    assert flog.records[0].source == "broken"
    assert flog.records[0].fallback_used == "good"


def test_router_raises_when_all_fail(tmp_path):
    flog = FailureLog(tmp_path / "f.jsonl")
    router = DataRouter({"broken": _Broken()},
                        {"daily_ohlc": {"primary": "broken"}}, flog)
    with pytest.raises(ProviderError):
        router.fetch("daily_ohlc", "get_daily_ohlc", ["A"], None, None)


def test_unsupported_capability_raises():
    with pytest.raises(NotSupportedError):
        _Good().get_intraday("A", "1m", None, None)


# -------------------------------------------------------------------- ssd --
def test_ssd_never_guesses_a_drive_letter():
    from app.core import ssd
    vols = ssd.list_volumes()
    assert isinstance(vols, list)
    # detect_ssd must return None rather than inventing a path.
    r = ssd.detect_ssd(hints=("definitely-not-a-real-drive-xyz",))
    assert r is None or r.score(("definitely-not-a-real-drive-xyz",)) >= 40


def test_resolve_root_honours_env(monkeypatch, tmp_path):
    from app.core import ssd
    monkeypatch.setenv("TRADING_AI_ROOT", str(tmp_path / "TA"))
    assert ssd.resolve_project_root() == (tmp_path / "TA").resolve()


def test_ensure_project_root_is_additive(tmp_path):
    from app.core.ssd import ensure_project_root
    keep = tmp_path / "MY_IMPORTANT_FILE.txt"
    keep.write_text("do not delete me")
    ensure_project_root(tmp_path)
    assert keep.read_text() == "do not delete me"   # untouched
    assert (tmp_path / "data" / "raw").is_dir()


# --------------------------------------------------------------- backtest --
def test_backtest_runs_and_charges_costs():
    from app.backtest.engine import BacktestConfig, CostModel, run_backtest
    d = make_daily(400, ("AAA", "BBB", "CCC", "DDD", "EEE", "FFF"))
    dates = pd.to_datetime(d["date"])
    cfg = BacktestConfig(start=(dates.min() + pd.Timedelta(days=250)).date(),
                         end=dates.max().date(), top_n=3)
    res = run_backtest(d, cfg, RankConfig(), CostModel())
    assert len(res.equity) > 20
    assert res.stats["total_costs"] > 0        # costs are real
    assert "sharpe" in res.stats


def test_cost_model_sell_exceeds_buy():
    from app.backtest.engine import CostModel
    c = CostModel()
    assert c.sell_cost(100000) > c.buy_cost(100000)   # STT on sell
