"""
SSD detection and root-path resolution.

Design rules (from spec sections 19 & 28):
  * NEVER hardcode a Windows drive letter such as E:.
  * Detect a removable/external volume at runtime, on Windows, Linux or macOS.
  * READ-ONLY detection. This module never formats, partitions, erases or
    deletes anything. The only write it performs is creating the TRADING_AI
    folder (and only when explicitly asked via ensure_project_root()).
  * If no SSD is found, fail loudly with a human-readable message rather than
    silently writing to the internal disk.
"""

from __future__ import annotations

import ctypes
import os
import platform
import shutil
import string
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

PROJECT_DIR_NAME = "TRADING_AI"

# Substrings that identify the user's drive. Matched case-insensitively against
# the volume label / model string. Configurable via config/paths.yaml.
DEFAULT_NAME_HINTS = ("sandisk", "extreme", "trading_ai", "trading ai")

# A 2TB SSD reports ~1.8-2.0 TiB. Anything in this band is a plausible match.
MIN_PLAUSIBLE_BYTES = 500 * 1024**3  # 500 GiB


@dataclass
class Volume:
    """A candidate storage volume discovered on this machine."""

    path: str          # mount point / drive root, e.g. "E:\\" or "/media/u/SSD"
    label: str         # volume label or device model, best effort
    fstype: str
    total_bytes: int
    free_bytes: int
    removable: bool    # reported as removable/external by the OS
    source: str        # which detector produced this record

    @property
    def total_gb(self) -> float:
        return self.total_bytes / 1024**3

    @property
    def free_gb(self) -> float:
        return self.free_bytes / 1024**3

    def score(self, hints: Iterable[str] = DEFAULT_NAME_HINTS) -> int:
        """Heuristic confidence that this is the user's external SSD."""
        s = 0
        hay = f"{self.label} {self.path}".lower()
        for h in hints:
            if h and h.lower() in hay:
                s += 50
        if self.removable:
            s += 30
        if self.total_bytes >= MIN_PLAUSIBLE_BYTES:
            s += 10
        # Penalise obvious internal/system roots.
        if self.path.rstrip("\\/").lower() in ("c:", "/", ""):
            s -= 60
        return s

    def to_dict(self) -> dict:
        d = asdict(self)
        d["total_gb"] = round(self.total_gb, 2)
        d["free_gb"] = round(self.free_gb, 2)
        return d


def _usage(path: str) -> tuple[int, int]:
    try:
        u = shutil.disk_usage(path)
        return u.total, u.free
    except OSError:
        return 0, 0


# --------------------------------------------------------------------------- #
# Windows
# --------------------------------------------------------------------------- #
def _detect_windows() -> list[Volume]:
    vols: list[Volume] = []
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    DRIVE_REMOVABLE, DRIVE_FIXED = 2, 3

    bitmask = kernel32.GetLogicalDrives()
    for i, letter in enumerate(string.ascii_uppercase):
        if not (bitmask >> i) & 1:
            continue
        root = f"{letter}:\\"
        dtype = kernel32.GetDriveTypeW(ctypes.c_wchar_p(root))
        if dtype not in (DRIVE_REMOVABLE, DRIVE_FIXED):
            continue  # skip network/CD-ROM/RAM drives

        name_buf = ctypes.create_unicode_buffer(1024)
        fs_buf = ctypes.create_unicode_buffer(1024)
        try:
            kernel32.GetVolumeInformationW(
                ctypes.c_wchar_p(root), name_buf, 1024,
                None, None, None, fs_buf, 1024,
            )
        except OSError:
            pass

        total, free = _usage(root)
        if total == 0:
            continue  # empty card reader etc.

        label = name_buf.value or ""
        removable = dtype == DRIVE_REMOVABLE

        # USB-attached SSDs frequently report DRIVE_FIXED. Ask WMI for the bus
        # type so an external NVMe/SATA enclosure is still classified correctly.
        if not removable:
            if _windows_is_usb(letter):
                removable = True
            if not label:
                label = _windows_model(letter) or ""

        vols.append(Volume(root, label, fs_buf.value or "", total, free,
                           removable, "windows:GetLogicalDrives"))
    return vols


