#!/usr/bin/env python3
"""Append a checked local-file acquisition record to an offline library ledger.

It records only supplied metadata and a locally calculated SHA-256; it never
fetches a URL. Rights classification defaults to REFERENCE_ONLY on purpose.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

CHUNK = 8 * 1024 * 1024
VALID_STATES = {"REFERENCE_ONLY", "LOCAL_FTS_OK", "RAG_ALLOWLIST"}
REQUIRED_HEADERS = [
    "resource_id", "title", "publisher", "collection", "official_landing_url", "resolved_direct_url",
    "retrieved_utc", "publication_or_version", "format", "bytes", "publisher_sha256_or_signature",
    "local_sha256", "local_path", "rights_class", "rights_claim", "rights_evidence_url",
    "ai_ingestion_evidence", "rag_state", "rag_approved_by", "rag_approved_utc", "attribution_required",
    "derivative_or_sharealike_obligations", "offline_opener", "update_frequency", "last_checked_utc",
    "next_review_utc", "priority", "tier", "notes",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            data = stream.read(CHUNK)
            if not data:
                return digest.hexdigest()
            digest.update(data)


def load_ids(ledger: Path) -> set[str]:
    if not ledger.exists():
        return set()
    with ledger.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if set(REQUIRED_HEADERS) - set(reader.fieldnames or []):
            raise ValueError("ledger has unexpected/missing headings; start from acquisition-ledger.csv template")
        return {row.get("resource_id", "").strip() for row in reader}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", type=Path)
    parser.add_argument("file", type=Path, help="local acquired file")
    parser.add_argument("--root", type=Path, required=True, help="library root; used to record a relative local path")
    parser.add_argument("--id", required=True, dest="resource_id")
    parser.add_argument("--title", required=True)
    parser.add_argument("--publisher", required=True)
    parser.add_argument("--landing-url", required=True)
    parser.add_argument("--direct-url", default="")
    parser.add_argument("--version", default="not recorded")
    parser.add_argument("--format", default="unknown")
    parser.add_argument("--rights-class", default="UNKNOWN_REVIEW")
    parser.add_argument("--rights-claim", default="Pending document-level rights review")
    parser.add_argument("--rights-evidence-url", default="")
    parser.add_argument("--ai-ingestion-evidence", default="")
    parser.add_argument("--rag-state", choices=sorted(VALID_STATES), default="REFERENCE_ONLY")
    parser.add_argument("--rag-approved-by", default="")
    parser.add_argument("--rag-approved-utc", default="")
    parser.add_argument("--attribution-required", default="Unknown")
    parser.add_argument("--derivative-obligations", default="Review before derivative use")
    parser.add_argument("--offline-opener", default="Record tested opener")
    parser.add_argument("--update-frequency", default="Review annually")
    parser.add_argument("--next-review-utc", required=True)
    parser.add_argument("--priority", choices=("P0", "P1", "P2", "P3"), required=True)
    parser.add_argument("--tier", choices=("T1", "T2", "T3"), required=True)
    parser.add_argument("--collection", default="")
    parser.add_argument("--publisher-hash-or-signature", default="")
    parser.add_argument("--notes", default="")
    args = parser.parse_args()

    raw_file = args.file.expanduser()
    local_file = raw_file.resolve()
    root = args.root.expanduser().resolve()
    ledger = args.ledger.expanduser().resolve()
    if raw_file.is_symlink() or not raw_file.is_file():
        print(f"ERROR: file must be a regular non-symlink local file: {raw_file}", file=sys.stderr)
        return 2
    try:
        relative = local_file.relative_to(root).as_posix()
    except ValueError:
        print("ERROR: --file must be below --root so the ledger has a portable relative path.", file=sys.stderr)
        return 2
    if args.rag_state in {"LOCAL_FTS_OK", "RAG_ALLOWLIST"} and not args.rights_evidence_url:
        print(f"ERROR: {args.rag_state} requires --rights-evidence-url.", file=sys.stderr)
        return 2
    if args.rag_state == "RAG_ALLOWLIST" and not (
        args.ai_ingestion_evidence and args.rag_approved_by and args.rag_approved_utc
    ):
        print(
            "ERROR: RAG_ALLOWLIST requires AI-ingestion evidence, approver, and approval UTC.",
            file=sys.stderr,
        )
        return 2
    try:
        existing_ids = load_ids(ledger)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.resource_id in existing_ids:
        print(f"ERROR: duplicate resource ID: {args.resource_id}", file=sys.stderr)
        return 2

    ledger.parent.mkdir(parents=True, exist_ok=True)
    write_header = not ledger.exists() or ledger.stat().st_size == 0
    now = utc_now()
    row = {
        "resource_id": args.resource_id, "title": args.title, "publisher": args.publisher,
        "collection": args.collection, "official_landing_url": args.landing_url, "resolved_direct_url": args.direct_url,
        "retrieved_utc": now, "publication_or_version": args.version, "format": args.format,
        "bytes": str(local_file.stat().st_size), "publisher_sha256_or_signature": args.publisher_hash_or_signature,
        "local_sha256": sha256(local_file), "local_path": relative, "rights_class": args.rights_class,
        "rights_claim": args.rights_claim, "rights_evidence_url": args.rights_evidence_url,
        "ai_ingestion_evidence": args.ai_ingestion_evidence, "rag_state": args.rag_state,
        "rag_approved_by": args.rag_approved_by, "rag_approved_utc": args.rag_approved_utc,
        "attribution_required": args.attribution_required,
        "derivative_or_sharealike_obligations": args.derivative_obligations,
        "offline_opener": args.offline_opener, "update_frequency": args.update_frequency,
        "last_checked_utc": now, "next_review_utc": args.next_review_utc,
        "priority": args.priority, "tier": args.tier, "notes": args.notes,
    }
    with ledger.open("a", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=REQUIRED_HEADERS)
        if write_header:
            writer.writeheader()
        writer.writerow(row)
    print(f"Recorded {args.resource_id}; SHA-256 {row['local_sha256']}; state {args.rag_state}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
