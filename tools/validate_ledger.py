#!/usr/bin/env python3
"""Validate offline-library ledger and RAG allowlist safety invariants."""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

SHA256 = re.compile(r"^[0-9a-f]{64}$")
VALID_STATES = {"REFERENCE_ONLY", "LOCAL_FTS_OK", "RAG_ALLOWLIST"}
LEDGER_HEADERS = {
    "resource_id", "title", "publisher", "official_landing_url", "local_sha256", "local_path",
    "rights_evidence_url", "ai_ingestion_evidence", "rag_state", "rag_approved_by", "rag_approved_utc",
}
ALLOWLIST_HEADERS = {
    "allowlist_id", "resource_id", "source_file_path", "source_sha256", "rights_basis",
    "ai_ingestion_evidence_url_or_file", "approved_by", "approval_utc", "extraction_method", "revoked_utc",
}


def rows(path: Path) -> tuple[set[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        headings = set(reader.fieldnames or [])
        records = [{key: (value or "").strip() for key, value in row.items()} for row in reader]
    return headings, records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", type=Path)
    parser.add_argument("--allowlist", type=Path, help="optional RAG allowlist CSV")
    args = parser.parse_args()
    try:
        ledger_headings, ledger_rows = rows(args.ledger)
        if args.allowlist:
            allowlist_headings, allowlist_rows = rows(args.allowlist)
        else:
            allowlist_headings, allowlist_rows = set(), []
    except (OSError, csv.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    missing_ledger = LEDGER_HEADERS - ledger_headings
    if missing_ledger:
        print("ERROR: ledger missing headings: " + ", ".join(sorted(missing_ledger)), file=sys.stderr)
        return 2
    if args.allowlist:
        missing_allowlist = ALLOWLIST_HEADERS - allowlist_headings
        if missing_allowlist:
            print("ERROR: allowlist missing headings: " + ", ".join(sorted(missing_allowlist)), file=sys.stderr)
            return 2
    ledger = [row for row in ledger_rows if row.get("resource_id") != "EXAMPLE-DO-NOT-KEEP"]
    allowlist = [row for row in allowlist_rows if row.get("allowlist_id") != "EXAMPLE-DO-NOT-KEEP"]

    failures: list[str] = []
    ids: set[str] = set()
    by_id: dict[str, dict[str, str]] = {}
    for number, row in enumerate(ledger, start=2):
        identifier = row.get("resource_id", "")
        if not identifier:
            failures.append(f"ledger line {number}: missing resource_id")
        elif identifier in ids:
            failures.append(f"ledger line {number}: duplicate resource_id {identifier}")
        ids.add(identifier)
        by_id[identifier] = row
        state = row.get("rag_state", "")
        if state not in VALID_STATES:
            failures.append(f"ledger {identifier}: bad rag_state {state!r}")
        if state == "RAG_ALLOWLIST":
            for field in ("ai_ingestion_evidence", "rag_approved_by", "rag_approved_utc", "rights_evidence_url"):
                if not row.get(field):
                    failures.append(f"ledger {identifier}: RAG_ALLOWLIST missing {field}")
        digest = row.get("local_sha256", "")
        if not SHA256.fullmatch(digest):
            failures.append(f"ledger {identifier}: local_sha256 must be 64 lowercase hex characters")
        if state in {"LOCAL_FTS_OK", "RAG_ALLOWLIST"} and not row.get("rights_evidence_url"):
            failures.append(f"ledger {identifier}: {state} requires rights_evidence_url")

    allowlisted_ids: set[str] = set()
    allowlist_ids: set[str] = set()
    for number, row in enumerate(allowlist, start=2):
        allowlist_id = row.get("allowlist_id", "")
        if not allowlist_id:
            failures.append(f"allowlist line {number}: missing allowlist_id")
        elif allowlist_id in allowlist_ids:
            failures.append(f"allowlist line {number}: duplicate allowlist_id {allowlist_id}")
        allowlist_ids.add(allowlist_id)
        identifier = row.get("resource_id", "")
        source = by_id.get(identifier)
        if source is None:
            failures.append(f"allowlist line {number}: unknown resource_id {identifier!r}")
            continue
        if row.get("revoked_utc"):
            if source.get("rag_state") == "RAG_ALLOWLIST":
                failures.append(f"allowlist line {number}: revoked item {identifier} is still RAG_ALLOWLIST in ledger")
            continue
        allowlisted_ids.add(identifier)
        if source.get("rag_state") != "RAG_ALLOWLIST":
            failures.append(f"allowlist line {number}: {identifier} is not RAG_ALLOWLIST in ledger")
        if row.get("source_file_path") != source.get("local_path"):
            failures.append(f"allowlist line {number}: source_file_path does not match ledger local_path for {identifier}")
        source_digest = row.get("source_sha256", "")
        if not SHA256.fullmatch(source_digest):
            failures.append(f"allowlist line {number}: source_sha256 must be 64 lowercase hex characters")
        if source_digest != source.get("local_sha256"):
            failures.append(f"allowlist line {number}: source SHA-256 does not match ledger for {identifier}")
        for field in ("rights_basis", "ai_ingestion_evidence_url_or_file", "approved_by", "approval_utc", "extraction_method"):
            if not row.get(field):
                failures.append(f"allowlist line {number}: missing {field}")
    for identifier, row in by_id.items():
        if row.get("rag_state") == "RAG_ALLOWLIST" and identifier not in allowlisted_ids:
            failures.append(f"ledger {identifier}: RAG_ALLOWLIST item has no allowlist row")

    if failures:
        for failure in failures:
            print("FAIL", failure)
        print(f"FAILED: {len(failures)} ledger/allowlist issue(s).")
        return 1
    print(f"VALID: {len(ledger)} ledger item(s), {len(allowlist)} allowlist item(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
