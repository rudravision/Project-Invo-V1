"""
Local Streamlit dashboard. Runs on your machine; nothing is sent to a cloud.

Launch:  streamlit run dashboard/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import streamlit as st

from app.analytics.ranking import RankConfig, rank_stocks, sector_heatmap
from app.core.config import load_settings
from app.data.quality import gate_signal, validate_daily
from app.db.database import Database

st.set_page_config(page_title="TRADING_AI", layout="wide")


@st.cache_resource
def get_settings():
    return load_settings(create=False)


@st.cache_data(ttl=300)
def load_data(db_path: str):
    db = Database(db_path)
    conn = db.connect()
    try:
        daily = pd.read_sql_query(
            "SELECT symbol,date,open,high,low,close,volume,is_synthetic"
            " FROM daily_ohlc ORDER BY symbol,date", conn)
        idx = pd.read_sql_query(
            "SELECT index_name,date,close FROM index_ohlc"
            " ORDER BY index_name,date", conn)
        sectors = dict(conn.execute("SELECT symbol,sector FROM symbols").fetchall())
        dq = pd.read_sql_query(
            "SELECT checked_at,dataset,check_name,severity,affected,detail"
            " FROM data_quality_log ORDER BY id DESC LIMIT 100", conn)
        fails = pd.read_sql_query(
            "SELECT time_utc,source,capability,error,fallback_used"
            " FROM source_failures ORDER BY id DESC LIMIT 50", conn)
    finally:
        conn.close()
    return daily, idx, sectors, dq, fails


def main():
    try:
        stg = get_settings()
    except Exception as e:
        st.error(f"Could not locate the SSD / project root.\n\n{e}")
        st.stop()

    st.title("TRADING_AI")
    st.caption(f"Local research dashboard - root: `{stg.root}`")

    if not stg.db_path.exists():
        st.warning("No database yet. Run `scripts/bootstrap_data.py` or "
                   "`scripts/make_demo_dataset.py`.")
        st.stop()

    daily, idx, sectors, dq, fails = load_data(str(stg.db_path))
    if daily.empty:
        st.warning("Database is empty.")
        st.stop()

    synthetic = bool(daily["is_synthetic"].max())
    if synthetic:
        st.error("**SYNTHETIC DEMO DATA** - these numbers are random, not "
                 "market data. Trading signals are disabled.")

    rep = validate_daily(daily)
    allowed, msg = gate_signal(rep, is_synthetic=synthetic)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Symbols", daily["symbol"].nunique())
    c2.metric("Daily rows", f"{len(daily):,}")
    c3.metric("Latest bar", str(pd.to_datetime(daily["date"]).max().date()))
    c4.metric("Signal gate", "ALLOWED" if allowed else "BLOCKED")

    if not allowed:
        st.error(msg)

    tabs = st.tabs(["Heatmap", "Ranking", "Data quality", "Source failures"])

    with tabs[0]:
        st.subheader("Sector / index heatmap")
        hm = sector_heatmap(idx)
        if hm.empty:
            st.info("No index data loaded.")
        else:
            cols = [c for c in ["index_name", "last_close", "ret_1d", "ret_5d",
                                "ret_21d", "ret_63d", "vol_20d"] if c in hm]
            st.dataframe(
                hm[cols].style.background_gradient(
                    cmap="RdYlGn",
                    subset=[c for c in cols if c.startswith("ret_")]),
                use_container_width=True)

    with tabs[1]:
        st.subheader("Stock ranking (rule-based prototype)")
        top = st.slider("Show top N", 5, 50, 20)
        ranked = rank_stocks(daily, RankConfig(), sectors=sectors)
        if ranked.empty:
            st.info("No symbols passed the liquidity/history filters.")
        else:
            cols = [c for c in ["rank", "symbol", "sector", "score", "close",
                                "ret_21", "ret_63", "rsi14", "vol20"]
                    if c in ranked]
            st.dataframe(ranked.head(top)[cols], use_container_width=True)
            sym = st.selectbox("Inspect symbol", ranked["symbol"].tolist())
            g = daily[daily["symbol"] == sym].copy()
            g["date"] = pd.to_datetime(g["date"])
            st.line_chart(g.set_index("date")["close"])

    with tabs[2]:
        st.subheader("Data quality log")
        st.text(rep.summary())
        if not dq.empty:
            st.dataframe(dq, use_container_width=True)

    with tabs[3]:
        st.subheader("Source failures and fallbacks")
        if fails.empty:
            st.success("No recorded source failures.")
        else:
            st.dataframe(fails, use_container_width=True)


if __name__ == "__main__":
    main()
