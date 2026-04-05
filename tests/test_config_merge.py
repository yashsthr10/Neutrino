from pathlib import Path

from src.config import apply_launch_overrides, load_merged_settings


def test_load_defaults() -> None:
    s = load_merged_settings()
    assert s.repo_path.exists()
    assert s.rules.token_budget >= 1


def test_launch_repo_override(tmp_path: Path) -> None:
    base = load_merged_settings()
    out = apply_launch_overrides(base, repo=tmp_path)
    assert out.repo_path == tmp_path.resolve()
