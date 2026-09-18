# Rights, indexing, and RAG review checklist

Use one completed copy per candidate document, archive, dataset, or content channel. A download button is **not** permission to redistribute, OCR, extract, embed, or prompt an LLM with the contents.

- Resource ID:
- Exact title / version:
- Local SHA-256:
- Publisher / rights holder:
- Official landing URL:
- Exact resolved direct URL:
- Date reviewed:
- Reviewer:

## Evidence

- [ ] Exact licence/copyright statement copied to `00_Admin/04_Rights_Evidence/`.
- [ ] Evidence URL and retrieval date recorded in `acquisition-ledger.csv`.
- [ ] Embedded third-party text, images, maps, trademarks, and datasets considered.
- [ ] Jurisdiction and intended use (private use, household LAN, public sharing, commercial use) considered.
- [ ] Attribution, notice, non-commercial, no-derivatives, share-alike, and source-offer obligations recorded.
- [ ] Publisher terms were checked for an AI/LLM, training, ingestion, extraction, or API restriction.

## Decision — choose exactly one

- [ ] `REFERENCE_ONLY`: native reader only; no text extraction, full-text indexing, embeddings, chunking, sidecar quotations, or model prompts.
- [ ] `LOCAL_FTS_OK`: local document search only; extracted text and results must never be provided to a model.
- [ ] `RAG_ALLOWLIST`: explicit evidence supports extraction, embeddings, retrieval, and local model context for this exact item and intended use. Add a matching row to `rag-allowlist.csv`.

## RAG-specific safeguards

- [ ] Original is frozen and its SHA-256 is captured.
- [ ] Extraction/OCR is authorized and reproducible.
- [ ] Page/section boundaries survive chunking.
- [ ] Retrieval output will identify source title, version/date, hash, page/section, and a bounded quotation.
- [ ] A human accepts responsibility for model output and removes/revokes the item if rights change.

Decision notes:
