"""Phase-1 environment check.

Usage:
    python tools/p1_doctor.py
    python tools/p1_doctor.py --save

Prints PASS/FAIL for every prerequisite and the exact command that fixes it.
"""

import argparse
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from invo_adb import (APP_ID, LISTENER, LOG_DIR_POSIX, adb, devices,
                      find_adb, pick_serial)

FALLBACK = ("Android Studio -> Settings -> Languages & Frameworks -> "
            "Android SDK -> SDK Tools -> tick 'Android SDK Platform-Tools'")


def line(tag, msg):
    print("[%s] %s" % (tag, msg))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--serial", default=None)
    ap.add_argument("--save", action="store_true", help="also write reports/doctor-<date>.txt")
    args = ap.parse_args()

    rows = []

    def check(name, ok, detail, fix):
        rows.append((name, ok, detail, fix))
        line("PASS" if ok else "FAIL", name + ("  ->  " + detail if detail else ""))
        if not ok and fix:
            print("      fix: " + fix)

    adb_path = find_adb()
    check("adb is installed", bool(adb_path), adb_path or "", FALLBACK)
    if not adb_path:
        finish(rows, args)
        return 1

    found, msg = devices(adb_path)
    check("phone is connected", bool(found), ", ".join(found) or msg,
          "Enable Settings -> Developer options -> USB debugging, then tap 'Allow' on the phone popup")
    if not found:
        finish(rows, args)
        return 1

    serial = pick_serial(args.serial, adb_path)

    code, out, _ = adb(["shell", "getprop", "ro.build.version.sdk"], serial=serial)
    sdk = out.strip()
    check("Android API level", sdk.isdigit() and int(sdk) >= 26, "sdk=" + sdk,
          "This app needs Android 8.0 or newer")

    code, out, _ = adb(["shell", "getprop", "ro.product.model"], serial=serial)
    print("      device model: " + out.strip())

    code, out, _ = adb(["shell", "pm", "list", "packages"], serial=serial)
    pkgs = [l.split(":", 1)[1].strip() for l in out.splitlines() if l.startswith("package:")]
    invo_like = [p for p in pkgs if "invo" in p.lower()]
    check("INVO is installed", bool(invo_like), ", ".join(invo_like) or "no package contains 'invo'",
          "Install INVO from the Play Store, or set invo_package in config/invo_config.json to the real id")

    code, out, _ = adb(["shell", "pm", "list", "packages", APP_ID], serial=serial)
    check("INVO Copier P1 is installed", APP_ID in out, out.strip() or "not installed",
          "Build then Run it from Android Studio (STEP 3 of docs/PHASE_1.md)")

    code, out, _ = adb(["shell", "settings", "get", "secure", "enabled_notification_listeners"], serial=serial)
    granted = APP_ID in out
    check("notification access granted", granted, "OK" if granted else out.strip(),
          "adb shell cmd notification allow_listener " + LISTENER)

    code, out, _ = adb(["shell", "ls", LOG_DIR_POSIX], serial=serial)
    has_logs = code == 0 and "No such file" not in out
    check("log folder exists", has_logs, out.strip().replace("\n", " "),
          "Open the app once (it creates the folder)")

    code, out, _ = adb(["shell", "dumpsys", "notification"], serial=serial)
    channels = [l.strip() for l in out.splitlines() if "involio" in l.lower() or "com.invo" in l.lower()]
    print("      dumpsys notification lines mentioning invo: %d" % len(channels))
    if channels:
        for c in channels[:12]:
            print("        " + c[:150])

    finish(rows, args)
    bad = [r for r in rows if not r[1]]
    print("")
    if bad:
        print("RESULT: %d check(s) failed. Fix them before testing." % len(bad))
        return 1
    print("RESULT: all checks passed. Go to docs/PHASE_1.md step 5 (the live test).")
    return 0


def finish(rows, args):
    if not args.save:
        return
    import os
    path = os.path.join("reports", "doctor-%s.txt" % datetime.date.today().isoformat())
    os.makedirs("reports", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for name, ok, detail, fix in rows:
            f.write("%s | %s | %s | %s\n" % ("PASS" if ok else "FAIL", name, detail, fix))
    print("saved " + path)


if __name__ == "__main__":
    sys.exit(main())
