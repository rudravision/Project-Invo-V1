# Offline Recovery Library Plan — 2 TB SanDisk Portable SSD

**Prepared:** 2026-09-18 UTC
**Design target:** a household-held, self-contained reference and recovery library for prolonged loss of Internet, mobile service, cloud accounts, banking, grid power, supply chains, and normal services.
**Important:** this is an engineering acquisition plan, not a claim that a USB SSD alone makes a household medically, legally, electrically, or structurally competent. Training, printed quick references, tools, water, food, power, maps, local relationships, and duplicate media matter at least as much as files.

## 1. Master storage-budget table

### Capacity assumptions and partition layout

A marketed **2 TB** SSD is normally about **2,000 decimal GB** (roughly **1.82 TiB** as displayed by many operating systems). The design intentionally stops planned library content at about **1,300 GB**, rather than filling the drive.

| GPT order | Volume / state | File system | Decimal allocation | Planned stored content at completion | Deliberate free / reserve | Purpose and rationale |
|---:|---|---|---:|---:|---:|---|
| 1 | `BOOTTOOLS` | exFAT | 30 GB | ≤30 GB | Keep at least 5 GB free while updating | Cross-platform bootable ISOs, recovery tools, portable readers, OS installers, drivers, hashes, manuals, and test records. exFAT is broadly readable but is not the sole copy of anything important. |
| 2 | `CIVLIB` | NTFS | 1,470 GB | **≤1,270 GB, subject to free-space stop threshold** | **Target ≥200 GB as reported after formatting** | Main public/reference library, maps, readers, approved local indexes, models, and curated video. Formatting overhead means the operational threshold—not arithmetic alone—wins. NTFS is the primary Windows-friendly library file system; test Linux/macOS access before relying on it. |
| 3 | `FAMILYVAULT` | NTFS | 300 GB | up to 300 GB of *VeraCrypt containers* | Do not automatically fill it | Personal records, scans, family media, recovery exports, and encrypted backups. The partition itself is not a substitute for encrypted containers or a separate physical backup. |
| 4 | unallocated | none | **200 GB** | 0 | **200 GB** | Leave unformatted from the start. This is host-visible slack, not a guaranteed replacement for manufacturer-managed SSD over-provisioning. |
|  | **Total** | GPT | **2,000 GB** | **≤1,600 GB including a full 300 GB vault** | **≥400 GB unfilled/unallocated outside the planned library** | Gives room for personal files, staged replacement, and less-full flash operation. |

**Why this is not a promise about SSD endurance:** a USB SSD enclosure/controller may hide internal flash behavior. Unallocated host space can be sensible operational slack, but it does not prove that the manufacturer will treat it as formal over-provisioning. Monitor health where the bridge exposes it, avoid sustained full-disk writes, and retain a separate physical duplicate.

### Cumulative tiers

Tier totals include `BOOTTOOLS`; all sizes are **planning caps**, not claimed upstream file sizes. Exact bytes belong in the acquisition ledger after each verified download.

| Cumulative tier | What is usable at this point | `BOOTTOOLS` used | `CIVLIB` content used | Cumulative total | Additional space added at this tier | What remains intentionally unused in `CIVLIB` |
|---|---|---:|---:|---:|---:|---:|
| **Tier 1 — Essential survival** | Immediate emergency, health, water, food, local hazard, core maps, readers, recovery tools, a small offline reference set, and a small local model | 30 GB | 220 GB | **250 GB** | 250 GB | ~1,250 GB |
| **Tier 2 — Comprehensive recovery** | Broader agriculture, construction, utilities, mechanics, education, India data, encyclopedic archives, and stronger AI models | 30 GB | 970 GB | **1,000 GB** | 750 GB | ~500 GB |
| **Tier 3 — Civilization archive + AI** | Carefully chosen long-tail science/humanities/technical material, additional reference archives, validated local resources, and optional larger models | 30 GB | up to 1,270 GB | **about 1,300 GB** | up to 300 GB | **target ≥200 GB; stop earlier if needed** |
| **Personal continuity capacity** | Encrypted household records and personal files | — | — | plus up to 300 GB | separately managed | `FAMILYVAULT` is intentionally not a license to fill the device |

### Content allocation guide

This is a value-per-GB ceiling. Move a category down rather than exceed the tier merely because a large archive is available. Text, diagrams, datasets, maps, installers, and manuals normally beat video for resilience per GB.

| Category | Tier 1 allowance within `CIVLIB` | Added in Tier 2 | Added in Tier 3 | Tier-3 cumulative intent | Selection rule |
|---|---:|---:|---:|---:|---|
| Administration, readers, licences, scripts, catalogs | 5 GB | 15 GB | 25 GB | 45 GB | Retain installers/manuals for every stored format and operating system used by the household. |
| Emergency, India/Maharashtra plans, local continuity | 15 GB | 20 GB | 0 GB | 35 GB | Current local plans and printed quick cards first. |
| Health, public health, nutrition, WASH | 20 GB | 30 GB | 0 GB | 50 GB | Authoritative originals; no autonomous diagnosis or dosing. |
| Water, food preservation, agriculture, seeds, livestock, fisheries | 27 GB | 120 GB | 25 GB | 172 GB | Favor FAO, Indian agricultural extension, and locally applicable material. |
| Shelter, construction, plumbing, electrical, PV, batteries, generators | 12 GB | 65 GB | 0 GB | 77 GB | Site-specific work still requires qualified review and current local code. |
| Mechanics, engines, pumps, bicycles, welding, machining, materials | 8 GB | 65 GB | 45 GB | 118 GB | Prioritize manuals for equipment actually owned or locally common. |
| Mathematics, sciences, geography, geology, weather, navigation, India/Maharashtra maps | 40 GB | 35 GB | 10 GB | 85 GB | Preserve scalable map data and concise scientific references. |
| Radio, computing, networking, programming, Linux/Windows docs | 14 GB | 45 GB | 0 GB | 59 GB | Retain offline docs, source releases, OS installers, and hardware drivers. |
| Education, language, history, law/civics, public-domain books | 17 GB | 160 GB | 65 GB | 242 GB | Use legal/offline-ready collections; protect rights restrictions. |
| Kiwix/ZIM and other curated reference archives | 37 GB | 100 GB | 95 GB | 232 GB | Select individual current packages by purpose; do not invent static ZIM names/sizes. |
| Offline AI models, runtime, embeddings, approved indexes, test records | 16 GB | 55 GB | 25 GB | 96 GB | Keep only models that have been tested on real household hardware. |
| Curated skill video | 5 GB | 20 GB | 10 GB | 35 GB | Use short, captioned, high-signal lessons; avoid bulk entertainment archives. |
| Local gazetteer, printable maps/cards, permitted family continuity material | 4 GB | 20 GB | 0 GB | 24 GB | Export paper-ready copies and multiple open formats. |
| **Total `CIVLIB` content** | **220 GB** | **750 GB** | **300 GB** | **1,270 GB** | Stop here; preserve 200 GB free. |

### Universal acquisition and rights controls

The following controls apply to **every** row later in this plan:

1. Acquire from the publisher/rights holder or an explicitly authorized distribution channel. Do not treat a web search result, Internet Archive upload, cloud mirror, or “free download” label as authority.
2. Save the original unchanged, its official landing URL, resolved direct URL, retrieval UTC timestamp, publication/version date, byte count, publisher checksum/signature if available, local SHA-256, and a copy/screenshot/PDF of the rights statement.
3. Start every item as exactly **`REFERENCE_ONLY`**. A public web page, government host, or Creative Commons badge alone does not authorize OCR, text extraction, embedding, vectorization, prompting, redistribution, or derivative packaging.
4. A reviewer may move an item to **`LOCAL_FTS_OK`** only after recording the rights basis for local text search. Its extracted text and search results must never enter a model context or vector store.
5. A reviewer may move an item to **`RAG_ALLOWLIST`** only with item-specific evidence supporting the intended local AI ingestion. It needs a matching row in `rag-allowlist.csv`, a frozen original SHA-256, an approver, date, extraction method, and revocation path.
6. Keep attribution, non-commercial, no-derivatives, share-alike, trademark, source-offer, and third-party-content obligations alongside the original. Do not publicly share an ODbL-derived database, ZIM, vector database, or bundle until its obligations are reviewed.

The repository supplies ready-to-copy templates in [`templates/`](templates/) and validates the boundary with [`tools/validate_ledger.py`](tools/validate_ledger.py).

## 2. Folder structure

### Volume roots

```text
[2 TB SSD, GPT]
├── BOOTTOOLS/                         # 30 GB, exFAT, unencrypted
│   ├── START-HERE.txt
│   ├── 00_Start_Here/
│   ├── 01_Bootable_ISOs/
│   ├── 02_OS_Installers/
│   ├── 03_Recovery_Tools/
│   ├── 04_Portable_Apps/
│   ├── 05_Drivers_Firmware/
│   ├── 06_Documentation_Licences/
│   ├── 07_Checksums_Manifests/
│   ├── 08_Test_Logs/
│   └── 90_Staging_Unverified/
├── CIVLIB/                            # 1,470 GB, NTFS, keep ≥200 GB free
│   ├── START-HERE.txt
│   ├── 00_Admin/
│   ├── 01_Emergency/
│   ├── 02_Health/
│   ├── 03_Water_Food_Agriculture/
│   ├── 04_Shelter_Utilities_Energy/
│   ├── 05_Mechanics_Manufacturing/
│   ├── 06_Science_Navigation_Maps/
│   ├── 07_Computing_Communications/
│   ├── 08_Education_Language_Humanities/
│   ├── 09_Reference_ZIM/
│   ├── 10_Offline_AI_Index/
│   ├── 11_Curated_Video/
│   ├── 12_Local_Continuity/
│   ├── 90_Staging_Unverified/
│   ├── 91_Quarantine/
│   └── 99_Recovery_Exports/
├── FAMILYVAULT/                       # 300 GB, NTFS; contains encrypted containers
│   ├── START-HERE.txt
│   ├── 01_Encrypted_Containers/
│   ├── 02_Container_Header_Backups/
│   ├── 03_Encrypted_Backup_Exports/
│   ├── 04_Nonsecret_Recovery_Notes/
│   └── 05_Verification_Logs/
└── [200 GB unallocated]
```

Create this skeleton only after confirming the intended mounted volume:

```bash
python3 tools/bootstrap_library.py /mounted/CIVLIB --profile civlib --apply
python3 tools/bootstrap_library.py /mounted/BOOTTOOLS --profile boottools --apply
python3 tools/bootstrap_library.py /mounted/FAMILYVAULT --profile familyvault --apply
```

The helper only creates missing folders; it does **not** format, partition, download, repair, encrypt, or overwrite existing files.

### `CIVLIB` detail

```text
CIVLIB/
├── 00_Admin/
│   ├── 00_Start_Here/                 # printed/on-screen use instructions
│   ├── 01_Ledgers/                    # acquisition-ledger.csv; rag-allowlist.csv
│   ├── 02_Catalogs/
│   │   ├── 01_Metadata/                # static HTML/CSV catalog; no source text
│   │   ├── 02_Local_FTS_No_LLM/        # only approved LOCAL_FTS_OK search data
│   │   └── 03_Static_HTML/
│   ├── 03_Manifests/                  # SHA-256 manifests; immutable baseline copies
│   ├── 04_Rights_Evidence/            # copied licence notices, terms, approval forms
│   ├── 05_Logs/                       # SMART, verification, acquisition, test records
│   ├── 06_Hardware_Drivers/
│   ├── 07_Software_Licenses/
│   ├── 08_Offline_Readers/
│   └── 09_Scripts/
├── 01_Emergency/                      # quick cards, hazard guides, India/MH plans
├── 02_Health/                         # originals sorted by emergency/maternal/WASH/etc.
├── 03_Water_Food_Agriculture/
├── 04_Shelter_Utilities_Energy/
├── 05_Mechanics_Manufacturing/
├── 06_Science_Navigation_Maps/
├── 07_Computing_Communications/
├── 08_Education_Language_Humanities/
├── 09_Reference_ZIM/                  # ZIM files plus catalog/licence records
├── 10_Offline_AI_Index/
│   ├── 01_Models/                     # model files and model cards/licences
│   ├── 02_Runtimes/                   # llama.cpp, Python wheels/env exports, manuals
│   ├── 03_Allowlist_Records/          # hashes + permission records; not duplicate sources by default
│   ├── 04_Extracted_Allowlisted_Text/ # only RAG_ALLOWLIST source text, provenance retained
│   ├── 05_Indexes/                    # local vector DB / FTS index, versioned and rebuildable
│   ├── 06_Configurations/             # launch scripts, prompts, model/runtime settings
│   └── 07_Test_Transcripts/           # known-good cited-answer tests; no private material
├── 11_Curated_Video/                  # small, captioned, legally acquired lessons
├── 12_Local_Continuity/               # nonsecret map layers, print queue, local gazetteer
├── 90_Staging_Unverified/             # downloaded but not yet checksum/rights-reviewed
├── 91_Quarantine/                     # suspect files; never add to a manifest/index
└── 99_Recovery_Exports/               # recovered copies; preserve provenance and never overwrite source
```

