"""Load and merge TOML + env + CLI overrides."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.config.paths import project_config_file, user_config_dir, user_config_file
from src.config.schema import (
    CliRules,
    InferenceProviderConfig,
    ModelConfig,
    NeutrinoSettings,
    ProfileConfig,
)


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    import tomllib

    with path.open("rb") as f:
        return tomllib.load(f)


def _toml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value)
    raise TypeError(f"unsupported TOML scalar type: {type(value)!r}")


def _write_toml(path: Path, data: dict[str, Any]) -> None:
    """Write a small nested dict as TOML (stdlib only — no tomli-w dependency)."""
    lines: list[str] = []

    def emit_table(header: str | None, body: dict[str, Any], *, depth: int = 0) -> None:
        scalars: list[tuple[str, Any]] = []
        nested: list[tuple[str, dict[str, Any]]] = []
        for key, value in body.items():
            if value is None:
                continue
            if isinstance(value, dict):
                nested.append((key, value))
            else:
                scalars.append((key, value))
        if header is not None:
            if lines and lines[-1] != "":
                lines.append("")
            lines.append(f"[{header}]")
        for key, value in scalars:
            if isinstance(value, (list, tuple)):
                inner = ", ".join(_toml_scalar(v) for v in value)
                lines.append(f"{key} = [{inner}]")
            else:
                lines.append(f"{key} = {_toml_scalar(value)}")
        for key, value in nested:
            child = f"{header}.{key}" if header else key
            if depth >= 3:
                continue
            emit_table(child, value, depth=depth + 1)

    # Top-level scalars first (none expected today), then tables.
    top_scalars = {
        k: v for k, v in data.items() if v is not None and not isinstance(v, dict)
    }
    if top_scalars:
        emit_table(None, top_scalars)
    for key, value in data.items():
        if isinstance(value, dict):
            emit_table(key, value)

    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines).rstrip() + "\n"
    path.write_text(text, encoding="utf-8")


def _merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _merge_dict(out[k], v)
        else:
            out[k] = v
    return out


def inference_config_to_dict(cfg: InferenceProviderConfig) -> dict[str, Any]:
    """Serialize non-secret inference settings for TOML persistence."""
    data = cfg.model_dump(mode="json", exclude_none=True)
    extra = data.get("extra")
    if not extra:
        data.pop("extra", None)
    return data


def save_user_inference(
    cfg: InferenceProviderConfig,
    *,
    path: Path | None = None,
) -> Path:
    """Persist provider/model selection to the user config file.

    Updates only the ``[inference]`` table (and drops legacy ``[model]`` so it
    cannot override on next load). Other keys (rules, profiles, …) are kept.
    """
    target = path or user_config_file()
    existing = _read_toml(target)
    existing["inference"] = inference_config_to_dict(cfg)
    existing.pop("model", None)
    _write_toml(target, existing)
    # Ensure config dir exists for credentials co-location even if empty otherwise.
    user_config_dir().mkdir(parents=True, exist_ok=True)
    return target


def _coerce_settings(data: dict[str, Any]) -> dict[str, Any]:
    """Build kwargs for NeutrinoSettings.model_validate."""
    payload: dict[str, Any] = {}
    if "inference" in data and isinstance(data["inference"], dict):
        payload["inference"] = InferenceProviderConfig.model_validate(data["inference"])
    if "model" in data and isinstance(data["model"], dict):
        payload["model"] = ModelConfig.model_validate(data["model"])
        if "inference" not in payload:
            payload["inference"] = payload["model"].to_inference()
    if "rules" in data and isinstance(data["rules"], dict):
        payload["rules"] = CliRules.model_validate(data["rules"])
    if "active_profile" in data:
        payload["active_profile"] = data["active_profile"]
    if "profiles" in data and isinstance(data["profiles"], dict):
        profiles: dict[str, ProfileConfig] = {}
        for name, raw in data["profiles"].items():
            if isinstance(raw, dict):
                body = dict(raw)
                body.setdefault("name", name)
                profiles[name] = ProfileConfig.model_validate(body)
        payload["profiles"] = profiles
    return payload


def load_merged_settings(
    *,
    config_path: Path | None = None,
    user_config: Path | None = None,
    project_config: Path | None = None,
    cwd: Path | None = None,
) -> NeutrinoSettings:
    """
    Repository root is always the process current working directory (where you run `neutrino`).

    File precedence (later wins): user config -> ./src.toml -> optional --config file.
    Environment variables override per pydantic-settings when constructing NeutrinoSettings().
    """
    root = (cwd or Path(".")).resolve()

    merged: dict[str, Any] = {}
    merged = _merge_dict(merged, _read_toml(user_config or user_config_file()))
    merged = _merge_dict(
        merged, _read_toml(project_config or project_config_file(root))
    )
    if config_path is not None and config_path.is_file():
        merged = _merge_dict(merged, _read_toml(config_path))

    payload = _coerce_settings(merged)
    base = NeutrinoSettings()
    settings = base.model_copy(update=payload, deep=True) if payload else base
    return settings.model_copy(update={"repo_path": root}, deep=True)


def apply_launch_overrides(
    base: NeutrinoSettings,
    *,
    repo: Path | None = None,
    verbose: bool | None = None,
    layout: str | None = None,
    profile: str | None = None,
) -> NeutrinoSettings:
    """Optional programmatic overrides (e.g. tests). CLI does not pass repo."""
    updates: dict[str, Any] = {}
    if repo is not None:
        updates["repo_path"] = repo.resolve()
    if profile is not None:
        updates["active_profile"] = profile
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