def _powershell(script: str) -> str:
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=25,
        )
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _windows_is_usb(letter: str) -> bool:
    out = _powershell(
        f"(Get-Partition -DriveLetter {letter} -ErrorAction SilentlyContinue |"
        f" Get-Disk).BusType"
    )
    return out.strip().upper() in ("USB", "1394", "THUNDERBOLT")


def _windows_model(letter: str) -> str:
    return _powershell(
        f"(Get-Partition -DriveLetter {letter} -ErrorAction SilentlyContinue |"
        f" Get-Disk).FriendlyName"
    )


# --------------------------------------------------------------------------- #
# Linux
# --------------------------------------------------------------------------- #
def _detect_linux() -> list[Volume]:
    vols: list[Volume] = []
    try:
        out = subprocess.run(
            ["lsblk", "-J", "-b", "-o",
             "NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE,RM,HOTPLUG,MODEL,VENDOR,TRAN"],
            capture_output=True, text=True, timeout=20,
        ).stdout
        import json
        tree = json.loads(out or "{}")
    except Exception:
        return _detect_posix_fallback("linux:fallback")

    def walk(nodes):
        for n in nodes:
            mp = n.get("mountpoint")
            if mp:
                total, free = _usage(mp)
                if total:
                    label = " ".join(
                        x for x in (n.get("vendor"), n.get("model")) if x
                    ).strip()
                    removable = bool(n.get("rm") or n.get("hotplug")) or \
                        (n.get("tran") in ("usb", "thunderbolt"))
                    vols.append(Volume(mp, label, n.get("fstype") or "",
                                       total, free, removable, "linux:lsblk"))
            walk(n.get("children") or [])

    walk(tree.get("blockdevices") or [])
    return vols or _detect_posix_fallback("linux:fallback")


def _detect_posix_fallback(source: str) -> list[Volume]:
    """Scan the conventional external-media mount roots."""
    vols: list[Volume] = []
    roots = ["/media", "/run/media", "/mnt", "/Volumes"]
    for root in roots:
        p = Path(root)
        if not p.is_dir():
            continue
        candidates = list(p.iterdir())
        # /media/<user>/<label> nesting
        for c in list(candidates):
            if c.is_dir():
                try:
                    candidates.extend(c.iterdir())
                except OSError:
                    pass
        for c in candidates:
            if not c.is_dir() or not os.path.ismount(str(c)):
                continue
            total, free = _usage(str(c))
            if total:
                vols.append(Volume(str(c), c.name, "", total, free,
                                   True, source))
    return vols


# --------------------------------------------------------------------------- #
# macOS
# --------------------------------------------------------------------------- #
def _detect_darwin() -> list[Volume]:
    vols: list[Volume] = []
    vol_root = Path("/Volumes")
    if vol_root.is_dir():
        for c in vol_root.iterdir():
            if not c.is_dir():
                continue
            total, free = _usage(str(c))
            if not total:
                continue
            removable = True
            try:
                info = subprocess.run(
                    ["diskutil", "info", str(c)],
                    capture_output=True, text=True, timeout=20,
                ).stdout
                removable = ("Removable Media:" in info and "Removable" in info) \
                    or ("Internal:" in info and "Internal:                  No" in info)
            except (OSError, subprocess.SubprocessError):
                pass
            vols.append(Volume(str(c), c.name, "", total, free,
                               removable, "darwin:/Volumes"))
    return vols


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def list_volumes() -> list[Volume]:
    """Enumerate all mounted volumes. Read-only, never raises."""
    system = platform.system()
    try:
        if system == "Windows":
            return _detect_windows()
        if system == "Linux":
            return _detect_linux()
        if system == "Darwin":
            return _detect_darwin()
    except Exception:
        pass
    return _detect_posix_fallback(f"{system.lower()}:fallback")


