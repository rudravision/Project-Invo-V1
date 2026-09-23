#!/usr/bin/env python3
"""
The friendly menu. Written for someone who does not want to type commands.

Everything in this file speaks plain English, explains what it is about to do
before doing it, and never leaves the user staring at a stack trace.
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PY = sys.executable
LINE = "=" * 70


# --------------------------------------------------------------------------- #
# little helpers
# --------------------------------------------------------------------------- #
def clear():
    print("\n" * 2)


def pause():
    try:
        input("\n   Press ENTER to go back to the menu... ")
    except (EOFError, KeyboardInterrupt):
        pass


def run(args: list[str], title: str) -> int:
    """Run a sub-script and show its output live."""
    print(LINE)
    print(f"  {title}")
    print(LINE)
    print()
    try:
        return subprocess.call([PY] + args)
    except KeyboardInterrupt:
        print("\n   Stopped by you. Nothing was damaged.")
        return 130
    except Exception as e:  # noqa: BLE001
        print(f"\n   Could not run that step: {e}")
        return 1


def yes(question: str, default_no: bool = True) -> bool:
    suffix = "[y/N]" if default_no else "[Y/n]"
    try:
        ans = input(f"   {question} {suffix} ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    if not ans:
        return not default_no
    return ans.startswith("y")


def probe_report() -> dict | None:
    files = sorted((ROOT / "reports").glob("source_probe_*.json"))
    if not files:
        return None
    try:
        return json.loads(files[-1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def has_real_data() -> tuple[bool, str]:
    """Is there genuine (non-synthetic) market data in the database?"""
    try:
        from app.core.config import load_settings
        from app.db.database import Database
        st = load_settings(str(ROOT), create=False)
        if not st.db_path.exists():
            return False, "no database yet"
        db = Database(st.db_path)
        conn = db.connect()
        try:
            real = conn.execute(
                "SELECT COUNT(*) FROM daily_ohlc WHERE is_synthetic=0"
            ).fetchone()[0]
            synth = conn.execute(
                "SELECT COUNT(*) FROM daily_ohlc WHERE is_synthetic=1"
            ).fetchone()[0]
        finally:
            conn.close()
        if real:
            return True, f"{real:,} real rows"
        if synth:
            return False, f"{synth:,} practice rows only"
        return False, "database is empty"
    except Exception:  # noqa: BLE001
        return False, "could not read the database"


# --------------------------------------------------------------------------- #
# status banner
# --------------------------------------------------------------------------- #
def banner():
    print(LINE)
    print("   TRADING_AI  -  your market research assistant")
    print(LINE)
    print(f"   Folder : {ROOT}")

    real, detail = has_real_data()
    print(f"   Data   : {'REAL market data - ' + detail if real else 'practice data - ' + detail}")

    rep = probe_report()
    if rep is None:
        print("   Sources: not tested yet  (do step 2)")
    else:
        working = [r for r in rep["results"] if r["status"] == "WORKING"]
        when = rep["generated_at_utc"][:10]
        if working:
            print(f"   Sources: {len(working)} working  (tested {when})")
        else:
            print(f"   Sources: none working  (tested {when})")
    print(LINE)


MENU = """
   WHAT DO YOU WANT TO DO?

     1.  Check my computer and SSD are ready
     2.  Test which market-data sources work        <-- do this early
     3.  Download real NSE market data
     4.  Show me today's rankings and sector heatmap
     5.  Open the visual dashboard in my browser

     6.  Back up my data
     7.  Set up Telegram alerts
     8.  What is this costing me?
     9.  Load practice data (fake numbers, for a safe try-out)

     0.  Quit
"""


# --------------------------------------------------------------------------- #
# actions
# --------------------------------------------------------------------------- #
def action_check():
    print("""
   This looks at eight things: your SSD, free space, internet, whether a
   market-data source answers, your database, Python, your credentials and
   Telegram.

   It only reads. It changes nothing.
