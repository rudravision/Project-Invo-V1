"""
Canonical handling of NSE index names.

NSE publishes index names in `ind_close_all_<ddmmyyyy>.csv` in mixed case and
with inconsistent spacing and wording: "Nifty 50", "Nifty Bank",
"Nifty Financial Services", "Nifty Healthcare Index", "NIFTY MIDSMALL
HEALTHCARE", "India VIX". We store them verbatim, which is right - the raw
record should match the source.

The bug this module exists to prevent: comparing those stored names against
hard-coded uppercase constants like "NIFTY 50". That silently matched
nothing, so a database holding 172 indices reported "No index data yet", the
heatmap showed no sectors at all, and strongest/weakest sector were blank.

Everything here compares on a normalised key instead, and every lookup goes
through one function.
"""

from __future__ import annotations

import re

_WS = re.compile(r"[\s_]+")
_PUNCT = re.compile(r"[^A-Z0-9 ]")
_DIGIT_RUN = re.compile(r"(?<=[A-Z])(?=[0-9])")


def norm(name: str | None) -> str:
    """Normalise an index name for comparison.

    'Nifty Healthcare Index' -> 'NIFTY HEALTHCARE INDEX'
    'nifty  pvt   bank'      -> 'NIFTY PVT BANK'
    """
    if not name:
        return ""
    s = _PUNCT.sub(" ", str(name).upper())
    # NSE is inconsistent about the space before a number: both "Nifty 50"
    # and "Nifty50" appear in its files.
    s = _DIGIT_RUN.sub(" ", s)
    return _WS.sub(" ", s).strip()


# Sector indices we want on the heatmap. Each entry is
#   display label -> the accepted spellings NSE has used.
SECTOR_INDEX_ALIASES: dict[str, tuple[str, ...]] = {
    "Bank": ("NIFTY BANK",),
    "IT": ("NIFTY IT",),
    "Auto": ("NIFTY AUTO",),
    "FMCG": ("NIFTY FMCG",),
    "Pharma": ("NIFTY PHARMA",),
    "Metal": ("NIFTY METAL",),
    "Realty": ("NIFTY REALTY",),
    "Energy": ("NIFTY ENERGY",),
    "Financial Services": ("NIFTY FINANCIAL SERVICES", "NIFTY FIN SERVICE",
                           "NIFTY FINANCE"),
    "PSU Bank": ("NIFTY PSU BANK",),
    "Private Bank": ("NIFTY PRIVATE BANK", "NIFTY PVT BANK"),
    "Media": ("NIFTY MEDIA",),
    "Healthcare": ("NIFTY HEALTHCARE INDEX", "NIFTY HEALTHCARE"),
    "Consumer Durables": ("NIFTY CONSUMER DURABLES", "NIFTY CONSR DURBL"),
    "Oil & Gas": ("NIFTY OIL AND GAS", "NIFTY OIL & GAS"),
    "Infrastructure": ("NIFTY INFRA", "NIFTY INFRASTRUCTURE"),
    "Commodities": ("NIFTY COMMODITIES",),
    "Consumption": ("NIFTY CONSUMPTION",),
    "PSE": ("NIFTY PSE",),
    "Services": ("NIFTY SERV SECTOR", "NIFTY SERVICES SECTOR"),
}

# Broad market indices worth showing separately from sectors.
BROAD_INDEX_ALIASES: dict[str, tuple[str, ...]] = {
    "Nifty 50": ("NIFTY 50",),
    "Nifty Next 50": ("NIFTY NEXT 50",),
    "Nifty 100": ("NIFTY 100",),
    "Nifty 200": ("NIFTY 200",),
    "Nifty 500": ("NIFTY 500",),
    "Nifty Midcap 100": ("NIFTY MIDCAP 100",),
    "Nifty Smallcap 100": ("NIFTY SMLCAP 100", "NIFTY SMALLCAP 100"),
    "India VIX": ("INDIA VIX",),
}

NIFTY50 = "NIFTY 50"

_SECTOR_LOOKUP = {norm(a): label
                  for label, aliases in SECTOR_INDEX_ALIASES.items()
                  for a in aliases}
_BROAD_LOOKUP = {norm(a): label
                 for label, aliases in BROAD_INDEX_ALIASES.items()
                 for a in aliases}


def sector_label(name: str | None) -> str | None:
    """Display label if `name` is a sector index we track, else None."""
    return _SECTOR_LOOKUP.get(norm(name))


def broad_label(name: str | None) -> str | None:
    return _BROAD_LOOKUP.get(norm(name))


def is_sector(name: str | None) -> bool:
    return norm(name) in _SECTOR_LOOKUP


def is_broad(name: str | None) -> bool:
    return norm(name) in _BROAD_LOOKUP


def is_nifty50(name: str | None) -> bool:
    return norm(name) == NIFTY50


def display(name: str | None) -> str:
    """Short, readable label for any index name."""
    return (sector_label(name) or broad_label(name)
            or re.sub(r"^NIFTY\s+", "", norm(name)).title() or "Unknown")


def pick_row(hm, name_col: str = "index_name", *, which: str = "nifty50"):
    """Return the row of a heatmap frame for a given index, or None.

    `which` is 'nifty50' or an exact alias. Matching is normalised, so it
    works whatever case NSE used that day.
    """
    if hm is None or len(hm) == 0 or name_col not in hm:
        return None
    target = NIFTY50 if which == "nifty50" else norm(which)
    keys = hm[name_col].map(norm)
    hit = hm[keys == target]
    return None if hit.empty else hit.iloc[0]