### Naming, provenance, and access rules

- Use stable ASCII names: `YYYY-Publisher-Short_Title-edition-language.ext`; avoid rename churn after hashing. Example: `2018-WHO-Basic_Emergency_Care-en.pdf`.
- One file, one acquisition-ledger row. Collections need one row **per archive file** and one row for each installer/ISO/model artifact—not one vague row for a web site.
- Keep canonical originals in their subject folders. `10_Offline_AI_Index/03_Allowlist_Records/` holds pointers/hashes/rights evidence rather than unnecessary source copies. Do not duplicate a source merely for convenience unless its terms permit it.
- Do **not** create `.txt`, OCR PDFs, thumbnails, chunks, embeddings, or vector payloads for `REFERENCE_ONLY`. Do **not** pass `LOCAL_FTS_OK` text or search results to a model. A filename/path is metadata; source content is not.
- Keep mutable files—logs, staging, database WAL files, caches, and downloaded-but-unverified files—out of a frozen manifest or explicitly exclude them. Catalogs and indexes are rebuildable derivatives, not the sole copy of knowledge.
- `FAMILYVAULT` holds VeraCrypt containers and nonsecret recovery notes only. Passwords and recovery keys must be memorized or held separately in a carefully planned physical method; do not save them beside the containers.

## 3. Resource/download table

### How to read this register

- **Size field:** where a publisher does not publish a stable, immutable package size—or the collection is selected at acquisition—it says **“measure; reserve …”**. That is a capacity reservation, not an invented byte count. Record the actual byte count and SHA-256 in the ledger after download. Exact verified Qwen GGUF Q4_K_M sizes are called out separately. **Row reservations are selection envelopes, not additive promises; the master category/tier caps override them.**
- **Direct page:** a landing/catalog page is deliberately supplied instead of guessing a brittle file URL where a publisher chooses the current file dynamically. Resolve the click-through direct URL on acquisition day and record it.
- **Rights / state:** a licence statement controls only the identified item and conditions; it does not automatically allow AI ingestion. All rows begin `REFERENCE_ONLY` unless a completed review says otherwise. Where the cell says “capture/record exact licence,” its legal status is deliberately **`PENDING_DOCUMENT_LEVEL_REVIEW`**, not an implied permission.
- **Opener:** retain the named reader/installer/manual locally, in the architecture-matched form actually tested (Windows x64/ARM64, Linux x64/ARM64, and/or Android as applicable).
- **Priority:** `P0` = Tier-1 first weekend; `P1` = Tier-1/2 next; `P2` = Tier-2/3 valuable; `P3` = optional after essential material, hardware, and backup are complete.

### A. Emergency, health, nutrition, water, and public health

| ID and resource / contents | Why, tier, priority | Size / format / offline opener | Official source and direct page | Rights, version/date, update cadence, initial state |
|---|---|---|---|---|
| `WHO-BEC-2018` — **WHO Basic Emergency Care: Approach to the acutely ill and injured** | Structured first-contact emergency assessment; use with training and referral. **T1 P0** | Measure; reserve 0.1 GB. PDF; SumatraPDF/Okular/Evince. | WHO landing/download page: <https://www.who.int/publications/i/item/9789241513081> | Landing-page metadata identifies **CC BY-NC-SA 3.0 IGO**. 2018. Check annual replacement/corrections. **REFERENCE_ONLY** pending document-level AI review and attribution/NC/SA assessment. |
| `WHO-CHILD-HOSPITAL-2013` — **Pocket Book of Hospital Care for Children**, 2nd ed. | Pediatric inpatient reference; not a substitute for clinicians/facilities. **T1 P0** | Measure; reserve 0.2 GB. PDF; PDF reader. | WHO: <https://www.who.int/publications/i/item/9789241548373> | 2013. Capture the exact current rights notice in ledger; check annually for a successor. **REFERENCE_ONLY**. |
| `WHO-PCPNC-2015` — **Pregnancy, childbirth, postpartum and newborn care**, 3rd ed. | Maternal/newborn reference and training context; urgent complications require skilled care. **T1 P0** | Measure; reserve 0.2 GB. PDF; PDF reader. | WHO: <https://www.who.int/publications/i/item/9789241549356> | Landing page states WHO all rights reserved. 2015. Annual successor/protocol check. **REFERENCE_ONLY**; no OCR/RAG without written basis. |
| `WHO-IMCI-YOUNG-INFANT-2019` — **IMCI chart booklet: Management of the sick young infant aged up to 2 months** | Infant danger-sign and referral reference. The 2019 booklet supersedes the young-infant portion of the 2014 IMCI charts. **T1 P0** | Measure; reserve 0.1 GB. PDF; PDF reader; print critical pages only after rights review. | WHO: <https://www.who.int/publications/i/item/9789241516365> | Landing-page metadata identifies **CC BY-NC-SA 3.0 IGO**. 2019. Check annually. **REFERENCE_ONLY** pending use/AI review. |
| `WHO-EML-2025` — **WHO Model List of Essential Medicines, 24th list** | Medicine reference for names/selection context—not a personal prescribing, dose, interaction, or counterfeit-verification system. **T1 P0** | Measure; reserve 0.1 GB. PDF/associated files; PDF reader. | WHO publication page: <https://www.who.int/publications/i/item/B09474> | 2025 list. Check when WHO issues a new list and at least annually. Capture document notice. **REFERENCE_ONLY**. |
| `WHO-PFA-2011` — **Psychological first aid: Guide for field workers** | Practical psychosocial-support principles during disruption. **T1 P1** | Measure; reserve 0.1 GB. PDF; PDF reader. | WHO: <https://www.who.int/publications/i/item/9789241548205> | 2011. Check annually for updates; record exact notice. **REFERENCE_ONLY**. |
| `WHO-SANITATION-2018` — **Guidelines on sanitation and health** | Household/community sanitation, disease prevention, and planning. **T1 P0** | Measure; reserve 0.2 GB. PDF; PDF reader. | WHO: <https://www.who.int/publications/i/item/9789241514705> | 2018. Annual review. Capture rights at download. **REFERENCE_ONLY**. |
| `WHO-DRINKING-WATER-2022` — **Guidelines for drinking-water quality, 4th ed. incorporating addenda** | Water safety planning/reference; apply local testing and qualified engineering where possible. **T1 P0** | Measure; reserve 0.3 GB. PDF; PDF reader. | WHO: <https://www.who.int/publications/i/item/9789240045064> | 2022 current page. Check annual successor/addenda. **REFERENCE_ONLY**. |
| `WHO-SMALL-WATER-2024` — **Guidelines for drinking-water quality: small water supplies** | Small-system water management and public-health framing. **T1 P1** | Measure; reserve 0.3 GB. PDF; PDF reader. | WHO: <https://www.who.int/publications/i/item/9789240088740> | 2024. Annual review. Capture current notice. **REFERENCE_ONLY**. |
| `CDC-FOOD-SAFETY` — **CDC food-safety reference pages and any explicitly downloadable fact sheets** | Foodborne-disease prevention; pair with local food-preservation guidance. **T1 P1** | Dynamic pages/files; reserve 0.5 GB. HTML/PDF; browser/PDF reader. | CDC food-safety landing page: <https://www.cdc.gov/food-safety/about/index.html> | Current web material; record each saved item and whether it is a U.S. government work or contains third-party material. Review annually. **REFERENCE_ONLY** until item-level review. |
| `NCHFP-USDA-CANNING-2015` — **USDA Complete Guide to Home Canning** | Process-specific food-preservation reference. Conditions, equipment, altitude, and current local guidance matter. **T1 P1** | Measure; reserve 0.2 GB. PDF; PDF reader. | National Center for Home Food Preservation collection: <https://nchfp.uga.edu/resources/category/usda-guide>; official PDF entry: <https://nchfp.uga.edu/papers/guide/INTRO_HomeCanrev0715.pdf> | 2015 revision. Check official page annually. Record government/university rights notice and embedded content. **REFERENCE_ONLY**. |
| `WHO-NUTRITION-CATALOG` — **WHO nutrition, infant-feeding, and public-health publications selected item-by-item** | Adds nutrition, breastfeeding, child feeding, and emergency public-health depth without trusting an uncurated bundle. **T1 P1** | Variable; reserve 2 GB initially. PDFs/HTML; PDF reader/browser. | WHO publications catalogue: <https://www.who.int/publications> | Resolve exact title/version/rights per file; recheck annually. **REFERENCE_ONLY** by default. |
| `LOCAL-MEDICAL-PROTOCOLS` — locally applicable clinic/PHC, ambulance, poison, snakebite, maternal/newborn, vaccination, and public-health instructions | Makes the library locally actionable; preserve contact/address/version/date. **T1 P0** | Usually small; reserve 1 GB. PDF/print/CSV; PDF reader and paper copy. | Acquire only from the responsible local/Indian authority or treating clinician; record the exact authoritative URL/document. | Time-sensitive. Verify before monsoon and every six months. **REFERENCE_ONLY** unless explicit permission is documented. Never use AI to decide diagnosis/dose/referral. |

**Medical use boundary:** show the publication date, source, page, and confidence limits whenever a human reads or uses a health reference. An offline model must never represent itself as a clinician, calculate a medication dose from ambiguous information, replace emergency referral, or conceal that advice may be outdated or locally inapplicable.

### B. Food, agriculture, seeds, livestock, fisheries, botany

| ID and resource / contents | Why, tier, priority | Size / format / offline opener | Official source and direct page | Rights, version/date, update cadence, initial state |
|---|---|---|---|---|
| `FAO-SEED-STORAGE-2018` — **Seeds Toolkit, Module 6: Seed storage** | Seed drying, storage, quality, and continuity. High value per GB. **T1 P0** | Measure; reserve 0.1 GB. PDF; PDF reader. | FAO direct PDF: <http://www.fao.org/3/ca1495en/CA1495EN.pdf> | **2018**; title must remain exactly *Seeds Toolkit – Module 6: Seed storage*. Capture the PDF rights notice/FAO terms. Annual check. **REFERENCE_ONLY**. |
| `FAO-POULTRY` — **Small-scale poultry production** | Flock housing, feeding, health, and production context. **T1 P1** | Measure; reserve 0.2 GB. PDF; PDF reader. | FAO technical guide PDF: <https://www.fao.org/3/y5169e/y5169e.pdf> | Publication date/version must be read from the acquired file. Review annually. **REFERENCE_ONLY** pending document-specific rights evidence. |
| `FAO-SSF-GUIDELINES` — **Voluntary Guidelines for Securing Sustainable Small-Scale Fisheries** | Fisheries livelihoods/governance/resource-management reference. **T2 P2** | Measure; reserve 0.2 GB. PDF; PDF reader. | FAO direct PDF: <http://www.fao.org/3/a-i4356en.pdf> | Publication date/version in acquired file; capture rights notice. Review every 2 years. **REFERENCE_ONLY**. |
| `MPKV-EXTENSION-CATALOG` — **Mahatma Phule Krishi Vidyapeeth extension publications, Maharashtra-relevant selections** | Local crop, soil, horticulture, livestock, and farm-extension relevance. Select specific titles useful to the household’s district/languages. **T1 P0** | Variable; reserve 10 GB T1, then 40 GB T2. PDFs/pages; PDF reader/browser. | Official MPKV catalogue: <https://mpkv.ac.in/Extension/ExtensionPublication> | Catalogue changes; record each title, author, date, direct URL, notice, and language. Check before each growing season and annually. **REFERENCE_ONLY** by default. |
| `ICAR-LOCAL-AGRICULTURE` — **ICAR/Krishi Vigyan Kendra and state-agriculture publications relevant to the actual district** | Local sowing calendars, pests, irrigation, soil, crop varieties, and veterinary support must be regional, not generic. **T1 P0** | Variable; reserve 10 GB T1 and 30 GB T2. PDF/CSV/print; PDF reader/spreadsheet. | Use the responsible ICAR/KVK/state department’s official page; log the exact official landing/direct URL per item rather than relying on republished PDFs. | Seasonal and region-specific; verify before kharif and rabi seasons. **REFERENCE_ONLY** unless a specific item is cleared. |
| `FAO-AGRICULTURE-CATALOG` — **FAO crop, soil, irrigation, agroecology, post-harvest, and animal-health publications selected by task** | Authoritative global complements to Maharashtra-specific advice. **T2 P1** | Variable; reserve 35 GB. PDF/HTML/data; PDF reader/browser. | FAO publications portal: <https://www.fao.org/publications/en/> | Select only current, practical, locally contextualized items; capture individual rights. Annual review. **REFERENCE_ONLY** by default. |
| `FAO-ECTAD-ANIMAL-HEALTH` — **FAO Emergency Centre for Transboundary Animal Diseases Asia/Pacific selected publications** | Veterinary/public-animal-health, surveillance, and zoonosis context; does not replace a veterinarian or support unsupervised animal treatment. **T2 P2** | Variable; reserve 5 GB. PDF/HTML; PDF reader/browser. | Official FAO ECTAD Asia/Pacific publications: <https://fao.org/in-action/ectad/resources/publications/en> | Dynamic catalogue. Record exact publication, date, rights statement, and any regional applicability. Review annually. **REFERENCE_ONLY**. |
| `HOME-FOOD-SEED-LOGS` — household seed inventory, crop calendar, input/output, preservation batches, local plant observations | Turns reference into local memory; retain exports in open CSV/ODS/PDF-A and paper. **T1 P0** | Small; reserve 2 GB. CSV/ODS/PDF-A/photos; LibreOffice, PDF reader, image viewer. | Locally created. Template/source record retained under `12_Local_Continuity`. | Update each season and after each preservation batch. Household owner controls rights; individual privacy review still applies before any RAG use. |
| `FIELD-GUIDES-LOCAL-FLORA-FAUNA` — legally acquired local botany, pests, fungi, fisheries, and animal identification guides | Supports observation and avoids overconfident identification. Never rely on a model for poisonous plant/mushroom or venomous-animal identification. **T2 P1** | Variable; reserve 10 GB. PDF/ePub/photos; PDF reader/Calibre. | Prefer state university, herbarium, ICAR/KVK, and official biodiversity sources; record exact item source. | Recheck local species/status every 2 years. **REFERENCE_ONLY** unless rights explicitly support the intended processing. |

### C. Disaster, shelter, water infrastructure, electrical energy, mechanics, maps, weather, navigation

| ID and resource / contents | Why, tier, priority | Size / format / offline opener | Official source and direct page | Rights, version/date, update cadence, initial state |
|---|---|---|---|---|
| `MH-SDMA-DDMP` — **Maharashtra State Disaster Management Authority district disaster-management-plan catalogue and the household’s district plan** | Local hazards, authorities, routes, facilities, and response structure. **T1 P0** | Variable; reserve 2 GB. PDFs/HTML/print; PDF reader/browser. | Official catalogue: <https://sdma.maharashtra.gov.in/en/district-disaster-management-plan-ddmp/> | Download the current district plan and record district/version/date. Before monsoon and annually. **REFERENCE_ONLY** or `LOCAL_FTS_OK` only after review. |
| `MH-SDMA-HANDBOOK-2025` — **Aapatti Vyavsthapan Margadarshika** (Marathi disaster-management handbook) | Maharashtra-language household/community disaster readiness. **T1 P0** | Measure; reserve 0.5 GB. PDF; PDF reader. | Maharashtra SDMA publication page: <https://sdma.maharashtra.gov.in/en/publication/appatti-vyavsthapan-margadarshika-book/> | Page currently identifies a 2025 handbook; record actual file/version/notice. Check annually/pre-monsoon. **REFERENCE_ONLY**. |
| `NDMA-GUIDELINES` — **National Disaster Management Authority guideline catalogue, selected hazard guides** | National hazard, preparedness, response, and mitigation reference. **T1 P1** | Variable; reserve 5 GB. PDFs; PDF reader. | Official catalogue: <https://ndma.gov.in/Governance/Guidelines> | Resolve specific editions/rights per guide. Annual and pre-monsoon review. **REFERENCE_ONLY**. |
| `IMD-WARNING-SOP` — **India Meteorological Department forecasting/warning SOP material** | Understand warning chain, terminology, and local weather information. Not a substitute for live warning feeds. **T1 P1** | Measure; reserve 0.2 GB. PDF; PDF reader. | IMD PDF: <https://mausam.imd.gov.in/imd_latest/contents/pdf/forecasting_sop.pdf> | Record date/version in file; annually review current procedures. **REFERENCE_ONLY**. |
| `MSEDCL-SAFETY` — **Maharashtra State Electricity Distribution Company safety guidelines/manuals** | Consumer electrical safety and local utility context. Dead lines/equipment must be treated as live until competent authority confirms otherwise. **T1 P0** | Variable; reserve 2 GB. PDFs; PDF reader. | MSEDCL safety material: <https://www.mahadiscom.in/en/training-safety-department-safety-guidelines-and-manual/> | Current catalogue; log individual title/version/rights. Annual review. **REFERENCE_ONLY**. |
| `FEMA-SAFE-ROOMS` — **FEMA safe-room publications/resources, including P-320/P-361 where appropriate** | Well-illustrated hazard/shelter concepts; **not** Indian site-specific construction approval. **T2 P2** | Measure each file; reserve 1 GB. PDF; PDF reader. | Official landing: <https://www.fema.gov/emergency-managers/risk-management/building-science/safe-rooms>; resource catalogue: <https://fema.gov/design-construction-guidance-community-safe-rooms> | Current resource page; one known legacy PDF is <https://www.fema.gov/sites/default/files/documents/building-safe-room-home-small-business.pdf>. Check annually. **REFERENCE_ONLY**. Licensed local design review and local codes prevail. |
| `BUILD-CHANGE-RESILIENT-HOUSING-2021` — **Build Change Guide to Resilient Housing: An Essential Handbook for Governments and Practitioners** | Practical resilient-housing programme principles and drawings context; adapt only through locally competent structural/building review. **T2 P2** | Measure; reserve 0.5 GB. PDF/online guide; PDF reader/browser. | Official guide landing/download: <https://buildchange.org/guide-to-resilient-housing> | Landing page identifies the 2021 guide and links to a Creative Commons licence; capture the **exact** licence/version/notice from the acquired item. Review annually. **REFERENCE_ONLY** pending full rights and local applicability review. |
| `EPA-SEPTICSMART` — **EPA SepticSmart and onsite wastewater maintenance material** | Septic maintenance and contamination-prevention background. Climate, soil, and legal requirements differ locally. **T2 P2** | Dynamic small files; reserve 0.5 GB. HTML/PDF; browser/PDF reader. | EPA septic topic: <https://www.epa.gov/septic> | Current materials; record individual item/date/rights. Biennial review. **REFERENCE_ONLY**. |
| `RAINWATER-LOCAL` — official local/state rainwater-harvesting and groundwater/recharge guidance | India-specific rainfall, groundwater, health, building, and legal context is more valuable than generic designs. **T1 P0** | Variable; reserve 2 GB. PDF/HTML/print; PDF reader. | Obtain only from the relevant Maharashtra/local government, water authority, university, or engineering body and record the exact official item URL. | Verify annually and before construction. **REFERENCE_ONLY**; engineering review required. |
| `NREL-PV-INTRO` — **NREL/DOE photovoltaic reference documents, selected per task** | PV components, solar-resource concepts, and system context; do not improvise high-voltage DC, lithium battery, grounding, or grid interconnection. **T2 P1** | Selective PDFs; reserve 5 GB. PDF; PDF reader. | NREL publication source: <https://www.nrel.gov/research/publications.html>; one official PV introductory PDF: <https://docs.nrel.gov/docs/legosti/fy97/6981.pdf> | Capture report-specific rights/third-party content. Check every 2 years. **REFERENCE_ONLY**. |
| `OWNED-EQUIPMENT-MANUALS` — manuals, wiring diagrams, parts lists, service instructions for the household’s water filter, pump, inverter, PV controller, battery, generator, vehicle, bicycle, radio, tools, and appliances | The most locally useful mechanical/electrical archive. **T1 P0** | Variable; reserve 15 GB T1 / 50 GB T2. PDF/HTML/photos; PDF reader/browser/image viewer. | Download only from the manufacturer, authorized dealer/service portal, or your legitimate product documentation. Record model/serial and source URL. | Update when equipment changes; test opening annually. Usually **REFERENCE_ONLY** unless terms clearly allow more. |
| `MECHANICAL-FOUNDATIONS` — legally obtained original manuals/texts for engines, pumps, bicycle repair, welding, machining, materials, and hand tools | Builds repair vocabulary and safe maintenance skill. **T2 P1** | Variable; reserve 65 GB T2 +45 GB T3. PDF/ePub/video; PDF reader/Calibre/VLC. | Favor original publishers, public-domain works, government/university material, or clearly licensed original repositories; log each item. | Review source/version every 2 years. **REFERENCE_ONLY** by default. |
| `GEOFABRIK-INDIA-OSM` — current India OpenStreetMap PBF extract plus a documented locally generated Maharashtra subset | Base map data for QGIS/offline map packages. OSM is not authoritative for hazards, boundaries, routes, medical facilities, or navigation decisions. **T1 P0** | Dynamic extract; reserve 15 GB source/subsets/styles/tiles. `.osm.pbf`, GeoPackage, GPX/KML/GeoJSON; QGIS; tested offline mobile app. | Official India extract page: <https://download.geofabrik.de/asia/india.html>; download terms: <https://www.geofabrik.de/data/download.html> | OSM data is **ODbL**; preserve attribution and obligations: <https://www.openstreetmap.org/copyright> and <https://osmfoundation.org/wiki/Licence/Attribution_Guidelines>. Obtain current extract, then log date/hash and reproducible Maharashtra-subset command. Review quarterly/pre-monsoon. `LOCAL_FTS_OK` does **not** apply to map geometry; no RAG by default. |
| `LOCAL-MAP-LAYERS` — GPX/KML/GeoJSON/GeoPackage layers for home, routes, water points, clinics, hazards, community assets, printed map layouts | Makes base maps relevant and printable; protect sensitive locations. **T1 P0** | Variable; reserve 10 GB. Open geodata/PDF/print; QGIS, text editor, mobile map app. | Locally collected and source-attributed. Keep source, survey date, confidence, and sharing restriction for each feature. | Update after field checks, route changes, flooding, construction, or every six months. Household-controlled content; do not feed private/sensitive layers into a model by default. |
| `QGIS-OFFLINE` — QGIS installer/source/docs and offline project styles | Open, offline GIS for PBF-derived layers, GPX/KML/GeoJSON, GeoPackage, and printable maps. **T1 P1** | Installer/docs dynamic; reserve 5 GB including architecture variants and plugins tested offline. | Official source/download: <https://qgis.org/>; API/docs: <https://api.qgis.org/api/> | QGIS licensing is separate from map/data licences. Record exact release/hash and plugin licences. Test annually after OS changes. |
| `ORGANIC-MAPS-MOBILE` — Organic Maps application plus a tested downloaded India/Maharashtra offline map package | Low-power mobile offline map/search/route fallback alongside QGIS and paper. It is an OSM-derived convenience layer, not authority. **T1 P1** | App/map package changes; reserve 10 GB within maps allocation. Android/iOS app + downloaded map data; Organic Maps. | Official site/download choices: <https://organicmaps.app/> | Official site describes offline maps/GPS and OSM data. Record exact app build, platform, package/source date, licence, and map download test; preserve ODbL attribution obligations for underlying data. Quarterly/pre-monsoon check. **REFERENCE_ONLY** for any associated content; do not treat in-app Wikipedia as RAG corpus. |
| `NAVIGATION-WEATHER-FOUNDATIONS` — compass, paper-map, celestial/basic navigation, meteorology, geography, geology materials | Low-power navigation and hazard literacy. **T2 P1** | Curated texts/maps; reserve 15 GB. PDF/ePub/print; PDF reader/Calibre. | Favor public-domain, university, meteorological-agency, or government originals; log exact source. | Recheck maps/hazard layers annually. `REFERENCE_ONLY` by default. |

**Map workflow:** retain the original India PBF, a text file describing the precise subset tool/version/command and source date, QGIS project/style files, attribution notices, offline mobile-map-package source/date, GPX/KML/GeoJSON local layers, and several printed maps. Test a full offline route/search/print workflow with Wi-Fi/cellular disabled. Never describe OSM as an official evacuation, boundary, hazard, or emergency-routing authority.

### D. Education, languages, encyclopedias, public-domain books, and technical reference