""")
    code = run([str(ROOT / "scripts" / "system_check.py"), "--root", str(ROOT)],
               "SYSTEM CHECK")
    if code == 0:
        print("\n   Everything important passed. You are good to go.")
    else:
        print("""
   Some CRITICAL items failed - look for the [FAIL] lines above.

   The usual culprits:
     * "SSD detected FAIL" -> plug the drive in, or open
       config\\paths.yaml and type your drive's name under ssd_name_hints
     * "Disk space FAIL"   -> free up space on the SSD
     * "Market data source FAIL" -> your internet, or NSE is down right now
""")
    pause()


def action_probe():
    print("""
   This sends one small, polite request to each free data source and records
   exactly what came back - the real answer, not a guess.

   It takes about a minute. It downloads almost nothing.

   IMPORTANT: this is the step that tells us the truth. Everything I built
   was written in a sandbox with no internet access to NSE, so nothing has
   been confirmed working yet. This finds out.
""")
    if not yes("Run the test now?", default_no=False):
        return
    run([str(ROOT / "scripts" / "probe_sources.py")], "TESTING DATA SOURCES")

    rep = probe_report()
    if rep:
        working = [r["source"] for r in rep["results"] if r["status"] == "WORKING"]
        blocked = [r for r in rep["results"] if r["status"] == "BLOCKED"]
        print("\n" + LINE)
        if working:
            print(f"   GOOD NEWS: {len(working)} sources work.")
            print("   You can go to step 3 and download real data.")
        elif blocked:
            print("   Sources answered but refused access.")
            print("   That usually means NSE is blocking automated requests")
            print("   from your network right now. Try again later, or use a")
            print("   broker account (step 7 explains).")
        else:
            print("   Nothing worked.")
            print("   Check: is your internet on? Is a VPN or office firewall")
            print("   in the way? NSE is sometimes down in the evening.")
        print(LINE)
    pause()


def action_download():
    rep = probe_report()
    if rep is None:
        print("""
   Hold on - we have not tested the data sources yet.

   Please do step 2 first. Otherwise this would be downloading blind.
""")
        pause()
        return

    working = [r["source"] for r in rep["results"] if r["status"] == "WORKING"]
    if not working:
        print("""
   The last test found no working source, so there is nothing to download
   from. I will not pretend otherwise or invent data.

   Try step 2 again later - NSE availability varies through the day.
""")
        pause()
        return

    print(f"""
   This downloads real NSE end-of-day data for the NIFTY 200 stocks.

   Before downloading anything it will show you exactly how many megabytes
   it expects to use and ask you to confirm.

   It only fetches days you do not already have, so running it again
   tomorrow costs just one day's download.
""")
    days = "120"
    try:
        ans = input("   How many days of history? [120] ").strip()
        if ans.isdigit():
            days = ans
    except (EOFError, KeyboardInterrupt):
        return

    run([str(ROOT / "scripts" / "bootstrap_data.py"), "--root", str(ROOT),
         "--days", days], "DOWNLOADING REAL MARKET DATA")
    pause()


def action_reports():
    print("""
   This reads the data already on your SSD and produces:
     * a sector heatmap  - which parts of the market are strong or weak
     * a stock ranking   - the shortlist, best-scoring first
     * a backtest        - how the ranking rule would have done historically

   No internet needed. Nothing is downloaded.
""")
    real, _ = has_real_data()
    if not real:
        print("   NOTE: you are on practice data, so no real signals will be")
        print("   produced. The numbers below are random - they are only")
        print("   there to show you the shape of the output.\n")

    run([str(ROOT / "scripts" / "run_pipeline.py"), "--root", str(ROOT)],
        "TODAY'S RESEARCH")
    print(f"\n   Saved into: {ROOT / 'reports'}")
    print("   You can open those .txt and .csv files any time.")
    pause()


def action_dashboard():
    print("""
   This opens a visual dashboard in your web browser - charts, tables and
   colour-coded heatmaps instead of text.

   It runs entirely on your own computer. Nothing is uploaded anywhere.

   To close it later: come back to this window and press Ctrl+C.
