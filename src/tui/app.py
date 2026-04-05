"""Textual app: Claude/Gemini-style column — header status, stream, multiline prompt."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from textual import on
from textual.actions import SkipAction
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Static, TextArea

from src.config.schema import NeutrinoSettings
from src.orchestrator.fake import FakeOrchestratorPort
from src.ports.orchestrator_port import (
    AgentMessage,
    ApprovalRequest,
    ContextSummary,
    DiffChunk,
    ExplanationAvailable,
    FailureRecovery,
    LogLine,
    OrchestratorPort,
    PhaseMarker,
    PhaseStepComplete,
    ReasoningBlock,
    RepoTreeSnapshot,
    RunFinished,
    StateTransition,
    StatusSnapshot,
    ThinkingDelta,
    TokenUpdate,
    ToolCallEvent,
    UIEvent,
)
from src.tui.commands import dispatch, parse_slash_line
from src.tui.messages import ApprovalChosen, OrchestratorEventMessage, SubmitPrompt
from src.tui.screens import (
    ApprovalEditScreen,
    CommandPaletteScreen,
    ContextSummaryScreen,
    ExplainScreen,
    FailureRecoveryScreen,
    TextPreviewScreen,
)
from src.tui.widgets import ApprovalBar, FsmTimeline, HeaderBar, PromptPanel, StreamPanel


class NeutrinoApp(App[None]):
    """Single column: header (Neutrino + status), chronological stream, REPL prompt."""

    TITLE = "Neutrino"

    CSS = """
    Screen {
        layout: vertical;
    }
    #main-column {
        height: 1fr;
        layout: vertical;
    }
    #split-row {
        height: 1fr;
        layout: horizontal;
    }
    #split-side {
        width: 36;
        border: solid $boost;
        background: $panel;
        padding: 1;
        color: $text-muted;
    }
    """

    BINDINGS = [
        # Approval hotkeys must be priority so they work while the prompt TextArea is focused.
        Binding("a", "approval_accept", show=False, priority=True),
        Binding("e", "approval_edit", show=False, priority=True),
        Binding("v", "approval_view", show=False, priority=True),
        Binding("y", "approval_yes", show=False, priority=True),
        Binding("n", "approval_no", show=False, priority=True),
        Binding("r", "toggle_reasoning", "Reasoning", show=True, priority=True),
        Binding("h", "collapse_reasoning", "Hide R.", show=True),
        Binding("ctrl+p", "history_prev", "Hist-", show=False),
        Binding("ctrl+n", "history_next", "Hist+", show=False),
        Binding("ctrl+q", "quit", "Quit", show=True),
        Binding("ctrl+shift+c", "clipboard_copy", "Copy", show=True, priority=True),
        Binding("ctrl+shift+v", "clipboard_paste", "Paste", show=True, priority=True),
        Binding("ctrl+m", "cycle_mode", "Mode", show=True, priority=True),
        Binding("ctrl+k", "open_palette", "Palette", show=True, priority=True),
        Binding("shift+question_mark", "explain_why", "Explain", show=True, priority=True),
        Binding("ctrl+r", "retry_global", "Retry", show=False, priority=True),
        Binding("ctrl+l", "clear_or_reset", "Clear", show=False, priority=True),
        Binding("ctrl+shift+x", "cancel_task", "Cancel run", show=False, priority=True),
    ]

    def __init__(
        self, settings: NeutrinoSettings, orchestrator: OrchestratorPort | None = None
    ) -> None:
        super().__init__()
        self.settings = settings
        self._pending_approval: ApprovalRequest | None = None
        self._orch = orchestrator
        self._emit_bound = self._make_emit()
        self._last_fsm = "INIT"
        self._last_tokens = 0
        self._token_budget: int | None = settings.rules.token_budget
        self._show_reasoning_in_stream = True
        self._input_history: list[str] = []
        self._history_index: int | None = None
        self._welcome_placeholder_active = True
        self._last_explanation: tuple[str, ...] = ()
        self._approval_bar = ApprovalBar()

    def _make_emit(self):
        def emit(ev: UIEvent) -> None:
            self.post_message(OrchestratorEventMessage(ev))

        return emit

    def compose(self) -> ComposeResult:
        yield HeaderBar()
        yield FsmTimeline()
        if self.settings.rules.layout == "split":
            with Horizontal(id="split-row"):
                with Vertical(id="main-column"):
                    yield StreamPanel()
                    yield self._approval_bar
                    yield PromptPanel()
                yield Static(
                    "Split layout: secondary panel (diff / tree) placeholder.",
                    id="split-side",
                )
        else:
            with Vertical(id="main-column"):
                yield StreamPanel()
                yield self._approval_bar
                yield PromptPanel()
        yield Footer()

    def on_mount(self) -> None:
        if self._orch is None:
            self._orch = FakeOrchestratorPort(
                self._emit_bound,
                Path(self.settings.repo_path),
            )
        orch = cast(OrchestratorPort, self._orch)
        mode = self.settings.rules.runtime_mode
        self._refresh_header(mode_label=self._mode_label(mode), tokens=0, state="READY")
        stream = self.query_one(StreamPanel)
        stream.append_log(
            "Welcome to src. Stream below is chronological. "
            "Ctrl+Enter or F2 to send, Ctrl+Shift+C/V clipboard, Ctrl+Q quit. "
            "Ctrl+M cycle mode, Ctrl+K palette, Shift+? explain, /help for commands.",
            "info",
        )
        orch.set_runtime_mode(mode)
        self._approval_bar.update_request(None)
        self.query_one("#prompt-input", TextArea).focus()

    def _mode_label(self, mode: str) -> str:
        if mode == "auto":
            return "AUTO"
        complexity = "SIMPLE" if mode == "fast" else "COMPLEX"
        return f"{mode.upper()} ({complexity})"

    def _refresh_header(self, *, mode_label: str, tokens: int, state: str) -> None:
        hb = self.query_one(HeaderBar)
        hb.update_status(
            mode_label=mode_label,
            tokens=tokens,
            repo_path=self.settings.repo_path,
            fsm_state=state,
        )
        budget = (
            self._token_budget
            if self._token_budget is not None
            else self.settings.rules.token_budget
        )
        hb.update_token_bar(tokens, budget)

    def _orch_port(self) -> OrchestratorPort:
        return cast(OrchestratorPort, self._orch)

    def _palette_entries(self) -> list[tuple[str, str]]:
        return [
            ("help", "Help (/help)"),
            ("logs", "Focus stream / logs"),
            ("reset", "Reset session"),
            ("context", "Refresh context (modal)"),
            ("retry", "Retry last task"),
            ("tree", "Show repo tree"),
            ("mode_cycle", "Cycle runtime mode (same as Ctrl+M)"),
            ("palette", "Open command palette (meta)"),
            ("cancel", "Cancel current run"),
        ]

    def action_open_palette(self) -> None:
        if isinstance(self.focused, TextArea) and self.focused.id == "prompt-input":
            pass
        self.push_screen(
            CommandPaletteScreen(self._palette_entries()),
            callback=self._on_palette_result,
        )

    def _on_palette_result(self, result: str | None) -> None:
        if not result:
            return
        if result == "palette":
            self.action_open_palette()
            return
        orch = self._orch_port()
        if result == "help":
            self.action_help()
        elif result == "logs":
            self.action_logs_focus()
        elif result == "reset":
            self.action_reset()
        elif result == "context":
            orch.request_context_refresh()
        elif result == "retry":
            orch.request_retry()
        elif result == "tree":
            orch.request_repo_tree()
        elif result == "mode_cycle":
            self.action_cycle_mode()
        elif result == "cancel":
            orch.cancel_run()

    def action_retry_global(self) -> None:
        if isinstance(self.focused, TextArea):
            return
        self._orch_port().request_retry()

    def action_clear_or_reset(self) -> None:
        if isinstance(self.focused, TextArea):
            return
        self.action_reset()

    def action_cancel_task(self) -> None:
        self._orch_port().cancel_run()

    def action_cycle_mode(self) -> None:
        order = ("fast", "deep", "auto")
        cur = self.settings.rules.runtime_mode
        try:
            i = order.index(cur)
            nxt = order[(i + 1) % len(order)]
        except ValueError:
            nxt = "fast"
        new_rules = self.settings.rules.model_copy(update={"runtime_mode": nxt})
        self.settings = self.settings.model_copy(update={"rules": new_rules}, deep=True)
        self._orch_port().set_runtime_mode(nxt)
        self._refresh_header(
            mode_label=self._mode_label(nxt),
            tokens=self._last_tokens,
            state=self._last_fsm,
        )

    def action_collapse_reasoning(self) -> None:
        if isinstance(self.focused, TextArea):
            return
        self.query_one(StreamPanel).collapse_reasoning_blocks()

    def action_explain_why(self) -> None:
        if isinstance(self.focused, TextArea):
            return
        if not self._last_explanation:
            self.query_one(StreamPanel).append_log(
                "No explanation loaded yet for this run.", "warning"
            )
            return
        self.push_screen(ExplainScreen(self._last_explanation))

    def action_help(self) -> None:
        self.query_one(StreamPanel).append_assistant(
            "Commands: /help /reset /logs /context /retry /mode fast|deep|auto /tree | "
            "r toggles [REASONING] stream lines, h collapses [REASONING] blocks | "
            "Send: Ctrl+Enter or F2 (not global Enter) | "
            "Ctrl+M mode, Ctrl+K palette, Shift+? explain | "
            "Approval: use the bar buttons (Accept / Edit / View / Reject) or keys a e v r y n | "
            "Ctrl+Shift+X cancel run, Ctrl+R retry, Ctrl+L reset when prompt not focused | "
            "Ctrl+Shift+C/V clipboard | Quit: Ctrl+Q",
            final=True,
        )

    def action_clipboard_copy(self) -> None:
        w = self.focused
        if isinstance(w, TextArea):
            try:
                w.action_copy()
            except SkipAction:
                pass

    def action_clipboard_paste(self) -> None:
        w = self.focused
        if isinstance(w, TextArea):
            w.action_paste()

    @on(SubmitPrompt)
    def on_submit_prompt_message(self, _event: SubmitPrompt) -> None:
        self.action_submit_prompt()

    def action_logs_focus(self) -> None:
        self.query_one(StreamPanel).scroll_end()

    def action_toggle_file_tree(self) -> None:
        self._orch_port().request_repo_tree()

    def action_reset(self) -> None:
        stream = self.query_one(StreamPanel)
        stream.clear_stream()
        stream.append_log("Session cleared. /help for commands.", "info")

    def action_toggle_reasoning(self) -> None:
        if self._pending_approval:
            self._apply_approval_action("reject")
            return
        self._show_reasoning_in_stream = not self._show_reasoning_in_stream
        self.query_one(StreamPanel).append_log(
            f"[REASONING] visibility: {'on' if self._show_reasoning_in_stream else 'off'}",
            "info",
        )

    def action_approval_accept(self) -> None:
        if not self._pending_approval:
            raise SkipAction()
        self._apply_approval_action("accept")

    def action_approval_edit(self) -> None:
        if not self._pending_approval:
            raise SkipAction()
        self._apply_approval_action("edit")

    def action_approval_view(self) -> None:
        if not self._pending_approval:
            raise SkipAction()
        self._apply_approval_action("view")

    def action_approval_yes(self) -> None:
        if not self._pending_approval:
            raise SkipAction()
        self._apply_approval_action("y")

    def action_approval_no(self) -> None:
        if not self._pending_approval:
            raise SkipAction()
        self._apply_approval_action("n")

    def action_submit_prompt(self) -> None:
        ta = self.query_one("#prompt-input", TextArea)
        text = ta.text
        raw = text.rstrip("\n")
        if not raw.strip():
            return

        stream = self.query_one(StreamPanel)
        if self._welcome_placeholder_active:
            stream.clear_stream()
            self._welcome_placeholder_active = False

        ta.text = ""
        self._history_index = None

        stream.append_user(raw)

        if raw.startswith("/") and "\n" not in text:
            parsed = parse_slash_line(raw)
            if parsed is None:
                return
            tgt = dispatch(parsed, ui=self, orch=self._orch_port())
            if tgt is None:
                stream.append_error(f"Unknown command: {parsed.raw}")
            if parsed.name == "mode" and len(parsed.args) >= 1:
                m = parsed.args[0].lower()
                if m in ("fast", "deep", "auto"):
                    new_rules = self.settings.rules.model_copy(update={"runtime_mode": m})
                    self.settings = self.settings.model_copy(
                        update={"rules": new_rules},
                        deep=True,
                    )
            self._push_history(raw)
            return

        self._push_history(raw)
        self._orch_port().submit_task(raw)

    def _push_history(self, entry: str) -> None:
        if not self._input_history or self._input_history[-1] != entry:
            self._input_history.append(entry)
        self._history_index = None

    def action_history_prev(self) -> None:
        if not self._input_history:
            return
        ta = self.query_one("#prompt-input", TextArea)
        if self._history_index is None:
            self._history_index = len(self._input_history) - 1
        else:
            self._history_index = max(0, self._history_index - 1)
        ta.text = self._input_history[self._history_index]

    def action_history_next(self) -> None:
        if not self._input_history or self._history_index is None:
            return
        ta = self.query_one("#prompt-input", TextArea)
        if self._history_index >= len(self._input_history) - 1:
            self._history_index = None
            ta.text = ""
            return
        self._history_index += 1
        ta.text = self._input_history[self._history_index]

    def _set_approval_ui(self, req: ApprovalRequest | None) -> None:
        self._approval_bar.update_request(req)

    @on(ApprovalChosen)
    def on_approval_chosen(self, event: ApprovalChosen) -> None:
        self._apply_approval_action(event.action)

    def _on_failure_done(self, option_id: str | None) -> None:
        if option_id:
            self._orch_port().select_recovery_option(option_id)

    def on_orchestrator_event_message(self, message: OrchestratorEventMessage) -> None:
        ev = message.event
        stream = self.query_one(StreamPanel)
        timeline = self.query_one(FsmTimeline)

        if isinstance(ev, PhaseMarker):
            stream.append_phase(ev.phase)
        elif isinstance(ev, StateTransition):
            stream.append_state(ev.from_state, ev.to_state)
            self._last_fsm = ev.to_state
            timeline.set_active(ev.to_state)
            self._refresh_header(
                mode_label=self._status_mode_label(),
                tokens=self._last_tokens,
                state=self._last_fsm,
            )
        elif isinstance(ev, TokenUpdate):
            self._last_tokens = ev.used
            if ev.budget is not None:
                self._token_budget = ev.budget
            self._refresh_header(
                mode_label=self._status_mode_label(),
                tokens=ev.used,
                state=self._last_fsm,
            )
        elif isinstance(ev, ToolCallEvent):
            stream.append_tool(ev.name, ev.args_summary, success=ev.success)
        elif isinstance(ev, LogLine):
            stream.append_log(ev.message, ev.level)
        elif isinstance(ev, AgentMessage):
            stream.append_assistant(ev.content, final=ev.final)
        elif isinstance(ev, ReasoningBlock):
            if self._show_reasoning_in_stream:
                stream.append_reasoning(ev.content, collapsed_default=ev.collapsed_default)
        elif isinstance(ev, DiffChunk):
            stream.append_diff(ev.path, ev.old_text, ev.new_text)
        elif isinstance(ev, ApprovalRequest):
            self._pending_approval = ev
            self._set_approval_ui(ev)
            stream.append_checkpoint(
                f"Apply changes?  id={ev.request_id}  — buttons below or keys a/e/v/r/y/n",
            )
        elif isinstance(ev, RepoTreeSnapshot):
            stream.append_repo_tree(ev.root_label, ev.paths)
        elif isinstance(ev, StatusSnapshot):
            self._last_fsm = ev.fsm_state
            self._last_tokens = ev.tokens_used
            self._refresh_header(
                mode_label=ev.mode_label,
                tokens=ev.tokens_used,
                state=ev.fsm_state,
            )
        elif isinstance(ev, RunFinished):
            self._pending_approval = None
            self._set_approval_ui(None)
            stream.append_run_finished(ev.message or ("Done." if ev.ok else "Failed."), ev.ok)
        elif isinstance(ev, ThinkingDelta):
            if stream.current_phase_id is None or ev.phase_id == stream.current_phase_id:
                stream.append_to_current_block(ev.text, append_newline=ev.append_newline)
            else:
                stream.append_log(f"[delta @{ev.phase_id}] {ev.text}", "info")
        elif isinstance(ev, PhaseStepComplete):
            stream.append_phase_step_complete(ev.message)
        elif isinstance(ev, ContextSummary):
            self.push_screen(ContextSummaryScreen(ev))
        elif isinstance(ev, FailureRecovery):
            self.push_screen(FailureRecoveryScreen(ev), callback=self._on_failure_done)
        elif isinstance(ev, ExplanationAvailable):
            self._last_explanation = ev.bullets

    def _status_mode_label(self) -> str:
        return self._mode_label(self.settings.rules.runtime_mode)

    def _apply_approval_action(self, kind: str) -> None:
        """Apply approval from buttons or keyboard (accept, reject, view, edit, y, n)."""
        req = self._pending_approval
        if req is None:
            return
        orch = self._orch_port()
        kind = kind.lower()
        stream = self.query_one(StreamPanel)

        if kind in ("y", "yes"):
            self._pending_approval = None
            self._set_approval_ui(None)
            orch.send_approval(req.request_id, True)
            stream.append_log("Approved, applying.", "info")
            return
        if kind in ("n", "no"):
            self._pending_approval = None
            self._set_approval_ui(None)
            orch.send_approval(req.request_id, False)
            stream.append_log("Rejected.", "warning")
            return
        if kind == "accept":
            self._pending_approval = None
            self._set_approval_ui(None)
            orch.send_approval_action(req.request_id, "accept")
            stream.append_log("Approved, applying.", "info")
            return
        if kind == "reject":
            self._pending_approval = None
            self._set_approval_ui(None)
            orch.send_approval_action(req.request_id, "reject")
            stream.append_log("Rejected.", "warning")
            return
        if kind == "view":
            orch.send_approval_action(req.request_id, "view")
            full = req.full_file_text or "(no full file in event)"
            self.push_screen(TextPreviewScreen(f"Full file ({req.request_id})", full))
            return
        if kind == "edit":

            def _after_edit(text: str | None) -> None:
                if text is not None:
                    orch.submit_approval_edit(req.request_id, text)

            self.push_screen(ApprovalEditScreen(req.preview_snippet or ""), callback=_after_edit)
            return