| ID and resource / contents | Why, tier, priority | Size / format / offline opener | Official source and direct page | Rights, version/date, update cadence, initial state |
|---|---|---|---|---|
| `NCERT-TEXTBOOKS` — current NCERT school textbooks selected by grade/subject/language | Indian primary/secondary education continuity. **T1 P1**, expand T2. | Variable; reserve 20 GB T1 / 60 GB T2. PDF; PDF reader. | Official NCERT textbook portal: <https://ncert.nic.in/textbook.php> | Download/access terms must be preserved. NCERT forbids repackaging its books in digital content/software; do **not** put them in shared ZIMs, extraction pipelines, embeddings, or RAG absent written permission. Review academic year. **REFERENCE_ONLY**. |
| `EBALBHARATI-TEXTBOOKS` — Maharashtra State Bureau e-Balbharati books selected by grade/language | Maharashtra curriculum and Marathi/local-language access. **T1 P1**, expand T2. | Variable; reserve 20 GB T1 / 60 GB T2. PDF/eBook; supported native reader. | Catalogue: <https://ebalbharati.in/>; online books: <https://books.ebalbharati.in/> | Preserve title-level reproduction restrictions. Review academic year. **REFERENCE_ONLY**; no OCR/index/RAG without written permission. |
| `OPENSTAX-CORE` — selected OpenStax maths, science, economics, computing, and social-science textbooks | Strong university-level foundations at low storage cost. **T2 P1** | Selective PDFs; reserve 50 GB. PDF/ePub where offered; PDF reader/Calibre. | Subjects catalogue: <https://openstax.org/subjects> | Choose each book’s current “Get the book” page and preserve its exact licence/terms. Some OpenStax pages expressly restrict LLM ingestion; do not infer RAG permission from a Creative Commons label. Review annually. **REFERENCE_ONLY** unless a specific item is cleared. |
| `MIT-OCW-SELECTED` — carefully selected MIT OpenCourseWare course notes, texts, and low-volume media | Deep university reference, but choose durable downloadable materials rather than copying the whole site. **T2 P2** | Variable; reserve 40 GB. PDF/HTML/video; PDF reader/browser/VLC. | Official site: <https://ocw.mit.edu/> | Capture course-specific licence/attribution/NC terms and any AI restrictions. Review every 2 years. **REFERENCE_ONLY** by default. |
| `KOLIBRI-SELECTED` — Kolibri platform plus only content channels whose licences and size are individually reviewed | Structured offline education for a household or local LAN. **T2 P1** | Platform/channel dependent; reserve 40 GB initially. Installer/content database; browser/local Kolibri app. | Official overview: <https://learningequality.org/kolibri/about-kolibri/>; download: <https://learningequality.org/kolibri/download/> | Kolibri platform is not a blanket content-rights grant. Record channel/version/licence. Test fully offline, including content import. Review yearly. |
| `KIWIX-READER` — Kiwix desktop/mobile readers and documentation | Opens selected ZIM offline archives. **T1 P0** | Small; reserve 2 GB for installers/docs across required platforms. Installer/package; Kiwix Reader. | Official reader page: <https://get.kiwix.org/en/solutions/applications/kiwix-reader/>; source: <https://github.com/kiwix/kiwix-desktop> | Record exact release/checksum/licence. Test annual launch and ZIM search. |
| `KIWIX-ZIM-SELECTED` — carefully selected Wikipedia/Wiktionary/Wikimedia/medical/educational ZIM packages | Large offline encyclopedic/dictionary value; choose current, language-appropriate packages after reading content licence and storage impact. **T1 P1**, expand T2/T3. | Dynamic; reserve 35 GB T1 / 100 GB T2 / 95 GB T3. `.zim`; Kiwix Reader. | Use Kiwix’s current official catalogue/application workflow; FAQ: <https://get.kiwix.org/en/faq/> | Do **not** hardcode filenames, dates, sizes, or hashes: resolve current package then ledger it. ZIMs are snapshots, not incremental updates; keep old tested snapshot until replacement works. Underlying content rights vary. **REFERENCE_ONLY** unless individual content/path permission is established. |
| `PROJECT-GUTENBERG-CORE` — public-domain books selected for practical literature, science history, agriculture history, dictionaries, and culture | Durable, tiny, openly usable reading archive where the item’s status is appropriate. **T2 P2** | Curated ePub/HTML/plain text; reserve 20 GB. ePub/HTML/TXT; Calibre/browser. | Terms: <https://www.gutenberg.org/policy/terms_of_use.html> | United States public-domain status and Gutenberg terms do not automatically answer every jurisdiction/use question. Record each item/source/notice. Review collection yearly. `LOCAL_FTS_OK`/RAG only after item-level rights review. |
| `WIKIMEDIA-DATA-SELECTED` — selected openly licensed media/datasets only when attribution and share-alike obligations are documented | Images, diagrams, and references can be high-value, but large media is easy to overcollect. **T3 P3** | Strictly curated; reserve 10 GB. Images/CSV/HTML; image viewer/browser. | Start from the individual Wikimedia item’s original/licence page; record exact URL and attribution. | Licence is item-specific. Review annually. **REFERENCE_ONLY** by default; no bulk scraping. |
| `IFIXIT-OWNED-DEVICE-GUIDES` — repair guides for equipment actually owned or locally common | Clear repair photographs and steps; prioritize downloaded official guide pages/manuals only when permitted. **T2 P1** | Variable; reserve 15 GB. HTML/PDF/images; browser/PDF reader. | Licensing information: <https://www.ifixit.com/Info/Licensing> | iFixit licence conditions vary and include attribution/non-commercial/share-alike considerations. Preserve individual guide URLs/licences; do not assume RAG/redistribution permission. **REFERENCE_ONLY** by default. |
| `DICTIONARIES-LANGUAGE` — legal offline dictionaries for English, Marathi, Hindi, local languages, and technical vocabulary | Low-power literacy, translation, and education. **T1 P1** | Variable; reserve 5 GB T1 / 15 GB T2. ZIM/dictionary databases/ePub; Kiwix/GoldenDict-ng/Calibre as legally acquired and tested. | Prefer original publishers, official dictionary projects, or clearly licensed source databases; record each source. | Review when a new snapshot is acquired. **REFERENCE_ONLY** by default. |
| `OPEN-LIBRARY-ARCHIVE-CAUTION` — Internet Archive/Open Library/other historical sources only after title-level legal review | Potentially useful historical manuals/books, but availability is not a redistribution or AI-processing licence. **T3 P3** | Variable; hard cap 30 GB. PDF/ePub/scans; PDF reader/Calibre. | Original item page and rights statement must be logged; do not rely on a mirror or borrower-only access. | Item-specific. **REFERENCE_ONLY** unless proof says otherwise. |

### E. Computing, communications, installers, software, recovery, and readers

