"""Update checking.

The repository is private, so an unattended download is impossible without
storing a credential. These tests pin the behaviour that matters: the
program must say exactly which obstacle it hit, and must never claim to be
up to date when it simply could not look.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.update import (UNREACHABLE, UP_TO_DATE, UPDATE_READY, api_version_url, check,
                        is_newer, local_version, parse_version,
                        raw_version_url)


class FakeResponse:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text


def root_with(tmp_path, version="2026.09.24.5"):
    (tmp_path / "VERSION").write_text(version + "\n", encoding="utf-8")
    return tmp_path


# ------------------------------------------------------------ versions ----
@pytest.mark.parametrize("raw,expect", [
    ("2026.09.24.11", (2026, 9, 24, 11)),
    ("2026.09.24\n", (2026, 9, 24)),
    ("  1.2  ", (1, 2)),
    ("not a version", None), ("", None),
])
def test_version_parsing(raw, expect):
    assert parse_version(raw) == expect


@pytest.mark.parametrize("remote,local,expect", [
    ("2026.09.24.11", "2026.09.24.5", True),
    ("2026.09.24.5", "2026.09.24.11", False),
    ("2026.09.25", "2026.09.24.11", True),
    ("2026.09.24.1", "2026.09.24", True),      # padded compare
    ("2026.09.24", "2026.09.24", False),
    ("garbage", "2026.09.24", False),          # never "newer" on nonsense
])
def test_version_comparison(remote, local, expect):
    assert is_newer(remote, local) is expect


def test_local_version_missing_file_is_unknown(tmp_path):
    assert local_version(tmp_path) == "unknown"


def test_raw_url_points_at_the_version_file():
    u = raw_version_url()
    assert u.startswith("https://raw.githubusercontent.com/")
    assert u.endswith("/TRADING_AI/VERSION")


# -------------------------------------------------------------- outcomes --
def test_update_available(tmp_path):
    out = check(root_with(tmp_path, "2026.09.24.5"), "http://x",
                fetch=lambda u, **k: FakeResponse(200, "2026.09.24.11"))
    assert out["state"] == UPDATE_READY
    assert out["latest"] == "2026.09.24.11"
    assert "GET_LATEST.bat" in out["what_to_do"]
    assert "not touched" in out["what_to_do"]


def test_already_up_to_date(tmp_path):
    out = check(root_with(tmp_path, "2026.09.24.11"), "http://x",
                fetch=lambda u, **k: FakeResponse(200, "2026.09.24.11"))
    assert out["state"] == UP_TO_DATE
    assert "up to date" in out["message"]


@pytest.mark.parametrize("status", [401, 403, 404])
def test_private_repo_is_explained_not_disguised(tmp_path, status):
    """The real situation today. It must name the cause and the options."""
    out = check(root_with(tmp_path), "http://x",
                fetch=lambda u, **k: FakeResponse(status, ""))
    assert out["state"] == UNREACHABLE
    assert out["reason"] == "private_repo"
    assert "PRIVATE" in out["message"]
    assert "public" in out["what_to_do"]
    assert "Git for Windows" in out["what_to_do"]
    assert "UPDATE_MY_COPY.bat" in out["what_to_do"]


def test_offline_is_reported_as_offline(tmp_path):
    def boom(url, **kw):
        raise OSError("getaddrinfo failed")

    out = check(root_with(tmp_path), "http://x", fetch=boom)
    assert out["state"] == UNREACHABLE
    assert out["reason"] == "no_internet"
    assert "offline" in out["message"]


def test_never_claims_up_to_date_when_it_could_not_look(tmp_path):
    """The failure mode that would matter most: a false all-clear."""
    for resp in (FakeResponse(403, ""), FakeResponse(500, ""),
                 FakeResponse(200, "<html>not a version</html>")):
        out = check(root_with(tmp_path), "http://x",
                    fetch=lambda u, _r=resp, **k: _r)
        assert out["state"] == UNREACHABLE
        assert out["latest"] is None


def test_unexpected_status_is_surfaced(tmp_path):
    out = check(root_with(tmp_path), "http://x",
                fetch=lambda u, **k: FakeResponse(503, ""))
    assert out["reason"] == "unexpected_status"
    assert "503" in out["message"]


# ------------------------------------------------------------ in the app --
def test_endpoint_returns_a_usable_payload(tmp_path):
    from tests.test_gui_api import build_root
    from app.gui.server import create_app

    app = create_app(str(build_root(tmp_path)))
    app.config["TESTING"] = True
    d = app.test_client().get("/api/update/check").get_json()
    # no network in the test environment, so this must be the honest branch
    assert d["state"] in (UNREACHABLE, UP_TO_DATE, UPDATE_READY)
    assert d["installed"]
    assert d["message"]


# ------------------------------------------------- blocked-network route --
def test_api_url_is_a_credential_free_fallback():
    u = api_version_url()
    assert u.startswith("https://api.github.com/repos/")
    assert "TRADING_AI/VERSION" in u
    assert "ref=" in u


def test_falls_back_to_the_api_when_raw_is_blocked(tmp_path):
    """Several Indian ISPs block raw.githubusercontent.com."""
    seen = []

    def fetch(url, **kw):
        seen.append(url)
        if "raw.githubusercontent.com" in url:
            raise OSError("SSL connect error")
        return FakeResponse(200, "2026.09.24.99")

    out = check(root_with(tmp_path, "2026.09.24.12"), fetch=fetch)
    assert out["state"] == UPDATE_READY
    assert out["latest"] == "2026.09.24.99"
    assert any("raw.githubusercontent" in u for u in seen)
    assert any("api.github.com" in u for u in seen)


def test_both_routes_down_reports_offline_once(tmp_path):
    def fetch(url, **kw):
        raise OSError("no route to host")

    out = check(root_with(tmp_path), fetch=fetch)
    assert out["state"] == UNREACHABLE
    assert out["reason"] == "no_internet"
