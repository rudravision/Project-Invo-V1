"""LAKSHMI Phase 1: FII/DII flows and index valuation.

Two things are being protected here:

* **Parsing tolerance.** The user will sometimes hand-download a CSV from
  NSE because the undocumented API refused us. Column spellings vary, so
  the parser has to cope without silently dropping data.
* **Refusal to guess.** A 6-day rolling sum must not be compared against a
  threshold designed for 20 days. When the data is short, the answer is
  "not available", not a smaller number.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.data.macro import (FlowRow, flow_series, import_flows_file,
                            import_valuation_file, india_vix_latest,
                            latest_valuation, parse_date, parse_flows_csv,
                            parse_nse_fiidii, parse_valuation_csv,
                            rolling_net, store_flows, store_valuation, _num)
from app.db.database import Database
from app.db.migrations import migrate


@pytest.fixture()
def db(tmp_path):
    d = Database(tmp_path / "m.sqlite")
    migrate(d, tmp_path / "bk")
    return d


# ------------------------------------------------------------- parsing ----
@pytest.mark.parametrize("raw,expect", [
    ("12,115.00", 12115.0), ("-667", -667.0), ("(1,234)", -1234.0),
    ("", None), ("-", None), ("NA", None), (None, None), (526, 526.0),
])
def test_number_parsing_handles_nse_formatting(raw, expect):
    assert _num(raw) == expect


@pytest.mark.parametrize("raw", [
    "2026-09-24", "24-Sep-2026", "24-09-2026", "24/09/2026", "Sep 24, 2026",
])
def test_date_parsing_accepts_every_nse_spelling(raw):
    assert parse_date(raw) == "2026-09-24"


def test_unparseable_date_returns_none_not_today():
    assert parse_date("garbage") is None
    assert parse_date("") is None


def test_parse_nse_api_payload():
    rows = parse_nse_fiidii([
        {"category": "FII/FPI *", "date": "24-Sep-2026",
         "buyValue": "12,115.00", "sellValue": "11,589.00",
         "netValue": "526.00"},
        {"category": "DII **", "date": "24-Sep-2026",
         "buyValue": "12,368.00", "sellValue": "12,172.00",
         "netValue": "196.00"},
    ])
    assert len(rows) == 1
    r = rows[0]
    assert r.date == "2026-09-24"
    assert r.fii_net == 526.0 and r.dii_net == 196.0
    assert r.source == "nse:fiidii"


def test_parse_nse_payload_survives_junk():
    assert parse_nse_fiidii(None) == []
    assert parse_nse_fiidii({"unexpected": "shape"}) == []
    assert parse_nse_fiidii([{"category": "FII", "date": "nonsense"}]) == []


def test_net_is_derived_when_the_source_omits_it():
    r = FlowRow(date="2026-09-24", fii_buy=100.0, fii_sell=40.0).filled_net()
    assert r.fii_net == 60.0
    # and stays None when it cannot be derived
    assert FlowRow(date="2026-09-24", fii_buy=100.0).filled_net().fii_net is None


CSV_FLOWS = """Date,FII Buy,FII Sell,FII Net,DII Buy,DII Sell,DII Net
24-Sep-2026,"12,115.00","11,589.00",526.00,"12,368.00","12,172.00",196.00
23-Sep-2026,"13,122.00","13,790.00",-667.00,"12,800.00","10,723.00","2,076.00"
"""


def test_parse_hand_downloaded_csv():
    rows = parse_flows_csv(CSV_FLOWS)
    assert len(rows) == 2
    assert rows[0].fii_net == 526.0
    assert rows[1].dii_net == 2076.0


def test_parse_csv_with_different_column_spellings():
    text = ("Trade Date,FPI Buy,FPI Sell,DII Gross Purchase,DII Gross Sales\n"
            "24-Sep-2026,100,40,80,30\n")
    rows = parse_flows_csv(text)
    assert rows[0].fii_net == 60.0
    assert rows[0].dii_net == 50.0


def test_unrecognisable_csv_explains_itself():
    with pytest.raises(ValueError, match="nseindia.com"):
        parse_flows_csv("some,random,file\n1,2,3\n")


def test_parse_valuation_csv():
    text = ("Date,P/E,P/B,Div Yield,Close\n"
            "23-Sep-2026,19.82,2.82,1.21,\"24,150.30\"\n")
    rows = parse_valuation_csv(text)
    assert rows[0]["pe"] == 19.82 and rows[0]["pb"] == 2.82
    assert rows[0]["div_yield"] == 1.21
    assert rows[0]["index_name"] == "Nifty 50"


# ------------------------------------------------------------- storage ----
def _seed(db, n, start="2026-08-03", fii=-100.0, dii=120.0):
    d = dt.date.fromisoformat(start)
    rows = []
    while len(rows) < n:
        if d.weekday() < 5:
            rows.append(FlowRow(date=d.isoformat(), fii_buy=1000.0,
                                fii_sell=1000.0 - fii, fii_net=fii,
                                dii_buy=1000.0, dii_sell=1000.0 - dii,
                                dii_net=dii, source="test"))
        d += dt.timedelta(days=1)
    return store_flows(db, rows)


def test_store_and_read_back(db):
    assert _seed(db, 5) == 5
    rows = flow_series(db)
    assert len(rows) == 5
    assert rows[0]["fii_net"] == -100.0
    assert rows[0]["segment"] == "cash"


def test_storing_the_same_day_twice_updates_not_duplicates(db):
    store_flows(db, [FlowRow(date="2026-09-24", fii_net=100.0, source="a")])
    store_flows(db, [FlowRow(date="2026-09-24", fii_net=250.0, source="b")])
    rows = flow_series(db)
    assert len(rows) == 1
    assert rows[0]["fii_net"] == 250.0 and rows[0]["source"] == "b"


def test_store_ignores_empty_input(db):
    assert store_flows(db, []) == 0
    assert store_valuation(db, []) == 0


# ------------------------------------------------------ rolling windows ----
def test_rolling_net_refuses_a_short_window(db):
    """A 6-day sum judged against a 20-day threshold would mislead."""
    _seed(db, 6)
    r = rolling_net(db, window=20)
    assert r["available"] is False
    assert r["observations"] == 6
    assert "20 are needed" in r["reason"]
    assert "fii_net" not in r


def test_rolling_net_sums_the_window(db):
    _seed(db, 25, fii=-100.0, dii=120.0)
    r = rolling_net(db, window=20)
    assert r["available"] is True
    assert r["fii_net"] == pytest.approx(-2000.0)
    assert r["dii_net"] == pytest.approx(2400.0)
    assert r["observations"] == 25
    assert r["units"] == "INR crore"


def test_rolling_net_refuses_when_a_day_is_missing_its_figure(db):
    _seed(db, 25)
    store_flows(db, [FlowRow(date=flow_series(db)[-1]["date"], fii_net=None,
                             dii_net=None, source="gap")])
    r = rolling_net(db, window=20)
    assert r["available"] is False
    assert "misleading" in r["reason"]


# ----------------------------------------------------------- valuation ----
def test_latest_valuation_round_trip(db):
    store_valuation(db, [
        {"date": "2026-09-22", "pe": 19.5, "pb": 2.8, "div_yield": 1.2,
         "close": 24000.0, "source": "test"},
        {"date": "2026-09-23", "pe": 19.82, "pb": 2.82, "div_yield": 1.21,
         "close": 24150.3, "source": "test"},
    ])
    v = latest_valuation(db)
    assert v["date"] == "2026-09-23" and v["pe"] == 19.82


def test_latest_valuation_is_none_when_empty(db):
    assert latest_valuation(db) is None


def test_india_vix_is_read_from_the_index_table(db):
    db.upsert_index([{"index_name": "India VIX", "date": "2026-09-23",
                      "open": 11.0, "high": 11.5, "low": 10.6, "close": 11.2,
                      "change_pct": 0.0, "source": "test",
                      "is_synthetic": 0}])
    v = india_vix_latest(db)
    assert v and v["value"] == pytest.approx(11.2)


def test_india_vix_absent_is_none_not_zero(db):
    assert india_vix_latest(db) is None


# --------------------------------------------------------- file import ----
def test_import_flows_from_a_downloaded_file(db, tmp_path):
    f = tmp_path / "fii_dii.csv"
    f.write_text(CSV_FLOWS, encoding="utf-8")
    out = import_flows_file(db, f)
    assert out["imported"] == 2
    assert out["first"] == "2026-09-24"
    assert len(flow_series(db)) == 2


def test_import_valuation_from_a_downloaded_file(db, tmp_path):
    f = tmp_path / "pe.csv"
    f.write_text("Date,P/E,P/B,Div Yield\n23-Sep-2026,19.82,2.82,1.21\n",
                 encoding="utf-8")
    out = import_valuation_file(db, f)
    assert out["imported"] == 1
    assert latest_valuation(db)["pe"] == 19.82


def test_missing_file_is_a_clear_error(db):
    with pytest.raises(FileNotFoundError):
        import_flows_file(db, "/nope/nothing.csv")


# ------------------------------------------------------------ provider ----
def test_provider_declares_the_new_capabilities():
    from app.data.base import Capability, DataProvider, NotSupportedError

    assert Capability.FII_DII_FLOWS.value == "fii_dii_flows"

    class Bare(DataProvider):
        name = "bare"

        def capabilities(self):
            return set()

        def health_check(self):
            return True

        def info(self):
            return None

        def get_daily_ohlc(self, symbols, start, end):
            return None

    # a provider that cannot do this must say so, not return empty data
    with pytest.raises(NotSupportedError):
        Bare().get_fii_dii()
    with pytest.raises(NotSupportedError):
        Bare().get_valuation()
