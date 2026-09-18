#!/usr/bin/env python3
"""Create and verify deterministic SHA-256 manifests using Python's standard library.

Manifest format:
    # offline-library-sha256-manifest-v1
    relative/path<TAB>byte_count<TAB>sha256_hex

The utility never follows symlinks. It rejects file names containing tabs or
newlines because they cannot be represented safely in this simple TSV format.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

HEADER = "# offline-library-sha256-manifest-v1"
CHUNK_SIZE = 8 * 1024 * 1024


@dataclass(frozen=True)
class Entry:
    relative: str
    size: int
    digest: str


def normalized_path(path: Path) -> str:
    return path.as_posix()


def validate_relative(value: str) -> None:
    if not value or value.startswith("/") or "\\" in value:
        raise ValueError(f"invalid manifest path: {value!r}")
    if "\t" in value or "\n" in value or "\r" in value:
        raise ValueError(f"unsupported tab/newline in path: {value!r}")
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError(f"unsafe manifest path: {value!r}")


def under_root(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def ignored(relative: str, patterns: list[str]) -> bool:
    # Match both the complete relative name and individual path components.
    return any(fnmatch.fnmatchcase(relative, pattern) for pattern in patterns)


def walk_files(root: Path, patterns: list[str], manifest: Path | None) -> Iterator[Path]:
    manifest_resolved = manifest.resolve() if manifest else None
    for current, dirs, names in os.walk(root, followlinks=False):
        current_path = Path(current)
        # Do not descend into symlinked directories.
        dirs[:] = sorted(
            d for d in dirs if not (current_path / d).is_symlink()
        )
        for name in sorted(names):
            file_path = current_path / name
            if file_path.is_symlink() or not file_path.is_file():
                continue
            if manifest_resolved and file_path.resolve() == manifest_resolved:
                continue
            relative = normalized_path(file_path.relative_to(root))
            validate_relative(relative)
            if ignored(relative, patterns):
                continue
            yield file_path


def hash_file(path: Path) -> tuple[int, str]:
    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            block = stream.read(CHUNK_SIZE)
            if not block:
                break
            digest.update(block)
    after = path.stat()
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise RuntimeError(f"file changed while hashing: {path}")
    return before.st_size, digest.hexdigest()


def create(root: Path, manifest: Path, patterns: list[str]) -> int:
    root = root.resolve()
    manifest = manifest.resolve()
    manifest.parent.mkdir(parents=True, exist_ok=True)
    entries: list[Entry] = []
    errors: list[str] = []
    for file_path in walk_files(root, patterns, manifest):
        relative = normalized_path(file_path.relative_to(root))
        try:
            size, digest = hash_file(file_path)
            entries.append(Entry(relative, size, digest))
            print(f"HASH {relative}")
        except (OSError, RuntimeError) as exc:
            errors.append(str(exc))
            print(f"ERROR {exc}", file=sys.stderr)
    if errors:
        print(f"Manifest not written: {len(errors)} file(s) could not be hashed.", file=sys.stderr)
        return 2

    entries.sort(key=lambda entry: entry.relative.encode("utf-8"))
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{manifest.name}.", suffix=".tmp", dir=manifest.parent, text=True
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as output:
            output.write(HEADER + "\n")
            output.write("# path\tbytes\tsha256\n")
            for entry in entries:
                output.write(f"{entry.relative}\t{entry.size}\t{entry.digest}\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_name, manifest)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise
    print(f"WROTE {manifest} ({len(entries)} files)")
    return 0


def read_manifest(manifest: Path) -> dict[str, Entry]:
    result: dict[str, Entry] = {}
    with manifest.open("r", encoding="utf-8", newline="") as stream:
        first = stream.readline().rstrip("\n\r")
        if first != HEADER:
            raise ValueError(f"unsupported manifest header in {manifest}")
        for line_number, raw in enumerate(stream, start=2):
            line = raw.rstrip("\n\r")
            if not line or line.startswith("#"):
                continue
            fields = line.split("\t")
            if len(fields) != 3:
                raise ValueError(f"line {line_number}: expected 3 tab-separated fields")
            relative, size_text, digest = fields
            validate_relative(relative)
            if relative in result:
                raise ValueError(f"line {line_number}: duplicate path {relative!r}")
            if not size_text.isdigit():
                raise ValueError(f"line {line_number}: invalid byte count")
            if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
                raise ValueError(f"line {line_number}: invalid lowercase SHA-256")
            result[relative] = Entry(relative, int(size_text), digest)
    return result


def verify(root: Path, manifest: Path, patterns: list[str], check_unexpected: bool) -> int:
    root = root.resolve()
    manifest = manifest.resolve()
    try:
        entries = read_manifest(manifest)
    except (OSError, ValueError) as exc:
        print(f"ERROR: cannot read manifest: {exc}", file=sys.stderr)
        return 2

    failures = 0
    for relative, entry in sorted(entries.items()):
        raw_path = root / relative
        path = raw_path.resolve()
        if not under_root(root, path):
            print(f"INVALID {relative}: escapes root", file=sys.stderr)
            failures += 1
            continue
        if raw_path.is_symlink() or not raw_path.is_file():
            print(f"MISSING {relative}")
            failures += 1
            continue
        try:
            actual_size, actual_digest = hash_file(raw_path)
        except (OSError, RuntimeError) as exc:
            print(f"ERROR {relative}: {exc}", file=sys.stderr)
            failures += 1
            continue
        if actual_size != entry.size or actual_digest != entry.digest:
            print(f"CHANGED {relative}")
            failures += 1
        else:
            print(f"OK {relative}")

    if check_unexpected:
        for file_path in walk_files(root, patterns, manifest):
            relative = normalized_path(file_path.relative_to(root))
            if relative not in entries:
                print(f"UNEXPECTED {relative}")
                failures += 1

    expected = len(entries)
    if failures:
        print(f"FAILED: {failures} problem(s), {expected} manifest entry/entries checked.")
        return 1
    print(f"VERIFIED: {expected} manifest entry/entries checked; no discrepancies.")
    return 0


def path_argument(value: str) -> Path:
    return Path(value).expanduser()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("create", "verify"):
        sub = subparsers.add_parser(command)
        sub.add_argument("root", type=path_argument, help="directory tree to hash")
        sub.add_argument("--manifest", required=True, type=path_argument)
        sub.add_argument(
            "--exclude",
            action="append",
            default=[],
            metavar="GLOB",
            help="root-relative glob to omit; repeatable",
        )
    subparsers.choices["verify"].add_argument(
        "--check-unexpected",
        action="store_true",
        help="also fail when non-excluded files exist outside the manifest",
    )
    args = parser.parse_args()

    root = args.root.resolve()
    if not root.is_dir():
        print(f"ERROR: root is not a directory: {root}", file=sys.stderr)
        return 2
    if args.command == "create":
        return create(root, args.manifest, args.exclude)
    return verify(root, args.manifest, args.exclude, args.check_unexpected)


if __name__ == "__main__":
    raise SystemExit(main())