| ID and resource / contents | Why, tier, priority | Size / format / offline opener | Official source and direct page | Rights, version/date, update cadence, initial state |
|---|---|---|---|---|
| `DEBIAN-LIVE` — stable Debian Live ISO(s), checksums, signatures, release notes, and offline install docs | A known-good general recovery/workstation environment. Store the architecture actually owned, not every image. **T1 P0** | Dynamic ISO; reserve 8 GB. ISO; tested bootable USB/computer. | Official live image page: <https://www.debian.org/CD/live/> | Record exact stable release, architecture, SHA-512/signature verification result, and release date. Recheck yearly/when security-supported release changes. |
| `WINDOWS-INSTALLER` — official Windows installation media for licensed household hardware, activation/recovery instructions, and driver set | Recovery path for Windows equipment. Offline use still depends on licence/activation realities. **T1 P0** | Dynamic ISO; reserve 8 GB. ISO/installer; tested hardware. | Microsoft Windows 11 download: <https://www.microsoft.com/software-download/windows11> | Record exact edition/build, official hash if provided, licence proof separately in encrypted vault. Refresh yearly. |
| `RUFUS` — official Rufus installer/portable release, signatures/checksums, and instructions | Creates/recreates boot media on Windows. **T1 P0** | Small; reserve 0.5 GB. EXE/docs; Windows. | Official source: <https://rufus.ie/> | Record version/hash/licence; test with sacrificial USB annually. |
| `RESCUEZILLA` — Rescuezilla ISO/manual | Friendly imaging/cloning recovery environment. Test before dependence. **T1 P0** | Dynamic ISO; reserve 4 GB. ISO; booted test machine. | Official download: <https://rescuezilla.com/download> | Record release/hash/signature and test date. Refresh annually. Never image over the only source. |
| `GNU-DDRESCUE` — ddrescue package/source/manual and a printed quick procedure | First-line media rescue: clone/image a failing device while preserving a mapfile. **T1 P0** | Small source/manual; reserve 1 GB including live environment. CLI/manual; Debian live or tested Linux. | Official manual: <https://www.gnu.org/software/ddrescue/manual/ddrescue_manual.html> | Record package/version/hash/licence. Test mapfile workflow on disposable media annually. **Never** repair the only failing drive before cloning. |
| `TESTDISK-PHOTOREC` — TestDisk/PhotoRec releases and documentation | Partition/file recovery on a **copy** after image/clone. **T1 P0** | Small; reserve 1 GB. ZIP/CLI/docs; Windows/Linux. | Official download/wiki: <https://www.cgsecurity.org/wiki/TestDisk_Download> | Record release/hash/licence and test. Do not write repairs to the only source. |
| `DMDE` — DM Disk Editor and Data Recovery Software installer/manual | Additional recovery inspection/recovery option; licensing/features vary. **T1 P1** | Small; reserve 1 GB. Installer/ZIP/manual; Windows/Linux. | Official download: <https://dmde.com/download.html> | Record exact edition/licence/hash; test read-only inspection. Use only on clones/copies. |
| `FSARCHIVER` — package/manual | Linux-oriented file-system archival option; useful for supported filesystems, not primary Windows NTFS recovery. **T2 P2** | Small; reserve 1 GB. package/docs; Linux. | Acquire from its official project/distribution source and record the exact URL/version. | NTFS support is experimental; do not make it the primary Windows-volume recovery method. Test on disposable data annually. |
| `SMARTMONTOOLS` — smartctl package/docs | Captures drive health when the device/USB bridge exposes SMART. **T1 P0** | Small; reserve 1 GB. installer/package/docs; Windows/Linux. | Official source: <https://github.com/smartmontools/smartmontools> | Record release/hash/licence. Test on the actual enclosure. Absence of SMART does not prove health. |
| `PAR2` — par2cmdline source/binaries/docs | Optional parity for selected immutable high-value file sets; not a backup and not a replacement for checksums. **T2 P2** | Small tool plus selected parity; reserve 10–40 GB only after a tested plan. CLI/docs. | Official source: <https://github.com/Parchive/par2cmdline> | Record version/licence and exact parity percentage. Generate only after sources are final and manifests verify. |
| `7ZIP` — 7-Zip installers/manual | Open/extract archive formats and make recovery packages. **T1 P0** | Small; reserve 0.5 GB. installer/portable docs; Windows/Linux. | Official download: <https://www.7-zip.org/> | Record architecture/version/hash/licence. Test ZIP/7z extraction annually. |
| `VERACRYPT` — VeraCrypt installers, documentation, licence, and header-backup procedure | Encrypted personal vault containers. Encryption is not backup; headers and passwords are critical. **T1 P0** | Small; reserve 1 GB. installer/docs; tested OS. | Official licence: <https://veracrypt.io/en/VeraCrypt%20License.html> | Obtain current release only from official VeraCrypt channels; record exact release/hash/licence. Test mounting a noncritical container and restore a header backup annually. |
| `SUMATRAPDF` — lightweight Windows portable PDF/eBook/CHM reader | Opens PDF, EPUB, MOBI, CBZ/CBR, DjVu, XPS, CHM, and common images offline. **T1 P0** | Current site lists a small portable/installer release; reserve 0.5 GB incl. docs. EXE; Windows. | Official page: <https://www.sumatrapdfreader.org/free-pdf-reader> | Record exact version/hash/licence; test sample of each needed format annually. |
| `CALIBRE` — eBook manager/reader and portable release where available | Opens/manages ePub and other eBooks; useful for conversion only when rights allow. **T1 P1** | Dynamic installer; reserve 1 GB. installer/portable/docs; Windows/Linux/macOS. | Official download: <https://main.calibre-ebook.com/download> | Record version/signatures/licence. Do not convert protected/restricted books merely for convenience. |
| `VLC` — cross-platform media player | Opens MP4/WebM/MKV/audio/subtitles for curated instruction media. **T1 P1** | Official Windows download currently reports 38 MB on its page; reserve 1 GB with docs/other architecture packages. Installer; Windows/Linux/Android. | Official page: <http://www.videolan.org/vlc/> | Current page reported VLC 3.0.23 for Windows when this plan was prepared; record actual retrieved version/hash/licence. Review annually. |
| `LIBREOFFICE` — office suite plus offline help | Opens/saves ODF, CSV, text, and many office files; use open exports for long-term records. **T1 P1** | Dynamic installer; reserve 2 GB per tested architecture/language set. Installer/docs; Windows/Linux/macOS. | Official download: <https://www.libreoffice.org/download/> | Record exact version/checksum/licence and language packs. Test annual opening/export of CSV, ODS, ODT, PDF/A. |
| `QGIS-INSTALLER` — QGIS releases/docs, retained with map projects | Open GIS viewer/editor for offline data and map output. **T1 P1** | Dynamic; reserve included in map/admin allocation. Installer/package/docs. | Official source: <https://qgis.org/> | Record exact release/hash/licence and test on actual hardware after OS changes. |
| `KIWIX-INSTALLER` — Kiwix readers for required desktop/mobile platforms | Opens `.zim` archives. **T1 P0** | Dynamic; reserve included in reader allocation. | Official source: <https://get.kiwix.org/en/solutions/applications/kiwix-reader/> | Record version/hash/licence and test current ZIMs. |
| `DB-BROWSER-SQLITE` — DB Browser for SQLite installer/portable release and docs | Inspects local metadata/FTS databases offline without exposing content to an LLM. **T2 P2** | Dynamic; reserve 1 GB. installer/ZIP/docs. | Official downloads: <https://download.sqlitebrowser.org/> | Record release/hash/licence. Treat local FTS databases as derived, rebuildable data. |
| `TESSERACT-OCRMYPDF-TIKA` — locally retained text-extraction/OCR toolchain *only for sources whose review explicitly permits it* | Reproducible extraction for `LOCAL_FTS_OK` or `RAG_ALLOWLIST`; never a rights override. **T2 P2** | Toolchain varies; reserve 10 GB including language data/docs. CLI/docs; tested Linux/Windows environment. | Tesseract: <https://github.com/tesseract-ocr/tesseract>; OCRmyPDF: <https://github.com/ocrmypdf/OCRmyPDF>; Apache Tika: <https://tika.apache.org/> | Record exact releases/licences and language packs. No use on `REFERENCE_ONLY`; capture extraction logs/version. |
| `DEBIAN-DOCS-LINUX` — Debian documentation, man-page archives, package lists, and selected official software manuals | Rebuilding a Linux workstation/network without a live web connection. **T2 P1** | Curated; reserve 20 GB. HTML/PDF/man/ISO; browser/man/PDF reader. | Official documentation: <https://www.debian.org/doc/> | Record exact release/version and licences. Refresh when base OS changes. |
| `PYTHON-RUNTIME` — CPython runtime installer/embeddable package matched to retained script tests | Makes the included offline Python utilities usable if a host lacks a suitable interpreter. **T1 P0** | Dynamic installer/package; reserve 1 GB across required OS/architectures and docs. Installer/package; local Python 3. | Official downloads: <https://www.python.org/downloads/> | Record exact release, architecture, SHA-256/signature where supplied, licence, and a `python3 tools/... --help` test. Refresh when the retained scripts/runtime change. |
| `PYTHON-OFFLINE-DOCS` — Python language/library documentation archive matched to a retained CPython release | Small, complete, offline programming reference for automation, data checking, and rebuild scripts. **T1 P1** | Current Python docs page lists roughly 9 MiB zipped HTML / 5 MiB ePub for Python 3.11.16; reserve 0.1 GB per selected version. HTML/ePub/TXT; browser/Calibre. | Official current docs download: <https://docs.python.org/3/download.html> | Match docs to the installed Python version; Python page/release/licence evidence must be retained. Refresh when base Python changes. **REFERENCE_ONLY** until specific processing rights are reviewed. |
| `GNU-PROGRAMMING-DOCS` — GNU C intro/reference, Make, GDB, shell/build/tool manuals selected by task | Offline C/build/debugging fundamentals useful for software reconstruction. **T2 P2** | Small docs; reserve 1 GB. HTML/PDF/Info/source; browser/PDF reader/Info. | GNU C manual: <https://www.gnu.org/software/c-intro-and-ref/>; GNU Make manual: <https://www.gnu.org/software/make/manual/make.html>; GDB docs: <https://www.gnu.org/software/gdb/documentation/> | GNU C page identifies GFDL 1.3-or-later with stated invariant/cover texts; capture exact notice per manual. Review on toolchain update. **REFERENCE_ONLY** by default. |
| `IETF-RFC-CORE` — selected RFCs for IP, DNS, TCP/UDP, DHCP, TLS, email, and other networking protocols actually used | Authoritative protocol documentation and a legitimately reproducible standards corpus when full-copy terms are honored. **T2 P1** | Selective HTML/TXT/PDF; reserve 5 GB. HTML/TXT/PDF; browser/text reader/PDF reader. | RFC Editor: <https://www.rfc-editor.org/>; rights guidance: <https://www.rfc-editor.org/rfc/rfc8721.html>; IETF Trust legal provisions: <https://trustee.ietf.org/license-info> | RFC 8721 describes encouraged full copying, but each RFC’s copyright notice and IETF Trust provisions govern. Record individual RFC/version/notice; no automatic RAG. Review when protocols/software change. |
| `MICROSOFT-LOCAL-DOCS` — locally saved Microsoft documentation only where terms and acquisition method permit | Windows recovery, networking, PowerShell, and hardware reference; retain product-specific manuals too. **T2 P2** | Curated; reserve 15 GB. HTML/PDF/CHM where allowed; browser/SumatraPDF. | Start from official Microsoft documentation: <https://learn.microsoft.com/> and record each item. | Dynamic/legal terms per item; do not bulk mirror or AI-ingest by assumption. **REFERENCE_ONLY**. |
| `RADIO-COMMS-LOCAL` — legal local amateur/shortwave/radio operating references, manuals for owned radios, frequency plan, and offline digital-radio software only after regulatory review | Communications resilience requires lawful operation, trained operators, power planning, antennas, and local permissions—not just applications. **T2 P1** | Variable; reserve 15 GB. PDF/manual/software; browser/PDF reader/test app. | Official WPC regulations: <http://wpc.dot.gov.in/content/10_1_Regulations.aspx>; amateur material: <http://www.wpc.dot.gov.in/exam_amatr.asp>. Obtain software from its original project site and record each exact artifact. | WPC material includes amateur-service rules/amendments; laws/licences/frequencies can change. Review annually and before transmitting; retain equipment-specific manual. **REFERENCE_ONLY** by default. |
| `SOFTWARE-SOURCE-ARCHIVE` — source releases, package installers, signatures, licences, and printed install notes for the exact readers/tools above | Makes the library executable after OS failure. **T1 P0**, expand T2. | Reserve 10 GB T1 / 30 GB T2. ZIP/tar/ISO/docs; 7-Zip, OS tools. | Original project/publisher release pages listed above. | Record each artifact individually. Keep current plus one known-good previous version; review at least annually. |

### F. Personal vault, local records, paper bridge, and video discipline

| ID and resource / contents | Why, tier, priority | Size / format / offline opener | Official source and direct page | Rights, version/date, update cadence, initial state |
|---|---|---|---|---|
| `FAMILY-VAULT` — encrypted containers for identity/medical/financial/property records, family photos, locally made scans, and emergency exports | Personal continuity when cloud/banking access is unavailable. **T1 P0** | Up to 300 GB; VeraCrypt containers, plus PDF/A, CSV, ODF, JPEG/PNG/TIFF as appropriate. VeraCrypt + tested readers. | Locally created from records the household may retain. VeraCrypt licence source: <https://veracrypt.io/en/VeraCrypt%20License.html> | Refresh after major life/asset/medical changes; check at least every six months. Sensitive/private: exclude from AI by default and maintain a separately verified encrypted physical backup. |
| `PAPER-BRIDGE` — printed emergency cards, contacts, medication/allergy summary, map sheets, water-treatment and shutoff notes, boot/recovery quick sheet, and library index | Works when devices, batteries, readers, or software fail. **T1 P0** | Small digital originals + paper. PDF/A/print; PDF reader/printer. | Locally assembled from permitted sources and household facts; cite each source on the sheet. | Review every six months, before monsoon, and after equipment/contact changes. Keep confidential health detail in protected copy. |
| `CURATED-VIDEO` — short, captioned, legal/offline lessons for key physical skills | Good for demonstrations, but heavily size-limited. **T1 P2**, expand only after text/manual coverage. | ≤5 GB T1; +20 GB T2; +10 GB T3. MP4/WebM + captions/transcript if permitted; VLC. | Use original publisher/download source and retain each item’s licence/URL; do not bulk rip streaming services. | Recheck quarterly that playback/subtitles work. `REFERENCE_ONLY` by default. |
| `LOCAL-PRIVACY-MAP` — a nonsecret public-style map package and a separately controlled sensitive local layer set | Enables navigation while minimizing disclosure of home resources, caches, vulnerabilities, and family routines. **T1 P0** | Included in map allocation. GeoPackage/GPX/KML/GeoJSON/PDF; QGIS/offline mobile app. | Locally compiled with source/date/permission notes. | Field-check twice yearly. Never share or RAG-index sensitive location data by default. |

### Acquisition order within each tier

1. **Tier 1 (`~250 GB`)**: partition record; reader/recovery toolchain; local contacts/maps/printed cards; WHO emergency/WASH/child/maternal candidates; local district plan; MPKV/KVK and owned-equipment manuals; food/seed storage; India PBF + test subset; core school material; selected Kiwix/dictionaries; 4B local model; full manifests and duplicate test.
2. **Tier 2 (to `~1 TB`)**: current agriculture extension, water/shelter/electrical/mechanical material, wider education, carefully selected ZIM/Kolibri material, richer maps, source/docs, 8B/14B/32B models only after hardware tests, and recovery parity for selected immutable objects.
3. **Tier 3 (to `~1.3 TB`)**: long-tail technical/science/public-domain content, selected global reference archives, additional language/culture material, bounded video, and only the larger AI artifact that has a demonstrated hardware use case. Do not download merely to consume allocated space.

## 4. Offline-AI architecture

### Design principle: useful local search before generative AI

The best offline answer path is often **open the original in its native reader, then search the original**. AI is optional synthesis over a deliberately tiny, rights-approved corpus—not an archive replacement.

```text
                        ┌─────────────────────────────────────┐
                        │ Canonical acquired originals         │
                        │ subject folders + ledger + hashes    │
                        └───────────────┬─────────────────────┘
                                        │ rights review, never automatic
             ┌──────────────────────────┼───────────────────────────┐
             │                          │                           │
             ▼                          ▼                           ▼
  REFERENCE_ONLY                 LOCAL_FTS_OK                 RAG_ALLOWLIST
  native reader only             local keyword index only     approved extraction only
  no OCR/extraction/             SQLite FTS5 results shown    chunks + embeddings +
  indexing/embedding/LLM         to human; never LLM input    original page/section refs
             │                          │                           │
             ▼                          ▼                           ▼
  PDF/Kiwix/QGIS/etc.             human opens original         local vector + lexical search
                                                               → citation builder → local model
                                                               → answer with evidence/synthesis/
                                                                  uncertainty visibly separated
```

**Hard boundary:** file paths, titles, rights state, hashes, and page counts are metadata. The system may catalog that metadata. It may not quietly extract `REFERENCE_ONLY` content into thumbnails, a full-text database, browser cache, document parser, prompt, vector payload, test transcript, or training corpus.

### Recommended local components

