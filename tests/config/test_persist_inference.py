"""Persist / restore active provider+model via user config.toml."""

from __future__ import annotations

from pathlib import Path

from src.config.load import load_merged_settings, save_user_inference
from src.config.schema import InferenceProviderConfig


def test_save_user_inference_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        '[rules]\nverbose = true\n\n[model]\nprovider = "ollama"\nname = "old"\n',
        encoding="utf-8",
    )
    cfg = InferenceProviderConfig(
        type="native",
        vendor="google_genai",
        model="gemini-3.5-flash",
        base_url=None,
        temperature=0.2,
    )
    saved = save_user_inference(cfg, path=path)
    assert saved == path

    text = path.read_text(encoding="utf-8")
    assert "[inference]" in text
    assert 'vendor = "google_genai"' in text
    assert 'model = "gemini-3.5-flash"' in text
    assert "[model]" not in text
    assert "[rules]" in text
    assert "verbose = true" in text

    loaded = load_merged_settings(
        user_config=path,
        project_config=tmp_path / "missing-src.toml",
        cwd=tmp_path,
    )
    inf = loaded.resolved_inference()
    assert inf.type == "native"
    assert inf.vendor == "google_genai"
    assert inf.model == "gemini-3.5-flash"
