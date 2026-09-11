"""Shared ADB helpers for the INVO Copier Phase-1 tools.

Stdlib only. No installs, no pip, no network.
"""

import os
import shutil
import subprocess
import sys

APP_ID = "com.invocopier"
LISTENER = "com.invocopier/com.invocopier.notification.InvoNotificationListener"
LOG_DIR_POSIX = "/sdcard/Android/data/com.invocopier/files/logs"


def find_adb():
    """Locate the adb binary: PATH first, then the usual Android SDK spots."""
    env = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
    candidates = []
    if env:
        candidates.append(os.path.join(env, "platform-tools", "adb.exe"))
        candidates.append(os.path.join(env, "platform-tools", "adb"))
    home = os.path.expanduser("~")
    candidates += [
        os.path.join(home, "Library", "Android", "sdk", "platform-tools", "adb"),
        os.path.join(home, "Android", "Sdk", "platform-tools", "adb.exe"),
        os.path.join(home, "Android", "Sdk", "platform-tools", "adb"),
        r"C:\Users\%USERNAME%\AppData\Local\Android\Sdk\platform-tools\adb.exe",
    ]
    found = shutil.which("adb")
    if found:
        return found
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def run(args, timeout=60, binary=False):
    """Run a command, return (returncode, stdout, stderr)."""
    try:
        p = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except FileNotFoundError:
        return 127, b"" if binary else "", "command not found: %s" % (args[0],)
    except subprocess.TimeoutExpired:
        return 124, b"" if binary else "", "timeout after %ss" % timeout
    out = p.stdout if binary else p.stdout.decode("utf-8", "replace")
    err = p.stderr if binary else p.stderr.decode("utf-8", "replace")
    return p.returncode, out, err


def adb(args, adb_path=None, serial=None, timeout=60, binary=False):
    adb_path = adb_path or find_adb()
    if not adb_path:
        return 127, b"" if binary else "", "adb not found on this computer"
    cmd = [adb_path]
    if serial:
        cmd += ["-s", serial]
    cmd += list(args)
    return run(cmd, timeout=timeout, binary=binary)


def devices(adb_path=None):
    code, out, err = adb(["devices"], adb_path)
    if code != 0:
        return [], err.strip() or out.strip()
    serials = []
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            serials.append(parts[0])
    return serials, ""


def pick_serial(serial=None, adb_path=None):
    if serial:
        return serial
    found, msg = devices(adb_path)
    if not found:
        print("No device with USB debugging authorised is connected.")
        if msg:
            print("adb said: " + msg)
        print("Fix: plug the phone in, unlock it, and tap 'Allow' on the "
              "'Allow USB debugging?' popup.")
        sys.exit(2)
    if len(found) > 1:
        print("Multiple devices: " + ", ".join(found))
        print("Re-run with  --serial <one of those>")
        sys.exit(2)
    return found[0]


def ensure_dir(path):
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    return path
