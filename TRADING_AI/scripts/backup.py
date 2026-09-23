#!/usr/bin/env python3
"""
BACKUP: database + config + models, with checksums and rotation (spec 24).

Never touches data/raw -- raw downloads are immutable and already checksummed
in the raw_files table. Nothing is deleted except backups older than --keep.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import load_settings
from app.db.database import Database, atomic_write_text, sha256_file


def archive(src: Path, dest: Path, keep: int) -> dict | None:
    """tar.gz a directory, checksum it, rotate older archives of same prefix."""
    if not src.exists() or not any(src.rglob("*")):
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(dest, "w:gz") as tf:
        tf.add(src, arcname=src.name)
    digest = sha256_file(dest)
    dest.with_suffix(dest.suffix + ".sha256").write_text(
        f"{digest}  {dest.name}\n", encoding="utf-8")

    prefix = dest.name.split("_2")[0]
    olds = sorted(dest.parent.glob(f"{prefix}_*.tar.gz"),
                  key=lambda p: p.stat().st_mtime, reverse=True)
    for o in olds[keep:]:
        o.unlink(missing_ok=True)
        o.with_suffix(o.suffix + ".sha256").unlink(missing_ok=True)
    return {"file": dest.name, "sha256": digest,
            "mb": round(dest.stat().st_size / 1024**2, 2)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None)
    ap.add_argument("--keep", type=int, default=10)
    a = ap.parse_args()

    st = load_settings(a.root)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = st.backups_dir
    out.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print(f"TRADING_AI BACKUP   {stamp}")
    print(f"Destination: {out}")
    print("=" * 70)

    manifest: dict = {"created": stamp, "items": []}

    # 1. database (consistent online backup)
    if st.db_path.exists():
        db = Database(st.db_path)
        ok, detail = db.integrity_check()
        print(f"Integrity check: {'OK' if ok else 'FAILED'} - {detail}")
        if not ok:
            print("\nDatabase is corrupt. Backing it up anyway so the damaged")
            print("copy is preserved for recovery, but DO NOT overwrite a")
            print("known-good backup with it.")
        target = db.backup(out, keep=a.keep)
        item = {"kind": "database", "file": target.name,
                "sha256": sha256_file(target),
                "mb": round(target.stat().st_size / 1024**2, 2),
                "integrity_ok": ok}
        manifest["items"].append(item)
        print(f"  database -> {item['file']} ({item['mb']} MB)")
    else:
        print("No database found - skipping.")

    # 2. configuration (excluding secrets)
    cfg = st.root / "config"
    if cfg.exists():
        tmp = out / f"_cfg_{stamp}"
        tmp.mkdir(parents=True, exist_ok=True)
        for f in cfg.glob("*.yaml"):
            (tmp / f.name).write_bytes(f.read_bytes())
        res = archive(tmp, out / f"config_{stamp}.tar.gz", a.keep)
        for f in tmp.iterdir():
            f.unlink()
        tmp.rmdir()
        if res:
            res["kind"] = "config"
            manifest["items"].append(res)
            print(f"  config   -> {res['file']} ({res['mb']} MB)  "
                  f"[.env excluded: secrets are never archived]")

    # 3. models (versioned)
    res = archive(st.models_dir, out / f"models_{stamp}.tar.gz", a.keep)
    if res:
        res["kind"] = "models"
        manifest["items"].append(res)
        print(f"  models   -> {res['file']} ({res['mb']} MB)")

    # 4. reports + backtests
    for d, name in ((st.reports_dir, "reports"),
                    (st.root / "backtests", "backtests")):
        res = archive(d, out / f"{name}_{stamp}.tar.gz", a.keep)
        if res:
            res["kind"] = name
            manifest["items"].append(res)
            print(f"  {name:<8} -> {res['file']} ({res['mb']} MB)")

    atomic_write_text(out / f"manifest_{stamp}.json",
                      json.dumps(manifest, indent=2))

    # verify everything on disk
    if st.db_path.exists():
        print("\nVerifying existing backups:")
        for b in Database(st.db_path).verify_backups(out):
            mark = {True: "OK", False: "CHECKSUM MISMATCH", None: "no checksum"}[b["ok"]]
            print(f"  {b['file']:<42} {b['size_mb']:>8} MB  {mark}")

    total = sum(f.stat().st_size for f in out.glob("*") if f.is_file())
    print(f"\nBackup folder total: {total / 1024**2:.1f} MB  (keep={a.keep})")
    print("Raw data untouched - it is immutable by design.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
