"""Ctrl+K command palette: fuzzy filter + list selection."""

from __future__ import annotations

import difflib
from typing import Callable

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, Input, Label, ListItem, ListView


class CommandPaletteScreen(ModalScreen[str | None]):
    """Returns selected command id via dismiss, or None if cancelled."""

    BINDINGS = [("escape", "dismiss", "Close")]

    def __init__(
        self,
        commands: list[tuple[str, str]],
        *,
        filter_fn: Callable[[str, list[tuple[str, str]]], list[tuple[str, str]]] | None = None,
    ) -> None:
        super().__init__()
        self._all = list(commands)
        self._filtered = list(commands)
        self._filter_fn = filter_fn or self._default_filter

    @staticmethod
    def _default_filter(query: str, items: list[tuple[str, str]]) -> list[tuple[str, str]]:
        q = query.strip().lower()
        if not q:
            return items
        out: list[tuple[str, str]] = []
        for cid, label in items:
            if q in label.lower() or q in cid.lower():
                out.append((cid, label))
        if out:
            return out
        labels_lower = [x[1].lower() for x in items]
        matches = difflib.get_close_matches(q, labels_lower, n=12, cutoff=0.3)
        if not matches:
            return items
        out2: list[tuple[str, str]] = []
        for m in matches:
            for i, low in enumerate(labels_lower):
                if low == m:
                    out2.append(items[i])
                    break
        return out2 or items

    def compose(self) -> ComposeResult:
        with Vertical(id="palette-root"):
            yield Input(placeholder="Type to filter commands…", id="palette-input")
            yield ListView(id="palette-list")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_list()
        self.query_one("#palette-input", Input).focus()

    def _refresh_list(self) -> None:
        lv = self.query_one("#palette-list", ListView)
        for node in list(lv.query("ListItem")):
            node.remove()
        for cid, label in self._filtered:
            lv.append(ListItem(Label(label), name=cid))

    def on_input_changed(self, event: Input.Changed) -> None:
        self._filtered = self._filter_fn(event.value, self._all)
        self._refresh_list()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        name = event.item.name
        if isinstance(name, str) and name:
            self.dismiss(name)

    def action_dismiss(self) -> None:
        self.dismiss(None)
