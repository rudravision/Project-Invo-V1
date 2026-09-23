"""
Settings: resolves the SSD root and loads YAML config.

Credentials are read ONLY from environment variables or an untracked .env
file on the SSD. They are never written to the repo, never logged and never
committed.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .ssd import (PROJECT_DIR_NAME, SSDNotFoundError, ensure_project_root,
                  free_space_report, resolve_project_root)

log = logging.getLogger(__name__)


@dataclass
class Settings:
    root: Path
    paths: dict = field(default_factory=dict)
    sources: dict = field(default_factory=dict)

    # -- derived directories ----------------------------------------------
    @property
    def db_path(self) -> Path:
        return self.root / "database" / "trading_ai.sqlite"

    @property
    def raw_dir(self) -> Path:
        return self.root / "data" / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.root / "data" / "processed"

    @property
    def historical_dir(self) -> Path:
        return self.root / "data" / "historical"

    @property
    def intraday_dir(self) -> Path:
        return self.root / "data" / "intraday"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    @property
    def reports_dir(self) -> Path:
        return self.root / "reports"

    @property
    def backups_dir(self) -> Path:
        return self.root / "backups"

    @property
    def models_dir(self) -> Path:
        return self.root / "models"

    @property
    def min_free_gb(self) -> float:
        return float(self.paths.get("min_free_gb", 20))

    def free_space(self) -> dict:
        return free_space_report(self.root)

    def source_defaults(self) -> dict:
        return self.sources.get("defaults", {})

    def roles(self) -> dict:
        return self.sources.get("roles", {})

    def source_config(self, name: str) -> dict:
        return (self.sources.get("sources", {}) or {}).get(name, {})


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise SystemExit(f"Could not parse {path}:\n  {e}")


def _config_dir(root: Path) -> Path:
    """Config on the SSD wins; fall back to the config shipped with the code."""
    on_ssd = root / "config"
    if (on_ssd / "paths.yaml").exists():
        return on_ssd
    return Path(__file__).resolve().parents[2] / "config"


def load_settings(explicit_root: str | None = None,
                  create: bool = True) -> Settings:
    """Resolve the project root and load configuration.

    Order: explicit arg -> config/paths.yaml project_root -> $TRADING_AI_ROOT
           -> auto-detected external SSD.
    """
    # Bootstrap config that ships with the source tree.
    shipped = Path(__file__).resolve().parents[2] / "config"
    boot_paths = _load_yaml(shipped / "paths.yaml")
    hints = boot_paths.get("ssd_name_hints") or None

    configured = explicit_root or (boot_paths.get("project_root") or "").strip()
    root = resolve_project_root(configured or None,
                                hints or ("sandisk", "extreme", "trading_ai"))

    # If the resolved path is a drive root rather than the project folder,
    # append TRADING_AI so we never scatter files across the drive.
    if root.name != PROJECT_DIR_NAME and not (root / "database").exists():
        if root.parent == root or root.is_mount():
            root = root / PROJECT_DIR_NAME

    if create:
        ensure_project_root(root)

    cfgdir = _config_dir(root)
    return Settings(
        root=root,
        paths=_load_yaml(cfgdir / "paths.yaml") or boot_paths,
        sources=_load_yaml(cfgdir / "sources.yaml")
        or _load_yaml(shipped / "sources.yaml"),
    )


def load_credentials(root: Path) -> dict[str, str]:
    """Read secrets from the environment, topped up by <root>/config/.env.

    The .env file must never be committed. INSTALL adds it to .gitignore.
    """
    creds: dict[str, str] = {}
    env_file = root / "config" / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            creds[k.strip()] = v.strip().strip('"').strip("'")
    # Environment always overrides the file.
    for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "UPSTOX_API_KEY",
              "UPSTOX_API_SECRET", "UPSTOX_ACCESS_TOKEN", "FYERS_APP_ID",
              "FYERS_ACCESS_TOKEN", "BREEZE_API_KEY", "BREEZE_API_SECRET"):
        if os.environ.get(k):
            creds[k] = os.environ[k]
    return creds


def setup_logging(settings: Settings, level: int = logging.INFO) -> None:
    """Console + rotating file logging, with logs stored on the SSD."""
    from logging.handlers import RotatingFileHandler

    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)-28s %(message)s")

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    root_logger.addHandler(ch)

    fh = RotatingFileHandler(settings.logs_dir / "trading_ai.log",
                             maxBytes=10 * 1024**2, backupCount=10,
                             encoding="utf-8")
    fh.setFormatter(fmt)
    root_logger.addHandler(fh)
