"""Apply-patch format parse/apply — ported from Aider patch_coder (no aider imports)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class DiffError(ValueError):
    """Problem while parsing or applying a patch."""


class ActionType(str, Enum):
    ADD = "Add"
    DELETE = "Delete"
    UPDATE = "Update"


@dataclass
class Chunk:
    orig_index: int = -1
    del_lines: List[str] = field(default_factory=list)
    ins_lines: List[str] = field(default_factory=list)


@dataclass
class PatchAction:
    type: ActionType
    path: str
    new_content: Optional[str] = None
    chunks: List[Chunk] = field(default_factory=list)
    move_path: Optional[str] = None


@dataclass
class Patch:
    actions: Dict[str, PatchAction] = field(default_factory=dict)
    fuzz: int = 0


def _norm(line: str) -> str:
    return line.rstrip("\r")


def _without_diff_prefix(line: str) -> str:
    """Strip optional unified-diff ``+`` / ``-`` / `` `` prefix for sentinel checks."""
    if line.startswith(("+", "-", " ")):
        return line[1:]
    return line


def _is_patch_boundary(line: str, *, include_hunk: bool = False) -> bool:
    """True for structural patch markers, even if the model prefixed them with ``+``.

    Models frequently emit ``+*** End Patch`` as if it were file content; without
    this check that marker is written into the target file.
    """
    body = _norm(_without_diff_prefix(line)).strip()
    if not body:
        return False
    if body in {"*** End Patch", "*** End of File", "***"}:
        return True
    prefixes = (
        "*** End Patch",
        "*** Update File:",
        "*** Delete File:",
        "*** Add File:",
        "*** Begin Patch",
        "*** Move to:",
    )
    if body.startswith(prefixes):
        return True
    if include_hunk and body.startswith("@@"):
        return True
    return False


def find_context_core(lines: List[str], context: List[str], start: int) -> Tuple[int, int]:
    if not context:
        return start, 0
    for i in range(start, len(lines) - len(context) + 1):
        if lines[i : i + len(context)] == context:
            return i, 0
    norm_context = [s.rstrip() for s in context]
    for i in range(start, len(lines) - len(context) + 1):
        if [s.rstrip() for s in lines[i : i + len(context)]] == norm_context:
            return i, 1
    norm_context_strip = [s.strip() for s in context]
    for i in range(start, len(lines) - len(context) + 1):
        if [s.strip() for s in lines[i : i + len(context)]] == norm_context_strip:
            return i, 100
    return -1, 0


def find_context(
    lines: List[str], context: List[str], start: int, eof: bool
) -> Tuple[int, int]:
    if eof:
        if len(lines) >= len(context):
            new_index, fuzz = find_context_core(lines, context, len(lines) - len(context))
            if new_index != -1:
                return new_index, fuzz
        new_index, fuzz = find_context_core(lines, context, start)
        return new_index, fuzz + 10_000
    return find_context_core(lines, context, start)


def peek_next_section(lines: List[str], index: int) -> Tuple[List[str], List[Chunk], int, bool]:
    context_lines: List[str] = []
    del_lines: List[str] = []
    ins_lines: List[str] = []
    chunks: List[Chunk] = []
    mode = "keep"
    start_index = index

    while index < len(lines):
        line = lines[index]
        if _is_patch_boundary(line, include_hunk=True):
            break
        norm_line = _norm(line)
        if norm_line.startswith("***"):
            raise DiffError(f"Invalid patch line found in update section: {line}")

        index += 1
        last_mode = mode
        if line.startswith("+"):
            mode = "add"
            line_content = line[1:]
        elif line.startswith("-"):
            mode = "delete"
            line_content = line[1:]
        elif line.startswith(" "):
            mode = "keep"
            line_content = line[1:]
        elif line.strip() == "":
            mode = "keep"
            line_content = ""
        else:
            raise DiffError(f"Invalid line prefix in update section: {line}")

        if mode == "keep" and last_mode != "keep":
            if del_lines or ins_lines:
                chunks.append(
                    Chunk(
                        orig_index=len(context_lines) - len(del_lines),
                        del_lines=del_lines,
                        ins_lines=ins_lines,
                    )
                )
            del_lines, ins_lines = [], []

        if mode == "delete":
            del_lines.append(line_content)
            context_lines.append(line_content)
        elif mode == "add":
            ins_lines.append(line_content)
        elif mode == "keep":
            context_lines.append(line_content)

    if del_lines or ins_lines:
        chunks.append(
            Chunk(
                orig_index=len(context_lines) - len(del_lines),
                del_lines=del_lines,
                ins_lines=ins_lines,
            )
        )

    is_eof = False
    if index < len(lines) and _norm(_without_diff_prefix(lines[index])).strip() in {
        "*** End of File",
    }:
        index += 1
        is_eof = True
    if index == start_index and not is_eof:
        raise DiffError("Empty patch section found.")
    return context_lines, chunks, index, is_eof


def identify_files_needed(text: str) -> List[str]:
    paths = set()
    for line in text.splitlines():
        norm_line = _norm(line)
        if norm_line.startswith("*** Update File: "):
            paths.add(norm_line[len("*** Update File: ") :].strip())
        elif norm_line.startswith("*** Delete File: "):
            paths.add(norm_line[len("*** Delete File: ") :].strip())
    return list(paths)


def looks_like_patch(text: str) -> bool:
    return any(
        _norm(line).startswith(
            ("*** Begin Patch", "*** Update File:", "*** Add File:", "*** Delete File:")
        )
        for line in text.splitlines()
    )


def parse_patch_text(text: str, current_files: Dict[str, str]) -> Patch:
    lines = text.splitlines()
    if not lines:
        return Patch()
    if _norm(lines[0]).startswith("*** Begin Patch"):
        start_index = 1
    else:
        if not looks_like_patch(text):
            raise DiffError("Response does not appear to be in patch format.")
        start_index = 0

    patch = Patch()
    index = start_index
    fuzz_accumulator = 0

    while index < len(lines):
        line = lines[index]
        norm_line = _norm(line)

        if _is_patch_boundary(line) and _norm(_without_diff_prefix(line)).strip().startswith(
            "*** End Patch"
        ):
            break

        if norm_line.startswith("*** Update File: "):
            path = norm_line[len("*** Update File: ") :].strip()
            index += 1
            if not path:
                raise DiffError("Update File action missing path.")
            move_to = None
            if index < len(lines) and _norm(lines[index]).startswith("*** Move to: "):
                move_to = _norm(lines[index])[len("*** Move to: ") :].strip()
                index += 1
            if path not in current_files:
                raise DiffError(f"Update File Error - missing file content for: {path}")
            action, index, fuzz = _parse_update_file_sections(
                lines, index, current_files[path]
            )
            action.path = path
            action.move_path = move_to
            existing = patch.actions.get(path)
            if existing is not None:
                if existing.type != ActionType.UPDATE:
                    raise DiffError(f"Conflicting actions for file: {path}")
                existing.chunks.extend(action.chunks)
                if move_to:
                    existing.move_path = move_to
            else:
                patch.actions[path] = action
            fuzz_accumulator += fuzz
            continue

        if norm_line.startswith("*** Delete File: "):
            path = norm_line[len("*** Delete File: ") :].strip()
            index += 1
            if not path:
                raise DiffError("Delete File action missing path.")
            if path not in current_files:
                raise DiffError(f"Delete File Error - file not found: {path}")
            patch.actions[path] = PatchAction(type=ActionType.DELETE, path=path)
            continue

        if norm_line.startswith("*** Add File: "):
            path = norm_line[len("*** Add File: ") :].strip()
            index += 1
            if not path:
                raise DiffError("Add File action missing path.")
            if path in patch.actions:
                raise DiffError(f"Duplicate action for file: {path}")
            action, index = _parse_add_file_content(lines, index)
            action.path = path
            patch.actions[path] = action
            continue

        if not norm_line.strip():
            index += 1
            continue
        raise DiffError(f"Unknown or misplaced line while parsing patch: {line}")

    patch.fuzz = fuzz_accumulator
    return patch


def _parse_update_file_sections(
    lines: List[str], index: int, file_content: str
) -> Tuple[PatchAction, int, int]:
    action = PatchAction(type=ActionType.UPDATE, path="")
    orig_lines = file_content.splitlines()
    current_file_index = 0
    total_fuzz = 0

    while index < len(lines):
        if _is_patch_boundary(lines[index]) and not _norm(
            _without_diff_prefix(lines[index])
        ).strip().startswith("@@"):
            break

        scope_lines: List[str] = []
        while index < len(lines) and _norm(lines[index]).startswith("@@"):
            scope_line_content = lines[index][len("@@") :].strip()
            if scope_line_content:
                scope_lines.append(scope_line_content)
            index += 1

        if scope_lines:
            found_scope = False
            temp_index = current_file_index
            while temp_index < len(orig_lines):
                match = True
                for i, scope in enumerate(scope_lines):
                    if (
                        temp_index + i >= len(orig_lines)
                        or _norm(orig_lines[temp_index + i]).strip() != scope
                    ):
                        match = False
                        break
                if match:
                    current_file_index = temp_index + len(scope_lines)
                    found_scope = True
                    break
                temp_index += 1
            if not found_scope:
                raise DiffError("Could not find scope context:\n" + "\n".join(scope_lines))

        context_block, chunks_in_section, next_index, is_eof = peek_next_section(lines, index)
        found_index, fuzz = find_context(orig_lines, context_block, current_file_index, is_eof)
        total_fuzz += fuzz
        if found_index == -1:
            raise DiffError(
                f"Could not find patch context starting near line {current_file_index}:\n"
                + "\n".join(context_block)
            )
        for chunk in chunks_in_section:
            chunk.orig_index += found_index
            action.chunks.append(chunk)
        current_file_index = found_index + len(context_block)
        index = next_index

    return action, index, total_fuzz


def _parse_add_file_content(lines: List[str], index: int) -> Tuple[PatchAction, int]:
    added_lines: List[str] = []
    while index < len(lines):
        line = lines[index]
        if _is_patch_boundary(line):
            break
        norm_line = _norm(line)
        if not line.startswith("+"):
            if norm_line.strip() == "":
                added_lines.append("")
            else:
                raise DiffError(f"Invalid Add File line (missing '+'): {line}")
        else:
            added_lines.append(line[1:])
        index += 1
    # Defense in depth: drop a trailing End Patch that slipped past as content.
    while added_lines and _norm(added_lines[-1]).strip() in {
        "*** End Patch",
        "*** End of File",
    }:
        added_lines.pop()
    return PatchAction(type=ActionType.ADD, path="", new_content="\n".join(added_lines)), index


def apply_update_content(text: str, action: PatchAction) -> str:
    if action.type is not ActionType.UPDATE:
        raise DiffError("_apply_update called with non-update action")
    orig_lines = text.splitlines()
    dest_lines: List[str] = []
    current_orig_line_idx = 0
    for chunk in sorted(action.chunks, key=lambda c: c.orig_index):
        chunk_start_index = chunk.orig_index
        if chunk_start_index < current_orig_line_idx:
            raise DiffError(
                f"{action.path}: Overlapping or out-of-order chunk detected."
            )
        dest_lines.extend(orig_lines[current_orig_line_idx:chunk_start_index])
        num_del = len(chunk.del_lines)
        actual_deleted = orig_lines[chunk_start_index : chunk_start_index + num_del]
        norm_chunk_del = [_norm(s).strip() for s in chunk.del_lines]
        norm_actual_del = [_norm(s).strip() for s in actual_deleted]
        if norm_chunk_del != norm_actual_del:
            raise DiffError(
                f"{action.path}: Mismatch applying patch near line {chunk_start_index + 1}."
            )
        dest_lines.extend(chunk.ins_lines)
        current_orig_line_idx = chunk_start_index + num_del
    dest_lines.extend(orig_lines[current_orig_line_idx:])
    while dest_lines and _norm(dest_lines[-1]).strip() in {
        "*** End Patch",
        "*** End of File",
    }:
        dest_lines.pop()
    result = "\n".join(dest_lines)
    if result or orig_lines:
        result += "\n"
    return result
