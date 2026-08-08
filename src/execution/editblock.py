"""SEARCH/REPLACE edit apply — ported from Aider editblock algorithms (no aider imports)."""

from __future__ import annotations

import difflib
import math
import re
from difflib import SequenceMatcher
from pathlib import Path

DEFAULT_FENCE = ("```", "```")

HEAD = r"^<{5,9} SEARCH>?\s*$"
DIVIDER = r"^={5,9}\s*$"
UPDATED = r"^>{5,9} REPLACE\s*$"

HEAD_ERR = "<<<<<<< SEARCH"
DIVIDER_ERR = "======="
UPDATED_ERR = ">>>>>>> REPLACE"


def prep(content: str) -> tuple[str, list[str]]:
    if content and not content.endswith("\n"):
        content += "\n"
    return content, content.splitlines(keepends=True)


def perfect_replace(
    whole_lines: list[str], part_lines: list[str], replace_lines: list[str]
) -> str | None:
    part_tup = tuple(part_lines)
    part_len = len(part_lines)
    for i in range(len(whole_lines) - part_len + 1):
        if tuple(whole_lines[i : i + part_len]) == part_tup:
            return "".join(whole_lines[:i] + replace_lines + whole_lines[i + part_len :])
    return None


def match_but_for_leading_whitespace(
    whole_lines: list[str], part_lines: list[str]
) -> str | None:
    num = len(whole_lines)
    if not all(whole_lines[i].lstrip() == part_lines[i].lstrip() for i in range(num)):
        return None
    add = {
        whole_lines[i][: len(whole_lines[i]) - len(part_lines[i])]
        for i in range(num)
        if whole_lines[i].strip()
    }
    if len(add) != 1:
        return None
    return add.pop()


def replace_part_with_missing_leading_whitespace(
    whole_lines: list[str], part_lines: list[str], replace_lines: list[str]
) -> str | None:
    leading = [len(p) - len(p.lstrip()) for p in part_lines if p.strip()] + [
        len(p) - len(p.lstrip()) for p in replace_lines if p.strip()
    ]
    if leading and min(leading):
        num_leading = min(leading)
        part_lines = [p[num_leading:] if p.strip() else p for p in part_lines]
        replace_lines = [p[num_leading:] if p.strip() else p for p in replace_lines]

    num_part_lines = len(part_lines)
    for i in range(len(whole_lines) - num_part_lines + 1):
        add_leading = match_but_for_leading_whitespace(
            whole_lines[i : i + num_part_lines], part_lines
        )
        if add_leading is None:
            continue
        fixed = [add_leading + rline if rline.strip() else rline for rline in replace_lines]
        return "".join(whole_lines[:i] + fixed + whole_lines[i + num_part_lines :])
    return None


def perfect_or_whitespace(
    whole_lines: list[str], part_lines: list[str], replace_lines: list[str]
) -> str | None:
    res = perfect_replace(whole_lines, part_lines, replace_lines)
    if res:
        return res
    return replace_part_with_missing_leading_whitespace(whole_lines, part_lines, replace_lines)


def try_dotdotdots(whole: str, part: str, replace: str) -> str | None:
    dots_re = re.compile(r"(^\s*\.\.\.\n)", re.MULTILINE | re.DOTALL)
    part_pieces = re.split(dots_re, part)
    replace_pieces = re.split(dots_re, replace)
    if len(part_pieces) != len(replace_pieces):
        raise ValueError("Unpaired ... in SEARCH/REPLACE block")
    if len(part_pieces) == 1:
        return None
    all_dots_match = all(
        part_pieces[i] == replace_pieces[i] for i in range(1, len(part_pieces), 2)
    )
    if not all_dots_match:
        raise ValueError("Unmatched ... in SEARCH/REPLACE block")

    part_pieces = [part_pieces[i] for i in range(0, len(part_pieces), 2)]
    replace_pieces = [replace_pieces[i] for i in range(0, len(replace_pieces), 2)]
    for part_chunk, replace_chunk in zip(part_pieces, replace_pieces):
        if not part_chunk and not replace_chunk:
            continue
        if not part_chunk and replace_chunk:
            if not whole.endswith("\n"):
                whole += "\n"
            whole += replace_chunk
            continue
        if whole.count(part_chunk) != 1:
            raise ValueError
        whole = whole.replace(part_chunk, replace_chunk, 1)
    return whole


