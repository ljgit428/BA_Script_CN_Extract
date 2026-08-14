#!/usr/bin/env python3
"""按 MessageGroupId 或 CharacterId 提取 Academy Messenger 通讯为可读 TXT。"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from opencc import OpenCC


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DB_DIR = PROJECT_ROOT / "raw" / "ba-data-global" / "DB"
RESULT_MOMOTALK_DIR = PROJECT_ROOT / "result" / "Momotalk"

DEFAULT_INPUT = RAW_DB_DIR / "AcademyMessangerExcelTable.json"
DEFAULT_DB = RAW_DB_DIR
DEFAULT_PROFILE_NAMES = "LocalizeCharProfileExcelTable.json"
DEFAULT_COSTUME_NAMES = "CostumeExcelTable.json"
DEFAULT_TEXT_OUTPUT_DIR = RESULT_MOMOTALK_DIR / "academy_messanger_texts"
DEFAULT_TEXT_REPORT_DIR = RESULT_MOMOTALK_DIR / "academy_messanger_reports"
DEFAULT_CHARACTER_OUTPUT_DIR = RESULT_MOMOTALK_DIR / "academy_messanger_characters"
DEFAULT_CHARACTER_REPORT_DIR = RESULT_MOMOTALK_DIR / "academy_messanger_character_reports"
DEFAULT_CHARACTER_STORY_OUTPUT_DIR = RESULT_MOMOTALK_DIR / "academy_messanger_character_stories"
DEFAULT_CHARACTER_STORY_REPORT_DIR = RESULT_MOMOTALK_DIR / "academy_messanger_character_story_reports"
DEFAULT_COMPRESSED_OUTPUT_DIR = RESULT_MOMOTALK_DIR / "Momotalk_message"
DEFAULT_STORY_OUTPUT_DIR = RESULT_MOMOTALK_DIR / "academy_messanger_stories"
DEFAULT_STORY_REPORT_DIR = RESULT_MOMOTALK_DIR / "academy_messanger_story_reports"

# CharacterExcel/CostumeExcel use internal English resource names, while the
# profile table contains the localized outfit description. Keep the mapping
# conservative: only append a label when a strong technical or localized clue
# identifies a non-base form.
TECHNICAL_VARIANT_LABELS = (
    ("swimsuit", "泳装"),
    ("swimwear", "泳装"),
    ("newyear", "新年"),
    ("new_year", "新年"),
    ("new-year", "新年"),
    ("casual", "便服"),
    ("uniform", "制服"),
    ("schooluniform", "制服"),
    ("dress", "礼服"),
    ("formal", "礼服"),
    ("bunny", "兔女郎"),
    ("maid", "女仆"),
    ("riding", "骑乘服"),
    ("cheerleader", "啦啦队服"),
    ("cheering", "应援服"),
    ("tracksuit", "运动服"),
    ("sportswear", "运动服"),
    ("jersey", "运动服"),
    ("christmas", "圣诞"),
    ("halloween", "万圣节"),
    ("valentine", "情人节"),
    ("pajama", "睡衣"),
    ("sleepwear", "睡衣"),
    ("idol", "偶像服"),
    ("band", "乐队服"),
    ("festival", "祭典服"),
    ("summer", "夏装"),
    ("winter", "冬装"),
    ("camp", "露营服"),
    # Event background/resource names used when DevName is only CHxxxx.
    ("gehennapartyroom", "礼服"),
    ("waterfall", "泳装"),
    ("fishingvillage2", "泳装"),
    ("beachstage", "泳装"),
    ("waterparkoutside", "救生员"),
    ("onsen", "温泉"),
    ("shansquarepark", "旗袍"),
    ("baseballpark", "棒球服"),
    ("themeparktheater", "魔法少女"),
    ("ironcontinent", "特殊战斗服"),
    ("hyakkiyakotreesquare", "修学旅行"),
    ("newyearfestival", "新年"),
    ("cheerleading", "啦啦队服"),
    ("bunnygirl", "兔女郎"),
    ("holiday", "圣诞"),
)

# Only use profile text patterns that describe a distinctive outfit/event form.
# Generic words such as "制服" are intentionally excluded because they can
# occur in an ordinary student's base introduction.
LOCALIZED_VARIANT_LABELS = (
    ("禮服", "礼服"),
    ("泳裝", "泳装"),
    ("泳衣", "泳装"),
    ("兔女郎", "兔女郎"),
    ("女僕", "女仆"),
    ("女仆", "女仆"),
    ("運動服", "运动服"),
    ("體育服", "运动服"),
    ("私服", "便服"),
    ("聖誕", "圣诞"),
    ("萬聖", "万圣节"),
    ("情人節", "情人节"),
    ("應援", "应援服"),
    ("啦啦隊", "啦啦队服"),
    ("睡衣", "睡衣"),
    ("變成年幼", "幼年"),
    ("年幼的身體", "幼年"),
    ("溫泉浴場", "温泉"),
    ("溫泉", "温泉"),
    ("旗袍", "旗袍"),
    ("救生員", "救生员"),
    ("水上樂園", "救生员"),
    ("魔法少女服裝", "魔法少女"),
    ("特殊戰鬥服", "特殊战斗服"),
    ("球場", "棒球服"),
    ("修學旅行", "修学旅行"),
    ("海灘", "泳装"),
    ("海邊", "泳装"),
    ("漁村", "泳装"),
)

# Some released costumes intentionally use a CHxxxx resource name without a
# costume suffix. Their localized profile is still definitive; keep explicit
# exceptions for names that cannot be recovered from a technical suffix.
EXPLICIT_VARIANT_LABELS = {
    "10086": "礼服",
}


def first_variant_label(text: str, patterns: tuple[tuple[str, str], ...]) -> str:
    lowered = text.lower()
    for marker, label in patterns:
        if marker.lower() in lowered:
            return label
    return ""



def localized_profile_text(row: dict[str, Any]) -> str:
    """Return outfit-relevant localized profile text without relying on one key."""
    return " ".join(
        str(value or "").strip()
        for key, value in row.items()
        if key.endswith("Tw") and any(
            token in key.lower()
            for token in ("introduction", "description", "new", "profile")
        )
    )



def variant_evidence_text(row: dict[str, Any], costume: dict[str, Any]) -> str:
    fields = ("DevName", "ScenarioCharacter")
    costume_fields = (
        "DevName",
        "SpineResourceName",
        "SpineResourceNameDiorama",
        "ModelPrefabName",
        "TextureDir",
        "CollectionTexturePath",
        "CollectionBGTexturePath",
    )
    return " ".join(
        [str(row.get(field) or "") for field in fields]
        + [str(costume.get(field) or "") for field in costume_fields]
    )




def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as file:
        return json.load(file)


def rows_from(data: Any) -> list[dict[str, Any]]:
    rows = data.get("DataList") if isinstance(data, dict) else data
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("输入文件不是有效的 DataList JSON 数组。")
    return rows


def clean_text(value: Any, converter: OpenCC) -> str:
    text = str(value or "").replace("\\n", "\n").replace("#n", "\n")
    text = text.replace("[USERNAME]老师", "老师")
    text = re.sub(r"\[ruby=[^\]]*\](.*?)\[/ruby\]", r"\1", text, flags=re.S)
    # 移除 Unity 文本颜色引擎标记，例如 [FF6666]文本[-]。
    text = re.sub(r"\[[0-9A-F]{6}\]", "", text, flags=re.I)
    text = text.replace("[-]", "")
    text = re.sub(r"\s*\((?:SeleToGroup|SeleGroup):\s*\d+\)", "", text)
    text = text.replace("<br>", "\n").replace("<br/>", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    return converter.convert(text).strip()


def norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9가-힣一-龥ぁ-んァ-ン]", "", str(value or "").lower())


class CharacterResolver:
    """将通讯 CharacterId 映射为基础姓名，并保留服装/形态。"""

    def __init__(self, db_dir: Path, converter: OpenCC) -> None:
        self.db_dir = db_dir
        self.converter = converter
        self.by_id: dict[str, str] = {}
        self.character_rows: dict[str, dict[str, Any]] = {}
        self.by_profile: dict[str, str] = {}
        self.profile_rows: dict[str, dict[str, Any]] = {}
        self.costume_by_group: dict[str, dict[str, Any]] = {}
        self.by_scenario: dict[str, set[str]] = defaultdict(set)
        self.by_kr: dict[str, set[str]] = defaultdict(set)
        self.variant_records: dict[str, dict[str, Any]] = {}
        self.unmapped: Counter[str] = Counter()
        self._load()

    def _load(self) -> None:
        character_path = self.db_dir / "CharacterExcelTable.json"
        scenario_path = self.db_dir / "ScenarioCharacterNameExcelTable.json"
        costume_path = self.db_dir / DEFAULT_COSTUME_NAMES

        if character_path.exists():
            for row in rows_from(load_json(character_path)):
                character_id = str(row.get("Id") or "").strip()
                scenario_name = str(row.get("ScenarioCharacter") or "").strip()
                dev_name = str(row.get("DevName") or "").strip()
                if character_id:
                    self.character_rows[character_id] = row
                    self.by_id[character_id] = scenario_name or dev_name

        # CostumeExcel has no localized labels, but its default resource row
        # gives a reliable technical identity for suffix-based detection.
        if costume_path.exists():
            for row in rows_from(load_json(costume_path)):
                if str(row.get("IsDefault") or "").lower() != "true":
                    continue
                group_id = str(row.get("CostumeGroupId") or "").strip()
                if group_id:
                    self.costume_by_group[group_id] = row

        profile_path = self.db_dir / DEFAULT_PROFILE_NAMES
        if profile_path.exists():
            for row in rows_from(load_json(profile_path)):
                character_id = str(row.get("CharacterId") or "").strip()
                # Academy Messenger uses the short personal name (e.g. 咲希)
                # rather than the full family+personal name in dialogue labels.
                personal_name = str(row.get("PersonalNameTw") or "").strip()
                full_name = str(row.get("FullNameTw") or "").strip()
                profile_name = personal_name or full_name
                if character_id and profile_name:
                    self.by_profile[character_id] = profile_name
                    self.profile_rows[character_id] = row

        if scenario_path.exists():
            for row in rows_from(load_json(scenario_path)):
                name_kr = str(row.get("NameKR") or "").strip()
                name_tw = str(row.get("NameTW") or "").strip()
                if name_kr and name_tw:
                    self.by_kr[norm(name_kr)].add(name_tw)
                for key in ("CharacterName", "SpinePrefabName", "NameKR", "NameJP", "NameEN"):
                    key_value = str(row.get(key) or "").strip()
                    if key_value and name_tw:
                        self.by_scenario[norm(key_value)].add(name_tw)

    def _variant_label(self, character_id: str) -> tuple[str, str, str]:
        """Return (label, evidence source, confidence) for one CharacterId."""
        if character_id in EXPLICIT_VARIANT_LABELS:
            return EXPLICIT_VARIANT_LABELS[character_id], "explicit_character_id", "high"

        character = self.character_rows.get(character_id, {})
        profile = self.profile_rows.get(character_id, {})
        group_id = str(character.get("CostumeGroupId") or "").strip()
        costume = self.costume_by_group.get(group_id, {})
        dev_name = str(character.get("DevName") or "").strip()
        evidence = variant_evidence_text(character, costume)

        # A *_default record is the base form unless a stronger localized clue
        # or an explicit exception says otherwise.
        is_base_dev_name = dev_name.lower().endswith("_default")
        if not is_base_dev_name:
            label = first_variant_label(evidence, TECHNICAL_VARIANT_LABELS)
            if label:
                return label, "character_or_costume_resource", "high"

        # Profile introductions are localized and distinguish otherwise opaque
        # CHxxxx costumes such as 10086 (CH0230). This is only reached for a
        # non-default technical record, and the pattern table intentionally
        # contains distinctive outfit/event phrases rather than generic words.
        if not is_base_dev_name:
            profile_text = localized_profile_text(profile)
            label = first_variant_label(profile_text, LOCALIZED_VARIANT_LABELS)
            if label:
                return label, "localized_profile_description", "high"

        if is_base_dev_name:
            return "", "base_default", "high"

        # Do not invent a costume name from the ID. Filenames always include the
        # CharacterId, so an unresolved label cannot cause file loss; the audit
        # report keeps it visible for later data-source refinement.
        return "", "no_variant_evidence", "low"

    def _record(self, character_id: str, base_name: str, status: str) -> str:
        character = self.character_rows.get(character_id, {})
        group_id = str(character.get("CostumeGroupId") or "").strip()
        costume = self.costume_by_group.get(group_id, {})
        label, source, confidence = self._variant_label(character_id)
        display_name = f"{base_name}（{label}）" if label else base_name
        self.variant_records[character_id] = {
            "character_id": character_id,
            "base_name": base_name,
            "display_name": display_name,
            "variant_label": label,
            "variant_source": source,
            "confidence": confidence,
            "dev_name": str(character.get("DevName") or ""),
            "scenario_character": str(character.get("ScenarioCharacter") or ""),
            "costume_group_id": group_id,
            "costume_unique_id": str(costume.get("CostumeUniqueId") or ""),
            "model_prefab_name": str(costume.get("ModelPrefabName") or ""),
            "collection_bg_texture_path": str(costume.get("CollectionBGTexturePath") or ""),
            "resolver_status": status,
        }
        return display_name

    def mapping_report(self) -> list[dict[str, Any]]:
        return [self.variant_records[key] for key in sorted(self.variant_records)]

    def resolve(self, character_id: Any) -> tuple[str, str]:
        raw_id = "" if character_id is None else str(character_id).strip()
        if not raw_id:
            return "系统", "empty"
        if raw_id == "0":
            return "系统", "system"

        profile_name = self.by_profile.get(raw_id, "")
        if profile_name:
            base_name = self.converter.convert(profile_name)
            label, _, _ = self._variant_label(raw_id)
            display_name = self._record(raw_id, base_name, "profile")
            return display_name, "profile_variant" if label else "profile"

        scenario_name = self.by_id.get(raw_id, "")
        candidates = [scenario_name]
        if scenario_name:
            candidates.append(scenario_name.removesuffix("_default"))
            candidates.append(scenario_name.split("_")[0])

        for candidate in candidates:
            values = self.by_scenario.get(norm(candidate), set())
            if len(values) == 1:
                base_name = self.converter.convert(next(iter(values)))
                label, _, _ = self._variant_label(raw_id)
                display_name = self._record(raw_id, base_name, "mapped")
                return display_name, "mapped_variant" if label else "mapped"

        self.unmapped[raw_id] += 1
        return f"角色({raw_id})", "unmapped"


def format_meta(row: dict[str, Any]) -> str:
    fields = [
        ("条件", row.get("MessageCondition")),
        ("条件值", row.get("ConditionValue")),
        ("好感度剧情", row.get("FavorScheduleId")),
        ("前置组", row.get("PreConditionGroupId")),
        ("后一组", row.get("NextGroupId")),
        ("反馈延迟毫秒", row.get("FeedbackTimeMillisec")),
    ]
    values = []
    for label, value in fields:
        text = str(value or "").strip()
        if text and text not in {"0", "None"}:
            values.append(f"{label}: {text}")
    return " | ".join(values)


def convert_group(
    group_id: str,
    messages: list[dict[str, Any]],
    resolver: CharacterResolver,
    converter: OpenCC,
) -> tuple[str, dict[str, Any]]:
    lines = [f"MessageGroupId: {group_id}", ""]
    stats: dict[str, Any] = {
        "group_id": group_id,
        "records": len(messages),
        "text_records": 0,
        "image_records": 0,
        "empty_records": 0,
        "missing_tw_records": [],
        "characters": [],
    }

    for row in messages:
        character, status = resolver.resolve(row.get("CharacterId"))
        if character not in stats["characters"]:
            stats["characters"].append(character)
        message_type = str(row.get("MessageType") or "Text")
        message = clean_text(row.get("MessageTW"), converter)
        meta = format_meta(row)

        if message_type.lower() == "image":
            stats["image_records"] += 1
            image_path = str(row.get("ImagePath") or "").strip()
            lines.append(f"{character}: [图片]{(' ' + image_path) if image_path else ''}")
            lines.append("")
            continue

        if not message:
            stats["empty_records"] += 1
            stats["missing_tw_records"].append(
                {
                    "id": row.get("Id"),
                    "character_id": row.get("CharacterId"),
                    "message_type": message_type,
                    "message_kr": str(row.get("MessageKR") or "").strip(),
                    "message_jp": str(row.get("MessageJP") or "").strip(),
                    "message_en": str(row.get("MessageEN") or "").strip(),
                }
            )
            continue

        stats["text_records"] += 1
        if meta:
            lines.append(f"[{meta}]")
        lines.extend(f"{character}: {part.strip()}" for part in message.splitlines() if part.strip())
        lines.append("")

    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n", stats


def character_id_text(value: Any) -> str:
    """Return a stable grouping key while keeping an explicit key for missing IDs."""
    if value is None:
        return "unknown"
    text = str(value).strip()
    return text or "unknown"


def safe_filename(value: str) -> str:
    """Make a resolved character name safe to use as a Windows filename."""
    invalid_chars = '<>:/\\\\|?*"'
    text = value.translate({ord(char): "_" for char in invalid_chars})
    text = "".join("_" if ord(char) < 32 else char for char in text).strip(" .")
    return text or "unknown"


def convert_characters(
    rows: list[dict[str, Any]],
    output_dir: Path,
    report_dir: Path,
    resolver: CharacterResolver,
    converter: OpenCC,
) -> dict[str, Any]:
    """Write one readable TXT per CharacterId, preserving source row order."""
    characters: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        characters[character_id_text(row.get("CharacterId"))].append(row)

    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    previous_manifest_path = report_dir / "character_manifest.json"
    if previous_manifest_path.exists():
        try:
            previous_manifest = json.loads(previous_manifest_path.read_text(encoding="utf-8"))
            for item in previous_manifest:
                old_file = str(item.get("file") or "").strip()
                if old_file:
                    old_path = output_dir / old_file
                    if old_path.is_file():
                        old_path.unlink()
        except (OSError, json.JSONDecodeError):
            pass
    manifest: list[dict[str, Any]] = []

    for character_id, messages in characters.items():
        resolved_name, status = resolver.resolve(
            None if character_id == "unknown" else character_id
        )
        lines = [
            f"标题：Academy Messenger（CharacterId {character_id}）",
            f"角色：{resolved_name}",
            "",
        ]
        previous_group: str | None = None
        text_records = 0
        image_records = 0
        empty_records = 0
        missing_records: list[dict[str, Any]] = []

        for row in messages:
            group_id = str(row.get("MessageGroupId") or "ungrouped")
            if group_id != previous_group:
                if previous_group is not None and lines and lines[-1] != "":
                    lines.append("")
                lines.append(f"=== MessageGroupId: {group_id} ===")
                previous_group = group_id

            meta = format_meta(row)
            if meta:
                lines.append(f"[{meta}]")

            message_type = str(row.get("MessageType") or "Text")
            if message_type.lower() == "image":
                image_path = str(row.get("ImagePath") or "").strip()
                lines.append(
                    f"{resolved_name}: [图片]{(' ' + image_path) if image_path else ''}"
                )
                lines.append("")
                image_records += 1
                continue

            message = clean_text(row.get("MessageTW"), converter)
            if not message:
                empty_records += 1
                lines.append(f"{resolved_name}: [缺少繁中消息文本]")
                lines.append("")
                missing_records.append(
                    {
                        "id": row.get("Id"),
                        "message_group_id": row.get("MessageGroupId"),
                        "character_id": row.get("CharacterId"),
                        "message_type": message_type,
                        "message_kr": str(row.get("MessageKR") or "").strip(),
                        "message_jp": str(row.get("MessageJP") or "").strip(),
                        "message_en": str(row.get("MessageEN") or "").strip(),
                    }
                )
                continue

            text_records += 1
            lines.extend(
                f"{resolved_name}: {part.strip()}"
                for part in message.splitlines()
                if part.strip()
            )
            lines.append("")

        filename = f"{safe_filename(resolved_name)}_{safe_filename(character_id)}.txt"
        destination = output_dir / filename
        destination.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        manifest.append(
            {
                "character_id": character_id,
                "resolved_name": resolved_name,
                "resolver_status": status,
                "file": filename,
                "records": len(messages),
                "text_records": text_records,
                "image_records": image_records,
                "empty_records": empty_records,
                "missing_tw_records": missing_records,
            }
        )

    mapping = resolver.mapping_report()
    summary = {
        "input_records": len(rows),
        "character_ids": len(characters),
        "generated_files": len(manifest),
        "output_dir": str(output_dir),
        "text_records": sum(item["text_records"] for item in manifest),
        "image_records": sum(item["image_records"] for item in manifest),
        "empty_records": sum(item["empty_records"] for item in manifest),
        "unmapped_character_ids": dict(resolver.unmapped.most_common()),
        "unmapped_count_mode": "per_character_id",
        "variant_labeled_count": sum(bool(item["variant_label"]) for item in mapping),
        "variant_review_ids": [
            item["character_id"]
            for item in mapping
            if item["variant_source"] == "no_variant_evidence"
        ],
    }
    (report_dir / "character_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (report_dir / "character_manifest.json").write_text(
        json.dumps(sorted(manifest, key=lambda item: item["character_id"]), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (report_dir / "character_missing_tw_messages.json").write_text(
        json.dumps(
            [record for item in manifest for record in item["missing_tw_records"]],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (report_dir / "character_variant_mapping.json").write_text(
        json.dumps(resolver.mapping_report(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary


def nonzero_id(value: Any) -> str | None:
    text = str(value or "").strip()
    return text if text and text != "0" else None


def message_lines(
    row: dict[str, Any], resolver: CharacterResolver, converter: OpenCC
) -> tuple[list[str], bool]:
    """Render one row and return (lines, has_text)."""
    character, _ = resolver.resolve(row.get("CharacterId"))
    message_type = str(row.get("MessageType") or "Text")
    if message_type.lower() == "image":
        image_path = str(row.get("ImagePath") or "").strip()
        return [f"{character}: [图片]{(' ' + image_path) if image_path else ''}"], True

    message = clean_text(row.get("MessageTW"), converter)
    if not message:
        return [], False
    return [
        f"{character}: {part.strip()}"
        for part in message.splitlines()
        if part.strip()
    ], True


def build_message_graph(
    rows: list[dict[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], list[str], dict[str, int]]:
    """Build groups and preserve their first-seen order from the source table."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    order: dict[str, int] = {}
    for index, row in enumerate(rows):
        group_id = str(row.get("MessageGroupId") or "ungrouped")
        groups[group_id].append(row)
        order.setdefault(group_id, index)

    incoming: dict[str, set[str]] = defaultdict(set)
    for group_id, messages in groups.items():
        for row in messages:
            next_id = nonzero_id(row.get("NextGroupId"))
            if next_id in groups:
                incoming[next_id].add(group_id)
            # A precondition is also a dependency edge for root detection.
            # It is not traversed as a normal dialogue transition because it
            # describes unlock requirements rather than the next message.
            precondition_id = nonzero_id(row.get("PreConditionGroupId"))
            if precondition_id in groups:
                incoming[group_id].add(precondition_id)

    roots = [group_id for group_id in groups if not incoming[group_id]]
    roots.sort(key=order.__getitem__)
    return groups, roots, order