| Layer | Recommended local component | Function | Store on SSD | Rights/data safeguard |
|---|---|---|---|---|
| Native access | Kiwix Reader, PDF reader, Calibre, QGIS, VLC, LibreOffice, 7-Zip | Opens original formats directly offline. | `00_Admin/08_Offline_Readers/` and `BOOTTOOLS/04_Portable_Apps/`; retain installers/licences/manuals. | No content transformation merely by opening. |
| Metadata catalogue | `tools/build_catalog.py` output + CSV | Browse title, publisher, source URL, hash, state, opener, review due date. | `00_Admin/02_Catalogs/01_Metadata/` | No source text is read or displayed by the tool. |
| Local keyword search | SQLite **FTS5** | Optional search for documents individually approved `LOCAL_FTS_OK`; can run with no GPU/network. | `00_Admin/02_Catalogs/02_Local_FTS_No_LLM/` | Database must be excluded from model prompts/vector ingestion; keep source/page mapping. SQLite docs: <https://www.sqlite.org/docs.html>; FTS5: <https://www.sqlite.org/fts5.html>. |
| Extraction | Tesseract / OCRmyPDF / Apache Tika only after written approval | Extract or OCR `LOCAL_FTS_OK`/`RAG_ALLOWLIST` source material reproducibly. | Tool installers/docs in admin; outputs in segregated folders. | Never run against `REFERENCE_ONLY`; store source hash, tool version, command, language data, pages, date. |
| Embedding | Qwen3 Embedding family, preferably smallest adequate local model | Converts approved chunks to vectors; optional reranker improves retrieval. | `10_Offline_AI_Index/01_Models/` | Start with official `Qwen/Qwen3-Embedding-0.6B`: <https://huggingface.co/Qwen/Qwen3-Embedding-0.6B>; resolve its exact artifact size/hash at acquisition. Official Qwen announcement says the embedding/reranking series is Apache 2.0: <https://qwenlm.github.io/blog/qwen3-embedding/>. Retain model card/version/evidence and use only approved source text. |
| Lexical + vector retrieval | SQLite FTS5 plus Qdrant local mode, or a small versioned local vector index | First retrieve a small set of relevant approved chunks; attach provenance before synthesis. | `10_Offline_AI_Index/05_Indexes/` | Qdrant local-mode client: <https://pypi.org/project/qdrant-client/>. Indexes are rebuildable derivatives; do not mix states. |
| Local inference | `llama.cpp` / `llama-server` with an official Qwen GGUF | Runs a local conversational model without Internet. | `10_Offline_AI_Index/02_Runtimes/`, models in `01_Models/`. | Official runtime source: <https://github.com/ggml-org/llama.cpp>. Bind any local UI to loopback/private LAN only; no cloud API, telemetry, or automatic update required. |
| Citation renderer | Small local script/UI configuration with fixed answer contract | Makes provenance impossible to hide in normal answers. | `10_Offline_AI_Index/06_Configurations/` | It must reject chunks lacking source ID/hash/page/section/state. |

### Corpus ingest gate

Before an ingest job, require all of the following:

1. Ledger row has a 64-character lowercase local SHA-256, publisher/source URL, version/date, local path, and rights evidence.
2. Ledger `rag_state` is exactly `RAG_ALLOWLIST`.
3. Matching `rag-allowlist.csv` row has the same source SHA-256; rights basis; AI-ingestion evidence URL/file; named approver; UTC approval date; extraction method; and chunking profile.
4. Original is stable, verified, and retained in its canonical subject folder.
5. Extractor/OCR version, command, language data, page count, and output SHA-256 are recorded. Keep page/section boundaries in every chunk.
6. Generated chunks/index receive an `index_id` and can be deleted/rebuilt without touching originals.
7. A revocation action timestamps `revoked_utc` in the allowlist, changes the ledger state away from `RAG_ALLOWLIST`, deletes derived text/embeddings/chunks/caches/index entries, and records the completed rebuild. A revoked historical approval remains auditable but must never be emitted into a new ingest manifest.

Run this safety check before building indexes:

```bash
python3 tools/validate_ledger.py \
  /mounted/CIVLIB/00_Admin/01_Ledgers/acquisition-ledger.csv \
  --allowlist /mounted/CIVLIB/00_Admin/01_Ledgers/rag-allowlist.csv
```

Create a provenance-only manifest after validation and immediately before extraction; it re-hashes each approved source and refuses a changed or mislocated original:

```bash
python3 tools/build_rag_ingest_manifest.py \
  /mounted/CIVLIB/00_Admin/01_Ledgers/acquisition-ledger.csv \
  /mounted/CIVLIB/00_Admin/01_Ledgers/rag-allowlist.csv \
  --root /mounted/CIVLIB \
  --output /mounted/CIVLIB/10_Offline_AI_Index/03_Allowlist_Records/ingest-rag-2026-09.json \
  --index-id rag-2026-09
```

The JSON output contains only provenance and permitted paths; a downstream extractor must still obey it and retain page/section mapping.

### First usable RAG corpus — deliberately narrow

No third-party row in the resource table is automatically pre-approved for RAG. Start with sources for which the household can actually preserve the needed permission evidence:

1. **Nonsecret household-authored operating notes** whose author expressly chooses `RAG_ALLOWLIST` (for example, a nonprivate equipment inventory or locally written library-use guide). Exclude health records, location-sensitive maps, credentials, and family/private information by default.
2. **Exact public-domain works** whose status is checked for the household’s jurisdiction and intended use, with the original title/source notice retained. Project Gutenberg availability alone is not the proof.
3. **Clearly licensed technical documentation** only after a reviewer records licence conditions, invariant sections/attribution obligations, and the lack of a contradictory AI restriction. The GNU/PSF/IETF examples in the table are candidates for review, not blanket approvals.
4. **A specifically authorized or self-authored educational corpus** where the creator has explicitly granted the planned local extraction/embedding/model-context use.

This produces a genuinely offline search/explanation system without silently absorbing WHO, NCERT, e-Balbharati, OpenStax, iFixit, Kiwix, government PDFs, map data, or other restricted material. For those sources, native-reader access and, where independently approved, human-only local FTS remain valuable.

### Mandatory AI answer contract

Every RAG response must show three separate blocks, in this order:

```text
RETRIEVED EVIDENCE
[1] SOURCE-ID | title | publisher | edition/version/date | local SHA-256 prefix
    page 14 / section “Water storage”; bounded quotation or faithful retrieval excerpt
[2] SOURCE-ID | ...

MODEL SYNTHESIS
A clearly labelled explanation that only connects the retrieved evidence.
It identifies assumptions and does not invent a source, dosage, legal rule, measurement, or procedure.

UNCERTAINTY AND SAFETY LIMITS
What the sources do not establish; publication age; location/equipment/skills needed;
when to seek qualified help or follow current official instructions instead.
```

Additional rules:

- A response without retrieved evidence must say **“No approved local source was retrieved; this is general model knowledge, not a library-cited answer.”**
- Citation records include document ID, title, publisher, edition/version/date, local SHA-256 or immutable identifier, page/section, chunk ID, and retrieval timestamp.
- Restrict quotes to the smallest useful amount and preserve conditions/qualifiers. Never manufacture page numbers or claim sources say more than they do.
- Health, electricity, structural work, batteries, water treatment, explosives/firearms, radio legality, navigation, law, and emergency response need an elevated warning and a prompt to consult original/current/local authority when possible.
- Never use private vault files, sensitive map layers, medical records, passwords, or recovery keys as default model context. Disable conversation logging by default; redact test transcripts.

### Qwen local model acquisition and model matrix

Acquire **only official Qwen GGUF repositories**, select a specific quantization file on the repository’s Files page, then record the exact resolved artifact URL, local SHA-256, model card/licence evidence, and test result. Do not use an unverified community conversion or invent a filename. Official Qwen overview: <https://qwenlm.github.io/blog/qwen3/>.

The verified **Q4_K_M GGUF disk anchors** below are the official repository’s displayed sizes; runtime/KV cache/OS buffers require additional memory. “Practical RAM/VRAM” is a conservative planning envelope for one interactive user and short context, not a guarantee.


| Qwen model and official source | Parameters / recommended quantization | Verified Q4_K_M disk size | Conservative single-user practical memory envelope* | Strengths / limitations | Context and runtime guidance |
|---|---|---:|---|---|---|
| **Qwen3-4B-GGUF** — <https://huggingface.co/Qwen/Qwen3-4B-GGUF> | 4B; `Q4_K_M` is the baseline for constrained machines. | **2.5 GB** | CPU: 6–8 GB total system RAM at short context; NVIDIA: ~4–6 GB VRAM for meaningful full offload. | Smallest practical fully local assistant; fast, low storage, good for navigation/basic explanation. Weakest at complex multi-source reasoning and nuance. | Start 2k–4k context; one request at a time. Good Tier-1 model. |
| **Qwen3-8B-GGUF** — <https://huggingface.co/Qwen/Qwen3-8B-GGUF> | 8B; `Q4_K_M`. | **5.03 GB** | CPU: 12–15 GB RAM; NVIDIA: ~7–9 GB VRAM at short context. | Good balance of quality/size for a household assistant. Still can hallucinate and may be slow on CPU. | Start 4k context; reduce before increasing model size. |
| **Qwen3-14B-GGUF** — <https://huggingface.co/Qwen/Qwen3-14B-GGUF> | 14B; `Q4_K_M`. The verified repository licence is **Apache 2.0**; retain the exact model-card/licence evidence with the artifact. | **9 GB** | CPU: 20–28 GB RAM; NVIDIA: ~11–14 GB VRAM at short/modest context. | Strong general local synthesis/reasoning step up; CPU latency and KV cache are meaningful. | Start 4k–8k; normally the best 32 GB RAM target. |
| **Qwen3-30B-A3B-GGUF** — <https://huggingface.co/Qwen/Qwen3-30B-A3B-GGUF> | 30.5B total / 3.3B active MoE parameters; `Q4_K_M`. Active parameters do **not** remove total weight-storage/residency requirements. | **18.6 GB** | CPU: roughly 28–38 GB RAM for a lean, short-context single-user setup; NVIDIA: ~22–26 GB VRAM. | More capable than small models with MoE efficiency at inference, but total weights, tooling support, and startup/memory needs remain substantial. | Test 4k first. A 24 GB GPU is a reasonable target; CPU 32 GB is experimental/lean, not a promise. |
| **Qwen3-32B-GGUF** — <https://huggingface.co/Qwen/Qwen3-32B-GGUF> | 32B dense; `Q4_K_M` baseline. Higher quantizations only after a measured memory/storage test. | **19.8 GB** | CPU: ~32–45 GB RAM; NVIDIA: ~23–28 GB VRAM at short context. | Strongest listed Q4 dense option for careful cited synthesis; slower and heavier. It still cannot validate facts or replace source reading. | Best fit on 64 GB RAM or ≥24 GB GPU. Start at 4k–8k context. |

\*Memory estimates include room beyond raw weights for the runtime, allocator/buffers, and a short KV cache, but **not** every OS, display driver, GPU-offload mix, batch size, concurrent user, long prompt, or model-runtime variation. Measure with the actual retained version. If it fits only by exhausting RAM/VRAM or swapping, choose a smaller model or shorter context.

#### Hardware-specific selection guide

| Available hardware | First model to keep/test | Disk consumed by the verified Q4 model | Intended starting configuration | What not to assume |
|---|---|---:|---|---|
| **8 GB RAM, CPU only** | Qwen3-4B `Q4_K_M` | 2.5 GB | 2k context, one user, close other applications, no large local index loaded into memory. | It may still be tight depending on OS and integrated graphics. Do not expect reliable long-document synthesis. |
| **16 GB RAM, CPU only** | Qwen3-8B `Q4_K_M`; retain 4B fallback | 5.03 GB (+2.5 GB fallback if retained) | 2k–4k context, one user. | A 14B model may start only with unacceptable paging; model start is not operational usability. |
| **32 GB RAM, CPU only** | Qwen3-14B `Q4_K_M`; retain 8B/4B fallbacks | 9 GB (+ fallbacks as desired) | 4k–8k context, measured KV cache, one user. | 30B-A3B/32B Q4 can be a lean short-context experiment only; do not make them the sole model on this hardware. |
| **64 GB RAM, CPU only** | Qwen3-32B `Q4_K_M` or 30B-A3B Q4; retain 14B fallback | 19.8 GB / 18.6 GB | 4k–8k context, one user; test response latency and thermal/power budget. | Large context, parallel requests, or a higher quantization still needs measurement. |
| **NVIDIA 6 GB VRAM** | Qwen3-4B `Q4_K_M` | 2.5 GB | Full/near-full GPU offload at 2k–4k context, if runtime and display allocation allow. | A nominal 6 GB card rarely leaves 6 GB usable; leave headroom for driver/display/KV cache. |
| **NVIDIA 8 GB VRAM** | Qwen3-8B `Q4_K_M` is marginal; retain 4B fallback | 5.03 GB | Small context, one user; consider partial CPU offload if needed. | “Weights fit” does not mean a stable full-offload interactive session. |
| **NVIDIA 12 GB VRAM** | Qwen3-14B `Q4_K_M` | 9 GB | Modest 2k–4k context; test with display use and actual CUDA/runtime. | Long context or concurrent RAG can exhaust VRAM; use 8B fallback. |
| **NVIDIA 24 GB VRAM** | Qwen3-30B-A3B or Qwen3-32B `Q4_K_M` | 18.6 / 19.8 GB | 2k–8k context after measurement; retain 14B fallback. | Both weight size and KV cache compete for VRAM; a 24 GB label does not guarantee every runtime/configuration fits. |
| **NVIDIA 48 GB VRAM** | Qwen3-32B higher quantization candidate after an actual artifact check; Q4 remains a robust fallback | Q4 is 19.8 GB; resolve actual Q8 artifact size before budgeting it | Test Q4 first; then select a legitimate higher-quantization artifact only if runtime headroom and disk budget are documented. | Do not invent or pre-budget an unverified Q8 filename/size; higher quality is not a substitute for citations. |

#### Context, runtime, and RAG limits