def replace_closest_edit_distance(
    whole_lines: list[str],
    part: str,
    part_lines: list[str],
    replace_lines: list[str],
    *,
    similarity_thresh: float = 0.8,
) -> str | None:
    max_similarity = 0.0
    most_similar_chunk_start = -1
    most_similar_chunk_end = -1
    scale = 0.1
    min_len = math.floor(len(part_lines) * (1 - scale))
    max_len = math.ceil(len(part_lines) * (1 + scale))

    for length in range(max(1, min_len), max(max_len, 1) + 1):
        for i in range(len(whole_lines) - length + 1):
            chunk = "".join(whole_lines[i : i + length])
            similarity = SequenceMatcher(None, chunk, part).ratio()
            if similarity > max_similarity:
                max_similarity = similarity
                most_similar_chunk_start = i
                most_similar_chunk_end = i + length

    if max_similarity < similarity_thresh:
        return None
    return "".join(
        whole_lines[:most_similar_chunk_start]
        + replace_lines
        + whole_lines[most_similar_chunk_end:]
    )


def replace_most_similar_chunk(whole: str, part: str, replace: str) -> str | None:
    """Best-effort find `part` in `whole` and replace with `replace`."""
    whole, whole_lines = prep(whole)
    part, part_lines = prep(part)
    replace, replace_lines = prep(replace)

    res = perfect_or_whitespace(whole_lines, part_lines, replace_lines)
    if res:
        return res

    if len(part_lines) > 2 and not part_lines[0].strip():
        res = perfect_or_whitespace(whole_lines, part_lines[1:], replace_lines)
        if res:
            return res

    try:
        res = try_dotdotdots(whole, part, replace)
        if res:
            return res
    except ValueError:
        pass

    return replace_closest_edit_distance(whole_lines, part, part_lines, replace_lines)


def strip_quoted_wrapping(
    res: str, fname: str | None = None, fence: tuple[str, str] = DEFAULT_FENCE
) -> str:
    if not res:
        return res
    lines = res.splitlines()
    if fname and lines and lines[0].strip().endswith(Path(fname).name):
        lines = lines[1:]
    if lines and lines[0].startswith(fence[0]) and lines[-1].startswith(fence[1]):
        lines = lines[1:-1]
    out = "\n".join(lines)
    if out and not out.endswith("\n"):
        out += "\n"
    return out


def apply_search_replace(
    content: str | None,
    before_text: str,
    after_text: str,
    *,
    fname: str = "",
    fence: tuple[str, str] = DEFAULT_FENCE,
) -> str | None:
    before_text = strip_quoted_wrapping(before_text, fname, fence)
    after_text = strip_quoted_wrapping(after_text, fname, fence)
    if content is None:
        return None
    if not before_text.strip():
        return content + after_text
    return replace_most_similar_chunk(content, before_text, after_text)


def strip_filename(filename: str, fence: tuple[str, str]) -> str | None:
    filename = filename.strip()
    if filename == "...":
        return None
    triple = "```"
    for start in (fence[0], triple):
        if filename.startswith(start):
            candidate = filename[len(start) :]
            if candidate and ("." in candidate or "/" in candidate):
                return candidate
            return None
    filename = filename.rstrip(":").lstrip("#").strip().strip("`").strip("*")
    return filename or None


