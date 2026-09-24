"""
Checking whether a newer version of the program exists.

Why this is not simply "download and install"
---------------------------------------------
The project lives in a **private** GitHub repository. Private means every
request needs a credential, so an unattended download cannot work without
storing a token on the machine - and a stored token is a real security
liability on a trading box. We therefore do the honest thing: we report
precisely what the situation is and what the user can do about it, instead
of a spinner that never finishes.

Three outcomes, each with plain-language guidance:

  UP_TO_DATE   the published version matches the installed one
  UPDATE_READY a newer version is published and reachable
  UNREACHABLE  private repo, no internet, or the URL is wrong - and we say
               which one

Nothing here writes to disk or replaces code. Applying an update is done by
GET_LATEST.bat with the app closed, because replacing files underneath a
running program is how installations get corrupted.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

UP_TO_DATE = "UP_TO_DATE"
UPDATE_READY = "UPDATE_READY"
UNREACHABLE = "UNREACHABLE"

DEFAULT_BRANCH = "arena/01a0cf67-project-invo-v1"
DEFAULT_REPO = "rudravision/Project-Invo-V1"

_VERSION_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)\s*$")


def raw_version_url(repo: str = DEFAULT_REPO,
                    branch: str = DEFAULT_BRANCH) -> str:
    return (f"https://raw.githubusercontent.com/{repo}/{branch}"
            f"/TRADING_AI/VERSION")


def local_version(root: str | Path) -> str:
    p = Path(root) / "VERSION"
    try:
        return p.read_text(encoding="utf-8").strip() or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def parse_version(text: str) -> tuple[int, ...] | None:
    """'2026.09.24.11' -> (2026, 9, 24, 11). None if it is not a version."""
    if not text:
        return None
    m = _VERSION_RE.match(text.strip().splitlines()[0] if text.strip() else "")
    if not m:
        return None
    try:
        return tuple(int(x) for x in m.group(1).split("."))
    except ValueError:
        return None


def is_newer(remote: str, local: str) -> bool:
    r, l = parse_version(remote), parse_version(local)
    if r is None or l is None:
        return False
    # pad so 2026.9.24 and 2026.9.24.1 compare sensibly
    n = max(len(r), len(l))
    return r + (0,) * (n - len(r)) > l + (0,) * (n - len(l))


def _default_fetch(url: str, timeout: float = 8.0):
    import requests

    return requests.get(url, timeout=timeout,
                        headers={"User-Agent": "TRADING_AI-update-check"})


def check(root: str | Path, url: str | None = None,
          fetch: Callable | None = None) -> dict:
    """Compare the installed version against the published one."""
    installed = local_version(root)
    url = url or raw_version_url()
    fetch = fetch or _default_fetch

    try:
        r = fetch(url)
        status = getattr(r, "status_code", 0)
        body = getattr(r, "text", "") or ""
    except Exception as e:  # noqa: BLE001 - offline, DNS, TLS, anything
        return {
            "state": UNREACHABLE, "installed": installed, "latest": None,
            "reason": "no_internet",
            "message": ("Could not reach GitHub to check for updates. Either "
                        "this computer is offline, or a firewall is blocking "
                        "it."),
            "detail": str(e)[:200],
            "what_to_do": "Check your internet connection and try again.",
        }

    if status in (401, 403, 404):
        return {
            "state": UNREACHABLE, "installed": installed, "latest": None,
            "reason": "private_repo",
            "message": ("The project is in a PRIVATE GitHub repository, so "
                        "the program cannot download updates by itself - "
                        "every request needs your login."),
            "what_to_do": (
                "Two ways to fix this permanently:\n"
                "  1. Make the repository public. Then the program can "
                "check and fetch updates on its own, with no password "
                "stored anywhere.\n"
                "  2. Keep it private and install Git for Windows, signing "
                "in once. GET_LATEST.bat will then pull updates directly.\n"
                "Until then: download the ZIP from GitHub in your browser "
                "and run UPDATE_MY_COPY.bat."),
            "http_status": status,
        }

    if status != 200:
        return {
            "state": UNREACHABLE, "installed": installed, "latest": None,
            "reason": "unexpected_status",
            "message": f"GitHub replied with HTTP {status}.",
            "what_to_do": "Try again in a few minutes.",
            "http_status": status,
        }

    latest = (body.strip().splitlines() or [""])[0].strip()
    if parse_version(latest) is None:
        return {
            "state": UNREACHABLE, "installed": installed, "latest": None,
            "reason": "bad_payload",
            "message": ("The update file did not look like a version "
                        "number. The update address may be wrong."),
            "what_to_do": "Tell the developer; the update URL needs fixing.",
        }

    if is_newer(latest, installed):
        return {
            "state": UPDATE_READY, "installed": installed, "latest": latest,
            "message": (f"Version {latest} is available. You have "
                        f"{installed}."),
            "what_to_do": ("Close TRADING_AI, then run GET_LATEST.bat. Your "
                           "database, backups and settings are not touched."),
        }

    return {
        "state": UP_TO_DATE, "installed": installed, "latest": latest,
        "message": f"You are up to date (version {installed}).",
        "what_to_do": "Nothing to do.",
    }