- Qwen documentation identifies a **32,768-token trained context**. A **131,072-token** window requires YaRN; Qwen cautions that static YaRN can degrade short-context quality. Use YaRN only if a measured task truly needs it. Official guidance: <https://qwen.readthedocs.io/en/stable/inference/transformers.html> and <https://qwen.readthedocs.io/en/latest/deployment/vllm.html>.
- Qwen’s deployment guidance can reserve a large default context budget (notably 40,960 tokens in a vLLM-oriented setting). Lower the configured context before concluding a model cannot fit. The goal is **retrieval**, not stuffing books into a prompt.
- Initial operational setting: 2k–4k context on constrained equipment; 4k–8k on 32/64 GB or suitable GPU; retrieve 3–8 short, provenance-rich chunks; use lexical search/reranking to keep evidence compact.
- Keep a small model fallback and a no-AI path. Battery-limited CPU inference may be too slow/energy-expensive during an outage; Kiwix/PDF/FTS/paper remain the primary path.
- Store source code/binaries, model cards, licences, checksums, exact launch command, environment/package lockfile or wheelhouse where lawful, and a known-good answer test for each tested hardware family. Do not rely on an installer that must phone home.

### Minimal fully offline implementation sequence

1. Install/run a retained, verified `llama.cpp` release on a noncritical workstation and load one official Qwen GGUF locally. Block automatic cloud fallback/telemetry; use local files only.
2. Start with a **manual source-citation workflow**: human searches/open originals, then asks the model to explain only copied, permitted, cited excerpts. This is useful before any index exists.
3. Build a SQLite FTS5 database only for sources approved `LOCAL_FTS_OK`; show results in a human UI that links back to the original. Enforce a technical process rule that this database cannot be passed to the model.
4. Build extraction/chunk/vector retrieval only from `RAG_ALLOWLIST` files after ledger validation. Each chunk stores `source_id`, original SHA-256, title, edition/date, page/section, extracted-output SHA-256, chunk ID, and rights-review ID.
5. Retrieve lexically and semantically; optionally rerank; reject any chunk without provenance. Present the retrieved-evidence block before generating synthesis.
6. Test offline with Wi-Fi disabled: model load, source lookup, citation rendering, reader opening, index rebuild, low-RAM fallback, and backup restoration. Save only nonprivate test transcripts.

## 5. Integrity, backup, and long-term preservation architecture

### Threat model and design response

| Failure / threat | Primary prevention | Detection | Recovery path |
|---|---|---|---|
| Accidental deletion/overwrite | Read-only discipline for canonical completed folders; staging/quarantine; do not work on sole copy. | `--check-unexpected` manifest run, ledger/path mismatch, backup comparison. | Restore exact verified file from separate physical duplicate; record incident. |
| Silent corruption / bit rot | Avoid full SSD, safe eject, stable power/cable, duplicate media, immutable manifests, optional parity for selected stable sets. | SHA-256 manifest; file-open/playback tests; parity verification. | Recover from duplicate or tested PAR2 only if original/copy provenance is clear; regenerate derived indexes. |
| SSD/enclosure/controller failure | Separate physical copy; known-good cable; do not assume SMART works through USB. | SMART where supported; OS I/O errors; slow reads; hash failure. | Stop writing; clone/image first using ddrescue to a different healthy device with mapfile; recover only copies. |
| Loss/theft/privacy exposure | Keep public library separate from encrypted vault; physical security; minimize sensitive data. | Inventory/replacement log. | Restore encrypted vault from separate encrypted backup; rotate exposed credentials when services return. |
| Reader/OS obsolescence | Multiple open formats; retain readers/installers/source/docs/OS media; annual boot/open tests. | Test matrix in logs. | Use retained Linux/Windows recovery media or migrate files before the last reader stops working. |
| Source becomes outdated or rights change | Ledger review dates, current local-plan review, version comparison, rights evidence. | Scheduled review; publisher change notice when online. | Keep known-good old reference labeled obsolete; acquire/verify successor; revoke derived indexes if needed. |
| Human error during recovery | Printed “clone first” guide; read-only inspection; practice on disposable media. | Test records and mapfiles. | Pause, preserve original, use a second operator/known-good procedure; never repair in place. |

### GPT, file-system, and encryption decisions

1. Use **GPT**, not MBR, and record the physical SSD serial, partition labels, volume serial/UUID, actual decimal sizes, tool/version, initial SMART output, and photo/screenshot in `templates/partition-record.md`.
2. Format `BOOTTOOLS` as **exFAT** for broad emergency read access. exFAT has no journaling; it is a convenience volume, not the only copy of critical material. Safely eject it and verify its manifest after updates.
3. Format `CIVLIB` as **NTFS** for a Windows-centered primary library and robust handling of large files. Test the actual Linux/macOS/offline recovery environment before an emergency; macOS often reads but does not natively write NTFS. If your real environment needs cross-platform writing more than NTFS behavior, document a deliberate exFAT alternative and compensate with more frequent verification/backup—not an undocumented mix.
4. Format `FAMILYVAULT` as **NTFS** and place one or more **VeraCrypt containers** inside it. Use a robust passphrase, retain the actual VeraCrypt installer/manual/licence locally, and create/store verified **container header backups** separately from the sole container.
5. Do not store passwords, recovery keys, seed phrases, all recovery instructions, or unencrypted identity scans next to encrypted containers. Encryption cannot recover a forgotten passphrase, failed controller, overwritten header, or deleted file.
6. Never rely on one massive container as the sole personal archive. Separate “documents,” “photos,” and “working/private” containers so that a local failure is bounded and backup/verification is tractable.

### Acquisition, hashing, and manifest workflow

```text
official source → 90_Staging_Unverified → verify publisher hash/signature if available
                → capture rights evidence + ledger row + local SHA-256
                → open/test native reader → move to canonical subject folder
                → make/update immutable manifest → replicate to physical duplicate
                → (only after rights approval) FTS/RAG derivative build
```

- Use the supplied `acquisition-ledger.csv` fields: resource ID; title; publisher; collection; official landing URL; resolved direct URL; retrieval UTC; version/publication date; format; byte count; publisher checksum/signature; local SHA-256; local path; rights class/claim/evidence; AI-ingestion evidence; exact state; approver; attribution/derivative obligations; opener; review date; priority; tier; notes.
- Calculate source integrity independently of file name or cloud metadata. `tools/record_acquisition.py` calculates a local SHA-256 and defaults to `REFERENCE_ONLY`; it does not download or decide rights.
- Verify a publisher checksum/signature **before** trusting content whenever one is supplied. Record how it was verified, including key fingerprint/signature tool/version when applicable. A matching locally generated hash alone proves only that two local copies match.
- Freeze a completed tier by creating a deterministic SHA-256 manifest. Keep one manifest in the volume, one on the duplicate medium, and one small printed/exported index that identifies version/date and manifest hash. Do not overwrite a known-good baseline after a failed check.

Example commands:

```bash
# Create a baseline after the tier is stable. Mutable logs and the manifest folder are excluded.
python3 tools/sha256_manifest.py create /mounted/CIVLIB \
  --manifest /mounted/CIVLIB/00_Admin/03_Manifests/civlib-tier1-sha256.tsv \
  --exclude '00_Admin/03_Manifests/*' \
  --exclude '00_Admin/05_Logs/*' \
  --exclude '90_Staging_Unverified/*' \
  --exclude '91_Quarantine/*'

# Verify later. A nonzero exit code is an incident, not an invitation to regenerate the baseline.
python3 tools/sha256_manifest.py verify /mounted/CIVLIB \
  --manifest /mounted/CIVLIB/00_Admin/03_Manifests/civlib-tier1-sha256.tsv \
  --exclude '00_Admin/03_Manifests/*' \
  --exclude '00_Admin/05_Logs/*' \
  --exclude '90_Staging_Unverified/*' \
  --exclude '91_Quarantine/*' \
  --check-unexpected
```

### SMART, file-open, and parity regimen

- Install and retain `smartctl`/smartmontools but expect some USB bridges/portable SSDs to suppress SMART. Test `smartctl` against the **actual enclosure** during setup. Record unsupported status rather than treating it as “healthy.”
- When supported, save raw SMART reports at baseline, quarterly, before/after a long trip, and whenever behavior changes. Look for trends, not one magic pass/fail value.
- At every quarterly check, open a stratified sample: one ISO boot test; a PDF; ePub; ZIM search; map project; video with captions; VeraCrypt test container; reader installer; model load; and a recovery-tool help screen. Log reader/version/host used.
- Generate **PAR2** only for selected, frozen, highly valuable, mostly immutable sets after the first verified duplicate exists. Store parity files on a *different* physical medium or separately allocated location if capacity permits; 5–10% parity is a policy decision after a restoration drill, not a substitute for backups. Record exact PAR2 version, parameters, source manifest hash, and test result.
- Do not use parity as a reason to keep only one SSD. It cannot address theft, fire, controller loss, malicious overwrite, forgotten password, or a bad source file copied faithfully.

### Backup and duplication plan

| Copy | Contents | Medium / location | Encryption | Verification expectation |
|---|---|---|---|---|
| **Primary A** | `BOOTTOOLS`, `CIVLIB`, `FAMILYVAULT` | The portable 2 TB SSD in hand | Public library normally unencrypted; vault containers encrypted | Full Tier-1 manifest after build; full library at least annually. |
| **Duplicate B** | Exact/carefully versioned copy of public library + encrypted vault backup | A separate physical drive of equal/larger capacity, stored away from Primary A | Vault remains encrypted in transit/rest | Verify hashes after every replication and at least semiannually for Tier 1/annually for all. |
| **Optional offline C** | Highest-value Tier-1 public set + encrypted vault backup + boot/recovery kit | A third drive stored in a different building / trusted secure location | Vault encrypted | Quarterly/annual rotation based on accessibility; test actual restore. |
| **Paper bridge** | Contacts, maps, boot/recovery steps, inventory, medical summary, library index | Water-resistant paper copies in separate locations | Physical access controls | Review every six months and after key changes. |

Keep duplicate B disconnected when not copying/verifying; a permanently attached backup is vulnerable to the same electrical, malware, accidental-deletion, theft, and human-error event. If transport/sharing is a risk, encrypt the backup vault and control access separately. Do not rely on cloud-only storage for an offline recovery design.

### Verification, review, and replacement schedule

| Interval / trigger | Do this | Record in |
|---|---|---|
| At every acquisition | Verify publisher hash/signature where available; calculate local SHA-256; record source/rights/version/bytes; open/test file; decide initial state. | Acquisition ledger and acquisition log. |
| After any copy/update | Verify copied file/tree against source manifest before deleting any older known-good copy. | Verification log. |
| Monthly while actively building | Check free space, cable/enclosure behavior, current staging content, vault mount test, and backup currency. | Hardware/verification log. |
| Quarterly | SMART capture if supported; full Tier-1/`BOOTTOOLS` manifest; stratified all-format open/boot/model/map test; inspect physical case/cable. | SMART + verification log. |
| Every six months | Full vault-container hash/restore drill on a copy; contacts/paper bridge/local map review; duplicate B check. | Vault/verification/replacement log. |
| Before monsoon and during local hazard season | Refresh district plan, local contacts, routes, hazard maps, current official warning procedures, water/food inventory. | Emergency/local continuity log. |
| Annually | Full primary and duplicate manifests; full reader/installer/OS boot test; source/version/rights review; test local AI citation output; compare hardware compatibility. | Verification/replacement/ledger records. |
| Every 3–5 years, or sooner after failures/SMART concerns | Migrate to new independently tested media; do not wait for total failure. Verify old → new → duplicate hashes before retiring old source. | Replacement schedule and manifests. |
| At 10 years and 15–20+ years | Treat all media, cables, readers, and operating-system assumptions as migration candidates. Rebuild on contemporary, tested storage; retain an old-reader/emulator path until representative access tests pass. | Long-term migration report. |

### Failure and recovery protocol

1. **Stop writes** if the SSD becomes slow, disconnects, mounts read-only, reports I/O errors, fails a hash, or has concerning SMART symptoms. Photograph/log exact messages and device identity.
2. Do **not** run CHKDSK, fsck repair, partition restoration, “fix bad sectors,” filesystem repair, or data-recovery writes on the only failing original.
3. Attach the source as safely/read-only as practical, identify source and destination serials twice, and use GNU ddrescue to clone/image it to a **different healthy device**. Preserve the ddrescue mapfile on separate media and make a copy of that mapfile.
4. Verify the clone/image as far as possible; conduct TestDisk/PhotoRec/DMDE inspection/recovery only against the clone/image or another copy. Export recovered objects to a different destination with provenance notes.
5. Compare recovered objects to manifests/ledger. Quarantine uncertain files. Do not overwrite a healthy baseline from a partially recovered source.
6. Replace the physical drive and rebuild from independently verified copies. Record the incident, exact tools/versions, mapfile location, what was recovered, and what remains uncertain.