def story_group_text(
    group_id: str,
    messages: list[dict[str, Any]],
    incoming_answers: dict[str, list[str]],
    resolver: CharacterResolver,
    converter: OpenCC,
) -> tuple[list[str], list[str], int]:
    """Render one graph node, keeping choices and reactions visibly separate."""
    lines = [f"=== 消息组 {group_id} ==="]
    answers = [r for r in messages if str(r.get("MessageCondition")) == "Answer"]
    feedback = [r for r in messages if str(r.get("MessageCondition")) == "Feedback"]
    ordinary = [
        r for r in messages
        if str(r.get("MessageCondition")) not in {"Answer", "Feedback"}
    ]
    next_ids: list[str] = []
    for row in messages:
        next_id = nonzero_id(row.get("NextGroupId"))
        if next_id and next_id not in next_ids:
            next_ids.append(next_id)

    if ordinary:
        label = "普通消息"
        if any(str(r.get("MessageCondition")) == "FavorRankUp" for r in ordinary):
            label = "好感度/普通消息"
        lines.append(f"【{label}】")
        for row in ordinary:
            rendered, has_text = message_lines(row, resolver, converter)
            lines.extend(rendered)
            if not has_text:
                lines.append("[缺少繁中消息文本]")

    if answers:
        lines.append("【老师的选项】")
        unique_next: dict[str, list[int]] = defaultdict(list)
        for index, row in enumerate(answers, 1):
            rendered, has_text = message_lines(row, resolver, converter)
            lines.append(f"【选项{index}】")
            if rendered:
                # Answer text is normally one line, but preserve every line if the
                # source contains an explicit line break.
                answer_text = rendered[0].split(": ", 1)[1]
                lines.append(f"老师: {answer_text}")
                lines.extend(f"老师: {part}" for part in rendered[1:])
            else:
                lines.append("老师: [缺少繁中消息文本]")
            next_id = nonzero_id(row.get("NextGroupId"))
            if next_id:
                unique_next[next_id].append(index)
                lines.append(f"→ 后续消息组: {next_id}")
            if lines and lines[-1] != "":
                lines.append("")

        # Do not print a reaction heading here: the actual reaction belongs to
        # the destination group and is rendered there. This group only records
        # the available choices and their graph destinations.
        if len(unique_next) == 1 and len(answers) > 1:
            target = next(iter(unique_next))
            lines.append(
                f"（选项1-{len(answers)}共用后续消息组 {target}；"
                "原始数据未提供逐项反应对应关系。）"
            )

    if feedback:
        source = incoming_answers.get(group_id, [])
        if source:
            lines.append("【选项后的角色反应】")
            if len(source) > 1:
                lines.append("（多个选项路径汇合到此组，以下反应无法按选项进一步拆分。）")
        else:
            lines.append("【角色反馈】")
        for row in feedback:
            rendered, has_text = message_lines(row, resolver, converter)
            lines.extend(rendered)
            if not has_text:
                lines.append("[缺少繁中消息文本]")
            if lines and lines[-1] != "":
                lines.append("")

    if next_ids:
        non_answer_next = [
            next_id for next_id in next_ids
            if not any(nonzero_id(row.get("NextGroupId")) == next_id for row in answers)
        ]
        for next_id in non_answer_next:
            lines.append(f"→ 下一消息组: {next_id}")
    if not lines or lines[-1] != "":
        lines.append("")
    return lines, next_ids, len(answers) + len(feedback) + len(ordinary)


