#!/usr/bin/env python3
"""按 GroupId 切分三个 ScenarioScriptExcelTable JSON 文件。"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DB_DIR = PROJECT_ROOT / "raw" / "ba-data-global" / "DB"
RESULT_SCENARIO_DIR = PROJECT_ROOT / "result" / "scenario"

DEFAULT_INPUTS = [
    RAW_DB_DIR / "ScenarioScriptExcelTable1.json",
    RAW_DB_DIR / "ScenarioScriptExcelTable2.json",
    RAW_DB_DIR / "ScenarioScriptExcelTable3.json",
]
DEFAULT_OUTPUT_DIR = RESULT_SCENARIO_DIR / "all_scenarios"


def load_rows(input_path: Path) -> list[dict[str, Any]]:
    """读取 {"DataList": [...]} 或直接是列表的 JSON 文件。"""
    with input_path.open("r", encoding="utf-8-sig") as file:
        data = json.load(file)

    rows = data.get("DataList") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise ValueError(
            f"{input_path} 格式不正确：顶层必须是列表，或包含列表字段 DataList。"
        )
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"{input_path} 中存在不是对象的记录。")
    return rows


def write_rows(rows: list[dict[str, Any]], output_path: Path) -> None:
    """以 UTF-8 JSON 数组写出记录。"""
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(rows, file, ensure_ascii=False, indent=2)
        file.write("\n")


def split_scenario_script(
    input_paths: Iterable[str | Path],
    output_dir: str | Path,
    group_id: str | int | None = None,
) -> int:
    """按精确 GroupId 切分一个或多个源文件。

    文件按 input_paths 的顺序处理。若同一 GroupId 出现在多个表中，记录会按
    表的顺序追加；当前数据没有 ScriptId 或其他顺序字段，因此保留原始行顺序。
    指定 group_id 时只输出一个文件，否则为每个 GroupId 输出一个文件。
    """
    paths = [Path(path) for path in input_paths]
    destination_dir = Path(output_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    wanted_group = str(group_id) if group_id is not None else None
    grouped_rows: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    matched_files: list[tuple[str, int]] = []

    for input_path in paths:
        if not input_path.is_file():
            raise FileNotFoundError(f"找不到输入文件：{input_path}")

        file_matches = 0
        for row in load_rows(input_path):
            value = row.get("GroupId")
            if value is None:
                continue
            current_group = str(value)
            if wanted_group is None:
                grouped_rows[current_group].append(row)
            elif current_group == wanted_group:
                grouped_rows[wanted_group].append(row)
                file_matches += 1

        if wanted_group is not None and file_matches:
            matched_files.append((str(input_path), file_matches))

    if wanted_group is not None:
        rows = grouped_rows.get(wanted_group, [])
        if not rows:
            raise ValueError(f"三个输入文件中没有找到 GroupId={wanted_group} 的记录。")
        output_path = destination_dir / f"{wanted_group}.json"
        write_rows(rows, output_path)
        source_summary = ", ".join(
            f"{path}: {count} 条" for path, count in matched_files
        )
        print(f"完成：{output_path}，共 {len(rows)} 条（来源：{source_summary}）。")
        return 1

    for current_group, rows in grouped_rows.items():
        write_rows(rows, destination_dir / f"{current_group}.json")
    print(f"完成：共生成 {len(grouped_rows)} 个剧情文件，输出目录：{destination_dir}")
    return len(grouped_rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="按 GroupId 将三个 ScenarioScriptExcelTable JSON 切分成独立文件。"
    )
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument(
        "--group-id",
        help="只切分指定编号，例如 41070；严格匹配，不会匹配 10041070。",
    )
    modes.add_argument("--all", action="store_true", help="切分所有 GroupId。")
    parser.add_argument(
        "--input",
        nargs="+",
        default=DEFAULT_INPUTS,
        help="输入 JSON 文件，默认使用 raw/ba-data-global/DB 下的三张 ScenarioScript 表。",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help="输出目录，默认是 result/scenario/all_scenarios。",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    split_scenario_script(
        input_paths=args.input,
        output_dir=args.output_dir,
        group_id=args.group_id if not args.all else None,
    )


if __name__ == "__main__":
    main()
