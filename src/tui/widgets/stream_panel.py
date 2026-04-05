"""Chronological conversation / output stream (assistant, tools, diffs, state)."""

from __future__ import annotations

from rich.markup import escape
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Collapsible, RichLog

from src.tui.diff_format import unified_diff_preview

# Shown in collapsible headers so expand targets are self-explanatory.
_PHASE_SUBTITLES: dict[str, str] = {
    "PLAN": "Strategy, scope, and affected files",
    "EXECUTE": "Tool calls, agent text, and diffs",
    "VERIFY": "Tests and validation output",
    "REVIEW": "Final summary and assessment",
    "INIT": "Session bootstrap",
    "DONE": "Run complete",
}


def _snippet(text: str, *, max_len: int = 72) -> str:
    one_line = " ".join(text.split())
    if len(one_line) <= max_len:
        return one_line
    return one_line[: max_len - 3] + "..."


class StreamPanel(Vertical):
    """Scrollable column: phase blocks in Collapsible sections + main log for user lines."""

    DEFAULT_CSS = """
    StreamPanel {
        height: 1fr;
        min-height: 6;
        border: solid $primary;
        background: $surface;
    }
    StreamPanel VerticalScroll {
        height: 1fr;
    }
    /* Only cap the main transcript; nested phase/reasoning logs need room */
    StreamPanel RichLog#stream-main {
        height: auto;
        max-height: 28;
        min-height: 4;
    }
    StreamPanel Collapsible {
        width: 1fr;
        height: auto;
        margin-bottom: 1;
        border: solid $primary;
        background: $boost;
    }
    StreamPanel Collapsible CollapsibleTitle {
        width: 1fr;
        height: auto;
        min-height: 1;
        padding: 0 1 0 0;
        color: $accent;
        text-style: bold;
    }
    StreamPanel Collapsible RichLog {
        height: auto;
        max-height: 48;
        min-height: 3;
        border: none;
    }
    """

    def __init__(self) -> None:
        super().__init__(id="stream-panel")
        self._main_log = RichLog(
            highlight=True,
            markup=True,
            auto_scroll=True,
            wrap=True,
            id="stream-main",
        )
        self._scroll = VerticalScroll(self._main_log, id="stream-scroll")
        self._current_block_log: RichLog | None = None
        self._current_phase_id: str | None = None
        self._reasoning_collapsibles: list[Collapsible] = []

    def compose(self) -> ComposeResult:
        yield self._scroll

    def clear_stream(self) -> None:
        # Reuse the main RichLog; do not replace it. remove_children()/remove() are
        # async in Textual—remounting a new id="stream-main" in the same tick caused
        # DuplicateIds while the old node was still registered.
        self._main_log.clear()
        for child in list(self._scroll.children):
            if child is not self._main_log:
                child.remove()
        self._current_block_log = None
        self._current_phase_id = None
        self._reasoning_collapsibles.clear()

    def scroll_end(self) -> None:
        self._scroll.scroll_end(animate=False)

    @property
    def current_phase_id(self) -> str | None:
        return self._current_phase_id

    def _active_log(self) -> RichLog:
        return self._current_block_log or self._main_log

    def start_phase_block(self, phase_id: str, title: str | None = None) -> None:
        """Begin a new collapsible block for a phase (PLAN, EXECUTE, …)."""
        self._current_phase_id = phase_id
        key = phase_id.strip().upper()
        subtitle = _PHASE_SUBTITLES.get(key, "Orchestrator output for this step")
        # Title line: phase name + what you will see when expanded
        header = f"{key} — {subtitle}"
        if title and title.strip().upper() != key:
            header = f"{key} — {title.strip()}"
        block_log = RichLog(
            highlight=True,
            markup=True,
            auto_scroll=True,
            wrap=True,
        )
        coll = Collapsible(
            block_log,
            title=header,
            collapsed=False,
            collapsed_symbol="▶",
            expanded_symbol="▼",
        )
        self._scroll.mount(coll)
        self._current_block_log = block_log

    def append_to_current_block(self, text: str, *, append_newline: bool = True) -> None:
        """Append streaming chunk to the active phase block (falls back to main log)."""
        log = self._active_log()
        prefix = "→ "
        piece = f"{prefix}{text}"
        log.write(Text(piece, style="white"))
        if append_newline:
            pass

    def end_phase_block(self, status: str) -> None:
        """Close the current phase block with a status line."""
        log = self._active_log()
        sym = "✔" if status.lower() in ("ok", "done", "complete") else "⏳"
        log.write(Text(f"{sym} {status}", style="bold green" if sym == "✔" else "yellow"))
        self._current_block_log = None
        self._current_phase_id = None

    def collapse_reasoning_blocks(self) -> None:
        """Collapse all [REASONING] collapsibles (for `h`)."""
        for c in self._reasoning_collapsibles:
            c.collapsed = True

    def append_user(self, content: str) -> None:
        for line in content.splitlines() or [""]:
            self._main_log.write(Text(f"> {line}", style="bold cyan"))

    def append_assistant(self, content: str, *, final: bool = False) -> None:
        style = "green" if final else "white"
        self._active_log().write(Text(content, style=style))

    def append_phase(self, phase: str) -> None:
        self.start_phase_block(phase, title=None)

    def append_state(self, from_s: str, to_s: str) -> None:
        self._active_log().write(Text(f"[STATE] {from_s} → {to_s}", style="magenta"))

    def append_tool(self, name: str, detail: str, *, success: bool) -> None:
        sym = "ok" if success else "fail"
        st = "yellow" if success else "red"
        self._active_log().write(Text(f"[TOOL] {name}: {detail}  [{sym}]", style=st))

    def append_log(self, message: str, level: str) -> None:
        st = {"info": "dim", "warning": "yellow", "error": "bold red"}.get(level, "white")
        self._active_log().write(Text(message, style=st))

    def append_reasoning(self, content: str, *, collapsed_default: bool = True) -> None:
        rlog = RichLog(
            highlight=True,
            markup=True,
            auto_scroll=True,
            wrap=True,
        )
        rlog.write(Text(content, style="italic dim"))
        preview = _snippet(content)
        header = f"Reasoning — {preview}" if preview else "Reasoning — (empty)"
        coll = Collapsible(
            rlog,
            title=header,
            collapsed=collapsed_default,
            collapsed_symbol="▶",
            expanded_symbol="▼",
        )
        self._scroll.mount(coll)
        self._reasoning_collapsibles.append(coll)

    def append_diff(self, path: str, old_text: str, new_text: str) -> None:
        log = self._active_log()
        log.write(Text(f"[DIFF] {escape(path)}", style="bold cyan"))
        preview = unified_diff_preview(path, old_text, new_text)
        for line in preview.splitlines():
            if line.startswith("- "):
                log.write(Text(line, style="red"))
            elif line.startswith("+ "):
                log.write(Text(line, style="green"))
            elif line in ("---", "+++"):
                log.write(Text(line, style="dim"))
            else:
                log.write(Text(line))

    def append_error(self, message: str) -> None:
        self._active_log().write(Text(f"[ERROR] {escape(message)}", style="bold red"))

    def append_repo_tree(self, root: str, paths: tuple[str, ...]) -> None:
        log = self._active_log()
        log.write(Text(f"[TREE] {escape(root)}", style="bold blue"))
        for p in paths[:40]:
            log.write(Text(f"  {escape(p)}", style="dim"))
        if len(paths) > 40:
            log.write(Text(f"  ... ({len(paths)} paths)", style="dim"))

    def append_checkpoint(self, message: str) -> None:
        self._active_log().write(Text(message, style="bold yellow"))

    def append_run_finished(self, message: str, ok: bool) -> None:
        st = "green" if ok else "red"
        self._active_log().write(Text(message, style=st))

    def append_phase_step_complete(self, message: str) -> None:
        self._active_log().write(Text(f"✔ {message}", style="bold green"))
