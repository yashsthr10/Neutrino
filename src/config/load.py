"""Load and merge TOML + env + CLI overrides."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.config.paths import project_config_file, user_config_file
from src.config.schema import CliRules, ModelConfig, NeutrinoSettings


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    import tomllib

    with path.open("rb") as f:
        return tomllib.load(f)


def _merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _merge_dict(out[k], v)
        else:
            out[k] = v
    return out


def _coerce_settings(data: dict[str, Any]) -> dict[str, Any]:
    """Build kwargs for NeutrinoSettings.model_validate."""
    payload: dict[str, Any] = {}
    if "model" in data and isinstance(data["model"], dict):
        payload["model"] = ModelConfig.model_validate(data["model"])
    if "rules" in data and isinstance(data["rules"], dict):
        payload["rules"] = CliRules.model_validate(data["rules"])
    return payload


def load_merged_settings(
    *,
    config_path: Path | None = None,
) -> NeutrinoSettings:
    """
    Repository root is always the process current working directory (where you run `neutrino`).

    File precedence (later wins): user config -> ./src.toml -> optional --config file.
    Environment variables override per pydantic-settings when constructing NeutrinoSettings().
    """
    cwd = Path(".").resolve()

    merged: dict[str, Any] = {}
    merged = _merge_dict(merged, _read_toml(user_config_file()))
    merged = _merge_dict(merged, _read_toml(project_config_file(cwd)))
    if config_path is not None and config_path.is_file():
        merged = _merge_dict(merged, _read_toml(config_path))

    payload = _coerce_settings(merged)
    base = NeutrinoSettings()
    settings = base.model_copy(update=payload, deep=True) if payload else base
    # Always anchor the repo to the directory from which the app was started.
    return settings.model_copy(update={"repo_path": cwd}, deep=True)


def apply_launch_overrides(
    base: NeutrinoSettings,
    *,
    repo: Path | None = None,
    verbose: bool | None = None,
    layout: str | None = None,
) -> NeutrinoSettings:
    """Optional programmatic overrides (e.g. tests). CLI does not pass repo."""
    updates: dict[str, Any] = {}
    if repo is not None:
        updates["repo_path"] = repo.resolve()
    rules = base.rules
    if verbose is not None:
        rules = rules.model_copy(update={"verbose": verbose})
    if layout is not None:
        rules = rules.model_copy(update={"layout": layout})
    if rules != base.rules:
        updates["rules"] = rules
    if not updates:
        return base
    data = base.model_dump()
    data.update(updates)
    return NeutrinoSettings.model_validate(data)
