#!/usr/bin/env python3
"""Create a provenance-only ingest manifest for verified RAG_ALLOWLIST sources.

This tool never extracts text, calls a model, creates embeddings, or accesses the
network. It re-hashes every selected original and refuses sources that are not
explicitly approved in both the acquisition ledger and RAG allowlist.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

CHUNK = 8 * 1024 * 1024
SHA256_LENGTH = 64
LEDGER_HEADERS = {
    "resource_id", "title", "publisher", "publication_or_version", "local_path", "local_sha256", "rag_state",
}
ALLOWLIST_HEADERS = {
    "allowlist_id", "resource_id", "source_file_path", "source_sha256", "rights_basis",
    "ai_ingestion_evidence_url_or_file", "approved_by", "approval_utc", "extraction_method", "revoked_utc",
}


def read_rows(path: Path) -> tuple[set[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        headings = set(reader.fieldnames or [])
        records = [{key: (value or "").strip() for key, value in row.items()} for row in reader]
    return headings, records


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        while data := stream.read(CHUNK):
            result.update(data)
    return result.hexdigest()


def safe_relative(value: str) -> Path:
    path = Path(value)
    if not value or path.is_absolute() or "\\" in value or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError(f"unsafe root-relative source path: {value!r}")
    return path


def contained(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root)
        return True
    except ValueError:
        return False


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", type=Path)
    parser.add_argument("allowlist", type=Path)
    parser.add_argument("--root", required=True, type=Path, help="CIVLIB root containing canonical source files")
    parser.add_argument("--output", required=True, type=Path, help="JSON manifest to write atomically")
    parser.add_argument("--index-id", required=True, help="planned index/build identifier")
    args = parser.parse_args()

    root = args.root.expanduser().resolve()
    if not root.is_dir():
        print(f"ERROR: --root is not an existing directory: {root}", file=sys.stderr)
        return 2
    try:
        ledger_headings, raw_ledger_rows = read_rows(args.ledger.expanduser())
        allowlist_headings, raw_allow_rows = read_rows(args.allowlist.expanduser())
    except (OSError, csv.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    missing_ledger = LEDGER_HEADERS - ledger_headings
    missing_allowlist = ALLOWLIST_HEADERS - allowlist_headings
    if missing_ledger or missing_allowlist:
        if missing_ledger:
            print("ERROR: ledger missing headings: " + ", ".join(sorted(missing_ledger)), file=sys.stderr)
        if missing_allowlist:
            print("ERROR: allowlist missing headings: " + ", ".join(sorted(missing_allowlist)), file=sys.stderr)
        return 2
    ledger_rows = [r for r in raw_ledger_rows if r.get("resource_id") != "EXAMPLE-DO-NOT-KEEP"]
    allow_rows = [r for r in raw_allow_rows if r.get("allowlist_id") != "EXAMPLE-DO-NOT-KEEP"]

    ledger_by_id = {row.get("resource_id", ""): row for row in ledger_rows}
    seen_ids: set[str] = set()
    output_sources: list[dict[str, str]] = []
    errors: list[str] = []
    for row in allow_rows:
        if row.get("revoked_utc"):
            continue
        source_id = row.get("resource_id", "")
        if source_id in seen_ids:
            errors.append(f"duplicate allowlisted resource ID: {source_id}")
            continue
        seen_ids.add(source_id)
        ledger = ledger_by_id.get(source_id)
        if not ledger:
            errors.append(f"{source_id}: no ledger row")
            continue
        if ledger.get("rag_state") != "RAG_ALLOWLIST":
            errors.append(f"{source_id}: ledger state is not RAG_ALLOWLIST")
            continue
        expected = ledger.get("local_sha256", "")
        if (
            len(expected) != SHA256_LENGTH
            or any(character not in "0123456789abcdef" for character in expected)
            or expected != row.get("source_sha256", "")
        ):
            errors.append(f"{source_id}: allowlist/ledger SHA-256 mismatch")
            continue
        if row.get("source_file_path") != ledger.get("local_path"):
            errors.append(f"{source_id}: allowlist path does not match ledger canonical path")
            continue
        required = ("rights_basis", "ai_ingestion_evidence_url_or_file", "approved_by", "approval_utc", "extraction_method")
        missing = [field for field in required if not row.get(field)]
        if missing:
            errors.append(f"{source_id}: missing allowlist evidence: {', '.join(missing)}")
            continue
        try:
            relative = safe_relative(ledger["local_path"])
        except ValueError as exc:
            errors.append(f"{source_id}: {exc}")
            continue
        raw_path = root / relative
        if raw_path.is_symlink() or not raw_path.is_file() or not contained(root, raw_path):
            errors.append(f"{source_id}: canonical source missing, symlinked, or outside root")
            continue
        try:
            actual = digest(raw_path)
        except OSError as exc:
            errors.append(f"{source_id}: cannot hash source: {exc}")
            continue
        if actual != expected:
            errors.append(f"{source_id}: current source SHA-256 differs from approved ledger hash")
            continue
        output_sources.append(
            {
                "resource_id": source_id,
                "title": ledger.get("title", ""),
                "publisher": ledger.get("publisher", ""),
                "publication_or_version": ledger.get("publication_or_version", ""),
                "canonical_root_relative_path": relative.as_posix(),
                "source_sha256": expected,
                "rights_basis": row["rights_basis"],
                "ai_ingestion_evidence_url_or_file": row["ai_ingestion_evidence_url_or_file"],
                "approved_by": row["approved_by"],
                "approval_utc": row["approval_utc"],
                "extraction_method": row["extraction_method"],
                "ocr_permitted": row.get("ocr_permitted", ""),
                "chunking_profile": row.get("chunking_profile", ""),
                "embedding_model": row.get("embedding_model", ""),
                "embedding_model_version": row.get("embedding_model_version", ""),
            }
        )

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print("Refusing to write an incomplete RAG ingest manifest.", file=sys.stderr)
        return 1

    payload = {
        "schema": "offline-recovery-library-rag-ingest-manifest-v1",
        "generated_utc": utc_now(),
        "index_id": args.index_id,
        "library_root_note": "Paths are root-relative; do not move/modify canonical sources after approval.",
        "source_count": len(output_sources),
        "sources": sorted(output_sources, key=lambda item: item["resource_id"]),
    }
    destination = args.output.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    print(f"WROTE {destination} with {len(output_sources)} approved source(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
