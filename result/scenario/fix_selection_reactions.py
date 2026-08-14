from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Iterable

from opencc import OpenCC

T2S = OpenCC("t2s")

ROOT = Path(__file__).resolve().parent
SOURCE_DIR = ROOT / "all_scenarios"
TEXT_DIR = ROOT / "scenario_texts"
CHOICE_OPEN = "<选择>"
CHOICE_CLOSE = "</选择>"
OPTION_RE = re.compile(r"^(\d+)\. ")
SELECTOR_RE = re.compile(r"\[s(\d+)\]")
PROMPT_BOUNDARY_RE = re.compile(r"\[(?:n)?s(\d+)\]")


def read_lines(path: Path) -> tuple[list[str], str, bool]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        raw = handle.read()
    eol = "\r\n" if "\r\n" in raw else "\n"
    return raw.splitlines(), eol, raw.endswith(("\n", "\r"))


def write_lines(path: Path, lines: list[str], eol: str, final_newline: bool) -> None:
    content = eol.join(lines)
    if final_newline:
        content += eol
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(content)


def text_parts(value: str) -> list[str]:
    """Return the visible pieces represented by a source text row."""
    value = T2S.convert(value)
    parts = re.split(r"#n|\r?\n", value)
    return [part.strip() for part in parts if part.strip()]


def source_choice_data(records: list[dict]) -> list[dict[int, list[str]]]:
    """Collect non-empty translated rows for every numbered selection branch."""
    choices: list[dict[int, list[str]]] = []
    for index, record in enumerate(records):
        translated = record.get("TextTw") or ""
        selectors = [int(value) for value in SELECTOR_RE.findall(translated)]
        if not selectors:
            continue

        branch_rows: dict[int, list[str]] = {number: [] for number in selectors}
        seen_branch = False
        for following in records[index + 1 :]:
            translated = following.get("TextTw") or ""
            # Some source rows keep the next selection prompt in the same
            # SelectionGroup as the preceding branch. It is a new prompt, not
            # part of the previous branch reaction.
            if PROMPT_BOUNDARY_RE.findall(translated):
                break
            group = int(following.get("SelectionGroup", 0) or 0)
            if group == 0:
                if seen_branch:
                    break
                continue
            if group not in branch_rows:
                continue
            seen_branch = True
            branch_rows[group].extend(text_parts(translated))
        choices.append(branch_rows)
    return choices


def segment_variants(segment: str) -> list[str]:
    variants = [segment]
    stripped = re.sub(r"^\d+;[^;]+;\d+;", "", segment)
    if stripped != segment:
        variants.append(stripped)
    return variants


def match_text(value: str) -> str:
    """Normalize source-only ruby markup before comparing translated text."""
    value = re.sub(r"\[ruby=[^\]]+\]|\[/ruby\]", "", value)
    return value.strip()


def locate_segments(lines: list[str], segments: Iterable[str], start: int, end: int) -> list[int] | None:
    positions: list[int] = []
    cursor = start
    for segment in segments:
        found = None
        for index in range(cursor, end):
            if any(match_text(variant) in match_text(lines[index]) for variant in segment_variants(segment)):
                found = index
                break
        if found is None:
            return None
        positions.append(found)
        cursor = found + 1
    return positions


def trim_blank_edges(values: list[str]) -> list[str]:
    first = 0
    last = len(values)
    while first < last and not values[first].strip():
        first += 1
    while last > first and not values[last - 1].strip():
        last -= 1
    return values[first:last]


def add_choice_spacing(lines: list[str]) -> bool:
    """Put a blank line between every option row and following dialogue."""
    changed = False
    index = 0
    inside_choice = False
    while index < len(lines):
        if lines[index] == CHOICE_OPEN:
            inside_choice = True
        elif lines[index] == CHOICE_CLOSE:
            inside_choice = False
        elif inside_choice and OPTION_RE.match(lines[index]):
            if index + 1 < len(lines) and lines[index + 1].strip():
                lines.insert(index + 1, "")
                changed = True
                index += 1
        index += 1
    return changed