def detect_ssd(hints: Iterable[str] = DEFAULT_NAME_HINTS,
               min_score: int = 40) -> Volume | None:
    """Return the most likely external SSD, or None if nothing qualifies.

    Never guesses a drive letter. A None return is a legitimate, expected
    result that callers must handle with a clear error message.
    """
    ranked = sorted(list_volumes(), key=lambda v: v.score(hints), reverse=True)
    if ranked and ranked[0].score(hints) >= min_score:
        return ranked[0]
    return None


class SSDNotFoundError(RuntimeError):
    """Raised when the external SSD cannot be located."""


def human_report(hints: Iterable[str] = DEFAULT_NAME_HINTS) -> str:
    """A human-readable report of what was found. Used by SYSTEM_CHECK."""
    vols = sorted(list_volumes(), key=lambda v: v.score(hints), reverse=True)
    if not vols:
        return "No mounted volumes could be enumerated on this machine."
    lines = [
        f"{'PATH':<28} {'LABEL':<26} {'TOTAL GB':>10} {'FREE GB':>10} "
        f"{'REMOVABLE':>10} {'SCORE':>6}",
        "-" * 96,
    ]
    for v in vols:
        lines.append(
            f"{v.path:<28.28} {v.label:<26.26} {v.total_gb:>10.1f} "
            f"{v.free_gb:>10.1f} {str(v.removable):>10} {v.score(hints):>6}"
        )
    return "\n".join(lines)


def resolve_project_root(explicit: str | None = None,
                         hints: Iterable[str] = DEFAULT_NAME_HINTS) -> Path:
    """Resolve the TRADING_AI root directory.

    Priority:
      1. `explicit` argument (from config or CLI)
      2. TRADING_AI_ROOT environment variable
      3. Auto-detected external SSD -> <ssd>/TRADING_AI

    Raises SSDNotFoundError with actionable guidance when nothing is found.
    """
    if explicit:
        return Path(explicit).expanduser().resolve()

    env = os.environ.get("TRADING_AI_ROOT")
    if env:
        return Path(env).expanduser().resolve()

    ssd = detect_ssd(hints)
    if ssd is None:
        raise SSDNotFoundError(
            "Could not detect your external SanDisk SSD.\n\n"
            "Nothing has been written to your internal disk.\n\n"
            "Fix it with ONE of these:\n"
            "  1. Plug the SSD in and re-run.\n"
            "  2. Set the path explicitly, e.g. on Windows:\n"
            "       set TRADING_AI_ROOT=E:\\TRADING_AI\n"
            "     or on Linux/macOS:\n"
            "       export TRADING_AI_ROOT=/Volumes/SanDisk/TRADING_AI\n"
            "  3. Edit config/paths.yaml and set project_root.\n\n"
            "Volumes currently visible:\n" + human_report(hints)
        )
    return Path(ssd.path) / PROJECT_DIR_NAME


def ensure_project_root(root: Path) -> Path:
    """Create the TRADING_AI tree if absent. Purely additive.

    Existing files and folders are left untouched; mkdir(exist_ok=True) never
    truncates or deletes. No other path on the drive is modified.
    """
    subdirs = [
        "app", "config",
        "data/raw", "data/processed", "data/historical",
        "data/intraday", "data/backup",
        "database", "models/production", "models/experimental",
        "models/archived", "backtests", "paper_trading", "reports",
        "logs", "dashboard", "alerts", "notebooks", "tests", "backups",
        "docs", "scripts",
    ]
    root.mkdir(parents=True, exist_ok=True)
    for sd in subdirs:
        (root / sd).mkdir(parents=True, exist_ok=True)
    return root


def free_space_report(root: Path) -> dict:
    total, free = _usage(str(root))
    return {
        "path": str(root),
        "total_gb": round(total / 1024**3, 2),
        "free_gb": round(free / 1024**3, 2),
        "used_pct": round((1 - free / total) * 100, 1) if total else 0.0,
    }
