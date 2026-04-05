from src.tui.diff_format import unified_diff_preview


def test_unified_diff_preview_contains_markers() -> None:
    s = unified_diff_preview("a.py", "a\n", "b\n", max_lines=8)
    assert "---" in s
    assert "- a" in s
    assert "+ b" in s
