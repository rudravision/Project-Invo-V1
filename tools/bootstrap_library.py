#!/usr/bin/env python3
"""Create a non-destructive folder skeleton for an offline recovery library.

This tool never partitions or formats a device. It creates directories only after
an explicit --apply. Run it from a working computer, not from a failing device.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROFILES: dict[str, list[str]] = {
    "civlib": [
        "00_Admin/00_Start_Here",
        "00_Admin/01_Ledgers",
        "00_Admin/02_Catalogs/01_Metadata",
        "00_Admin/02_Catalogs/02_Local_FTS_No_LLM",
        "00_Admin/02_Catalogs/03_Static_HTML",
        "00_Admin/03_Manifests",
        "00_Admin/04_Rights_Evidence",
        "00_Admin/05_Logs",
        "00_Admin/06_Hardware_Drivers",
        "00_Admin/07_Software_Licenses",
        "00_Admin/08_Offline_Readers",
        "00_Admin/09_Scripts",
        "01_Emergency/01_Quick_Cards",
        "01_Emergency/02_India_Maharashtra",
        "01_Emergency/03_Local_Plans_Contacts",
        "01_Emergency/04_Hazard_Training",
        "02_Health/01_Emergency_Care",
        "02_Health/02_Maternal_Newborn_Child",
        "02_Health/03_Nutrition_Public_Health",
        "02_Health/04_WASH_IPC",
        "02_Health/05_Reference_Only_Clinical",
        "03_Water_Food_Agriculture/01_Water_WASH",
        "03_Water_Food_Agriculture/02_Food_Storage_Preservation",
        "03_Water_Food_Agriculture/03_Soil_Crops_Irrigation",
        "03_Water_Food_Agriculture/04_Seeds_Botany",
        "03_Water_Food_Agriculture/05_Livestock_Veterinary",
        "03_Water_Food_Agriculture/06_Fisheries",
        "04_Shelter_Utilities_Energy/01_Shelter_Construction",
        "04_Shelter_Utilities_Energy/02_Carpentry_Plumbing",
        "04_Shelter_Utilities_Energy/03_Electrical_Safety",
        "04_Shelter_Utilities_Energy/04_Solar_Batteries_Generators",
        "05_Mechanics_Manufacturing/01_Engines_Pumps_Vehicles",
        "05_Mechanics_Manufacturing/02_Bicycles_Tools",
        "05_Mechanics_Manufacturing/03_Machining_Welding",
        "05_Mechanics_Manufacturing/04_Materials",
        "06_Science_Navigation_Maps/01_Mathematics",
        "06_Science_Navigation_Maps/02_Physics_Chemistry_Biology",
        "06_Science_Navigation_Maps/03_Geography_Geology_Weather",
        "06_Science_Navigation_Maps/04_Navigation",
        "06_Science_Navigation_Maps/05_India_Maharashtra_Maps",
        "06_Science_Navigation_Maps/06_GPX_KML_GeoJSON_Local_Layers",
        "07_Computing_Communications/01_Radio_Legal_Readiness",
        "07_Computing_Communications/02_Radio_Software_Manuals",
        "07_Computing_Communications/03_Computer_Hardware",
        "07_Computing_Communications/04_Networking",
        "07_Computing_Communications/05_Programming_Linux_Windows",
        "07_Computing_Communications/06_Offline_Software_Docs",
        "08_Education_Language_Humanities/01_Primary_Secondary",
        "08_Education_Language_Humanities/02_University_STEM",
        "08_Education_Language_Humanities/03_Dictionaries_Languages",
        "08_Education_Language_Humanities/04_History_Law_Civics",
        "08_Education_Language_Humanities/05_Public_Domain_Books",
        "09_Reference_ZIM/01_Kiwix_Archives",
        "09_Reference_ZIM/02_Catalog_And_Licences",
        "10_Offline_AI_Index/01_Models",
        "10_Offline_AI_Index/02_Runtimes",
        "10_Offline_AI_Index/03_Allowlist_Records",
        "10_Offline_AI_Index/04_Extracted_Allowlisted_Text",
        "10_Offline_AI_Index/05_Indexes",
        "10_Offline_AI_Index/06_Configurations",
        "10_Offline_AI_Index/07_Test_Transcripts",
        "11_Curated_Video/01_Emergency",
        "11_Curated_Video/02_Skills",
        "12_Local_Continuity/01_Family_Plan_Nonsecret",
        "12_Local_Continuity/02_Local_Gazetteer",
        "12_Local_Continuity/03_Print_Queue",
        "90_Staging_Unverified",
        "91_Quarantine",
        "99_Recovery_Exports",
    ],
    "boottools": [
        "00_Start_Here",
        "01_Bootable_ISOs",
        "02_OS_Installers",
        "03_Recovery_Tools",
        "04_Portable_Apps",
        "05_Drivers_Firmware",
        "06_Documentation_Licences",
        "07_Checksums_Manifests",
        "08_Test_Logs",
        "90_Staging_Unverified",
    ],
    "familyvault": [
        "00_Start_Here",
        "01_Encrypted_Containers",
        "02_Container_Header_Backups",
        "03_Encrypted_Backup_Exports",
        "04_Nonsecret_Recovery_Notes",
        "05_Verification_Logs",
    ],
}

START_TEXT: dict[str, str] = {
    "civlib": """OFFLINE RECOVERY LIBRARY — START HERE

