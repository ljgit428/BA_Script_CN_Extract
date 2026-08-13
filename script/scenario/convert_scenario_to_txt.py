#!/usr/bin/env python3
"""将 ScenarioScript JSON 转换为可读的中文剧情 TXT。"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Iterable

from opencc import OpenCC


DEFAULT_ROLE_MAP = {
    "세이아": "圣亚",
    "나기사": "渚",
    "미카": "弥香",
    "하나코": "花子",
    "코하루": "小春",
    "아즈사": "梓",
    "히후미": "日步美",
    "하스미": "莲实",
    "마리": "玛丽",
    "사쿠라코": "樱子",
    "히나": "阳奈",
    "아코": "亚子",
    "미네": "美祢",
    "사오리": "沙织",
    "선생님": "Sensei",
}

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DB_DIR = PROJECT_ROOT / "raw" / "ba-data-global" / "DB"
RESULT_SCENARIO_DIR = PROJECT_ROOT / "result" / "scenario"
DB_CHARACTER_NAMES = RAW_DB_DIR / "ScenarioCharacterNameExcelTable.json"
DEFAULT_INPUT_DIR = RESULT_SCENARIO_DIR / "all_scenarios"
DEFAULT_OUTPUT_DIR = RESULT_SCENARIO_DIR / "scenario_texts"
DEFAULT_REPORT_DIR = RESULT_SCENARIO_DIR / "scenario_text_reports"

RoleResolver = Callable[[str], tuple[str, str]]


class CharacterNameResolver:
    """从 ScenarioCharacterName 表解析基础角色名和服装/状态变体。"""

    PREFIXES = ("통신", "복면", "알바", "꼬마")
    SUFFIX_PATTERNS = (
        r"\s*(?:ND|비무장)$",
        r"\s*(?:수영복|학교 수영복|교복|방한복|헬멧)$",
        r"\s*모드\s*\d+$",
    )
    VARIANT_LABELS = (
        ("알바", "打工装"),
        ("통신", "通信"),
        ("복면", "蒙面"),
        ("꼬마", "幼年"),
        ("수영복", "泳装"),
        ("교복", "制服"),
        ("방한복", "冬装"),
        ("비무장", "非武装"),
    )

    def __init__(self, db_path: str | Path, converter: OpenCC) -> None:
        self.db_path = Path(db_path)
        self.converter = converter
        self.names: dict[str, set[str]] = defaultdict(set)
        self._load()

    def _load(self) -> None:
        with self.db_path.open("r", encoding="utf-8-sig") as file:
            data = json.load(file)
        rows = data.get("DataList") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            raise ValueError(f"角色名表格式不正确：{self.db_path}")
        for row in rows:
            name_kr = str(row.get("NameKR") or "").strip()
            name_tw = str(row.get("NameTW") or "").strip()
            if name_kr and name_tw:
                self.names[name_kr].add(name_tw)

    @property
    def ambiguous(self) -> dict[str, list[str]]:
        return {
            key: sorted(values)
            for key, values in self.names.items()
            if len(values) > 1
        }

    def _to_cn(self, name_tw: str) -> str:
        return self.converter.convert(name_tw)

    def _candidate_names(self, raw_name: str) -> list[str]:
        candidates = [raw_name.strip()]
        compact = raw_name.strip().replace(" ", "")
        if compact not in candidates:
            candidates.append(compact)

        for prefix in self.PREFIXES:
            if raw_name.startswith(prefix):
                candidates.append(raw_name[len(prefix) :].strip())
            if compact.startswith(prefix):
                candidates.append(compact[len(prefix) :].strip())

        changed = True
        while changed:
            changed = False
            for current in list(candidates):
                for pattern in self.SUFFIX_PATTERNS:
                    stripped = re.sub(pattern, "", current, flags=re.I).strip()
                    if stripped and stripped not in candidates:
                        candidates.append(stripped)
                        changed = True
        return [candidate for candidate in candidates if candidate]

    def _variant_labels(self, raw_name: str) -> list[str]:
        labels: list[str] = []
        for marker, label in self.VARIANT_LABELS:
            if marker in raw_name and label not in labels:
                labels.append(label)
        mode = re.search(r"모드\s*(\d+)", raw_name, flags=re.I)
        if mode:
            labels.append(f"模式{mode.group(1)}")
        return labels

    def display_name(self, raw_name: str) -> tuple[str, str]:
        """返回用于 TXT 的角色名，保留可识别的服装/状态变体。"""
        base_name, status = self.resolve(raw_name)
        if status == "unmapped":
            return base_name, status
        labels = self._variant_labels(raw_name)
        if labels:
            return f"{base_name}（{'、'.join(labels)}）", "variant"
        return base_name, status

    def resolve(self, raw_name: str) -> tuple[str, str]:
        raw_name = raw_name.strip()
        if not raw_name:
            return raw_name, "empty"

        # 先处理精确名。歧义项使用稳定排序，并由报告保留供人工确认。
        for candidate in self._candidate_names(raw_name):
            values = self.names.get(candidate)
            if values:
                chosen = sorted(values)[0]
                status = "ambiguous" if len(values) > 1 else (
                    "exact" if candidate == raw_name else "variant"
                )
                return self._to_cn(chosen), status

        # 最长基础角色名匹配，覆盖“角色名 + 服装/状态”形式。
        compact_raw = raw_name.replace(" ", "")
        matches: list[tuple[int, str, set[str]]] = []
        for candidate, values in self.names.items():
            if candidate.replace(" ", "") in compact_raw:
                matches.append((len(candidate.replace(" ", "")), candidate, values))
        if matches:
            _, _, values = max(matches, key=lambda item: item[0])
            chosen = sorted(values)[0]
            status = "ambiguous" if len(values) > 1 else "variant"
            return self._to_cn(chosen), status

        # 例如“实现正义部成员 A”这类带空格的复合名称。
        token_matches = [
            (len(token), token, self.names[token])
            for token in raw_name.split()
            if token in self.names
        ]
        if token_matches:
            _, _, values = max(token_matches, key=lambda item: item[0])
            chosen = sorted(values)[0]
            status = "ambiguous" if len(values) > 1 else "variant"
            return self._to_cn(chosen), status

        # TextTw 偶尔会把角色名写成“코+하루”这类带装饰符号的别名。
        # 去掉非文字符号后，如果唯一对应 DB 名称，也用于角色显示解析。
        compact = re.sub(r"[^\\w]", "", raw_name, flags=re.UNICODE)
        aliases = [
            name
            for name in self.names
            if re.sub(r"[^\\w]", "", name, flags=re.UNICODE) == compact
        ]
        if len(aliases) == 1:
            values = self.names[aliases[0]]
            chosen = sorted(values)[0]
            return self._to_cn(chosen), "variant"

        return raw_name, "unmapped"


def clean_text(value: str) -> str:
    """清理翻译字段中的换行、脚本前缀、ruby 包装和演出标记。"""
    text = value.replace("\\n", "\n").replace("#n", "\n")
    text = text.replace("[USERNAME]老师", "老师")
    text = re.sub(r"\[ruby=[^\]]*\](.*?)\[/ruby\]", r"\1", text, flags=re.S)
    text = re.sub(r"\[(?:wa|wait|se|voice):[^\]]*\]", "", text, flags=re.I)
    # 移除 Unity 文本颜色引擎标记，例如 [FF6666]文本[-]。
    text = re.sub(r"\[[0-9A-F]{6}\]", "", text, flags=re.I)
    text = text.replace("[-]", "")
    text = re.sub(r"\s*\((?:SeleToGroup|SeleGroup):\s*\d+\)", "", text)
    text = text.replace("<br>", "\n").replace("<br/>", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def simplify(text: str, converter: OpenCC) -> str:
    return converter.convert(clean_text(text))


def split_script_lines(script: str) -> list[str]:
    return [line.strip() for line in script.replace("\\n", "\n").splitlines() if line.strip()]


def parse_dialogue_event(
    script_line: str,
    role_map: dict[str, str],
    resolver: CharacterNameResolver | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> tuple[str, str] | None:
    """解析一个对白事件，返回 (角色, 原文)，控制指令返回 None。"""
    raw_role: str | None = None
    source_text: str | None = None

    if script_line.lower().startswith("#na;"):
        parts = script_line.split(";", 2)
        if len(parts) == 2:
            return "旁白", parts[1]
        raw_role, source_text = parts[1], parts[2]
    else:
        match = re.match(r"^\d+;([^;]+);[^;]*(?:;(.*))?$", script_line, flags=re.S)
        if match and match.group(2):
            raw_role, source_text = match.group(1), match.group(2)

    if raw_role is None or source_text is None:
        return None

    if resolver is not None:
        role, status = resolver.display_name(raw_role)
        if diagnostics is not None:
            diagnostics.setdefault("role_status", Counter())[status] += 1
            if status == "unmapped":
                diagnostics.setdefault("unmapped_roles", Counter())[raw_role] += 1
            elif status == "ambiguous":
                diagnostics.setdefault("ambiguous_roles", Counter())[raw_role] += 1
            elif status == "variant":
                diagnostics.setdefault("variant_roles", Counter())[raw_role] += 1
        return role, source_text

    return role_map.get(raw_role.strip(), raw_role.strip()), source_text


def translation_candidates(row: dict[str, Any]) -> tuple[str, str]:
    """按优先级取得翻译文本和实际使用的语言字段。"""
    for key in ("TextTw", "TextJp", "TextEn", "TextTh"):
        value = str(row.get(key) or "").strip()
        if value:
            return value, key
    return "", ""


def strip_matching_script_prefix(
    translation: str,
    script_lines: list[str],
    role_map: dict[str, str] | None = None,
    resolver: CharacterNameResolver | None = None,
    converter: OpenCC | None = None,
) -> str:
    """只删除与当前 ScriptKr 编号、角色和动作字段都匹配的 TextTw 前缀。"""
    converter = converter or OpenCC("t2s")
    role_map = role_map or {}

    def normalize_role(raw_role: str) -> str:
        if resolver is not None:
            resolved, status = resolver.resolve(raw_role)
            if status == "unmapped":
                # TextTw 偶尔把角色名写成“코+하루”这类装饰变体。
                # 去掉符号后若能唯一对应 DB 名称，则按该名称继续解析。
                compact = re.sub(r"[^\w]", "", raw_role, flags=re.UNICODE)
                aliases = [
                    name for name in resolver.names
                    if re.sub(r"[^\w]", "", name, flags=re.UNICODE) == compact
                ]
                if len(aliases) == 1:
                    resolved, _ = resolver.resolve(aliases[0])
            value = converter.convert(resolved).strip()
        else:
            value = converter.convert(role_map.get(raw_role.strip(), raw_role.strip())).strip()
        # TextTw 的角色前缀可能已经是中文/混合写法，例如“알바茜香”。
        # 匹配时去掉变体标记，只比较基础角色名；显示时仍保留变体。
        for marker in (
            "알바", "打工", "통신", "通信", "복면", "蒙面", "꼬마", "幼年",
            "수영복", "泳装", "교복", "制服", "방한복", "冬装", "비무장", "非武装",
        ):
            value = value.replace(marker, "")
        value = re.sub(r"模式\s*\d+", "", value)
        return value.strip()

    signatures: set[tuple[str, str, str]] = set()
    for line in script_lines:
        match = re.match(r"^(\d+);([^;\r\n]+);([^;\r\n]*);", line)
        if match:
            signatures.add(
                (match.group(1), normalize_role(match.group(2)), match.group(3))
            )
    if not signatures:
        return translation

    prefix_pattern = re.compile(r"^(\s*)(\d+);([^;\r\n]+);([^;\r\n]*);")
    cleaned_lines: list[str] = []
    for line in translation.replace("\\n", "\n").splitlines():
        match = prefix_pattern.match(line)
        if match:
            signature = (
                match.group(2),
                normalize_role(match.group(3)),
                match.group(4),
            )
            if signature in signatures:
                line = line[match.end():]
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


def format_speaker(
    speaker: str,
    text: str,
    resolver: CharacterNameResolver | None = None,
) -> list[str]:
    cleaned = clean_text(text)
    if not cleaned:
        return []

    def plain_lines(current_speaker: str, value: str) -> list[str]:
        return [
            f"{current_speaker}: {line.strip()}"
            for line in value.splitlines()
            if line.strip()
        ]

    log_pattern = re.compile(r"\[log=([^\]]+)\](.*?)\[/log\]", flags=re.I | re.S)
    if speaker != "旁白" or not log_pattern.search(cleaned):
        return plain_lines(speaker, cleaned)

    output: list[str] = []
    cursor = 0
    for match in log_pattern.finditer(cleaned):
        prefix = cleaned[cursor:match.start()]
        # “―” is a screenplay marker introducing the logged speaker, not
        # dialogue content.
        if prefix.strip().strip("―—–-"):
            output.extend(plain_lines("旁白", prefix))

        raw_role = match.group(1).strip()
        role = raw_role
        if resolver is not None:
            role, _ = resolver.display_name(raw_role)
        content = re.sub(r"^\s*[―—–-]\s*", "", match.group(2))
        output.extend(plain_lines(role, content))
        cursor = match.end()

    suffix = cleaned[cursor:]
    if suffix.strip():
        output.extend(plain_lines("旁白", suffix))
    return output


def append_choice_item(
    output: list[str],
    choice_id: str,
    choice_text: str,
    block_open: bool,
) -> bool:
    """将一个选项及其已有反应追加到统一的选择块。"""
    lines = format_speaker("老师", choice_text)
    if not lines:
        return block_open
    if not block_open:
        if output and output[-1] != "":
            output.append("")
        output.append("<选择>")
    elif output and output[-1] != "":
        output.append("")
    lines[0] = f"{choice_id}. {lines[0]}"
    output.extend(lines)
    return True


def close_choice_block(output: list[str], block_open: bool) -> bool:
    """关闭选择块，并在后续公共剧情前保留一个空行。"""
    if not block_open:
        return False
    if output and output[-1] != "</选择>":
        output.append("</选择>")
    output.append("")
    return False


def parse_choice_entries(script: str, translation: str) -> list[tuple[str, str]]:
    """按 [s5]/[s6]/[ns] 标签提取每个选项，避免复用整条 TextTw。"""
    tag_pattern = re.compile(r"^\[(s|ns)(\d*)\]\s*(.*)$", re.I)
    script_entries: list[tuple[str, str]] = []
    for line in split_script_lines(script):
        match = tag_pattern.match(line)
        if match:
            script_entries.append((f"{match.group(1).lower()}{match.group(2)}", match.group(3).strip()))

    translated: dict[str, str] = {}
    for line in clean_text(translation).splitlines():
        match = tag_pattern.match(line.strip())
        if not match:
            continue
        value = match.group(3).strip()
        if value.startswith("「") and value.endswith("」"):
            value = value[1:-1]
        elif value.startswith("\"") and value.endswith("\""):
            value = value[1:-1]
        translated[f"{match.group(1).lower()}{match.group(2)}"] = value.strip()

    result: list[tuple[str, str]] = []
    for tag, source_text in script_entries:
        result.append((tag, translated.get(tag, source_text)))
    return result


def title_from_text(text: str) -> str:
    parts = [part.strip() for part in clean_text(text).split(";") if part.strip()]
    return "".join(parts)


def script_title_fallback(script_line: str) -> str:
    parts = [part.strip() for part in script_line.split(";")[1:] if part.strip()]
    return parts[-1] if parts else ""


def align_dialogue(
    events: list[tuple[str, str]],
    translation: str,
    converter: OpenCC,
    resolver: CharacterNameResolver | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> list[str]:
    """将一条记录中的角色事件与翻译文本按顺序尽量对齐。"""
    speakers = [speaker for speaker, source_text in events if source_text.strip()]
    if not speakers:
        return []

    segments = [line.strip() for line in clean_text(translation).splitlines() if line.strip()]
    if not segments:
        return []

    if len(speakers) != len(segments) and diagnostics is not None:
        diagnostics["dialogue_alignment_mismatch"] = (
            diagnostics.get("dialogue_alignment_mismatch", 0) + 1
        )

    if len(speakers) == 1:
        return format_speaker(
            speakers[0],
            simplify("\n".join(segments), converter),
            resolver=resolver,
        )

    if len(segments) < len(speakers):
        speakers = speakers[-len(segments):]
    elif len(segments) > len(speakers):
        segments = segments[: len(speakers) - 1] + [
            " ".join(segments[len(speakers) - 1 :])
        ]

    output: list[str] = []
    for speaker, segment in zip(speakers, segments):
        output.extend(
            format_speaker(
                speaker,
                simplify(segment, converter),
                resolver=resolver,
            )
        )
    return output


def convert_rows(
    rows: Iterable[dict[str, Any]],
    role_map: dict[str, str] | None = None,
    resolver: CharacterNameResolver | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> str:
    """按源记录顺序转换为 TXT 内容。"""
    role_map = {**DEFAULT_ROLE_MAP, **(role_map or {})}
    converter = resolver.converter if resolver else OpenCC("t2s")
    rows = list(rows)
    output: list[str] = []
    pending_choices: dict[str, str] = {}
    pending_order: list[str] = []
    active_branch: str | None = None
    choice_block_open = False

    if rows and rows[0].get("GroupId") is not None:
        output.extend([f"GroupId: {rows[0]['GroupId']}", ""])

    for row_index, row in enumerate(rows):
        if diagnostics is not None:
            diagnostics["rows"] = diagnostics.get("rows", 0) + 1

        script = str(row.get("ScriptKr") or "")
        script_lines = split_script_lines(script)
        translation, language = translation_candidates(row)
        translation = strip_matching_script_prefix(
            translation,
            script_lines,
            role_map=role_map,
            resolver=resolver,
            converter=converter,
        )
        if diagnostics is not None and language and language != "TextTw":
            diagnostics["fallback_language_rows"] = diagnostics.get("fallback_language_rows", 0) + 1
        if not script and not translation:
            continue

        selection_group = str(row.get("SelectionGroup") or "0")
        choice_entries = parse_choice_entries(script, translation)
        events = [
            event
            for line in script_lines
            if (event := parse_dialogue_event(line, role_map, resolver, diagnostics)) is not None
        ]
        has_branch_content = bool(events and translation)
        has_scene_text = any(
            line.lower().startswith(("#st;", "#stm;", "#place;"))
            for line in script_lines
        )
        # 场景标题/屏幕文字虽然会输出为旁白，但不属于分支对白。
        # 它们不能消耗 pending_choices，也不能结束当前选择块。
        has_branch_content = has_branch_content and not has_scene_text
        has_visible_content = bool(translation and (has_branch_content or any(
            line.lower().startswith(("#title;", "#nextepisode;", "#continued"))
            for line in script_lines
        )))
        branch_dialogue_output = False

        if choice_entries:
            # 新的选项集合开始时，先结束上一组尚未遇到公共剧情的选项，
            # 避免连续的两组选项被错误合并到同一个 <选择> 块。
            if pending_choices:
                for choice_id in pending_order:
                    if choice_id in pending_choices:
                        choice_block_open = append_choice_item(
                            output,
                            choice_id,
                            pending_choices[choice_id],
                            choice_block_open,
                        )
                pending_choices.clear()
                pending_order.clear()
                choice_block_open = close_choice_block(output, choice_block_open)
            active_branch = None
            if diagnostics is not None:
                diagnostics["choice_rows"] = diagnostics.get("choice_rows", 0) + len(choice_entries)
            for tag, choice_text in choice_entries:
                choice_id = re.sub(r"^(?:s|ns)", "", tag, flags=re.I)
                if choice_id:
                    if choice_id not in pending_choices:
                        pending_order.append(choice_id)
                    pending_choices[choice_id] = simplify(choice_text, converter)
                elif choice_text:
                    output.extend(format_speaker("老师", simplify(choice_text, converter)))
            continue

        # 没有实际对白的等待/演出记录不能消耗分支选项；后面还可能有真正的反应。
        if pending_choices and selection_group != "0" and not has_branch_content:
            continue

        # 只有遇到真正可见的公共剧情时，才输出没有独立反应的选项。
        # #wait、#all、#clearST 等演出控制行不能提前消耗 pending_choices。
        if pending_choices and selection_group == "0" and has_visible_content:
            for choice_id in pending_order:
                if choice_id in pending_choices:
                    choice_block_open = append_choice_item(
                        output,
                        choice_id,
                        pending_choices[choice_id],
                        choice_block_open,
                    )
            pending_choices.clear()
            pending_order.clear()
            choice_block_open = close_choice_block(output, choice_block_open)
            active_branch = None

        # 只有回到 SelectionGroup=0 的普通角色对白，才结束当前选择块。
        # 标题、#st 旁白和其他演出记录不能触发选择块的间隔。
        is_public_dialogue = (
            selection_group == "0"
            and bool(events and translation)
            and not any(
                line.lower().startswith(
                    ("#title;", "#nextepisode;", "#st;", "#stm;", "#place;", "#continued")
                )
                for line in script_lines
            )
        )
        if is_public_dialogue:
            choice_block_open = close_choice_block(output, choice_block_open)
            if active_branch is not None:
                if output and output[-1] != "":
                    output.append("")
            active_branch = None

        # 当前记录是某个选项的实际反应时，按选项声明顺序补齐此前的选项，
        # 再将当前反应挂到对应选项下，避免源数据中的 ns 分支抢到前面。
        if selection_group != "0" and selection_group in pending_choices and has_branch_content:
            choice_index = pending_order.index(selection_group)
            choices_to_render = pending_order[: choice_index + 1]
            for choice_id in choices_to_render:
                choice_text = pending_choices.pop(choice_id)
                pending_order.remove(choice_id)
                choice_block_open = append_choice_item(
                    output,
                    choice_id,
                    choice_text,
                    choice_block_open,
                )
                if choice_id == selection_group:
                    output.extend(
                        align_dialogue(
                            events,
                            translation,
                            converter,
                            resolver=resolver,
                            diagnostics=diagnostics,
                        )
                    )
                    branch_dialogue_output = True
            active_branch = selection_group
        elif selection_group != "0" and has_branch_content and active_branch != selection_group:
            # 同一分支可能包含多条连续对白；只有切换到另一分支时重新标记。
            if output and output[-1] != "":
                output.append("")
            active_branch = selection_group

        for script_line in script_lines:
            lower_line = script_line.lower()

            if lower_line.startswith("#title;"):
                title = title_from_text(translation) or script_title_fallback(script_line)
                if title:
                    output.extend([f"标题: {simplify(title, converter)}", ""])
                continue

            if lower_line.startswith("#nextepisode;"):
                next_title = title_from_text(translation) or script_title_fallback(script_line)
                if next_title:
                    output.append(f"下一话: {simplify(next_title, converter)}")
                continue

            if lower_line.startswith("#continued"):
                output.append("旁白: 未完待续")
                continue

            if lower_line.startswith(("#st;", "#stm;", "#place;")):
                if translation:
                    output.extend(
                        format_speaker(
                            "旁白",
                            simplify(translation, converter),
                            resolver=resolver,
                        )
                    )
                continue

        has_non_scene_events = events and not has_scene_text
        if (
            has_non_scene_events
            and translation
            and not branch_dialogue_output
            and not any(
                line.lower().startswith(("#title;", "#nextepisode;"))
                for line in script_lines
            )
        ):
            output.extend(
                align_dialogue(
                    events,
                    translation,
                    converter,
                    resolver=resolver,
                    diagnostics=diagnostics,
                )
            )
        elif events and has_scene_text and diagnostics is not None:
            # 同一记录混有场景指令和角色事件时，TextTw 通常只对应场景文字；
            # 不能把同一段翻译错误复制给角色，记录下来供后续人工对齐。
            diagnostics["mixed_scene_dialogue_rows"] = (
                diagnostics.get("mixed_scene_dialogue_rows", 0) + 1
            )
            diagnostics.setdefault("mixed_scene_dialogue_details", []).append(
                {
                    "row_index": row_index,
                    "group_id": row.get("GroupId"),
                    "selection_group": selection_group,
                    "roles": [speaker for speaker, _ in events],
                    "script": script,
                    "translation": translation,
                }
            )

    if pending_choices:
        for choice_id in pending_order:
            if choice_id in pending_choices:
                choice_block_open = append_choice_item(
                    output,
                    choice_id,
                    pending_choices[choice_id],
                    choice_block_open,
                )
    close_choice_block(output, choice_block_open)

    while output and output[-1] == "":
        output.pop()
    return "\n".join(output) + ("\n" if output else "")


def load_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as file:
        data = json.load(file)
    rows = data.get("DataList") if isinstance(data, dict) else data
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"{path} 不是有效的剧情 JSON 数组。")
    return rows


def convert_group(
    input_path: str | Path,
    output_path: str | Path,
    resolver: CharacterNameResolver | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> None:
    source = Path(input_path)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(convert_rows(load_rows(source), resolver=resolver, diagnostics=diagnostics), encoding="utf-8")


def jsonable_diagnostics(value: Any) -> Any:
    if isinstance(value, Counter):
        return dict(value.most_common())
    if isinstance(value, dict):
        return {str(k): jsonable_diagnostics(v) for k, v in value.items()}
    return value


def batch_convert(
    input_dir: str | Path,
    output_dir: str | Path,
    db_path: str | Path,
    report_dir: str | Path,
) -> None:
    source_dir = Path(input_dir)
    destination_dir = Path(output_dir)
    reports = Path(report_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)

    converter = OpenCC("t2s")
    resolver = CharacterNameResolver(db_path, converter)
    totals: dict[str, Any] = {
        "input_files": 0,
        "generated_files": 0,
        "empty_output_files": 0,
        "total_rows": 0,
        "role_status": Counter(),
        "unmapped_roles": Counter(),
        "ambiguous_roles": Counter(),
        "variant_roles": Counter(),
        "dialogue_alignment_mismatch": 0,
        "choice_rows": 0,
        "fallback_language_rows": 0,
        "mixed_scene_dialogue_rows": 0,
        "mixed_scene_dialogue_details": [],
        "errors": {},
    }

    for source in sorted(source_dir.glob("*.json"), key=lambda path: path.stem):
        totals["input_files"] += 1
        diagnostics: dict[str, Any] = {}
        destination = destination_dir / f"{source.stem}.txt"
        try:
            convert_group(source, destination, resolver=resolver, diagnostics=diagnostics)
            totals["generated_files"] += 1
            if destination.stat().st_size == 0:
                totals["empty_output_files"] += 1
            totals["total_rows"] += diagnostics.get("rows", 0)
            for key in ("role_status", "unmapped_roles", "ambiguous_roles", "variant_roles"):
                totals[key].update(diagnostics.get(key, {}))
            for key in (
                "dialogue_alignment_mismatch",
                "choice_rows",
                "fallback_language_rows",
                "mixed_scene_dialogue_rows",
            ):
                totals[key] += diagnostics.get(key, 0)
            for detail in diagnostics.get("mixed_scene_dialogue_details", []):
                totals["mixed_scene_dialogue_details"].append(
                    {
                        **detail,
                        "source_file": source.name,
                        "group_id": detail.get("group_id", source.stem),
                    }
                )
        except Exception as exc:  # 保证单个坏文件不阻断全部转换
            totals["errors"][source.name] = f"{type(exc).__name__}: {exc}"

    mapping = {
        name: {
            "name_tw": sorted(values)[0],
            "name_cn": converter.convert(sorted(values)[0]),
            "ambiguous": sorted(values) if len(values) > 1 else [],
            "source": "ScenarioCharacterNameExcelTable",
        }
        for name, values in sorted(resolver.names.items())
        if values
    }
    (reports / "character_mapping.json").write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (reports / "ambiguous_character_names.json").write_text(
        json.dumps(
            {key: sorted(values) for key, values in sorted(resolver.ambiguous.items())},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (reports / "unmapped_character_names.json").write_text(
        json.dumps(dict(totals["unmapped_roles"].most_common()), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (reports / "conversion_summary.json").write_text(
        json.dumps(jsonable_diagnostics(totals), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (reports / "mixed_scene_dialogue_details.json").write_text(
        json.dumps(totals["mixed_scene_dialogue_details"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"批量转换完成：输入 {totals['input_files']} 个，生成 {totals['generated_files']} 个，"
        f"失败 {len(totals['errors'])} 个。"
    )
    print(f"输出目录：{destination_dir}")
    print(f"报告目录：{reports}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="将剧情 JSON 转成中文剧情 TXT。")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--group-id", help="只转换一个 GroupId，例如 31010。")
    modes.add_argument("--all", action="store_true", help="转换 input-dir 下全部 GroupId。")
    parser.add_argument(
        "--input-dir",
        default=DEFAULT_INPUT_DIR,
        help="JSON 输入目录，默认是 result/scenario/all_scenarios。",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help="TXT 输出目录，默认是 result/scenario/scenario_texts。",
    )
    parser.add_argument(
        "--report-dir",
        default=DEFAULT_REPORT_DIR,
        help="诊断报告目录，默认是 result/scenario/scenario_text_reports。",
    )
    parser.add_argument("--db-path", default=DB_CHARACTER_NAMES, help="角色名 DB JSON 路径。")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    converter = OpenCC("t2s")
    resolver = CharacterNameResolver(args.db_path, converter)
    if args.all:
        batch_convert(args.input_dir, args.output_dir, args.db_path, args.report_dir)
    else:
        group_id = str(args.group_id)
        diagnostics: dict[str, Any] = {}
        convert_group(
            Path(args.input_dir) / f"{group_id}.json",
            Path(args.output_dir) / f"{group_id}.txt",
            resolver=resolver,
            diagnostics=diagnostics,
        )
        print(f"完成：{Path(args.output_dir) / f'{group_id}.txt'}")


if __name__ == "__main__":
    main()
