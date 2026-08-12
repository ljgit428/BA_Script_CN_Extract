#!/usr/bin/env python3
"""从仓库内 raw 数据重新生成 result 下的文本和中间文件。

默认运行完整流水线；也可以只运行 scenario 或 Momotalk 子流水线：

    python script/generate.py
    python script/generate.py --scenario-only
    python script/generate.py --momotalk-only

所有默认路径都由各转换器根据脚本位置解析，因此不依赖当前工作目录，
也不再依赖外部的 F:/data_collection 数据目录。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_DIR = PROJECT_ROOT / "script" / "scenario"
MOMOTALK_DIR = PROJECT_ROOT / "script" / "Momotalk"


def run_step(label: str, script: Path, *arguments: str) -> None:
    print(f"\n--- {label} ---")
    subprocess.run(
        [sys.executable, str(script), *arguments],
        cwd=PROJECT_ROOT,
        check=True,
    )


def generate_scenario() -> None:
    run_step("切分 ScenarioScript raw 数据", SCENARIO_DIR / "split_scenario_groups.py", "--all")
    run_step("生成 scenario_texts", SCENARIO_DIR / "convert_scenario_to_txt.py", "--all")


def generate_momotalk() -> None:
    converter = MOMOTALK_DIR / "academy_messanger_to_txt.py"
    run_step("生成 Academy Messenger 分组文本", converter)
    run_step("生成按角色文本", converter, "--by-character")
    run_step("生成角色羁绊剧情文本", converter, "--character-stories")
    run_step("生成 Momotalk_message", converter, "--Momotalk_message")
    run_step("生成按消息图重建的剧情文本", converter, "--stories")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="使用 raw 数据在 result 下重新生成 Scenario 和 Momotalk 输出。"
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--scenario-only",
        action="store_true",
        help="只生成 result/scenario 下的 Scenario 输出。",
    )
    modes.add_argument(
        "--momotalk-only",
        action="store_true",
        help="只生成 result/Momotalk 下的 Academy Messenger 输出。",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.momotalk_only:
        generate_scenario()
    if not args.scenario_only:
        generate_momotalk()
    print("\n全部生成完成，输出位于 result/。")


if __name__ == "__main__":
    main()
