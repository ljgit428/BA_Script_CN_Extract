#!/usr/bin/env python3
"""从 raw 数据提取按角色汇总的羁绊剧情文本。

每个 CharacterId 输出一个 TXT。羁绊日程由 AcademyFavorScheduleExcelTable
关联到 ScenarioScriptExcelTable 的 GroupId，再复用 Scenario 转换器生成对白。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from opencc import OpenCC


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = PROJECT_ROOT / "script"
RAW_DB_DIR = PROJECT_ROOT / "raw" / "ba-data-global" / "DB"
RESULT_DIR = PROJECT_ROOT / "result" / "bond_story"
TEXT_OUTPUT_DIR = RESULT_DIR / "bond_story_text"
REPORT_DIR = RESULT_DIR / "reports"

SCHEDULE_INPUT = RAW_DB_DIR / "AcademyFavorScheduleExcelTable.json"
SCRIPT_INPUTS = [
    RAW_DB_DIR / "ScenarioScriptExcelTable1.json",
    RAW_DB_DIR / "ScenarioScriptExcelTable2.json",
    RAW_DB_DIR / "ScenarioScriptExcelTable3.json",
]
CHARACTER_NAMES_INPUT = RAW_DB_DIR / "ScenarioCharacterNameExcelTable.json"

# AcademyFavorSchedule stores the location in Korean. Keep this mapping
# explicit so the output follows the project's established Chinese names.
LOCATION_NAMES = {
    "샬레": "夏莱",
}

# Reuse the project's existing Scenario and Momotalk name conversion logic.
sys.path.insert(0, str(SCRIPT_DIR / "scenario"))
sys.path.insert(0, str(SCRIPT_DIR / "Momotalk"))
from convert_scenario_to_txt import (  # noqa: E402
    CharacterNameResolver,
    clean_text,
    convert_rows,
)
from academy_messanger_to_txt import CharacterResolver  # noqa: E402


def load_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as file:
        data = json.load(file)
    rows = data.get("DataList") if isinstance(data, dict) else data
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"{path} 不是有效的 DataList JSON 数组。")
    return rows


def safe_filename(value: str) -> str:
    invalid_chars = '<>:/\\|?*"'
    text = value.translate({ord(char): "_" for char in invalid_chars})
    text = "".join("_" if ord(char) < 32 else char for char in text).strip(" .")
    return text or "unknown"


def as_id(value: Any) -> str:
    text = str(value or "").strip()
    return text or "unknown"


def schedule_sort_key(row: dict[str, Any]) -> tuple[int, int, int, int, str]:
    def number(field: str) -> int:
        try:
            return int(row.get(field) or 0)
        except (TypeError, ValueError):
            return 0

    return (
        number("ScheduleGroupId"),
        number("OrderInGroup"),
        number("FavorRank"),
        number("Id"),
        as_id(row.get("ScenarioSriptGroupId")),
    )


def without_group_header(text: str) -> str:
    """Remove the converter's technical GroupId header from the public output."""
    lines = text.splitlines()
    if lines and lines[0].startswith("GroupId:"):
        lines = lines[1:]
        if lines and not lines[0].strip():
            lines = lines[1:]
    return "\n".join(lines).strip()


def extract_scene_locations(
    rows: Iterable[dict[str, Any]], converter: OpenCC
) -> list[str]:
    """Extract actual scene names from ScenarioScript #place markers.

    AcademyFavorSchedule.Location is the unlock/contact location and currently
    always contains Schale. The actual setting of a bond story is carried by
    ScenarioScript #place rows and their localized TextTw value.
    """
    locations: list[str] = []
    for row in rows:
        script = str(row.get("ScriptKr") or "")
        has_place_marker = any(
            line.strip().lower().startswith("#place;")
            for line in script.replace("\\\\n", "\\n").splitlines()
        )
        if not has_place_marker:
            continue
        text = converter.convert(clean_text(str(row.get("TextTw") or ""))).strip()
        for location in text.splitlines():
            location = location.strip()
            if location and location not in locations:
                locations.append(location)
    return locations


