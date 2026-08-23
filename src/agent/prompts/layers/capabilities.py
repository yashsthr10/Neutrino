"""L2 — Capability contract from live ToolSpecs."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Protocol


class _ToolLike(Protocol):
    name: str
    description: str
    category: str
    when_to_use: str
    when_not_to_use: str
    pairs_with: tuple[str, ...]


_EDIT_FORMATS = """\
## Editing files — `executor.apply`

Required argument: `patch` (string). Optional: `format` = `patch` | `search_replace` \
| `udiff` | `auto` (default prefer `patch`).

### Create a new file (`format=patch`)

```
*** Begin Patch
*** Add File: relative/path.py
+line one
+line two
*** End Patch
```

Every content line for an add **must** start with `+`.
If the file already exists, use Update File or search_replace instead.

### Edit an existing file (`format=search_replace`)

```
relative/path.py
<<<<<<< SEARCH
exact old lines
=======
new lines
>>>>>>> REPLACE
```

SEARCH must match the file exactly (read first). Prefer small, precise hunks.

### Edit via patch (`format=patch`)

```
*** Begin Patch
*** Update File: relative/path.py
@@
 context
-old
+new
*** End Patch
```

Do **not** use shell (`terminal.run` / `executor.run`) to create/edit source when `executor.apply` \
can do it. Shell tools require explicit approval (`approved=true`).

Prefer `terminal.run` for general shell access (cwd, env, stdin). Use `executor.run` only when \
a simpler one-shot command suffices.

Prefer modest patches: scaffold short files first, then expand with updates.
"""

_TOOL_RESULT_CONTRACT = """\
## Tool results

Tool results arrive as `role=tool` messages with JSON `ToolResult` shape: \
`success`, `data`, `meta.error`, `errors`. They respond to **your** tool \
calls from the immediately preceding assistant turn — not user actions.

If a tool failed, **you** chose the arguments; adjust path/strategy and \
retry. Do not tell the user they called the tool or used the wrong path.

Soft failures (`validation_error`, `permission_denied`, `not_implemented`, \
`absolute paths are not allowed`, …) mean adjust arguments or strategy — \
do not invent a different tool name.
On apply mismatch / failed patch, re-read the file (`rna.read_file`) and craft \
a tighter edit. On `File already exists` from `executor.apply`, switch to \
`*** Update File` or `search_replace`.
"""

_ARCHITECTURE_DIAGRAMS = """\
## Architecture diagrams — `rna.get_hld` / `rna.get_lld`

- **`rna.get_hld`** — package/module dependency map (bird's-eye). Optional `scope`, \
`granularity` (`coarse`|`module`|`fine`|`file`). Default **`format=json`** (preferred for agents).
- **`rna.get_lld`** — class/function structure for one **file or directory** (`scope` required). \
Default **`format=json`**.
- **`rna.trace_workflow`** — runtime call path across files; use `file:symbol` entrypoints \
(e.g. `src/pkg/handler.py:handle`).

Use **`format=mermaid`** only when the user needs a diagram preview, not for routine reasoning.
"""


def render_capabilities(tools: list[Any] | tuple[Any, ...]) -> str:
    """Render L2 from tool objects exposing ToolSpec-like fields."""
    by_cat: dict[str, list[Any]] = defaultdict(list)
    names: set[str] = set()
    for t in tools:
        name = getattr(t, "name", None)
        if not isinstance(name, str) or not name:
            continue
        names.add(name)
        cat = getattr(t, "category", None) or "other"
        by_cat[str(cat)].append(t)

    lines = [
        "## AVAILABLE CAPABILITIES",
        "",
        "Behavioral guidance for tools available this turn. "
        "Match argument names exactly (snake_case).",
        "",
    ]
    for cat in sorted(by_cat):
        lines.append(f"### {cat}")
        lines.append("")
        for t in sorted(by_cat[cat], key=lambda x: x.name):
            lines.append(f"**`{t.name}`**")
            desc = (getattr(t, "description", "") or "").strip().split("\n")[0]
            if desc:
                lines.append(f"- {desc}")
            when = (getattr(t, "when_to_use", "") or "").strip()
            if when:
                lines.append(f"- When to use: {when}")
            when_not = (getattr(t, "when_not_to_use", "") or "").strip()
            if when_not:
                lines.append(f"- When not to use: {when_not}")
            pairs = getattr(t, "pairs_with", ()) or ()
            if pairs:
                lines.append("- Pairs with: " + ", ".join(f"`{p}`" for p in pairs))
            lines.append("")
    lines.append(_TOOL_RESULT_CONTRACT)
    if "rna.get_hld" in names or "rna.get_lld" in names:
        lines.append("")
        lines.append(_ARCHITECTURE_DIAGRAMS)
    if "executor.apply" in names:
        lines.append("")
        lines.append(_EDIT_FORMATS)
    return "\n".join(lines).strip() + "\n"
