#!/usr/bin/env python3
"""
COST TRACKER (spec 27).

Tracks what this system actually costs to run per month, in INR.
Target: 0 rupees/month. Anything non-zero must justify itself.

Usage:
    python scripts/cost_tracker.py                     # show current month
    python scripts/cost_tracker.py --add api "Upstox Plus" 500
    python scripts/cost_tracker.py --history
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import load_settings
from app.db.database import Database

CATEGORIES = ("api", "server", "data", "other")


def show(db: Database, month: str) -> None:
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT category, item, amount_inr, note FROM cost_ledger"
            " WHERE month=? ORDER BY category, item", (month,)).fetchall()
    finally:
        conn.close()

    totals = {c: 0.0 for c in CATEGORIES}
    for r in rows:
        totals[r["category"]] = totals.get(r["category"], 0.0) + r["amount_inr"]
    grand = sum(totals.values())

    print("=" * 66)
    print(f"COST TRACKER  -  {month}")
    print("=" * 66)
    if rows:
        print(f"{'CATEGORY':<10}{'ITEM':<28}{'INR':>12}  NOTE")
        print("-" * 66)
        for r in rows:
            print(f"{r['category']:<10}{(r['item'] or ''):<28}"
                  f"{r['amount_inr']:>12,.2f}  {r['note'] or ''}")
        print("-" * 66)
    print(f"{'API COST':<38}{totals['api']:>12,.2f}")
    print(f"{'SERVER COST':<38}{totals['server']:>12,.2f}")
    print(f"{'DATA COST':<38}{totals['data']:>12,.2f}")
    print(f"{'OTHER COST':<38}{totals['other']:>12,.2f}")
    print("=" * 66)
    print(f"{'CURRENT MONTHLY COST':<38}{grand:>12,.2f} INR")
    print("=" * 66)
    if grand == 0:
        print("\nTarget met: 0 INR/month.")
        print("Running on free public data, local compute and the SSD you")
        print("already own. Electricity and your internet bill are not counted.")
    else:
        print(f"\nAbove the 0 INR target by {grand:,.2f} INR/month.")
        print("Each paid line item should buy a measurable reliability or")
        print("accuracy gain. If it does not, cancel it.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None)
    ap.add_argument("--month", default=dt.date.today().strftime("%Y-%m"))
    ap.add_argument("--add", nargs=3, metavar=("CATEGORY", "ITEM", "AMOUNT"),
                    help="add a cost line, e.g. --add api Upstox 0")
    ap.add_argument("--note", default="")
    ap.add_argument("--history", action="store_true")
    a = ap.parse_args()

    st = load_settings(a.root)
    db = Database(st.db_path)

    if a.add:
        cat, item, amt = a.add
        if cat not in CATEGORIES:
            print(f"Category must be one of {CATEGORIES}")
            return 1
        with db.tx() as c:
            c.execute("INSERT INTO cost_ledger (month,category,item,"
                      "amount_inr,note) VALUES (?,?,?,?,?)",
                      (a.month, cat, item, float(amt), a.note))
        print(f"Recorded: {a.month} {cat} {item} INR {float(amt):,.2f}")

    # Seed a zero-cost baseline the first time it is run.
    conn = db.connect()
    try:
        n = conn.execute("SELECT COUNT(*) FROM cost_ledger WHERE month=?",
                         (a.month,)).fetchone()[0]
    finally:
        conn.close()
    if n == 0:
        with db.tx() as c:
            c.executemany(
                "INSERT INTO cost_ledger (month,category,item,amount_inr,note)"
                " VALUES (?,?,?,?,?)",
                [(a.month, "data", "NSE public archives", 0.0, "free"),
                 (a.month, "api", "broker free tier", 0.0,
                  "free with your own account"),
                 (a.month, "server", "local PC + SSD", 0.0,
                  "hardware already owned"),
                 (a.month, "other", "Telegram Bot API", 0.0, "free")])

    if a.history:
        conn = db.connect()
        try:
            for r in conn.execute(
                "SELECT month, SUM(amount_inr) t FROM cost_ledger"
                " GROUP BY month ORDER BY month"):
                print(f"  {r['month']}  INR {r['t']:>10,.2f}")
        finally:
            conn.close()
        return 0

    show(db, a.month)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