def load_script_groups(input_paths: Iterable[Path]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in input_paths:
        for row in load_rows(path):
            group_id = row.get("GroupId")
            if group_id is not None:
                groups[str(group_id)].append(row)
    return groups


def clear_owned_outputs(output_dir: Path) -> None:
    marker = output_dir / ".bond_story.generated"
    if not marker.exists():
        return
    try:
        old_files = {
            line.strip()
            for line in marker.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
    except OSError:
        old_files = set()
    for filename in old_files:
        if Path(filename).name == filename and filename.endswith(".txt"):
            path = output_dir / filename
            if path.is_file():
                path.unlink()


def generate(
    schedule_path: Path = SCHEDULE_INPUT,
    script_paths: Iterable[Path] = SCRIPT_INPUTS,
    names_path: Path = CHARACTER_NAMES_INPUT,
    db_dir: Path = RAW_DB_DIR,
    output_dir: Path = TEXT_OUTPUT_DIR,
    report_dir: Path = REPORT_DIR,
) -> dict[str, Any]:
    converter = OpenCC("t2s")
    schedule_rows = load_rows(schedule_path)
    script_groups = load_script_groups(script_paths)
    scenario_resolver = CharacterNameResolver(names_path, converter)
    character_resolver = CharacterResolver(db_dir, converter)

    by_character: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in schedule_rows:
        by_character[as_id(row.get("CharacterId"))].append(row)
    for rows in by_character.values():
        rows.sort(key=schedule_sort_key)

    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    clear_owned_outputs(output_dir)

    manifest: list[dict[str, Any]] = []
    missing_groups: list[dict[str, Any]] = []
    empty_groups: list[dict[str, Any]] = []
    generated_files: list[str] = []

    for character_id in sorted(by_character, key=lambda value: (value == "unknown", value)):
        schedules = by_character[character_id]
        if character_id == "unknown":
            display_name = "未知角色"
        else:
            display_name, _ = character_resolver.resolve(character_id)
            if display_name.startswith("角色("):
                # CharacterExcel's ScenarioCharacter is a useful fallback for
                # newly added IDs that are absent from the profile table.
                character_row = character_resolver.character_rows.get(character_id, {})
                raw_name = str(character_row.get("ScenarioCharacter") or "").strip()
                if raw_name:
                    display_name, _ = scenario_resolver.display_name(raw_name)

        lines = [f"{display_name}——羁绊剧情", ""]
        story_manifest: list[dict[str, Any]] = []
        converted_story_count = 0

        for number, schedule in enumerate(schedules, start=1):
            group_id = as_id(schedule.get("ScenarioSriptGroupId"))
            group_rows = script_groups.get(group_id, [])
            schedule_location = str(schedule.get("Location") or "").strip()
            schedule_location = LOCATION_NAMES.get(schedule_location, schedule_location)
            scene_locations = extract_scene_locations(group_rows, converter)
            story_info = {
                "number": number,
                "schedule_id": schedule.get("Id"),
                "character_id": schedule.get("CharacterId"),
                "favor_rank": schedule.get("FavorRank"),
                "schedule_group_id": schedule.get("ScheduleGroupId"),
                "order_in_group": schedule.get("OrderInGroup"),
                "scenario_group_id": schedule.get("ScenarioSriptGroupId"),
                "location": "、".join(scene_locations),
                "schedule_location": schedule_location,
                "scene_locations": scene_locations,
                "status": "generated" if group_rows else "missing_group",
            }
            story_manifest.append(story_info)

            lines.append(f"=== 羁绊剧情 {number} ===")
            favor_rank = schedule.get("FavorRank")
            if favor_rank not in (None, "", 0, "0"):
                lines.append(f"羁绊等级：{favor_rank}")
            if scene_locations:
                lines.append(f"场景地点：{'、'.join(scene_locations)}")
            lines.append("")

            if not group_rows:
                lines.append("[缺少对应剧情文本]")
                lines.append("")
                missing_groups.append(story_info)
                continue

            diagnostics: dict[str, Any] = {}
            converted = without_group_header(
                convert_rows(
                    group_rows,
                    resolver=scenario_resolver,
                    diagnostics=diagnostics,
                )
            )
            if converted:
                lines.append(converted)
                converted_story_count += 1
                story_info["status"] = "generated"
            else:
                lines.append("[剧情文本为空]")
                story_info["status"] = "empty_text"
                empty_groups.append(story_info)
            lines.append("")

        filename = f"{safe_filename(display_name)}_{safe_filename(character_id)}.txt"
        destination = output_dir / filename
        destination.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        generated_files.append(filename)
        manifest.append(
            {
                "character_id": character_id,
                "display_name": display_name,
                "file": filename,
                "bond_story_count": len(schedules),
                "converted_story_count": converted_story_count,
                "stories": story_manifest,
            }
        )

    (output_dir / ".bond_story.generated").write_text(
        "\n".join(sorted(generated_files)) + "\n", encoding="utf-8"
    )
    summary = {
        "schedule_records": len(schedule_rows),
        "character_ids": len(by_character),
        "generated_files": len(manifest),
        "converted_bond_stories": sum(item["converted_story_count"] for item in manifest),
        "missing_bond_stories": len(missing_groups),
        "empty_bond_stories": len(empty_groups),
        "stories_with_scene_locations": sum(
            bool(story["scene_locations"])
            for item in manifest
            for story in item["stories"]
        ),
        "scenario_script_groups": len(script_groups),
        "output_dir": str(output_dir),
        "report_dir": str(report_dir),
    }
    (report_dir / "bond_story_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (report_dir / "bond_story_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (report_dir / "missing_bond_stories.json").write_text(
        json.dumps(missing_groups, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (report_dir / "empty_bond_stories.json").write_text(
        json.dumps(empty_groups, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"羁绊剧情生成完成：{summary['character_ids']} 个角色，"
        f"{summary['converted_bond_stories']}/{summary['schedule_records']} 段有文本剧情，"
        f"{summary['empty_bond_stories']} 段原始文本为空，"
        f"生成 {summary['generated_files']} 个 TXT。"
    )
    print(f"输出目录：{output_dir}")
    print(f"报告目录：{report_dir}")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="从 raw 数据生成按角色汇总的羁绊剧情 TXT。")
    parser.add_argument("--schedule", type=Path, default=SCHEDULE_INPUT)
    parser.add_argument("--script", type=Path, nargs="+", default=SCRIPT_INPUTS)
    parser.add_argument("--names", type=Path, default=CHARACTER_NAMES_INPUT)
    parser.add_argument("--db-dir", type=Path, default=RAW_DB_DIR)
    parser.add_argument("--output-dir", type=Path, default=TEXT_OUTPUT_DIR)
    parser.add_argument("--report-dir", type=Path, default=REPORT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    generate(
        schedule_path=args.schedule,
        script_paths=args.script,
        names_path=args.names,
        db_dir=args.db_dir,
        output_dir=args.output_dir,
        report_dir=args.report_dir,
    )


if __name__ == "__main__":
    main()
