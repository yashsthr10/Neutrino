"""Unified-diff parse/apply — adapted from Aider udiff_coder using editblock matchers."""

from __future__ import annotations

import difflib
from itertools import groupby

from src.execution.editblock import replace_most_similar_chunk


class SearchTextNotUnique(ValueError):
    pass


def looks_like_udiff(text: str) -> bool:
    stripped = text.lstrip()
    return stripped.startswith("```diff") or (
        "\n--- " in text and "\n+++ " in text
    ) or stripped.startswith("--- ")


def hunk_to_before_after(hunk: list[str], lines: bool = False):
    before: list[str] = []
    after: list[str] = []
    for line in hunk:
        if len(line) < 1:
            op = " "
            body = line
        else:
            op = line[0]
            body = line[1:]
        if op == " ":
            before.append(body)
            after.append(body)
        elif op == "-":
            before.append(body)
        elif op == "+":
            after.append(body)
    if lines:
        return before, after
    return "".join(before), "".join(after)


def cleanup_pure_whitespace_lines(lines: list[str]) -> list[str]:
    return [
        line if line.strip() else line[-(len(line) - len(line.rstrip("\r\n"))) :]
        for line in lines
    ]


def normalize_hunk(hunk: list[str]) -> list[str]:
    before, after = hunk_to_before_after(hunk, lines=True)
    before = cleanup_pure_whitespace_lines(before)
    after = cleanup_pure_whitespace_lines(after)
    diff = difflib.unified_diff(before, after, n=max(len(before), len(after)))
    return list(diff)[3:]


def find_diffs(content: str) -> list[tuple[str | None, list[str]]]:
    if not content.endswith("\n"):
        content = content + "\n"
    lines = content.splitlines(keepends=True)
    line_num = 0
    edits: list[tuple[str | None, list[str]]] = []
    while line_num < len(lines):
        while line_num < len(lines):
            if lines[line_num].startswith("```diff"):
                line_num, these = process_fenced_block(lines, line_num + 1)
                edits.extend(these)
                break
            # bare unified diff without fence
            if lines[line_num].startswith("--- ") and line_num + 1 < len(lines):
                if lines[line_num + 1].startswith("+++ "):
                    line_num, these = process_fenced_block(lines, line_num)
                    edits.extend(these)
                    break
            line_num += 1
        else:
            break
    return edits


def process_fenced_block(
    lines: list[str], start_line_num: int
) -> tuple[int, list[tuple[str | None, list[str]]]]:
    line_num = start_line_num
    for line_num in range(start_line_num, len(lines)):
        if lines[line_num].startswith("```"):
            break
    else:
        line_num = len(lines)

    block = lines[start_line_num:line_num]
    block.append("@@ @@")

    if block and block[0].startswith("--- ") and len(block) > 1 and block[1].startswith("+++ "):
        a_fname = block[0][4:].strip()
        b_fname = block[1][4:].strip()
        if (a_fname.startswith("a/") or a_fname == "/dev/null") and b_fname.startswith("b/"):
            fname: str | None = b_fname[2:]
        else:
            fname = b_fname
        block = block[2:]
    else:
        fname = None

    edits: list[tuple[str | None, list[str]]] = []
    keeper = False
    hunk: list[str] = []
    for line in block:
        hunk.append(line)
        if len(line) < 2:
            continue
        if line.startswith("+++ ") and len(hunk) >= 2 and hunk[-2].startswith("--- "):
            if len(hunk) >= 3 and hunk[-3] == "\n":
                hunk = hunk[:-3]
            else:
                hunk = hunk[:-2]
            edits.append((fname, hunk))
            hunk = []
            keeper = False
            fname = line[4:].strip()
            continue
        op = line[0]
        if op in "-+":
            keeper = True
            continue
        if op != "@":
            continue
        if not keeper:
            hunk = []
            continue
        hunk = hunk[:-1]
        edits.append((fname, hunk))
        hunk = []
        keeper = False
    return line_num + 1, edits


def apply_hunk_to_content(content: str, hunk: list[str]) -> str | None:
    before_text, after_text = hunk_to_before_after(hunk)
    if not before_text.strip():
        return content + after_text
    if content.count(before_text) > 1 and len("".join(x.strip() for x in before_text.splitlines())) < 10:
        raise SearchTextNotUnique(before_text)
    new_content = replace_most_similar_chunk(content, before_text, after_text)
    return new_content


def collapse_repeats(s: str) -> str:
    return "".join(k for k, _g in groupby(s))
