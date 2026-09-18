# Offline Recovery Library Engineering Kit

This repository is a **planning and operations kit**, not a preloaded survival archive. It was prepared for building a durable, rights-aware, offline recovery library on a 2 TB portable SSD. The principal deliverable is [`OFFLINE_RECOVERY_LIBRARY_PLAN.md`](OFFLINE_RECOVERY_LIBRARY_PLAN.md).

## What is here

- `OFFLINE_RECOVERY_LIBRARY_PLAN.md` — storage tiers, folder layout, curated acquisition register, local-AI design, integrity plan, and build procedure.
- `templates/` — acquisition, rights, RAG-approval, verification, hardware, replacement, partition, and emergency-contact records.
- `tools/` — offline, standard-library Python utilities to create a volume skeleton, calculate/verify SHA-256 manifests, append acquisition records, validate the ledger/allowlist boundary, generate a static catalog, and produce a re-hashed RAG ingest manifest for approved sources only.

Downloaded content, models, indexes, logs, and personal data are ignored by Git intentionally. Put those only on the SSD and on separately stored backups.

## Non-negotiable rights boundary

Every acquired item must be one of exactly these states:

1. `REFERENCE_ONLY` — open in a native reader only. No OCR, text extraction, full-text indexing, embeddings, chunks, sidecar quotations, or model context.
2. `LOCAL_FTS_OK` — local keyword search is approved, but extracted text and search results must never enter an LLM or vector store.
3. `RAG_ALLOWLIST` — a reviewer has recorded item-specific evidence supporting extraction and local RAG for the intended use. Only these files may enter AI retrieval.

Free access, a government domain, and an apparent Creative Commons label are not blanket permission for AI ingestion or redistribution. Preserve rights evidence next to each source and retain originals unchanged.

## Quick dry-run checks

```bash
python3 tools/bootstrap_library.py /path/to/mounted/CIVLIB --profile civlib
python3 tools/sha256_manifest.py --help
python3 tools/validate_ledger.py templates/acquisition-ledger.csv --allowlist templates/rag-allowlist.csv
```

Use `--apply` only after confirming the target is the intended mounted volume. These scripts never partition, format, repair, or download material.

## Safety and maintenance

Medical, engineering, electrical, radio, map, and disaster material is educational reference—not an autonomous decision system. Use current local instructions and qualified help whenever they are available. For a failing drive, clone/image first; never run repair tools against the sole original.
