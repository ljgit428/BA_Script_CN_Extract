# 数据生成脚本

项目中的原始数据统一放在 `raw/ba-data-global/`，生成结果统一放在 `result/`。
脚本的默认路径按脚本文件位置计算，因此从任意当前工作目录执行都可以。

## 一键生成

在项目根目录执行：

```bash
python script/generate.py
```

只生成 Scenario：

```bash
python script/generate.py --scenario-only
```

只生成 Academy Messenger：

```bash
python script/generate.py --momotalk-only
```

只生成羁绊剧情：

```bash
python script/generate.py --bond-story-only
```

只生成 Field 自由会话（按 GroupId 分段）：

```bash
python script/generate.py --free-dialog-only
```

## 输出目录

- `result/scenario/all_scenarios/`：从 `ScenarioScriptExcelTable1/2/3.json` 按 `GroupId` 切分的 JSON
- `result/scenario/scenario_texts/`：Scenario JSON 对应的中文 TXT
- `result/scenario/scenario_texts_with_reactions/`：额外保留表情/动作反应的 Scenario TXT
- `result/scenario/scenario_text_reports/`：Scenario 转换诊断报告
- `result/scenario/scenario_text_reaction_reports/`：带反应文本的转换诊断报告
- `result/Momotalk/Momotalk_message/`：面向 AI 的按角色文件夹、按章节拆分的压缩通讯稿
- `result/Momotalk/Momotalk_message_combined/`：面向 AI 的按角色文件夹、不分割完整通讯稿
- `result/Momotalk/academy_messanger_character_stories/`：完整逐角色羁绊通讯稿
- `result/Momotalk/` 下的其他目录：其他 Academy Messenger 转换模式的输出
- `result/bond_story/bond_story_text/`：按角色文件夹、按章节拆分的羁绊剧情文本；章节中的场景地点来自 ScenarioScript 的 `#place` 标记
- `result/bond_story/bond_story_text_with_reactions/`：额外保留表情/动作反应的羁绊剧情文本
- `result/bond_story/bond_story_text_combined/`：不分割的羁绊剧情文本
- `result/bond_story/bond_story_text_with_reactions_combined/`：不分割且带反应的羁绊剧情文本
- `result/bond_story/reports/`：羁绊剧情生成报告（summary、manifest、空文本和缺失剧情组清单）
- `result/bond_story/bond_story_reaction_reports/`：带反应羁绊文本的生成报告
- `result/free_dialog/free_dialog_text/`：按 Field `GroupId` 分段的自由会话 TXT，不按角色合并
- `result/free_dialog/reports/`：自由会话生成统计和关联清单

## 单独运行

```bash
python script/scenario/split_scenario_groups.py --all
python script/scenario/convert_scenario_to_txt.py --all
python script/scenario/convert_scenario_to_txt.py --all --with-reactions
python script/Momotalk/academy_messanger_to_txt.py --Momotalk_message
python script/Momotalk/academy_messanger_to_txt.py --Momotalk_message_combined
python script/bond_story/generate_bond_stories.py
python script/bond_story/generate_bond_stories.py --with-reactions
python script/bond_story/generate_bond_stories.py --combined
python script/bond_story/generate_bond_stories.py --combined --with-reactions
python script/free_dialog/generate_free_dialog.py
```

`generate_bond_stories.py` 默认从 `raw/ba-data-global/DB/` 读取羁绊日程、ScenarioScript 和角色映射表，按角色文件夹和章节输出到 `result/bond_story/bond_story_text/`，报告输出到 `result/bond_story/reports/`。Momotalk 的参考标记会引用对应的 `<角色名>_羁绊剧情_<章节编号>.txt`；combined 模式则引用 `<角色名>_<CharacterId>_羁绊剧情.txt`。加上 `--with-reactions` 后会改写入 `result/bond_story/bond_story_text_with_reactions/` 和 `result/bond_story/bond_story_reaction_reports/`，原始文本集保持不变。它也支持 `--schedule`、`--script`、`--names`、`--db-dir`、`--output-dir` 和 `--report-dir` 覆盖默认路径。

`generate_free_dialog.py` 默认读取 `raw/ba-data-global/Excel/CharacterDialogFieldExcelTable.json`，每个 `GroupId` 生成一个 `result/free_dialog/free_dialog_text/<GroupId>.txt`。输出先给标题和场景/其他信息（FieldSeason、FieldDate、场景资源、说话人、触发器），再按阶段输出 `角色: 台词`，每行只有一个说话人。说话人优先来自 `result/free_dialog/free_dialog_speakers.json`（`extract_field_speakers.py` 解析 GL designlevel 场景 bundle 生成）：`targets` 精确 NPC（顺序即 `TargetIndex`）> 父节点 NPC > 触发器名标注 > 通用池互动路人 > FieldDate 关联主角独白（833=阳奈、843=圣亚/宁瑠；没有老师参与）；缺失时回退 `FieldDateExcelTable` 角色图标推断，再退回原始 `TargetIndex`。

所有转换器都支持命令行参数覆盖默认输入、输出和报告目录；默认值始终指向仓库内的 `raw/` 与 `result/`。
