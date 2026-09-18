# Offline helper tools

All tools work offline, use only Python 3 standard-library modules, and deliberately avoid disk formatting, partitioning, network download, OCR, indexing, and recovery writes.

## `bootstrap_library.py`

Creates only missing folder names and `START-HERE.txt` on an **existing** directory.

```bash
python3 tools/bootstrap_library.py /media/SSD/CIVLIB --profile civlib
python3 tools/bootstrap_library.py /media/SSD/CIVLIB --profile civlib --apply
python3 tools/bootstrap_library.py /media/SSD/BOOTTOOLS --profile boottools --apply
```

Confirm mount labels and physical drive identity before `--apply`. It refuses `/` and the home directory but cannot know whether a mounted path is the correct SSD.

## `sha256_manifest.py`

Create a deterministic manifest after content has been verified and the volume is stable:

```bash
python3 tools/sha256_manifest.py create /media/SSD/CIVLIB \
  --manifest /media/SSD/CIVLIB/00_Admin/03_Manifests/civlib-sha256.tsv \
  --exclude '00_Admin/03_Manifests/*' --exclude '00_Admin/05_Logs/*'
```

Verify later (including unexpected non-excluded files):

```bash
python3 tools/sha256_manifest.py verify /media/SSD/CIVLIB \
  --manifest /media/SSD/CIVLIB/00_Admin/03_Manifests/civlib-sha256.tsv \
  --exclude '00_Admin/03_Manifests/*' --exclude '00_Admin/05_Logs/*' \
  --check-unexpected
```

Do not overwrite a known-good manifest after a failed verification. Save the report, investigate, and recover from a separately verified duplicate when needed.

## `record_acquisition.py`

Appends one row per local file, calculates its SHA-256, and defaults to `REFERENCE_ONLY`.

```bash
python3 tools/record_acquisition.py \
  /media/SSD/CIVLIB/00_Admin/01_Ledgers/acquisition-ledger.csv \
  /media/SSD/CIVLIB/02_Health/01_Emergency/BEC_2018.pdf \
  --root /media/SSD/CIVLIB --id WHO-BEC-2018 --title 'Basic Emergency Care' \
  --publisher WHO --landing-url 'https://www.who.int/publications/i/item/9789241513081' \
  --version '2018' --format PDF --priority P0 --tier T1 \
  --next-review-utc 2027-09-18T00:00:00Z
```

Use `RAG_ALLOWLIST` only with item-specific AI-ingestion evidence, an approver, and an approval timestamp.

## `validate_ledger.py` and `build_catalog.py`

```bash
python3 tools/validate_ledger.py \
  /media/SSD/CIVLIB/00_Admin/01_Ledgers/acquisition-ledger.csv \
  --allowlist /media/SSD/CIVLIB/00_Admin/01_Ledgers/rag-allowlist.csv

python3 tools/build_catalog.py \
  /media/SSD/CIVLIB/00_Admin/01_Ledgers/acquisition-ledger.csv \
  --html /media/SSD/CIVLIB/00_Admin/02_Catalogs/library-catalog.html \
  --csv /media/SSD/CIVLIB/00_Admin/02_Catalogs/library-catalog.csv
```

The generated HTML is a metadata catalog; it intentionally never reads source documents or reveals their text.

## `build_rag_ingest_manifest.py`

Builds a JSON **provenance-only** source list for a later local extraction/indexing
job. It re-hashes every source and refuses anything outside the matching
`RAG_ALLOWLIST` ledger/allowlist records. It never reads/extracts document text,
contacts a network, or calls an LLM.

```bash
python3 tools/build_rag_ingest_manifest.py \
  /media/SSD/CIVLIB/00_Admin/01_Ledgers/acquisition-ledger.csv \
  /media/SSD/CIVLIB/00_Admin/01_Ledgers/rag-allowlist.csv \
  --root /media/SSD/CIVLIB \
  --output /media/SSD/CIVLIB/10_Offline_AI_Index/03_Allowlist_Records/ingest-2026-09.json \
  --index-id rag-2026-09
```

Treat the output as a permission gate, not proof that an extraction workflow is
correct. The downstream job must preserve page/section provenance and follow
`templates/rag-answer-contract.md`.
