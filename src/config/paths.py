"""XDG-style config paths."""

from __future__ import annotations

import os
from pathlib import Path


def user_config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    if base:
        return Path(base) / "neutrino"
    return Path.home() / ".config" / "neutrino"


def user_config_file() -> Path:
    return user_config_dir() / "config.toml"


def project_config_file(repo: Path) -> Path:
    return repo.resolve() / "src.toml"
