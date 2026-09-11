"""Pull and analyse the Phase-1 logs from your phone.

Usage (from the project folder):
    python tools/p1_logs.py                # pull + summary
    python tools/p1_logs.py --timeline     # human readable timeline
    python tools/p1_logs.py --file reports/logs/invo-events-20260910.jsonl

What it answers:
  * does INVO post real system notifications at all?      (METHOD 1)
  * do they carry a PendingIntent we could fire?          (METHOD 2)
  * can the notification text alone give us trader/asset/action/leverage?
  * are there duplicates?
  * how much latency between INVO posting and us receiving?
"""

import argparse
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from invo_adb import LOG_DIR_POSIX, adb, ensure_dir, pick_serial

INVO_HINTS = ("com.involio.app", "invo")


def pull(serial):
    out_dir = os.path.join("reports", "logs")
    os.makedirs(out_dir, exist_ok=True)
    code, out, err = adb(["shell", "ls", LOG_DIR_POSIX], serial=serial)
    if code != 0:
        print("No log folder yet on the phone. Open the app once, then retry.")
        print("ls said: " + (err or out).strip())
        return []
    names = [n.strip() for n in out.split() if n.endswith(".jsonl")]
    if not names:
        print("Log folder exists but contains no .jsonl file.")
        return []
    files = []
    for n in sorted(names):
        dest = os.path.join(out_dir, n)
        code, out2, err2 = adb(["pull", LOG_DIR_POSIX + "/" + n, dest], serial=serial, timeout=180)
        if code == 0:
            files.append(dest)
        else:
            print("pull failed for " + n + ": " + (err2 or out2).strip())
    return files


def load(paths):
    events = []
    for p in paths:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            for raw in f:
                raw = raw.strip()
                i = raw.find("\t{")
                if i < 0:
                    continue
                try:
                    events.append(json.loads(raw[i + 1:]))
                except ValueError:
                    pass
    return events


