"""L5 — Soft agent state renderer."""

from __future__ import annotations

from typing import Any


def render_agent_state(state: Any | None) -> str:
    if state is None:
        return (
            "## AGENT STATE\n\n"
            "Phase: DISCOVER\n"
            "Objective: Understand the requested outcome before acting.\n"
            "Completed: (none)\n"
            "Unknown: (none)\n"
            "Next objective: Inspect the repository as needed.\n"
        )

    phase = getattr(state, "phase", "DISCOVER")
    objective = getattr(state, "objective", "")
    completed = getattr(state, "completed", []) or []
    unknown = getattr(state, "unknown", []) or []
    nxt = getattr(state, "next_objective", "")

    lines = [
        "## AGENT STATE",
        "",
        f"Phase: {phase}",
        f"Objective: {objective}",
        "Completed:",
    ]
    if completed:
        for item in list(completed)[:12]:
            lines.append(f"- {item}")
    else:
        lines.append("- (none)")
    lines.append("Unknown:")
    if unknown:
        for item in list(unknown)[:8]:
            lines.append(f"- {item}")
    else:
        lines.append("- (none)")
    lines.append(f"Next objective: {nxt}")
    lines.append("")
    lines.append(
        "Suggested transitions: DISCOVER | PLAN | IMPLEMENT | VERIFY | REPAIR | DONE. "
        "These are guidance — choose the shortest honest path."
    )
    lines.append("")
    return "\n".join(lines)