def group_rows_in_order(
    rows: list[dict[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    """Group rows by MessageGroupId while retaining their first-seen order."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    order: dict[str, int] = {}
    for index, row in enumerate(rows):
        group_id = str(row.get("MessageGroupId") or "ungrouped")
        groups[group_id].append(row)
        order.setdefault(group_id, index)
    return groups, sorted(groups, key=order.__getitem__)


def nonzero_schedule_id(messages: list[dict[str, Any]], field: str) -> str | None:
    """Return the first non-zero schedule ID carried by a message group."""
    for row in messages:
        value = str(row.get(field) or "").strip()
        if value and value != "0":
            return value
    return None


def group_is_favor_rank_up(messages: list[dict[str, Any]]) -> bool:
    return any(
        str(row.get("MessageCondition") or "") == "FavorRankUp"
        for row in messages
    )


def convert_character_stories(
    rows: list[dict[str, Any]],
    output_dir: Path,
    report_dir: Path,
    resolver: CharacterResolver,
    converter: OpenCC,
) -> dict[str, Any]:
    """Write character manuscripts with explicit bond-story boundaries.

    A non-zero FavorScheduleId marks the messenger immediately before a bond
    story. The following rows belong to the post-story messenger section until
    the next FavorRankUp group, which starts the next normal contact. This is
    the relationship represented by the source table's
    PreConditionFavorScheduleId field and matches the in-game ordering.
    """
    characters: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        characters[character_id_text(row.get("CharacterId"))].append(row)

    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    previous_manifest_path = report_dir / "character_story_manifest.json"
    if previous_manifest_path.exists():
        try:
            previous_manifest = json.loads(previous_manifest_path.read_text(encoding="utf-8"))
            for item in previous_manifest:
                old_file = str(item.get("file") or "").strip()
                if old_file:
                    old_path = output_dir / old_file
                    if old_path.is_file():
                        old_path.unlink()
        except (OSError, json.JSONDecodeError):
            pass
    manifest: list[dict[str, Any]] = []

    for character_id, character_rows in characters.items():
        resolved_name, _ = resolver.resolve(
            None if character_id == "unknown" else character_id
        )
        groups, group_order = group_rows_in_order(character_rows)
        incoming_answers: dict[str, list[str]] = defaultdict(list)
        for source_id, messages in groups.items():
            if any(
                str(row.get("MessageCondition") or "") == "Answer"
                for row in messages
            ):
                for row in messages:
                    target = nonzero_id(row.get("NextGroupId"))
                    if target and target in groups and source_id not in incoming_answers[target]:
                        incoming_answers[target].append(source_id)

        lines = [
            f"标题：Academy Messenger 羁绊通讯剧情（CharacterId {character_id}）",
            f"角色：{resolved_name}",
            "",
        ]
        bond_count = 0
        active_bond: dict[str, Any] | None = None
        seen_schedule_ids: set[str] = set()
        rendered_groups: list[str] = []

        def close_bond() -> None:
            nonlocal active_bond
            if active_bond is None:
                return
            lines.append(
                f"【羁绊剧情 {active_bond['number']} 结束 "
                f"（FavorScheduleId: {active_bond['schedule_id']}）】"
            )
            lines.append("")
            active_bond = None

        for group_id in group_order:
            messages = groups[group_id]
            schedule_id = nonzero_schedule_id(messages, "FavorScheduleId")
            pre_schedule_id = nonzero_schedule_id(messages, "PreConditionFavorScheduleId")

            # FavorRankUp is the first message of the next normal contact, so
            # it closes the preceding bond section before being rendered.
            if active_bond is not None and group_is_favor_rank_up(messages):
                close_bond()

            # Recover gracefully if the trigger row is absent from a filtered
            # input but the first post-story group still carries the precondition.
            if (
                active_bond is None
                and pre_schedule_id
                and pre_schedule_id not in seen_schedule_ids
                and not schedule_id
            ):
                bond_count += 1
                active_bond = {
                    "number": bond_count,
                    "schedule_id": pre_schedule_id,
                    "trigger_group_id": None,
                    "first_post_group_id": group_id,
                    "group_ids": [],
                }
                lines.append(
                    f"【羁绊剧情 {bond_count} 开始 "
                    f"（FavorScheduleId: {pre_schedule_id}；前置记录未找到）】"
                )
                lines.append("")

            section, _, _ = story_group_text(
                group_id, messages, incoming_answers, resolver, converter
            )
            lines.extend(section)
            rendered_groups.append(group_id)

            # The trigger message is part of the preceding communication. Put
            # the bond marker immediately after it, before the next group.
            if schedule_id:
                if active_bond is not None:
                    close_bond()
                bond_count += 1
                seen_schedule_ids.add(schedule_id)
                active_bond = {
                    "number": bond_count,
                    "schedule_id": schedule_id,
                    "trigger_group_id": group_id,
                    "first_post_group_id": None,
                    "group_ids": [],
                }
                lines.append(
                    f"【羁绊剧情 {bond_count} 开始 "
                    f"（FavorScheduleId: {schedule_id}）】"
                )
                lines.append("")

            if active_bond is not None:
                active_bond["group_ids"].append(group_id)
                if (
                    active_bond["first_post_group_id"] is None
                    and group_id != active_bond["trigger_group_id"]
                ):
                    active_bond["first_post_group_id"] = group_id

        close_bond()
        destination = output_dir / f"{safe_filename(resolved_name)}_{safe_filename(character_id)}.txt"
        destination.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

        # Build the manifest after rendering so the trigger/post group data is
        # captured exactly as it appears in the manuscript.
        bond_manifest = []
        active_number = 0
        for group_id in group_order:
            messages = groups[group_id]
            schedule_id = nonzero_schedule_id(messages, "FavorScheduleId")
            if schedule_id:
                active_number += 1
                post_groups: list[str] = []
                for candidate in group_order[group_order.index(group_id) + 1 :]:
                    candidate_rows = groups[candidate]
                    if group_is_favor_rank_up(candidate_rows):
                        break
                    post_groups.append(candidate)
                bond_manifest.append(
                    {
                        "number": active_number,
                        "schedule_id": schedule_id,
                        "trigger_group_id": group_id,
                        "post_group_ids": post_groups,
                    }
                )

        manifest.append(
            {
                "character_id": character_id,
                "resolved_name": resolved_name,
                "file": destination.name,
                "records": len(character_rows),
                "message_groups": len(rendered_groups),
                "bond_story_count": len(bond_manifest),
                "bond_stories": bond_manifest,
            }
        )

    mapping = resolver.mapping_report()
    summary = {
        "input_records": len(rows),
        "character_ids": len(characters),
        "generated_files": len(manifest),
        "bond_story_count": sum(item["bond_story_count"] for item in manifest),
        "output_dir": str(output_dir),
        "boundary_rule": "FavorScheduleId starts; next FavorRankUp ends",
        "variant_labeled_count": sum(bool(item["variant_label"]) for item in mapping),
        "variant_review_ids": [
            item["character_id"]
            for item in mapping
            if item["variant_source"] == "no_variant_evidence"
        ],
    }
    (report_dir / "character_story_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (report_dir / "character_story_manifest.json").write_text(
        json.dumps(sorted(manifest, key=lambda item: item["character_id"]), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (report_dir / "character_variant_mapping.json").write_text(
        json.dumps(resolver.mapping_report(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary


def compressed_row_text(
    row: dict[str, Any], resolver: CharacterResolver, converter: OpenCC
) -> tuple[str, str, bool]:
    """Return (speaker, simplified text, used_fallback_language) for compression."""
    condition = str(row.get("MessageCondition") or "")
    speaker = "老师" if condition == "Answer" else resolver.resolve(row.get("CharacterId"))[0]
    if str(row.get("MessageType") or "Text").lower() == "image":
        image_path = str(row.get("ImagePath") or "").strip()
        return speaker, f"[图片: {image_path}]" if image_path else "[图片]", False

    for index, field in enumerate(("MessageTW", "MessageJP", "MessageEN", "MessageKR")):
        text = clean_text(row.get(field), converter)
        if text:
            return speaker, text, index > 0
    return speaker, "[缺少对话文本]", False



def append_compressed_dialogue(lines: list[str], speaker: str, text: str) -> None:
    """Prefix every non-empty source line and separate dialogue turns."""
    parts = [part.strip() for part in text.splitlines() if part.strip()]
    lines.extend(f"{speaker}: {part}" for part in parts or [text.strip()])
    if not lines or lines[-1] != "":
        lines.append("")



def compressed_branch_destinations(
    groups: dict[str, list[dict[str, Any]]],
) -> tuple[
    set[str],
    dict[str, list[str]],
    dict[str, list[str]],
    dict[str, list[str]],
]:
    """Summarize branch destinations without exposing internal group IDs."""
    merged: set[str] = set()
    branch_labels: dict[str, list[str]] = defaultdict(list)
    incoming_sources: dict[str, list[str]] = defaultdict(list)
    branch_option_labels: dict[str, list[str]] = {}
    for source_id, messages in groups.items():
        answers = [
            row for row in messages
            if str(row.get("MessageCondition") or "") == "Answer"
        ]
        targets: list[str] = []
        for row in answers:
            target = nonzero_id(row.get("NextGroupId"))
            if target and target not in targets:
                targets.append(target)
                incoming_sources[target].append(source_id)
        if len(answers) > 1 and len(targets) == 1:
            merged.add(targets[0])
        elif len(targets) > 1:
            option_labels: list[str] = []
            target_labels = {
                target: f"分支{number}"
                for number, target in enumerate(targets, 1)
            }
            for row in answers:
                target = nonzero_id(row.get("NextGroupId"))
                label = target_labels.get(target, "")
                option_labels.append(label)
                if label and target:
                    branch_labels[target].append(label)
            branch_option_labels[source_id] = option_labels
    return merged, branch_labels, incoming_sources, branch_option_labels



def explicit_branch_feedbacks(
    groups: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, list[list[dict[str, Any]]]], set[str]]:
    """Return explicit one-to-one answer feedback and consumed destination groups."""
    feedback_by_source: dict[str, list[list[dict[str, Any]]]] = {}
    consumed_groups: set[str] = set()
    for source_id, messages in groups.items():
        answers = [
            row
            for row in messages
            if str(row.get("MessageCondition") or "") == "Answer"
        ]
        targets = [nonzero_id(row.get("NextGroupId")) for row in answers]
        if (
            len(answers) < 2
            or any(target is None or target not in groups for target in targets)
            or len(set(targets)) != len(targets)
        ):
            continue

        branch_rows: list[list[dict[str, Any]]] = []
        valid = True
        for target in targets:
            target_messages = groups[target]
            if not target_messages or any(
                str(row.get("MessageCondition") or "") != "Feedback"
                for row in target_messages
            ):
                valid = False
                break
            branch_rows.append(target_messages)
        if valid:
            feedback_by_source[source_id] = branch_rows
            consumed_groups.update(targets)
    return feedback_by_source, consumed_groups



def compressed_group_lines(

    group_id: str,
    messages: list[dict[str, Any]],
    resolver: CharacterResolver,
    converter: OpenCC,
    merged_destinations: set[str],
    branch_destinations: dict[str, list[str]],
    incoming_sources: dict[str, list[str]],
    explicit_feedback: list[list[dict[str, Any]]] | None = None,
    previous_kind: str | None = None,
) -> tuple[list[str], int, int, int, str | None]:
    """Render a group with semantic headings and no database metadata."""
    lines: list[str] = []
    current_kind: str | None = previous_kind
    dialogue_count = 0
    image_count = 0
    fallback_count = 0

    if group_id in merged_destinations:
        current_kind = "feedback"
    elif group_id in branch_destinations:
        labels = "、".join(branch_destinations[group_id])
        lines.append(f"[{labels}后续]")
        current_kind = "feedback"

    def heading(kind: str) -> None:
        nonlocal current_kind
        if kind == current_kind:
            return
        labels = {
            # Chapter markers are the only top-level marker for ordinary
            # dialogue; avoid repeating [普通通讯] inside each chapter.
            "ordinary": "",
            "answer": "",
            "feedback": "",
        }
        if labels[kind]:
            lines.append(labels[kind])
        current_kind = kind

    answer_rows = [
        row
        for row in messages
        if str(row.get("MessageCondition") or "") == "Answer"
    ]
    rendered_answers = False
    for row in messages:
        condition = str(row.get("MessageCondition") or "")
        if condition == "Answer":
            # Keep every choice in one block, matching the Scenario and bond
            # story TXT format. Explicit one-to-one feedback is rendered under
            # its answer; ambiguous shared feedback remains after the block.
            if rendered_answers:
                continue
            rendered_answers = True
            if len(answer_rows) == 1:
                # A single teacher response is ordinary dialogue, not a
                # meaningful choice block.
                answer_row = answer_rows[0]
                speaker, text, used_fallback = compressed_row_text(
                    answer_row, resolver, converter
                )
                if used_fallback:
                    lines.append("[语言回退]")
                append_compressed_dialogue(lines, speaker, text)
                dialogue_count += 1
                if str(answer_row.get("MessageType") or "Text").lower() == "image":
                    image_count += 1
                if used_fallback:
                    fallback_count += 1
            else:
                lines.append("<选择>")
                for answer_number, answer_row in enumerate(answer_rows, 1):
                    if answer_number > 1:
                        lines.append("")
                    speaker, text, used_fallback = compressed_row_text(
                        answer_row, resolver, converter
                    )
                    parts = text.splitlines() or [text]
                    if used_fallback:
                        lines.append("[语言回退]")
                    lines.append(f"{answer_number}. {speaker}: {parts[0]}")
                    lines.extend(f"{speaker}: {part}" for part in parts[1:])
                    dialogue_count += 1
                    if str(answer_row.get("MessageType") or "Text").lower() == "image":
                        image_count += 1
                    if used_fallback:
                        fallback_count += 1

                    if explicit_feedback and answer_number <= len(explicit_feedback):
                        for feedback_row in explicit_feedback[answer_number - 1]:
                            feedback_speaker, feedback_text, feedback_fallback = compressed_row_text(
                                feedback_row, resolver, converter
                            )
                            if feedback_fallback:
                                lines.append("[语言回退]")
                            append_compressed_dialogue(
                                lines, feedback_speaker, feedback_text
                            )
                            dialogue_count += 1
                            if str(feedback_row.get("MessageType") or "Text").lower() == "image":
                                image_count += 1
                            if feedback_fallback:
                                fallback_count += 1
                lines.append("</选择>")
                if not lines or lines[-1] != "":
                    lines.append("")
            current_kind = "answer"
            continue

        kind = "feedback" if condition == "Feedback" else "ordinary"
        heading(kind)
        speaker, text, used_fallback = compressed_row_text(row, resolver, converter)
        if used_fallback:
            lines.append("[语言回退]")
        append_compressed_dialogue(lines, speaker, text)
        dialogue_count += 1
        if str(row.get("MessageType") or "Text").lower() == "image":
            image_count += 1
        if used_fallback:
            fallback_count += 1
    return lines, dialogue_count, image_count, fallback_count, current_kind



def convert_compressed_character_stories(
    rows: list[dict[str, Any]],
    output_dir: Path,
    resolver: CharacterResolver,
    converter: OpenCC,
) -> dict[str, Any]:
    """Write compact, AI-oriented TXT files while preserving all dialogue."""
    characters: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        characters[character_id_text(row.get("CharacterId"))].append(row)

    output_dir.mkdir(parents=True, exist_ok=True)
    # This is a dedicated generated directory. Only remove payloads when the
    # ownership marker proves that this mode created the previous files;
    # unrelated TXT files in a pre-existing directory are left untouched.
    ownership_marker = output_dir / ".Momotalk_message.generated"
    if ownership_marker.exists():
        try:
            previous_files = {
                line.strip()
                for line in ownership_marker.read_text(encoding="utf-8").splitlines()
                if line.strip()
            }
        except OSError:
            previous_files = set()
        for filename in previous_files:
            if Path(filename).name == filename and filename.endswith(".txt"):
                previous_path = output_dir / filename
                if previous_path.is_file():
                    previous_path.unlink()

    manifest: list[dict[str, Any]] = []
    for character_id, character_rows in characters.items():
        resolved_name, _ = resolver.resolve(
            None if character_id == "unknown" else character_id
        )
        groups, group_order = group_rows_in_order(character_rows)
        (
            merged_destinations,
            branch_destinations,
            incoming_sources,
            _branch_option_labels,
        ) = compressed_branch_destinations(groups)
        explicit_feedback_by_source, consumed_branch_groups = explicit_branch_feedbacks(groups)
        lines = [f"{resolved_name}——Academy Messenger 通讯", ""]
        seen_schedule_ids: set[str] = set()
        chapter_count = 0
        bond_count = 0
        dialogue_count = 0
        image_count = 0
        fallback_count = 0
        previous_kind: str | None = None

        for group_id in group_order:
            if group_id in consumed_branch_groups:
                continue
            messages = groups[group_id]
            schedule_id = nonzero_schedule_id(messages, "FavorScheduleId")
            pre_schedule_id = nonzero_schedule_id(messages, "PreConditionFavorScheduleId")

            # FavorRankUp identifies the first group of a new normal contact.
            # Present chapter markers at that boundary, before rendering the
            # group's dialogue. If a filtered input omits the first marker,
            # still create chapter 1 at the beginning of the file.
            if chapter_count == 0 or group_is_favor_rank_up(messages):
                chapter_count += 1
                lines.append(f"=== 章节{chapter_count} ===")
                lines.append("")
                previous_kind = None

            # If the trigger row was filtered out, the post-story group can
            # still identify the bond through PreConditionFavorScheduleId.
            if (
                pre_schedule_id
                and pre_schedule_id not in seen_schedule_ids
                and not schedule_id
            ):
                bond_count += 1
                seen_schedule_ids.add(pre_schedule_id)
                lines.append(
                    f"【此处触发羁绊剧情{bond_count}，正文见《{resolved_name}_羁绊剧情》】"
                )
                lines.append("")
                previous_kind = None

            section, section_dialogues, section_images, section_fallbacks, previous_kind = compressed_group_lines(
                group_id,
                messages,
                resolver,
                converter,
                merged_destinations,
                branch_destinations,
                incoming_sources,
                explicit_feedback_by_source.get(group_id),
                previous_kind,
            )
            lines.extend(section)
            if not lines or lines[-1] != "":
                lines.append("")
            dialogue_count += section_dialogues
            image_count += section_images
            fallback_count += section_fallbacks
            lines.append("")

            # FavorScheduleId belongs to the preceding communication. Put the
            # bond marker immediately after that communication, before the
            # first post-trigger dialogue, matching the manuscript layout.
            if schedule_id:
                bond_count += 1
                seen_schedule_ids.add(schedule_id)
                previous_kind = None
                lines.append(
                    f"【此处触发羁绊剧情{bond_count}，正文见《{resolved_name}_羁绊剧情》】"
                )
                lines.append("")

        destination = output_dir / f"{safe_filename(resolved_name)}_{safe_filename(character_id)}.txt"
        destination.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        manifest.append(
            {
                "character_id": character_id,
                "resolved_name": resolved_name,
                "file": destination.name,
                "records": len(character_rows),
                "message_groups": len(group_order),
                "bond_story_count": bond_count,
                "dialogue_records": dialogue_count,
                "image_records": image_count,
                "language_fallback_records": fallback_count,
            }
        )

    ownership_marker.write_text(
        "\n".join(sorted(item["file"] for item in manifest)) + "\n",
        encoding="utf-8",
    )
    return {
        "input_records": len(rows),
        "character_ids": len(characters),
        "generated_files": len(manifest),
        "bond_story_count": sum(item["bond_story_count"] for item in manifest),
        "dialogue_records": sum(item["dialogue_records"] for item in manifest),
        "image_records": sum(item["image_records"] for item in manifest),
        "language_fallback_records": sum(item["language_fallback_records"] for item in manifest),
        "output_dir": str(output_dir),
    }



def convert_stories(
    rows: list[dict[str, Any]],
    output_dir: Path,
    report_dir: Path,
    resolver: CharacterResolver,
    converter: OpenCC,
) -> dict[str, Any]:
    """Write one connected storyline per root group without guessing branch pairings."""
    groups, roots, order = build_message_graph(rows)
    incoming_answers: dict[str, list[str]] = defaultdict(list)
    for source_id, messages in groups.items():
        if any(str(r.get("MessageCondition")) == "Answer" for r in messages):
            for row in messages:
                target = nonzero_id(row.get("NextGroupId"))
                if target and target in groups and source_id not in incoming_answers[target]:
                    incoming_answers[target].append(source_id)

    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, Any]] = []
    covered: set[str] = set()

    def render_from(root: str) -> tuple[str, set[str]]:
        rendered: set[str] = set()
        lines = [f"标题：Academy Messenger 通讯剧情（起点 {root}）", ""]

        def visit(group_id: str) -> None:
            if group_id in rendered:
                lines.append(f"【消息组 {group_id} 已在前文输出，分支在此汇合】")
                lines.append("")
                return
            if group_id not in groups:
                lines.append(f"【缺失消息组 {group_id}】")
                lines.append("")
                return
            rendered.add(group_id)
            covered.add(group_id)
            section, next_ids, _ = story_group_text(
                group_id, groups[group_id], incoming_answers, resolver, converter
            )
            lines.extend(section)
            for next_id in next_ids:
                if next_id in groups:
                    visit(next_id)

        visit(root)
        return "\n".join(lines).rstrip() + "\n", rendered

    for root in roots:
        text, rendered = render_from(root)
        destination = output_dir / f"{root}.txt"
        destination.write_text(text, encoding="utf-8")
        manifest.append({
            "root_group_id": root,
            "file": destination.name,
            "group_count": len(rendered),
            "record_count": sum(len(groups[group_id]) for group_id in rendered),
        })

    # Handle isolated cycles or malformed links that cannot be reached from a root.
    for group_id in sorted(set(groups) - covered, key=order.__getitem__):
        text, rendered = render_from(group_id)
        destination = output_dir / f"{group_id}.txt"
        destination.write_text(text, encoding="utf-8")
        manifest.append({
            "root_group_id": group_id,
            "file": destination.name,
            "group_count": len(rendered),
            "record_count": sum(len(groups[item]) for item in rendered),
            "reason": "unreachable_from_root",
        })

    missing_preconditions = sorted(
        {
            precondition_id
            for messages in groups.values()
            for row in messages
            if (precondition_id := nonzero_id(row.get("PreConditionGroupId")))
            and precondition_id not in groups
        }
    )
    summary = {
        "input_records": len(rows),
        "message_groups": len(groups),
        "story_files": len(manifest),
        "covered_groups": len(covered),
        "uncovered_groups": len(set(groups) - covered),
        "missing_precondition_groups": missing_preconditions,
        "output_dir": str(output_dir),
        "branch_pairing": "not_inferred_when_source_data_is_ambiguous",
    }
    (report_dir / "story_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (report_dir / "story_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="提取 Academy Messenger 通讯。")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--db-dir", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_TEXT_OUTPUT_DIR)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_TEXT_REPORT_DIR)
    parser.add_argument("--stories", action="store_true", help="按 NextGroupId 重建完整通讯剧情")
    parser.add_argument("--by-character", action="store_true", help="按 CharacterId 为每个角色生成一个 TXT")
    parser.add_argument("--character-stories", action="store_true", help="按 CharacterId 整理羁绊剧情前后通讯稿")
    parser.add_argument(
        "--Momotalk_message",
        dest="momotalk_message",
        action="store_true",
        help="生成 result/Momotalk/Momotalk_message/ AI 角色剧情 TXT",
    )
    parser.add_argument("--character-output-dir", type=Path, default=DEFAULT_CHARACTER_OUTPUT_DIR)
    parser.add_argument("--character-report-dir", type=Path, default=DEFAULT_CHARACTER_REPORT_DIR)
    parser.add_argument("--character-story-output-dir", type=Path, default=DEFAULT_CHARACTER_STORY_OUTPUT_DIR)
    parser.add_argument("--character-story-report-dir", type=Path, default=DEFAULT_CHARACTER_STORY_REPORT_DIR)
    parser.add_argument("--compressed-output-dir", type=Path, default=DEFAULT_COMPRESSED_OUTPUT_DIR)
    parser.add_argument("--story-output-dir", type=Path, default=DEFAULT_STORY_OUTPUT_DIR)
    parser.add_argument("--story-report-dir", type=Path, default=DEFAULT_STORY_REPORT_DIR)
    args = parser.parse_args()

    converter = OpenCC("t2s")
    resolver = CharacterResolver(args.db_dir, converter)
    rows = rows_from(load_json(args.input))
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        group_id = str(row.get("MessageGroupId") or "ungrouped")
        groups[group_id].append(row)

    if not args.by_character and not args.character_stories and not args.momotalk_message:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        args.report_dir.mkdir(parents=True, exist_ok=True)
        manifest: list[dict[str, Any]] = []
        for group_id, messages in groups.items():
            text, stats = convert_group(group_id, messages, resolver, converter)
            (args.output_dir / f"{group_id}.txt").write_text(text, encoding="utf-8")
            manifest.append(stats)

        summary = {
            "input_records": len(rows),
            "message_groups": len(groups),
            "generated_files": len(groups),
            "output_dir": str(args.output_dir),
            "unmapped_character_ids": dict(resolver.unmapped.most_common()),
            "text_records": sum(x["text_records"] for x in manifest),
            "image_records": sum(x["image_records"] for x in manifest),
            "empty_records": sum(x["empty_records"] for x in manifest),
            "missing_tw_records": sum(len(x["missing_tw_records"]) for x in manifest),
        }
        (args.report_dir / "conversion_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (args.report_dir / "message_groups_manifest.json").write_text(
            json.dumps(sorted(manifest, key=lambda x: x["group_id"]), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (args.report_dir / "unmapped_character_ids.json").write_text(
            json.dumps(dict(resolver.unmapped.most_common()), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (args.report_dir / "missing_tw_messages.json").write_text(
            json.dumps(
                [item for group in manifest for item in group["missing_tw_records"]],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"完成：{len(rows)} 条消息，{len(groups)} 个 MessageGroupId，生成 {len(groups)} 个 TXT。")
        print(f"输出目录：{args.output_dir}")
        print(f"报告目录：{args.report_dir}")

    if args.momotalk_message:
        compressed_summary = convert_compressed_character_stories(
            rows,
            args.compressed_output_dir,
            resolver,
            converter,
        )
        print(
            f"AI 压缩剧情稿完成：{compressed_summary['character_ids']} 个角色，"
            f"{compressed_summary['generated_files']} 个 TXT，"
            f"{compressed_summary['bond_story_count']} 段羁绊剧情。"
        )
        print(f"AI 压缩剧情目录：{args.compressed_output_dir}")

    if args.character_stories:
        character_story_summary = convert_character_stories(
            rows,
            args.character_story_output_dir,
            args.character_story_report_dir,
            resolver,
            converter,
        )
        print(
            f"羁绊剧情稿整理完成：{character_story_summary['character_ids']} 个角色，"
            f"{character_story_summary['bond_story_count']} 段羁绊剧情，"
            f"生成 {character_story_summary['generated_files']} 个 TXT。"
        )
        print(f"剧情稿目录：{args.character_story_output_dir}")
        print(f"剧情稿报告目录：{args.character_story_report_dir}")

    elif args.by_character and not args.momotalk_message:
        character_summary = convert_characters(
            rows,
            args.character_output_dir,
            args.character_report_dir,
            resolver,
            converter,
        )
        print(
            f"按 CharacterId 提取完成：{character_summary['character_ids']} 个角色，"
            f"生成 {character_summary['generated_files']} 个 TXT。"
        )
        print(f"角色输出目录：{args.character_output_dir}")
        print(f"角色报告目录：{args.character_report_dir}")

    if args.stories:
        story_summary = convert_stories(
            rows,
            args.story_output_dir,
            args.story_report_dir,
            resolver,
            converter,
        )
        print(
            f"剧情重建完成：{story_summary['story_files']} 个剧情文件，"
            f"覆盖 {story_summary['covered_groups']}/{story_summary['message_groups']} 个消息组。"
        )
        print(f"剧情目录：{args.story_output_dir}")
        print(f"剧情报告：{args.story_report_dir}")


if __name__ == "__main__":
    main()