def match_choice_blocks(source_choices: list[dict[int, list[str]]], blocks: list[tuple[int, int, list[int]]]) -> list[tuple[int, int]]:
    """Pair source prompts with text blocks by their numbered option sets."""
    available = set(range(len(blocks)))
    pairs: list[tuple[int, int]] = []
    for source_index, branch_rows in enumerate(source_choices):
        source_options = set(branch_rows)
        candidates = [
            block_index
            for block_index in sorted(available)
            if set(blocks[block_index][2]) == source_options
        ]
        if not candidates:
            continue
        block_index = candidates[0]
        available.remove(block_index)
        pairs.append((source_index, block_index))
    return pairs


def audit_file(source_path: Path, text_path: Path) -> tuple[int, list[str]]:
    records = json.loads(source_path.read_text(encoding="utf-8"))
    source_choices = source_choice_data(records)
    lines, _, _ = read_lines(text_path)
    blocks: list[tuple[int, int, list[int]]] = []
    cursor = 0
    while True:
        try:
            opening = lines.index(CHOICE_OPEN, cursor)
            closing = lines.index(CHOICE_CLOSE, opening + 1)
        except ValueError:
            break
        options = [
            int(match.group(1))
            for line in lines[opening + 1 : closing]
            if (match := OPTION_RE.match(line))
        ]
        blocks.append((opening, closing, options))
        cursor = closing + 1

    problems: list[str] = []
    pairs = match_choice_blocks(source_choices, blocks)
    matched_sources = {source_index for source_index, _ in pairs}
    for source_index, branch_rows in enumerate(source_choices):
        if any(branch_rows.values()) and source_index not in matched_sources:
            problems.append(f"unmatched_source_choice={source_index + 1} options={sorted(branch_rows)}")
    for source_index, block_index in pairs:
        opening, closing, options = blocks[block_index]
        option_indexes = {
            number: index
            for index, line in enumerate(lines[opening + 1 : closing], opening + 1)
            if (match := OPTION_RE.match(line))
            for number in [int(match.group(1))]
        }
        for option_number, segments in source_choices[source_index].items():
            if not segments or option_number not in option_indexes:
                continue
            if locate_segments(lines, segments, option_indexes[option_number] + 1, closing) is None:
                problems.append(f"option={option_number} block={block_index + 1}")
    return len(blocks), problems