This volume contains an offline reference library. It is not a substitute for
training, qualified medical care, engineering review, official emergency orders,
or current local law.

1. Read 00_Admin/00_Start_Here and the current acquisition ledger.
2. Use native readers or Kiwix first. Check a document's RAG state before using
   any AI function.
3. REFERENCE_ONLY: open only; do not extract, index, embed, or send to an LLM.
   LOCAL_FTS_OK: locally searchable, but never pass text/results to a model.
   RAG_ALLOWLIST: only explicit approved sources may be extracted and retrieved.
4. Run a hash verification before depending on unfamiliar or long-stored files.
5. Record changes, new downloads, and failed checks in 00_Admin/05_Logs.

No password, recovery key, or confidential record belongs in this file.
""",
    "boottools": """BOOTTOOLS — START HERE

This volume is intentionally unencrypted so a working computer can access
recovery tools. Verify the current manifest before use. Test every bootable ISO
and portable tool on non-critical hardware before an emergency.

Never run repair, CHKDSK, partition restoration, or recovery writes against the
only failing source device. First clone/image it to a separate healthy device,
using GNU ddrescue with a preserved mapfile when applicable.
""",
    "familyvault": """FAMILYVAULT — START HERE

This folder holds VeraCrypt containers and non-secret recovery notes. Create and
open containers only with a verified local VeraCrypt installer/manual. Maintain
separate, tested encrypted backups and separately stored VeraCrypt header backups.

Do not put passwords, recovery keys, or complete access instructions in this
unencrypted file. Loss of passwords or headers can make data permanently
unrecoverable. Encryption does not replace backup or checksum verification.
""",
}


def safe_target(raw: str) -> Path:
    target = Path(raw).expanduser().resolve()
    dangerous = {Path("/").resolve(), Path.home().resolve()}
    if target in dangerous:
        raise ValueError(f"refusing unsafe target: {target}")
    if not target.exists() or not target.is_dir():
        raise ValueError(f"target must be an existing directory: {target}")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", help="existing mounted-volume directory to populate")
    parser.add_argument("--profile", choices=sorted(PROFILES), default="civlib")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually create folders (without this flag the tool only prints the plan)",
    )
    args = parser.parse_args()

    try:
        target = safe_target(args.target)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    planned = [target / relative for relative in PROFILES[args.profile]]
    start_file = target / "START-HERE.txt"
    print(f"Profile: {args.profile}\nTarget:  {target}")
    for path in planned:
        status = "exists" if path.exists() else "create"
        print(f"{status:7} {path.relative_to(target)}")
    print(("exists" if start_file.exists() else "create").ljust(7), "START-HERE.txt")

    if not args.apply:
        print("\nDry run only. Re-run with --apply after confirming the mounted volume.")
        return 0

    for path in planned:
        path.mkdir(parents=True, exist_ok=True)
    if not start_file.exists():
        start_file.write_text(START_TEXT[args.profile], encoding="utf-8", newline="\n")
    print("\nCreated missing directories. Existing files were not overwritten.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