def find_filename(
    lines: list[str], fence: tuple[str, str], valid_fnames: list[str] | None
) -> str | None:
    if valid_fnames is None:
        valid_fnames = []
    rev = list(reversed(lines[:3]))
    filenames: list[str] = []
    for line in rev:
        filename = strip_filename(line, fence)
        if filename:
            filenames.append(filename)
        if not line.startswith(fence[0]) and not line.startswith("```"):
            break
    if not filenames:
        return None
    for fname in filenames:
        if fname in valid_fnames:
            return fname
    for fname in filenames:
        for vfn in valid_fnames:
            if fname == Path(vfn).name:
                return vfn
    for fname in filenames:
        close = difflib.get_close_matches(fname, valid_fnames, n=1, cutoff=0.8)
        if len(close) == 1:
            return close[0]
    for fname in filenames:
        if "." in fname:
            return fname
    return filenames[0]


def find_original_update_blocks(
    content: str,
    fence: tuple[str, str] = DEFAULT_FENCE,
    valid_fnames: list[str] | None = None,
):
    """Yield (filename, original, updated) or (None, shell_content) for bash fences."""
    lines = content.splitlines(keepends=True)
    i = 0
    current_filename = None
    head_pattern = re.compile(HEAD)
    divider_pattern = re.compile(DIVIDER)
    updated_pattern = re.compile(UPDATED)
    missing_filename_err = (
        "Bad/missing filename. The filename must be alone on the line before the opening fence"
        f" {fence[0]}"
    )

    while i < len(lines):
        line = lines[i]
        if head_pattern.match(line.strip()):
            try:
                if i + 1 < len(lines) and divider_pattern.match(lines[i + 1].strip()):
                    filename = find_filename(lines[max(0, i - 3) : i], fence, None)
                else:
                    filename = find_filename(lines[max(0, i - 3) : i], fence, valid_fnames)
                if not filename:
                    if current_filename:
                        filename = current_filename
                    else:
                        raise ValueError(missing_filename_err)
                current_filename = filename
                original_text: list[str] = []
                i += 1
                while i < len(lines) and not divider_pattern.match(lines[i].strip()):
                    original_text.append(lines[i])
                    i += 1
                if i >= len(lines) or not divider_pattern.match(lines[i].strip()):
                    raise ValueError(f"Expected `{DIVIDER_ERR}`")
                updated_text: list[str] = []
                i += 1
                while i < len(lines) and not (
                    updated_pattern.match(lines[i].strip())
                    or divider_pattern.match(lines[i].strip())
                ):
                    updated_text.append(lines[i])
                    i += 1
                if i >= len(lines) or not (
                    updated_pattern.match(lines[i].strip())
                    or divider_pattern.match(lines[i].strip())
                ):
                    raise ValueError(f"Expected `{UPDATED_ERR}` or `{DIVIDER_ERR}`")
                yield filename, "".join(original_text), "".join(updated_text)
            except ValueError as e:
                processed = "".join(lines[: i + 1])
                raise ValueError(f"{processed}\n^^^ {e.args[0]}") from e
        i += 1


def find_similar_lines(search_lines: str, content_lines: str, threshold: float = 0.6) -> str:
    search = search_lines.splitlines()
    content = content_lines.splitlines()
    if not search or len(content) < len(search):
        return ""
    best_ratio = 0.0
    best_match: list[str] | None = None
    best_match_i = 0
    for i in range(len(content) - len(search) + 1):
        chunk = content[i : i + len(search)]
        ratio = SequenceMatcher(None, search, chunk).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_match = chunk
            best_match_i = i
    if best_ratio < threshold or best_match is None:
        return ""
    if best_match[0] == search[0] and best_match[-1] == search[-1]:
        return "\n".join(best_match)
    n = 5
    end = min(len(content), best_match_i + len(search) + n)
    start = max(0, best_match_i - n)
    return "\n".join(content[start:end])


def looks_like_search_replace(text: str) -> bool:
    return bool(re.search(HEAD, text, re.MULTILINE))
