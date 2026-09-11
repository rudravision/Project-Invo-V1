"""Dump and inspect the INVO screen hierarchy over ADB (UIAutomator).

This is the tool that ANSWERS the accessibility question with data instead of
guesses: if the texts below ("Mimic Trade", "Position Size", "$78,524", "40x")
appear here, we never need OCR or coordinates.

Usage:
    python tools/p1_ui.py                       # dump whatever is on screen now
    python tools/p1_ui.py --grep mimic          # only show nodes containing 'mimic'
    python tools/p1_ui.py --watch 20            # 20 snapshots, 2s apart (while you tap around)
    python tools/p1_ui.py --watch 20 --interval 1.5 --grep position
    python tools/p1_ui.py --screenshot

Output:
    reports/ui-<time>.xml      raw dump (send me this)
    reports/ui-<time>.txt      readable tree (send me this)
    reports/ui-latest.txt      always the newest readable tree
"""

import argparse
import datetime
import os
import re
import sys
import time
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from invo_adb import adb, pick_serial

REMOTE = "/sdcard/invo_ui_dump.xml"

WORDS = re.compile(r"mimic|swipe|position size|leverage|take profit|stop loss|long|short|close|available|margin", re.I)


def dump_once(serial, timeout):
    code, out, err = adb(["shell", "uiautomator", "dump", REMOTE], serial=serial, timeout=timeout)
    if code != 0 or "dumped to" not in (out + err).lower():
        return None, (out + err).strip()
    code, data, err = adb(["exec-out", "cat", REMOTE], serial=serial, timeout=timeout, binary=True)
    if code != 0 or not data or b"<hierarchy" not in data[:400]:
        return None, (err or b"").decode("utf-8", "replace").strip()
    adb(["shell", "rm", REMOTE], serial=serial)
    return data, None


def short(cls):
    return (cls or "").split(".")[-1]


def render(xml_bytes, grep=None):
    try:
        root = ET.fromstring(xml_bytes.decode("utf-8", "replace"))
    except ET.ParseError as e:
        return ["XML parse error: %s" % e], [], 0
    lines = []
    hits = []
    state = {"n": 0}

    def walk(node, depth):
        state["n"] += 1
        a = node.attrib
        text = (a.get("text") or "").replace("\n", " ").strip()
        desc = (a.get("content-desc") or "").replace("\n", " ").strip()
        rid = a.get("resource-id") or ""
        cls = short(a.get("class"))
        clickable = a.get("clickable") == "true"
        editable = cls in ("EditText", "AutoCompleteTextView")
        row = "  " * depth
        row += cls
        if rid:
            row += "  id=" + rid.split("/")[-1] + (" (" + rid + ")" if "/" in rid else "")
        if text:
            row += "  text=" + (text[:90] + ".." if len(text) > 90 else text)
        if desc:
            row += "  desc=" + (desc[:90] + ".." if len(desc) > 90 else desc)
        if clickable:
            row += "  [click]"
        if editable:
            row += "  [INPUT]"
        row += "  " + (a.get("bounds") or "")
        lines.append(row)
        blob = (text + " " + desc + " " + rid)
        if grep and grep.lower() in blob.lower():
            hits.append(row.strip())
        elif WORDS.search(blob):
            hits.append("(keyword) " + row.strip())
        for ch in list(node):
            walk(ch, depth + 1)

    for node in list(root):
        walk(node, 0)
    return lines, hits, state["n"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--serial", default=None)
    ap.add_argument("--grep", default=None, help="show only nodes matching this word")
    ap.add_argument("--watch", type=int, default=0, help="take N snapshots while you navigate the app")
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--timeout", type=int, default=40)
    ap.add_argument("--screenshot", action="store_true")
    args = ap.parse_args()

    serial = pick_serial(args.serial)
    os.makedirs("reports", exist_ok=True)

    if args.screenshot:
        path = os.path.join("reports", "ui-%s.png" % datetime.datetime.now().strftime("%H%M%S"))
        with open(path, "wb") as f:
            code, data, err = adb(["exec-out", "screencap", "-p"], serial=serial, binary=True, timeout=30)
            if code != 0:
                print("screencap failed: " + err.decode("utf-8", "replace"))
                return 1
            f.write(data)
        print("saved " + path)
        return 0

    rounds = args.watch if args.watch > 0 else 1
    for i in range(rounds):
        if args.watch > 0:
            print("--- snapshot %d/%d (do the next tap on the phone NOW) ---" % (i + 1, rounds))
            time.sleep(args.interval)
        data, err = dump_once(serial, args.timeout)
        if data is None:
            print("DUMP FAILED: " + str(err))
            print("Common causes: screen off/locked, or the app sets FLAG_SECURE on this screen.")
            print("Workaround: use the in-app button '5. Dump this screen' instead.")
            return 1

        lines, hits, n = render(data, args.grep)
        stamp = datetime.datetime.now().strftime("%H%M%S")
        xml_path = os.path.join("reports", "ui-%s.xml" % stamp)
        txt_path = os.path.join("reports", "ui-%s.txt" % stamp)
        with open(xml_path, "wb") as f:
            f.write(data)
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        with open(os.path.join("reports", "ui-latest.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        print("nodes=%d  saved=%s  (%s)" % (n, txt_path, xml_path))
        if n < 5:
            print("!! Very few nodes => this screen is not exposed to accessibility. "
                  "We would need OCR here. Tell me which screen this was.")
        elif hits:
            print("interesting nodes (%d):" % len(hits))
            for h in hits[:40]:
                print("   " + h)
            print("")
            print("=> Text is readable from the node tree. Accessibility approach is viable; no OCR needed for this screen.")
        else:
            print("No trade-related words found on THIS screen (fine if you were on a different page).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