""")
    if not yes("Open the dashboard?", default_no=False):
        return
    print("\n   Starting... your browser should open at http://localhost:8501")
    print("   (if it does not, type that address in yourself)\n")
    try:
        webbrowser.open("http://localhost:8501")
    except Exception:  # noqa: BLE001
        pass
    try:
        subprocess.call([PY, "-m", "streamlit", "run",
                         str(ROOT / "dashboard" / "app.py"),
                         "--server.headless", "true"])
    except KeyboardInterrupt:
        print("\n   Dashboard closed.")
    except Exception as e:  # noqa: BLE001
        print(f"\n   Could not start it: {e}")
        print("   Try option 1 to check your setup.")
    pause()


def action_backup():
    print("""
   This makes a safe, verified copy of your database, settings, models and
   reports into the backups folder on the SSD.

   Your raw downloaded files are never touched - they are permanently
   read-only by design.

   Old backups are tidied up automatically; the 10 most recent are kept.
""")
    run([str(ROOT / "scripts" / "backup.py"), "--root", str(ROOT)], "BACKUP")
    pause()


def action_telegram():
    env = ROOT / "config" / ".env"
    print(f"""
   TELEGRAM ALERTS - optional, free, about 5 minutes to set up.

   This lets the system message you on your phone.

   Step 1. In Telegram, search for the user  @BotFather
   Step 2. Send him:  /newbot     and follow the prompts.
   Step 3. He replies with a long token that looks like
              8123456789:AAG_xxxxxxxxxxxxxxxxxxxxxxxxxxxx
   Step 4. Search for  @userinfobot  and press Start.
           He replies with your Id - a number like  512345678
   Step 5. Paste both into this file:

              {env}

           so it reads:
              TELEGRAM_BOT_TOKEN=8123456789:AAG_xxxxxxxxxxxxx
              TELEGRAM_CHAT_ID=512345678

   Step 6. Come back and run option 1 - it will confirm the connection.

   Keep that file private. It is already excluded from backups and from
   version control, so your token never leaves your SSD.
""")
    if env.exists():
        print(f"   The file already exists. Open it in Notepad and edit it.")
        if yes("Open it in Notepad now?"):
            try:
                if sys.platform == "win32":
                    subprocess.Popen(["notepad.exe", str(env)])
                else:
                    subprocess.Popen(["xdg-open", str(env)])
            except Exception:  # noqa: BLE001
                print(f"   Could not open it. Navigate to it yourself:\n   {env}")
    else:
        print("   That file does not exist yet - run INSTALL first.")
    pause()


def action_cost():
    run([str(ROOT / "scripts" / "cost_tracker.py"), "--root", str(ROOT)],
        "RUNNING COSTS")
    pause()


def action_practice():
    print("""
   This loads PRACTICE data - invented random numbers, not the real market.

   Why bother? It lets you click around, see the heatmap, the rankings and
   the dashboard, and get comfortable, without needing a working internet
   data source.

   It is clearly labelled everywhere, and the system deliberately REFUSES
   to give trading signals from it.
""")
    if not yes("Load practice data?"):
        return
    from app.core.config import load_settings
    st = load_settings(str(ROOT))
    run([str(ROOT / "scripts" / "make_demo_dataset.py"),
         "--db", str(st.db_path), "--days", "400"], "LOADING PRACTICE DATA")
    print("\n   Done. Now try option 4 to see what the output looks like.")
    pause()


ACTIONS = {
    "1": action_check,
    "2": action_probe,
    "3": action_download,
    "4": action_reports,
    "5": action_dashboard,
    "6": action_backup,
    "7": action_telegram,
    "8": action_cost,
    "9": action_practice,
}


def main() -> int:
    while True:
        clear()
        banner()
        print(MENU)
        try:
            choice = input("   Type a number and press ENTER: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n   Bye.")
            return 0

        if choice in ("0", "q", "quit", "exit"):
            print("\n   Closing down safely...")
            try:
                subprocess.call([PY, str(ROOT / "scripts" / "shutdown.py"),
                                 "--root", str(ROOT)])
            except Exception:  # noqa: BLE001
                pass
            print("   Safe to unplug the SSD. Bye.")
            return 0

        action = ACTIONS.get(choice)
        if action is None:
            print("\n   I did not understand that. Type a number from 0 to 9.")
            pause()
            continue
        clear()
        try:
            action()
        except Exception as e:  # noqa: BLE001
            print(f"\n   Something went wrong: {e}")
            print("   Nothing was damaged. Try option 1 to check your setup.")
            pause()


if __name__ == "__main__":
    raise SystemExit(main())