### 10–20+ year migration rules

- Prefer durable/open, widely supported formats: UTF-8 text/HTML, PDF/A when authoring is under your control, PDF originals unchanged, ePub, ODF, CSV, SQLite, GeoPackage, GPX/KML/GeoJSON, PNG/JPEG/TIFF, FLAC/Opus, MP4/WebM with captions, and raw original source formats where their authenticity matters.
- Preserve the original **and** any authorized derivative. Never replace a source scan/PDF with an OCR or converted copy; derivatives must point to original SHA-256.
- Retain current plus one known-good previous reader/runtime/installer/driver release for each important platform. Keep source/licence/docs where redistribution allows it.
- Maintain a hardware inventory: computer model, OS, CPU architecture, RAM, GPU/VRAM/driver, USB ports, cable type, reader versions, boot test date, and model test result. Include a low-power CPU-only plan.
- At every migration, preserve a dated read-only snapshot/manifest of the old archive until new media, readers, selected samples, maps, encrypted-vault restore, and AI citation workflow all pass. Two matching new copies are better than one “successful” copy.
- Treat format and rights review as ongoing: a format may remain readable while a current policy changes what derivatives/indexes you may keep/share. Revoke/rebuild derived data as needed; originals and evidence remain auditable.

## 6. Numbered build order — empty SSD to operational library

1. **Inventory before buying/downloading.** Record the SSD’s exact model/serial, cable, adapters, host computers, CPU architecture, RAM, NVIDIA GPU/VRAM if any, OS versions, external power options, printers, phones, radios, and the tools actually owned. Fill `templates/hardware-inventory.csv` and `templates/replacement-schedule.csv`.
2. **Acquire a separate healthy backup drive before treating the SSD as a library.** Prefer equal/larger capacity and a different purchase batch/enclosure. Plan a physically separate storage location. A single SSD is not a preservation system.
3. **Create paper first.** Fill emergency contacts, household rendezvous, local water/medical/hazard/route information in `templates/emergency-contacts-template.md`; print a nonsecret copy. Do not wait for the library to be complete.
4. **Verify host and cable behavior.** On a noncritical computer, check that the SSD mounts reliably, transfers a disposable large test file, safely ejects, remounts, and—if possible—exposes SMART via the real USB bridge. Record results. Do not use a device that already disconnects or errors.
5. **Partition deliberately with a trusted local tool.** Confirm physical serial/size twice. Create GPT partitions: `BOOTTOOLS` 30 GB exFAT; `CIVLIB` 1,470 GB NTFS; `FAMILYVAULT` 300 GB NTFS; leave final 200 GB unallocated. This is destructive—do it only on the intended empty SSD. Complete `partition-record.md` immediately.
6. **Create folder skeletons.** Run the bootstrap helper against the mounted labels, then copy the templates into `CIVLIB/00_Admin/` and remove all `EXAMPLE-DO-NOT-KEEP` rows. Put the tools’ source code and `README`s in `CIVLIB/00_Admin/09_Scripts/` and a tested copy in `BOOTTOOLS`.
7. **Establish the ledger before content.** Make `acquisition-ledger.csv`, `rag-allowlist.csv`, `verification-log.csv`, rights evidence folder, partition record, hardware inventory, replacement schedule, and a plain-language `START-HERE.txt`. Define a human reviewer responsible for rights/state decisions.
8. **Build `BOOTTOOLS` first.** Acquire the exact architecture-compatible Debian Live and Windows recovery/install media, rescue media, ddrescue, TestDisk/PhotoRec, DMDE, smartmontools, 7-Zip, VeraCrypt, Rufus, readers, licences, checksums, manuals, drivers, and firmware as permitted. Verify publisher hashes/signatures and record every artifact.
9. **Practice recovery before storing irreplaceable data.** Boot the retained recovery media on spare/noncritical hardware; create/read a disposable disk image; use ddrescue with a test mapfile only on disposable media; open each recovery manual offline. Label any untested tool `UNTESTED` in the catalogue rather than assuming it works.
10. **Install/retain native readers.** Test PDFs, ePub, HTML, ZIM, GeoPackage/GPX/KML/GeoJSON, CSV/ODS, archive files, video with captions, model files, and encrypted test containers on each intended OS. Store installers, hashes, licences, manuals, and a simple offline opening guide.
11. **Collect Tier-1 local reality before global archives.** Download the current Maharashtra SDMA district plan and Marathi handbook; NDMA/IMD/MSEDCL material; local PHC/hospital/ambulance/veterinary/water contacts; local rainwater/hazard guidance; owned-equipment manuals; and current household maps. Record exact source/version/date and print critical nonsecret pages.
12. **Acquire Tier-1 health/WASH candidates from the official WHO pages.** Keep originals unchanged, start each `REFERENCE_ONLY`, record the landing/direct URLs, date/version, local hash, rights evidence, and opener. Do not OCR/FTS/embed them merely to make them “AI-ready.”
13. **Acquire Tier-1 food/agriculture candidates.** Start with FAO Seed Storage, small-scale poultry, current MPKV/KVK/district-specific materials, food-preservation reference, seed inventory, and locally relevant crop/water notes. Match language and region to the household’s actual needs.
14. **Build the map package.** Download the current Geofabrik India PBF from its official India page; verify/ledger it; retain ODbL attribution. Create a documented Maharashtra subset using a reproducible, logged local tool workflow. Add QGIS, local GPX/KML/GeoJSON/GeoPackage layers, a tested offline mobile map package, and printed maps. Test with all networks off.
15. **Acquire Tier-1 education/reference selectively.** Choose grades/languages from NCERT/e-Balbharati, a small dictionary/ZIM set, Kiwix Reader, and a few high-value reference texts. Respect NCERT/e-Balbharati restrictions; do not repackage, OCR, index, or RAG them without permission.
16. **Build a static metadata catalogue.** Use `tools/build_catalog.py` to generate a local `library-catalog.html`; verify that it links people to provenance, files, readers, and review dates without extracting content. This is the primary “what is here?” interface.
17. **Freeze and duplicate Tier 1.** Hash `BOOTTOOLS` and `CIVLIB` Tier-1 content; inspect failures; create manifests only once stable; copy to duplicate B; verify duplicate hashes; write verification log entries. Keep staging/log directories out of the immutable baseline.
18. **Create the personal vault carefully.** Make small, purpose-separated VeraCrypt test containers first. Verify mounting, a header-backup procedure, and restore from duplicate media. Then add personal records in open, usable formats plus originals. Do not place passwords/recovery keys on the same drive.
19. **Add Tier-2 practical infrastructure depth.** Work through agriculture, irrigation, preservation, veterinary, shelter, plumbing, electrical safety, PV/battery/generator, mechanics, pumps, bicycles, materials, radio/computing/networking, science, navigation, and local equipment manuals. Favor task-focused original resources over massive miscellaneous collections.
20. **Add Tier-2 education and knowledge archives.** Select OpenStax, MIT OCW, Kolibri, Kiwix, public-domain, dictionary, and public reference material only after title/channel-specific rights/size checks. Open and test each archive. Keep a meaningful language balance (Marathi/Hindi/English as useful to the household).
21. **Decide FTS/RAG rights separately.** For each file, complete `rights-review-checklist.md`. If approved only for local search, use `LOCAL_FTS_OK` and isolate that database from all model paths. If approved for RAG, add matching ledger and allowlist rows; run `validate_ledger.py`; then extract/index only that frozen hash.
22. **Deploy the small AI first.** Retain a verified `llama.cpp` release and Qwen3-4B Q4_K_M; run it offline with short context. Confirm it can explain manually supplied permitted excerpts and print the required evidence/synthesis/uncertainty blocks. Log CPU/RAM/temperature/power/latency and retain no private chat history.
23. **Scale AI only after test evidence.** Add 8B for 16 GB RAM, 14B for 32 GB, and 30B-A3B/32B for 64 GB/24 GB GPU only if the exact system has enough headroom. Keep 4B/8B fallbacks. Do not download a bigger model just because nominal storage permits it.
24. **Build a narrow RAG index.** Run `build_rag_ingest_manifest.py`; use only its approved, re-hashed sources; preserve page/section provenance; version the embedding/reranker/index; and verify citations with human spot checks. Rebuild index on a test source to prove reproducibility; keep originals and native-reader access primary.
25. **Add Tier 3 conservatively.** Use the remaining 300 GB content allowance for real gaps revealed by drills—e.g., more long-tail technical manuals, science/history, geographically relevant maps, language material, a tested larger model, or a small curated video set. Do not consume the 200 GB `CIVLIB` free margin.
26. **Make paper and low-power access real.** Print the library start sheet, emergency contacts, current local maps, water/power shutoff notes, recovery sequence, and a concise index. Test opening Tier-1 content on the lowest-power computer/phone likely to remain usable.
27. **Run an outage drill.** Disconnect Internet/cellular/Wi-Fi; boot a retained OS; open a WHO candidate in a native reader; search a Kiwix archive; display/print an offline Maharashtra map; open equipment manual; mount a test vault container; run a local model; and restore a test file from duplicate B. Record every failure.
28. **Correct the drill, then re-freeze.** Add missing reader/driver/manual/printed step, fix unopenable format, replace unreliable cable, shorten AI context, or reduce archive size. Re-run hashes, update the ledger/catalog, replicate to B, and retain the previous verified snapshot until the replacement passes.
29. **Maintain the schedule.** Follow the quarterly, semiannual, annual, and 3–5 year checks above. Check current district/emergency/agriculture material before seasonal risks. Document updates instead of silently overwriting old sources.
30. **Migrate before emergency failure.** Every several years, purchase/test newer storage, copy and independently verify every frozen tier/vault/reader/installer/manifest, test old and new media on real hosts, then maintain at least two verified physical copies. The library remains resilient only while it is actively maintained.

### Companion hardware and physical readiness (not stored on the SSD)

A self-contained library needs a way to power and read it. Keep and periodically test:

| Item | Minimum role | Maintenance note |
|---|---|---|
| Two compatible reading hosts where feasible | One primary low-power laptop/tablet/phone and one independent fallback able to read the SSD or copied Tier-1 media | Record OS/architecture/ports; test Tier 1 fully offline at least annually. |
| Known-good data cables, adapters, and a powered USB hub if needed | Portable SSD and boot-media access can fail because of a cable/adapter rather than the drive | Label/test each cable; retain at least two compatible spares. |
| Low-power power plan | Charged power bank/UPS/solar-capable charging setup appropriate to the household, plus DC/AC adapters actually tested with hosts | Do not improvise battery chemistry, mains wiring, or PV protection. Retain manuals and use qualified help. |
| Paper maps, contacts, index, and quick procedures | Works when no device, battery, or reader remains | Keep copies in at least two protected places; revise on the schedule. |
| Basic physical protection | Shock-resistant case, desiccant only if manufacturer-safe, stable storage temperature, inventory label, and separate duplicate location | Do not rely on waterproof/shock claims without a backup. |
| A small sacrificial USB/disk set | Lets you practice boot/recovery/imaging without endangering the archive | Mark clearly **TEST ONLY** and refresh periodically. |

---

## Working files included with this plan

- [`templates/acquisition-ledger.csv`](templates/acquisition-ledger.csv)
- [`templates/rag-allowlist.csv`](templates/rag-allowlist.csv)
- [`templates/rights-review-checklist.md`](templates/rights-review-checklist.md)
- [`templates/rag-answer-contract.md`](templates/rag-answer-contract.md)
- [`templates/verification-log.csv`](templates/verification-log.csv)
- [`templates/replacement-schedule.csv`](templates/replacement-schedule.csv)
- [`templates/hardware-inventory.csv`](templates/hardware-inventory.csv)
- [`templates/partition-record.md`](templates/partition-record.md)
- [`templates/emergency-contacts-template.md`](templates/emergency-contacts-template.md)
- [`templates/recovery-quick-guide.md`](templates/recovery-quick-guide.md)
- [`tools/bootstrap_library.py`](tools/bootstrap_library.py)
- [`tools/record_acquisition.py`](tools/record_acquisition.py)
- [`tools/validate_ledger.py`](tools/validate_ledger.py)
- [`tools/build_catalog.py`](tools/build_catalog.py)
- [`tools/build_rag_ingest_manifest.py`](tools/build_rag_ingest_manifest.py)
- [`tools/sha256_manifest.py`](tools/sha256_manifest.py)

These are intentionally offline/no-download utilities. Test them on a disposable directory before touching a real mounted library volume.
