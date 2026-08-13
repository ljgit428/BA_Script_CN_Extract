#!/usr/bin/env python3
"""按自由会话 GroupId 提取 Field 探索中的人物自由活动对白。

CharacterDialogFieldExcelTable 的每个 GroupId 代表一段独立会话，因此本脚本
按段落输出一个 TXT，而不是按角色合并。该表只提供 TargetIndex，不直接提供角色名；
脚本会尝试通过 FieldDate 的角色图标和 ScenarioCharacterName 表补充关联角色名。
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from opencc import OpenCC


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_EXCEL_DIR = PROJECT_ROOT / "raw" / "ba-data-global" / "Excel"
RESULT_DIR = PROJECT_ROOT / "result" / "free_dialog"
TEXT_OUTPUT_DIR = RESULT_DIR / "free_dialog_text"
REPORT_DIR = RESULT_DIR / "reports"

DIALOG_INPUT = RAW_EXCEL_DIR / "CharacterDialogFieldExcelTable.json"
INTERACTION_INPUT = RAW_EXCEL_DIR / "FieldInteractionExcelTable.json"
SCENE_INPUT = RAW_EXCEL_DIR / "FieldSceneExcelTable.json"
WORLD_MAP_INPUT = RAW_EXCEL_DIR / "FieldWorldMapZoneExcelTable.json"
DATE_INPUT = RAW_EXCEL_DIR / "FieldDateExcelTable.json"
NAME_INPUT = PROJECT_ROOT / "raw" / "ba-data-global" / "DB" / "ScenarioCharacterNameExcelTable.json"

# 已确认的 FieldSeason 中文名称。未收录的季节只输出原始 FieldSeasonId。
FIELD_SEASON_NAMES = {
    "843": "千年EXPO",
}

DIALOG_TYPE_NAMES = {
    "Talk": "对话",
    "Think": "内心独白",
    "Question": "疑问",
    "Exclaim": "感叹",
    "Upset": "不满",
    "Surprise": "惊讶",
    "Sweat": "汗",
    "Dot": "省略号",
    "Music": "音乐",
}


def load_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as file:
        data = json.load(file)
    rows = data.get("DataList") if isinstance(data, dict) else data
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"{path} 不是有效的 DataList JSON 数组。")
    return rows


def as_id(value: Any) -> str:
    if value is None:
        return "unknown"
    text = str(value).strip()
    return text or "unknown"


def safe_filename(value: str) -> str:
    invalid_chars = '<>:/\\|?*"'
    text = value.translate({ord(char): "_" for char in invalid_chars})
    text = "".join("_" if ord(char) < 32 else char for char in text).strip(" .")
    return text or "unknown"


def simplify(value: Any, converter: OpenCC) -> str:
    text = str(value or "")
    text = text.replace("\\n", "\n")
    text = re.sub(r"\[땀\]", "[汗]", text)
    text = re.sub(r"\[손땀\]", "[汗]", text)
    return converter.convert(text).strip()


def group_id_parts(group_id: str) -> tuple[str, str, str]:
    """从标准 Field GroupId 推导 FieldSeason、FieldDate 和 FieldScene 前缀。"""
    if group_id.isdigit() and len(group_id) >= 7:
        return group_id[:3], group_id[:5], group_id[:7]
    return "", "", ""


def flatten_ids(value: Any) -> list[str]:
    if isinstance(value, list):
        return [as_id(item) for item in value]
    if value in (None, ""):
        return []
    return [as_id(value)]


def build_interaction_index(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        for interaction_id in flatten_ids(row.get("InteractionId")):
            index[interaction_id].append(row)
    return index


def build_scene_index(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {as_id(row.get("UniqueId")): row for row in rows if row.get("UniqueId") is not None}


def build_zone_index(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        result_scene = as_id(row.get("ResultFieldScene"))
        if result_scene != "unknown":
            index[result_scene].append(row)
    return index


def find_scene(scene_index: dict[str, dict[str, Any]], scene_prefix: str) -> dict[str, Any] | None:
    if not scene_prefix:
        return None
    candidates = [
        (len(unique_id), row)
        for unique_id, row in scene_index.items()
        if scene_prefix.startswith(unique_id) or unique_id.startswith(scene_prefix)
    ]
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def find_interactions(
    group_id: str, interaction_index: dict[str, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    """只关联 FieldInteraction 中明确引用当前 GroupId 的记录。"""
    return interaction_index.get(group_id, [])


def build_date_index(rows: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (as_id(row.get("SeasonId")), as_id(row.get("UniqueId"))): row
        for row in rows
        if row.get("SeasonId") is not None and row.get("UniqueId") is not None
    }


def character_tokens(date_row: dict[str, Any] | None) -> list[str]:
    if not date_row:
        return []
    tokens: list[str] = []
    for field, prefix in (
        ("CharacterIconPath", "Field_Student_Portrait_"),
        ("DateResultSpinePath", "CharacterSpine_"),
    ):
        value = str(date_row.get(field) or "")
        if prefix in value:
            token = value.split(prefix, 1)[1].split("/", 1)[0]
            if token and token not in tokens:
                tokens.append(token)
    return tokens


def build_character_names(rows: list[dict[str, Any]], converter: OpenCC) -> dict[str, str]:
    names: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        spine = str(row.get("SpinePrefabName") or "")
        match = re.search(r"CharacterSpine_([^/]+)", spine)
        name_tw = str(row.get("NameTW") or "").strip()
        if match and name_tw:
            names[match.group(1)].add(converter.convert(name_tw))
    return {
        token: sorted(values)[0]
        for token, values in names.items()
        if values
    }


def speaker_label(target_index: Any, date_character: str) -> str:
    target = as_id(target_index)
    if date_character:
        return f"TargetIndex {target}（FieldDate 关联角色：{date_character}）"
    return f"TargetIndex {target}（角色名仍未在 Field 数据中直接提供）"


def clear_owned_outputs(output_dir: Path) -> None:
    marker = output_dir / ".free_dialog.generated"
    if not marker.exists():
        return
    try:
        files = {
            line.strip()
            for line in marker.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
    except OSError:
        files = set()
    for filename in files:
        if Path(filename).name == filename and filename.endswith(".txt"):
            path = output_dir / filename
            if path.is_file():
                path.unlink()


def generate(
    input_path: Path = DIALOG_INPUT,
    output_dir: Path = TEXT_OUTPUT_DIR,
    report_dir: Path = REPORT_DIR,
    interaction_path: Path = INTERACTION_INPUT,
    scene_path: Path = SCENE_INPUT,
    world_map_path: Path = WORLD_MAP_INPUT,
    date_path: Path = DATE_INPUT,
    name_path: Path = NAME_INPUT,
) -> dict[str, Any]:
    converter = OpenCC("t2s")
    dialog_rows = load_rows(input_path)
    interaction_rows = load_rows(interaction_path) if interaction_path.exists() else []
    scene_rows = load_rows(scene_path) if scene_path.exists() else []
    world_map_rows = load_rows(world_map_path) if world_map_path.exists() else []
    date_rows = load_rows(date_path) if date_path.exists() else []
    name_rows = load_rows(name_path) if name_path.exists() else []

    grouped: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for source_index, row in enumerate(dialog_rows):
        grouped[as_id(row.get("GroupId"))].append((source_index, row))
    interaction_index = build_interaction_index(interaction_rows)
    scene_index = build_scene_index(scene_rows)
    zone_index = build_zone_index(world_map_rows)
    date_index = build_date_index(date_rows)
    character_names = build_character_names(name_rows, converter)

    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    clear_owned_outputs(output_dir)

    manifest: list[dict[str, Any]] = []
    generated_files: list[str] = []
    for group_id in sorted(grouped, key=lambda value: (not value.isdigit(), value)):
        entries = grouped[group_id]
        season_id, date_id, scene_prefix = group_id_parts(group_id)
        scene = find_scene(scene_index, scene_prefix)
        linked_interactions = find_interactions(group_id, interaction_index)
        scene_id = as_id(scene.get("UniqueId")) if scene else ""
        world_map_zones = zone_index.get(scene_id, [])
        date_row = date_index.get((season_id, date_id))
        if date_row is None:
            same_date_rows = [
                row for (_, row_date), row in date_index.items() if row_date == date_id
            ]
            if len(same_date_rows) == 1:
                date_row = same_date_rows[0]
        tokens = character_tokens(date_row)
        token = next((candidate for candidate in tokens if candidate in character_names), "")
        if not token and tokens:
            token = tokens[0]
        date_character = character_names.get(token, "")
        season_name = FIELD_SEASON_NAMES.get(season_id, f"FieldSeason {season_id}" if season_id else "未知场景")
        filename = f"{safe_filename(group_id)}.txt"

        lines = [
            f"=== 自由会话 {group_id} ===",
            f"场景：{season_name}",
        ]
        if date_character:
            lines.append(f"关联角色：{date_character}（{token}）")
        elif token:
            lines.append(f"关联角色：{token}（角色名未在名称表中找到）")
        if date_id:
            lines.append(f"FieldDateId：{date_id}")
        if scene_id:
            lines.append(f"场景资源：{scene.get('ArtLevelPath') or scene.get('DesignLevelPath') or scene_id}")
        if world_map_zones:
            zone_ids = "、".join(as_id(row.get("Id")) for row in world_map_zones)
            lines.append(f"世界地图区域：{zone_ids}")
        lines.extend([
            f"来源表：{input_path.name}",
            "说明：CharacterDialogField 未提供逐阶段角色名；关联角色由 FieldDate 角色图标映射，以下仍保留原始 TargetIndex。",
            "",
        ])

        for _, row in sorted(entries, key=lambda item: (int(item[1].get("Phase") or 0), item[0])):
            phase = row.get("Phase")
            dialog_type = as_id(row.get("DialogType"))
            type_name = DIALOG_TYPE_NAMES.get(dialog_type, dialog_type)
            lines.extend([
                f"--- 阶段 {phase} ---",
                f"说话者：{speaker_label(row.get('TargetIndex'), date_character)}",
                f"类型：{type_name}（{dialog_type}）",
            ])
            text = simplify(row.get("LocalizeTW"), converter)
            if not text:
                text = simplify(row.get("LocalizeKR"), converter)
            lines.append(f"内容：{text or '[无本地化文本]'}")
            if row.get("Duration") not in (None, ""):
                lines.append(f"持续时间：{row['Duration']} ms")
            lines.append("")

        destination = output_dir / filename
        destination.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        generated_files.append(filename)
        manifest.append(
            {
                "group_id": group_id,
                "file": filename,
                "source_row_indices": [index for index, _ in entries],
                "phase_count": len(entries),
                "field_season_id": season_id,
                "field_date_id": date_id,
                "field_scene_id": scene_id,
                "field_season_name": season_name,
                "character_token": token,
                "character_name": date_character,
                "has_character_name": bool(date_character),
                "scene_resource": (scene or {}).get("ArtLevelPath", ""),
                "world_map_zone_ids": [as_id(row.get("Id")) for row in world_map_zones],
                "world_map_zone_group_ids": [as_id(row.get("GroupId")) for row in world_map_zones],
                "linked_interaction_ids": [
                    interaction_id
                    for row in linked_interactions
                    for interaction_id in flatten_ids(row.get("InteractionId"))
                ],
                "has_direct_speaker_name": False,
            }
        )

    marker = output_dir / ".free_dialog.generated"
    marker.write_text("\n".join(sorted(generated_files)) + "\n", encoding="utf-8")
    summary = {
        "source_file": str(input_path),
        "source_rows": len(dialog_rows),
        "generated_paragraphs": len(generated_files),
        "field_seasons": sorted({item["field_season_id"] for item in manifest if item["field_season_id"]}),
        "paragraphs_with_scene_resource": sum(bool(item["field_scene_id"]) for item in manifest),
        "paragraphs_with_interaction_link": sum(bool(item["linked_interaction_ids"]) for item in manifest),
        "paragraphs_with_world_map_zone": sum(bool(item["world_map_zone_ids"]) for item in manifest),
        "speaker_name_source_available": False,
        "field_date_character_names": sum(bool(item["character_name"]) for item in manifest),
        "output_dir": str(output_dir),
        "report_dir": str(report_dir),
    }
    (report_dir / "free_dialog_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (report_dir / "free_dialog_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"自由会话生成完成：{summary['generated_paragraphs']} 段，"
        f"{summary['source_rows']} 条阶段记录。"
    )
    print(f"输出目录：{output_dir}")
    print(f"报告目录：{report_dir}")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按 GroupId 提取 Field 探索自由会话 TXT。")
    parser.add_argument("--input", type=Path, default=DIALOG_INPUT, help="CharacterDialogField JSON 路径。")
    parser.add_argument("--output-dir", type=Path, default=TEXT_OUTPUT_DIR)
    parser.add_argument("--report-dir", type=Path, default=REPORT_DIR)
    parser.add_argument("--interaction", type=Path, default=INTERACTION_INPUT)
    parser.add_argument("--scene", type=Path, default=SCENE_INPUT)
    parser.add_argument("--world-map", type=Path, default=WORLD_MAP_INPUT)
    parser.add_argument("--date", type=Path, default=DATE_INPUT, help="FieldDate 角色图标表路径。")
    parser.add_argument("--names", type=Path, default=NAME_INPUT, help="Scenario 角色名称表路径。")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    generate(
        input_path=args.input,
        output_dir=args.output_dir,
        report_dir=args.report_dir,
        interaction_path=args.interaction,
        scene_path=args.scene,
        world_map_path=args.world_map,
        date_path=args.date,
        name_path=args.names,
    )


if __name__ == "__main__":
    main()
