"""Submit-key detection for PromptTextArea (terminal-specific key strings)."""

from textual import events

from src.tui.widgets.prompt_text_area import _is_submit_key


def _ev(key: str) -> events.Key:
    return events.Key(key, None)


def test_exact_ctrl_enter() -> None:
    assert _is_submit_key(_ev("ctrl+enter"))


def test_ctrl_shift_enter() -> None:
    assert _is_submit_key(_ev("ctrl+shift+enter"))


def test_plain_enter_not_submit() -> None:
    assert not _is_submit_key(_ev("enter"))


def test_f2() -> None:
    assert _is_submit_key(_ev("f2"))


def test_ctrl_j_not_submit() -> None:
    assert not _is_submit_key(_ev("ctrl+j"))