def is_invo(e):
    pkg = (e.get("pkg") or "").lower()
    return any(h in pkg for h in INVO_HINTS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--serial", default=None)
    ap.add_argument("--file", default=None, help="analyse a local .jsonl instead of pulling")
    ap.add_argument("--timeline", action="store_true")
    ap.add_argument("--report", default=os.path.join("reports", "phase1-report.md"))
    args = ap.parse_args()

    if args.file:
        files = [args.file]
    else:
        serial = pick_serial(args.serial)
        print("pulling logs from " + serial + " ...")
        files = pull(serial)
        if not files:
            return 1

    events = load(files)
    if not events:
        print("No parseable events found in: " + ", ".join(files))
        print("If the phone produced only plain text lines, send those lines to me as-is.")
        return 1

    notif = [e for e in events if e.get("ev") in ("POSTED", "REMOVED")]
    posted = [e for e in notif if e.get("ev") == "POSTED"]
    invo = [e for e in posted if is_invo(e)]

    by_pkg = {}
    for e in posted:
        by_pkg[e.get("pkg", "?")] = by_pkg.get(e.get("pkg", "?"), 0) + 1

    print("")
    print("files analysed : " + ", ".join(files))
    print("total events   : %d   notifications: %d   from INVO: %d" % (len(events), len(posted), len(invo)))
    print("")
    print("packages that posted notifications (this is how we find INVO's real package id):")
    for pkg, n in sorted(by_pkg.items(), key=lambda kv: -kv[1])[:25]:
        mark = "  <-- looks like INVO" if any(h in (pkg or "").lower() for h in INVO_HINTS) else ""
        print("   %5d  %s%s" % (n, pkg, mark))

    lines = []
    lines.append("# Phase 1 report\n")
    lines.append("generated: %s" % datetime_now())
    lines.append("files: %s\n" % ", ".join(files))
    lines.append("| metric | value |")
    lines.append("|---|---|")

    if not invo:
        print("")
        print("METHOD 1 RESULT: 0 INVO notifications captured.")
        print("=> INVO probably does NOT post system notifications (or uses a different package).")
        print("   Next step is METHOD 4 (screen polling). Run tools/p1_ui.py while tapping a trade.")
        lines.append("| INVO notifications seen | 0 |")
    else:
        cov = {k: 0 for k in ("handle", "asset", "action", "direction", "leverage", "entryPrice")}
        pid = 0
        lat = []
        chans = set()
        extra_keys = set()
        fps = {}
        amb = 0
        for e in invo:
            p = e.get("parse") or {}
            for k in cov:
                v = p.get(k)
                if v not in (None, "", 0, "UNKNOWN"):
                    cov[k] += 1
            if p.get("ambiguous"):
                amb += 1
            if e.get("hasContentIntent"):
                pid += 1
            if e.get("latencyMs") is not None:
                try:
                    lat.append(float(e["latencyMs"]))
                except (TypeError, ValueError):
                    pass
            if e.get("channelId"):
                chans.add(e["channelId"])
            ex = e.get("extras")
            if isinstance(ex, dict):
                extra_keys.update(ex.keys())
            fp = p.get("fpExact")
            if fp:
                fps[fp] = fps.get(fp, 0) + 1
        dups = sum(1 for v in fps.values() if v > 1)
        n = len(invo)

        print("")
        print("METHOD 1 RESULT: YES - INVO posts system notifications (%d captured)." % n)
        print("Fields reliably readable from the notification text alone:")
        for k, v in cov.items():
            print("   %-11s %3d/%d  (%.0f%%)" % (k, v, n, 100.0 * v / n))
        print("   ambiguous action (could not tell open/update/close): %d/%d" % (amb, n))
        print("")
        print("METHOD 2 RESULT: %d/%d notifications carry a contentIntent (%.0f%%)."
              % (pid, n, 100.0 * pid / n))
        unwrapped = sum(1 for e in invo
                        if isinstance(e.get("contentIntent"), dict)
                        and "UNWRITABLE" not in str(e["contentIntent"].get("unwrap", "")))
        print("   of those, %d can be unwrapped to see the exact screen they open." % unwrapped)
        print("")
        if lat:
            print("Delivery latency (INVO post -> our capture), ms:  min %d / median %d / max %d"
                  % (min(lat), statistics.median(lat), max(lat)))
        print("Notification channels seen: " + (", ".join(sorted(chans)) or "(none)"))
        print("Extras keys seen: " + (", ".join(sorted(extra_keys)) or "(none)"))
        print("Duplicate fingerprints: %d" % dups)
        print("")
        print("Sample of what was captured (first 3):")
        for e in invo[:3]:
            p = e.get("parse") or {}
            print("   %s  %s | %s -> %s %s %s %s lev=%s | verdict=%s" % (
                e.get("postTimeStr", ""), e.get("title", ""), e.get("text", "")[:60],
                p.get("action"), p.get("handle"), p.get("asset"), p.get("direction"),
                p.get("leverage"), e.get("verdict")))

        rows = [
            ("INVO notifications captured", n),
            ("readable handle", "%d%%" % (100 * cov["handle"] // n)),
            ("readable asset", "%d%%" % (100 * cov["asset"] // n)),
            ("readable open/update/close", "%d%%" % (100 * cov["action"] // n)),
            ("readable direction", "%d%%" % (100 * cov["direction"] // n)),
            ("readable leverage", "%d%%" % (100 * cov["leverage"] // n)),
            ("ambiguous", amb),
            ("has contentIntent", "%d%%" % (100 * pid // n)),
            ("duplicate fingerprints", dups),
            ("latency ms median", int(statistics.median(lat)) if lat else "n/a"),
        ]
        for k, v in rows:
            lines.append("| %s | %s |" % (k, v))

    if args.timeline:
        print("")
        print("--- timeline ---")
        for e in events:
            ev = e.get("ev")
            if ev in ("POSTED", "REMOVED"):
                p = e.get("parse") or {}
                print("%s %s %s %s %s %s" % (
                    e.get("postTimeStr") or e.get("ev", ""), ev, e.get("pkg"),
                    (e.get("title") or "")[:40], p.get("action", ""), p.get("asset", "")))
            elif ev:
                print("%s %s" % (e.get("receivedAt", ""), json.dumps(e)[:140]))

    os.makedirs(os.path.dirname(os.path.abspath(args.report)), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("")
    print("report written to " + args.report)
    print("Send me: reports/phase1-report.md  +  reports/logs/*.jsonl")
    return 0


def datetime_now():
    import datetime
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


if __name__ == "__main__":
    sys.exit(main())
