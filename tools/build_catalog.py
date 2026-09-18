#!/usr/bin/env python3
"""Build a portable HTML/CSV catalog from an offline recovery acquisition ledger.

No network access or document-content extraction occurs. The catalog displays
metadata already entered in the ledger. It deliberately does not provide a way
to search or expose REFERENCE_ONLY document text.
"""
from __future__ import annotations

import argparse
import csv
import html
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REQUIRED = {
    "resource_id", "title", "publisher", "official_landing_url", "resolved_direct_url",
    "retrieved_utc", "publication_or_version", "format", "bytes", "local_sha256",
    "local_path", "rights_class", "rights_claim", "rights_evidence_url",
    "ai_ingestion_evidence", "rag_state", "offline_opener", "update_frequency",
    "next_review_utc", "priority", "tier", "notes",
}
VALID_STATES = {"REFERENCE_ONLY", "LOCAL_FTS_OK", "RAG_ALLOWLIST"}


def human_bytes(value: str) -> str:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return "not recorded"
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    amount = float(number)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.2f} {unit}" if unit != "B" else f"{int(amount)} B"
        amount /= 1024
    return "not recorded"


def link(url: str, label: str) -> str:
    if not url:
        return "—"
    escaped_url = html.escape(url, quote=True)
    return f'<a href="{escaped_url}" rel="noreferrer">{html.escape(label)}</a>'


def cell(value: str) -> str:
    return html.escape(value or "—")


def read_ledger(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        headings = set(reader.fieldnames or [])
        missing = REQUIRED - headings
        if missing:
            raise ValueError("ledger lacks required headings: " + ", ".join(sorted(missing)))
        rows = []
        for line_no, row in enumerate(reader, start=2):
            resource_id = (row.get("resource_id") or "").strip()
            if not resource_id or resource_id == "EXAMPLE-DO-NOT-KEEP":
                continue
            state = (row.get("rag_state") or "").strip()
            if state not in VALID_STATES:
                raise ValueError(f"line {line_no}: invalid rag_state {state!r}")
            rows.append({key: (value or "").strip() for key, value in row.items()})
    return rows


def make_html(rows: list[dict[str, str]], title: str) -> str:
    counts = Counter(row["rag_state"] for row in rows)
    total_bytes = sum(int(row["bytes"]) for row in rows if row["bytes"].isdigit())
    generated = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    cards = "".join(
        f'<li><strong>{state}</strong>: {counts.get(state, 0)} item(s)</li>'
        for state in ("REFERENCE_ONLY", "LOCAL_FTS_OK", "RAG_ALLOWLIST")
    )
    body_rows = []
    for row in sorted(rows, key=lambda r: (r["tier"], r["priority"], r["title"].casefold())):
        body_rows.append(
            "<tr>"
            f"<td>{cell(row['resource_id'])}</td>"
            f"<td><strong>{cell(row['title'])}</strong><br><small>{cell(row['publisher'])}</small></td>"
            f"<td>{cell(row['tier'])} / {cell(row['priority'])}</td>"
            f"<td class=state>{cell(row['rag_state'])}</td>"
            f"<td>{human_bytes(row['bytes'])}</td>"
            f"<td><code>{cell(row['local_path'])}</code><br>{cell(row['format'])} · {cell(row['offline_opener'])}</td>"
            f"<td>{link(row['official_landing_url'], 'landing')}<br>{link(row['resolved_direct_url'], 'direct')}</td>"
            f"<td>{cell(row['publication_or_version'])}<br><small>Retrieved: {cell(row['retrieved_utc'])}</small></td>"
            f"<td>{cell(row['rights_class'])}<br><small>{cell(row['rights_claim'])}</small><br>{link(row['rights_evidence_url'], 'evidence')}</td>"
            f"<td>{cell(row['next_review_utc'])}</td>"
            "</tr>"
        )
    return f"""<!doctype html>
<html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>{html.escape(title)}</title>
<style>
:root{{color-scheme:light dark}} body{{font-family:system-ui,sans-serif;line-height:1.4;margin:2rem;max-width:1600px}} table{{border-collapse:collapse;width:100%;font-size:.88rem}} th,td{{text-align:left;vertical-align:top;padding:.55rem;border:1px solid #777}} th{{position:sticky;top:0;background:#234;color:#fff}} code{{overflow-wrap:anywhere}} small{{color:#666}} .warning{{border-left:5px solid #b52;padding:.7rem 1rem;background:#fff4e5}} .state{{font-weight:700}} @media print{{body{{margin:.5in}} th{{position:static}} a{{color:#000;text-decoration:none}}}}
</style></head><body>
<h1>{html.escape(title)}</h1>
<p>Generated locally at {generated}. {len(rows)} acquired item(s); recorded size: {human_bytes(str(total_bytes))}.</p>
<div class=warning><strong>Rights boundary:</strong> this catalog is metadata, not permission. <code>REFERENCE_ONLY</code> files must not be OCRed, text-extracted, locally indexed, embedded, chunked, quoted to a model, or used in RAG. <code>LOCAL_FTS_OK</code> permits a local search layer only; its extracted text and results must not enter model context. Only explicit, documented <code>RAG_ALLOWLIST</code> items may be passed to an AI workflow.</div>
<h2>RAG-state count</h2><ul>{cards}</ul>
<table><thead><tr><th>ID</th><th>Resource</th><th>Tier / priority</th><th>State</th><th>Size</th><th>Local access</th><th>Source</th><th>Version / retrieval</th><th>Rights evidence</th><th>Review due</th></tr></thead><tbody>{''.join(body_rows)}</tbody></table>
</body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", type=Path)
    parser.add_argument("--html", type=Path, required=True, help="output HTML catalog")
    parser.add_argument("--csv", type=Path, help="optional normalized CSV copy")
    parser.add_argument("--title", default="Offline Recovery Library Catalog")
    args = parser.parse_args()
    try:
        rows = read_ledger(args.ledger)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    args.html.parent.mkdir(parents=True, exist_ok=True)
    args.html.write_text(make_html(rows, args.title), encoding="utf-8", newline="\n")
    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        headings = [
            "resource_id", "title", "publisher", "tier", "priority", "rag_state", "bytes",
            "format", "local_path", "offline_opener", "official_landing_url", "resolved_direct_url",
            "publication_or_version", "rights_class", "rights_claim", "rights_evidence_url",
            "next_review_utc", "notes",
        ]
        with args.csv.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=headings, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
    print(f"Wrote {args.html} from {len(rows)} ledger item(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
