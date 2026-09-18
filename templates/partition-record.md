# Storage layout record

> Fill this in immediately after partitioning and print one copy. Do **not** place passwords, recovery keys, or personal identifying information in this unencrypted file.

- Prepared UTC:
- Operator:
- SSD manufacturer/model:
- Physical serial number:
- Capacity reported by operating system:
- Partitioning utility and version:
- USB cable/adapter tested:

| Order | GPT partition label | Intended size (decimal GB) | File system | Allocation unit / cluster | Volume UUID / serial | Purpose | Encrypted? |
|---:|---|---:|---|---|---|---|---|
| 1 | `BOOTTOOLS` | 30 | exFAT | record actual default | | boot/recovery tools; readable across systems | No |
| 2 | `CIVLIB` | 1,470 | NTFS | record actual default | | public/offline recovery library | No by default |
| 3 | `FAMILYVAULT` | 300 | NTFS | record actual default | | VeraCrypt container storage only | VeraCrypt containers inside |
| 4 | Unallocated reserve | 200 | — | — | — | leave unformatted; not a promised SSD over-provisioning setting | — |

## Evidence retained

- [ ] Screenshot/photo of partition map
- [ ] `diskpart list disk / list volume` or `lsblk -f` output
- [ ] Initial SMART report, if USB bridge supports it
- [ ] Initial `BOOTTOOLS` and `CIVLIB` manifests
- [ ] Backup location and test date recorded
