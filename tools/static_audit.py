#!/usr/bin/env python3
"""Cheap static audit for this Android module: string/comment aware brace and paren
balance, R.id references against the layout, manifest classes, and a few Kotlin
API traps we have already been bitten by. There is no compiler in this sandbox, so
this is a smoke test, not a build."""
import glob
import os
import re
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SRC = os.path.join(ROOT, "android", "app", "src", "main")
ANDROID_NS = "{http://schemas.android.com/apk/res/android}"


def strip_code(text: str) -> str:
    out = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c == '"':
            if text[i:i + 3] == '"""':
                j = text.find('"""', i + 3)
                i = n if j < 0 else j + 3
                continue
            i += 1
            while i < n:
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == '"':
                    i += 1
                    break
                i += 1
            continue
        if c == "'":
            i += 1
            while i < n:
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == "'":
                    i += 1
                    break
                i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


problems = []
kt_files = sorted(glob.glob(os.path.join(SRC, "java", "**", "*.kt"), recursive=True))
if not kt_files:
    problems.append("no kotlin sources found")

for path in kt_files:
    rel = os.path.relpath(path, ROOT).replace("\\", "/")
    body = strip_code(open(path, encoding="utf-8").read())
    for a, b in (("{", "}"), ("(", ")"), ("[", "]")):
        if body.count(a) != body.count(b):
            problems.append("%s: %s=%d %s=%d" % (rel, a, body.count(a), b, body.count(b)))
    raw = open(path, encoding="utf-8").read()
    for bad, why in (
        ("Notification.Action", "Notification.Action.intent is not public API"),
        ("getLegacyWindow", "no such API"),
        ("contentIntent.activity", "PendingIntent cannot be unwrapped"),
    ):
        if bad in raw:
            problems.append("%s: uses %s (%s)" % (rel, bad, why))
    for bad, why in (
        ("runBlocking {", "blocking the main thread in a service callback"),
        ("Thread.sleep(", "only legal inside a worker thread"),
    ):
        if bad in body and "worker" not in raw and "Thread {" not in raw:
            problems.append("%s: %s (%s)" % (rel, bad, why))

layout_path = os.path.join(SRC, "res", "layout", "activity_main.xml")
layout_ids = set()
if os.path.exists(layout_path):
    for node in ET.parse(layout_path).getroot().iter():
        v = node.get(ANDROID_NS + "id", "")
        if v.startswith("@+id/"):
            layout_ids.add(v[5:])
else:
    problems.append("layout missing")

for path in kt_files:
    rel = os.path.relpath(path, ROOT).replace("\\", "/")
    raw = open(path, encoding="utf-8").read()
    for rid in set(re.findall(r"\bR\.id\.([A-Za-z0-9_]+)", raw)):
        if rid not in layout_ids:
            problems.append("%s: R.id.%s is not in activity_main.xml" % (rel, rid))

manifest = os.path.join(SRC, "AndroidManifest.xml")
if os.path.exists(manifest):
    mtxt = open(manifest, encoding="utf-8").read()
    for node in ET.parse(manifest).getroot().iter("receiver"):
        name = node.get(ANDROID_NS + "name", "")
        if "$" in name:
            outer = name.split("$")[0]
        else:
            outer = name
        tail = outer.split(".")[-1]
        hits = [k for k in kt_files if os.path.basename(k) == tail + ".kt"]
        if not hits:
            problems.append("manifest receiver %s has no matching .kt file" % name)
        if "exported" not in ET.tostring(node, encoding="unicode"):
            problems.append("receiver %s missing android:exported" % name)
    if "<queries" not in mtxt:
        problems.append("manifest has no <queries> block, so the INVO package cannot be seen")
else:
    problems.append("manifest missing")

print("checked %d kotlin files, %d layout ids" % (len(kt_files), len(layout_ids)))
if problems:
    print("STATIC: PROBLEM")
    for p in problems:
        print("  -", p)
    sys.exit(1)
print("STATIC: OK")