def correct_file(source_path: Path, text_path: Path) -> tuple[bool, int, int]:
    records = json.loads(source_path.read_text(encoding="utf-8"))
    source_choices = source_choice_data(records)
    lines, eol, final_newline = read_lines(text_path)

    blocks: list[tuple[int, int, list[int]]] = []
    cursor = 0
    while True:
        try:
            opening = lines.index(CHOICE_OPEN, cursor)
            closing = lines.index(CHOICE_CLOSE, opening + 1)
        except ValueError:
            break
        options = [
            int(match.group(1))
            for line in lines[opening + 1 : closing]
            if (match := OPTION_RE.match(line))
        ]
        blocks.append((opening, closing, options))
        cursor = closing + 1

    changes = 0
    moved_groups = 0
    pairs = match_choice_blocks(source_choices, blocks)
    # Work backwards so edits do not invalidate the positions of later blocks.
    for source_index, block_index in sorted(pairs, key=lambda pair: pair[1], reverse=True):
        opening, closing, options = blocks[block_index]
        branch_rows = source_choices[source_index]
        if not options or not branch_rows:
            continue

        next_opening = blocks[block_index + 1][0] if block_index + 1 < len(blocks) else len(lines)
        ranges: list[tuple[int, int, int, list[str]]] = []
        for option_number, segments in branch_rows.items():
            if option_number not in options or not segments:
                continue
            positions = locate_segments(lines, segments, closing + 1, next_opening)
            if not positions:
                # The branch is already inside the choice, or this source row has
                # a translation shape that cannot be matched safely; leave it alone.
                continue
            first, last = positions[0], positions[-1]
            content = trim_blank_edges(lines[first : last + 1])
            if not content:
                continue
            ranges.append((first, last, option_number, content))

        if not ranges:
            continue

        # If multiple branches have the same response, it is shared dialogue:
        # attach it once after the last matching option rather than duplicating
        # or attaching it to the first option and leaving the later one empty.
        deduplicated: dict[tuple[int, int, tuple[str, ...]], tuple[int, int, int, list[str]]] = {}
        for item in ranges:
            first, last, option_number, content = item
            key = (first, last, tuple(content))
            previous = deduplicated.get(key)
            if previous is None or option_number > previous[2]:
                deduplicated[key] = item

        # Do not risk moving overlapping ranges or ranges that include another
        # option. Such cases are reported for manual review instead.
        occupied: set[int] = set()
        safe_ranges: list[tuple[int, int, int, list[str]]] = []
        for item in sorted(deduplicated.values()):
            first, last, option_number, content = item
            covered = set(range(first, last + 1))
            if occupied & covered:
                continue
            occupied.update(covered)
            safe_ranges.append(item)
        if not safe_ranges:
            continue

        remove: set[int] = set()
        moved: dict[int, list[str]] = {}
        for first, last, option_number, content in safe_ranges:
            remove.update(range(first, last + 1))
            moved[option_number] = content
        if closing + 1 < len(lines) and not lines[closing + 1].strip():
            remove.add(closing + 1)

        lines = [line for index, line in enumerate(lines) if index not in remove]
        # Re-find the closing tag after removing the external branch rows.
        opening = lines.index(CHOICE_OPEN, max(0, opening - len(remove)))
        closing = lines.index(CHOICE_CLOSE, opening + 1)
        for option_number in sorted(moved):
            option_index = next(
                index
                for index in range(opening + 1, closing)
                if lines[index].startswith(f"{option_number}. ")
            )
            insertion = [""] + moved[option_number] + [""]
            lines[option_index + 1 : option_index + 1] = insertion
            closing += len(insertion)
            changes += 1
            moved_groups += 1

    spacing_changed = add_choice_spacing(lines)
    if changes or spacing_changed:
        write_lines(text_path, lines, eol, final_newline)
    return changes > 0 or spacing_changed, changes, moved_groups


def main() -> None:
    if "--check" in sys.argv:
        audited_files = 0
        audited_blocks = 0
        problems: list[str] = []
        for source_path in sorted(SOURCE_DIR.glob("*.json")):
            text_path = TEXT_DIR / f"{source_path.stem}.txt"
            if not text_path.exists():
                continue
            blocks, file_problems = audit_file(source_path, text_path)
            audited_files += 1
            audited_blocks += blocks
            problems.extend(f"{source_path.stem}: {problem}" for problem in file_problems)
        print(f"audited_files={audited_files} audited_blocks={audited_blocks} unresolved={len(problems)}")
        for problem in problems[:100]:
            print(problem)
        raise SystemExit(1 if problems else 0)

    changed_files = 0
    changed_blocks = 0
    moved_groups = 0
    skipped = 0
    for source_path in sorted(SOURCE_DIR.glob("*.json")):
        text_path = TEXT_DIR / f"{source_path.stem}.txt"
        if not text_path.exists():
            skipped += 1
            continue
        changed, blocks, groups = correct_file(source_path, text_path)
        if changed:
            changed_files += 1
            changed_blocks += blocks
            moved_groups += groups
    print(
        f"changed_files={changed_files} changed_options={changed_blocks} "
        f"moved_groups={moved_groups} skipped={skipped}"
    )


if __name__ == "__main__":
    main()
