from src.tui.commands import CommandTarget, dispatch, parse_slash_line


class _UI:
    def action_help(self) -> None:
        pass

    def action_logs_focus(self) -> None:
        pass

    def action_toggle_file_tree(self) -> None:
        pass

    def action_reset(self) -> None:
        pass


class _Orch:
    def submit_task(self, user_query: str) -> None:
        pass

    def send_approval(self, request_id: str, approved: bool) -> None:
        pass

    def send_approval_action(self, request_id: str, action: str) -> None:
        pass

    def submit_approval_edit(self, request_id: str, new_text: str) -> None:
        pass

    def set_runtime_mode(self, mode: str) -> None:
        pass

    def request_retry(self) -> None:
        pass

    def request_context_refresh(self) -> None:
        pass

    def request_repo_tree(self) -> None:
        pass

    def select_recovery_option(self, option_id: str) -> None:
        pass

    def cancel_run(self) -> None:
        pass


def test_parse_slash() -> None:
    p = parse_slash_line("/mode fast")
    assert p is not None
    assert p.name == "mode"
    assert p.args == ["fast"]


def test_dispatch_mode_auto() -> None:
    p = parse_slash_line("/mode auto")
    assert p is not None
    assert dispatch(p, ui=_UI(), orch=_Orch()) == CommandTarget.ORCH


def test_parse_not_slash() -> None:
    assert parse_slash_line("hello") is None


def test_dispatch_unknown() -> None:
    p = parse_slash_line("/nope")
    assert p is not None
    assert dispatch(p, ui=_UI(), orch=_Orch()) is None


def test_dispatch_help() -> None:
    p = parse_slash_line("/help")
    assert p is not None
    assert dispatch(p, ui=_UI(), orch=_Orch()) == CommandTarget.UI
