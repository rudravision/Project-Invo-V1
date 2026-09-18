# Storage incident quick guide — clone first

> Print this after filling device names and recovery-media locations. This is a guardrail, not a replacement for the retained ddrescue/manual documentation.

## If the library SSD misbehaves

1. **Stop writing.** Do not download, sync, repair, reformat, or run CHKDSK/fsck against the only source.
2. Photograph/log the error, current date/time, cable/host, and the physical drive label/serial.
3. Try one known-good cable/host only if it does not trigger writes. Do not repeatedly power-cycle a failing drive.
4. Identify a separate healthy destination drive with enough capacity. Record source and destination serials twice.
5. Boot the tested recovery environment. Read the stored GNU ddrescue manual before starting.
6. Clone/image the source first and preserve a copy of the ddrescue mapfile on separate media.
7. Perform TestDisk/PhotoRec/DMDE/repair work only on the clone/image/copy, exporting recovered files to another destination.
8. Compare outputs to the last known-good manifest and acquisition ledger. Quarantine uncertain files.
9. Replace the failing media and restore from independently verified duplicates. Record the incident and any unrecovered files.

## Fill before an emergency

- Primary SSD serial:
- Duplicate B serial/location:
- Optional off-site C serial/location:
- Tested recovery-media label/version:
- GNU ddrescue manual path:
- Last known-good `BOOTTOOLS` manifest:
- Last known-good `CIVLIB` manifest:
- Last successful verification UTC:
- Person who can assist:

**Never repair the only failing source in place.**
