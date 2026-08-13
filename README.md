# BA Script CN Extract

从 Blue Archive 的文本数据中提取中文剧情文本，重点生成四类结果：

- `Momotalk_message`：按角色整理的 AI 友好型 Academy Messenger 通讯稿
- `scenario_texts`：按剧情 `GroupId` 整理的 Scenario 中文剧情稿
- `bond_story`：按角色汇总的羁绊剧情稿
- `free_dialog`：按 `GroupId` 分段整理的 Field 探索自由会话稿

原始数据不包含在本仓库中；只将三个重点最终结果作为备份提交到 Git。数据来自：

> [electricgoat/ba-data](https://github.com/electricgoat/ba-data)

## 环境要求

- Python 3.10+
- `opencc-python-reimplemented`

安装依赖：

```bash
python -m pip install -r script/scenario/requirements.txt
```

## 准备 raw 数据

在项目根目录执行：

```bash
git clone https://github.com/electricgoat/ba-data.git raw/ba-data-global
```

数据目录应至少包含：

```text
raw/ba-data-global/
├── DB/
│   ├── AcademyMessangerExcelTable.json
│   ├── CharacterExcelTable.json
│   ├── CostumeExcelTable.json
│   ├── LocalizeCharProfileExcelTable.json
│   ├── ScenarioCharacterNameExcelTable.json
│   ├── ScenarioScriptExcelTable1.json
│   ├── ScenarioScriptExcelTable2.json
│   └── ScenarioScriptExcelTable3.json
└── ...
```

## 生成 Momotalk_message

这是本项目最主要的输出。它会从 raw 数据直接生成每个角色/皮肤一个 TXT 文件，保留：

- 角色和皮肤名称
- 普通通讯
- 老师选项
- 分支与共同后续
- 羁绊剧情边界
- 图片事件和语言回退信息

执行：

```bash
python script/Momotalk/academy_messanger_to_txt.py --Momotalk_message
```

输出：

```text
result/Momotalk/Momotalk_message/
├── 阳奈_10004.txt
├── 阳奈（礼服）_10086.txt
├── 咲希（泳装）_10072.txt
├── 系统_0.txt
└── ...
```

当前数据通常生成约 257 个角色/皮肤 TXT；实际数量以 raw 数据为准。

## 生成 scenario_texts

Scenario 转换分为两步。

### 第一步：按 GroupId 切分原始 JSON

```bash
python script/scenario/split_scenario_groups.py --all
```

中间 JSON 会写入：

```text
result/scenario/all_scenarios/
```

### 第二步：转换为中文 TXT

```bash
python script/scenario/convert_scenario_to_txt.py --all
```

最终文本写入：

```text
result/scenario/scenario_texts/
```

诊断报告写入：

```text
result/scenario/scenario_text_reports/
```

当前数据通常生成约 3187 个 Scenario TXT；实际数量以 raw 数据为准。

## 生成 bond_story

羁绊剧情使用 `AcademyFavorScheduleExcelTable.json` 将每个角色的羁绊日程关联到对应的 Scenario `GroupId`，再按羁绊等级顺序汇总为每个角色一个 TXT。每段剧情的“场景地点”从 ScenarioScript 的 `#place` 标记提取，不再把日程固定地点夏莱误当成实际场景。它不会复制生成其他 Momotalk 输出目录。

执行：

```bash
python script/bond_story/generate_bond_stories.py
```

输出：

```text
result/bond_story/
├── bond_story_text/
│   ├── 亚瑠_10000.txt
│   ├── 阳奈_10004.txt
│   └── ...
└── reports/
```

剧情文本写入 `result/bond_story/bond_story_text/`，报告写入 `result/bond_story/reports/`；报告包含缺失剧情组、原始空文本记录和生成清单。当前数据通常生成 257 个角色 TXT、1077 条羁绊日程（其中 1073 条有可转换文本）；实际数量以 raw 数据为准。

### bond_story_text 的输入数据

生成器直接读取仓库内的 `raw/ba-data-global/DB/`，不依赖先生成 `scenario_texts` 或其他 Momotalk 目录：

```text
AcademyFavorScheduleExcelTable.json
ScenarioScriptExcelTable1.json
ScenarioScriptExcelTable2.json
ScenarioScriptExcelTable3.json
CharacterExcelTable.json
CostumeExcelTable.json
LocalizeCharProfileExcelTable.json
ScenarioCharacterNameExcelTable.json
```

其中：

1. `AcademyFavorScheduleExcelTable.json` 提供角色、羁绊等级和对应的 `ScenarioSriptGroupId`。
2. 三张 `ScenarioScriptExcelTable` 提供实际剧情对白、选项、旁白和 `#place` 场景标记。
3. 角色和皮肤表用于解析 TXT 文件名及角色显示名。
4. `TextTw` 会转换为简体中文；`#place` 对应的文本会输出为 `场景地点`。

### bond_story_text 的输出结构

每个 `CharacterId` 生成一个独立 TXT，文件名格式为：

```text
<角色显示名>_<CharacterId>.txt
```

TXT 内按 `FavorRank`/原始顺序排列羁绊剧情，并保留：

- 羁绊等级
- 实际场景地点（一个剧情可能有多个地点）
- 角色对白、老师选项和选项反馈
- 旁白、分支和原始剧情顺序

报告目录包含：

- `bond_story_summary.json`：总数量和生成统计
- `bond_story_manifest.json`：角色、文件和每段剧情的场景地点清单
- `empty_bond_stories.json`：原始剧情组存在但文本为空的记录
- `missing_bond_stories.json`：找不到对应 Scenario 剧情组的记录

### 重新生成和自定义路径

重复运行会只清理上一次由本模式生成并记录在 `.bond_story.generated` 中的 TXT，不会删除目录中的其他文件。默认路径之外，也可以覆盖输入和输出目录：

```bash
python script/bond_story/generate_bond_stories.py \
  --schedule path/to/AcademyFavorScheduleExcelTable.json \
  --script path/to/ScenarioScriptExcelTable1.json \
         path/to/ScenarioScriptExcelTable2.json \
         path/to/ScenarioScriptExcelTable3.json \
  --names path/to/ScenarioCharacterNameExcelTable.json \
  --db-dir path/to/DB \
  --output-dir path/to/bond_story_text \
  --report-dir path/to/reports
```

## 生成 Field 自由会话

Field 探索中的人物自由活动对白保存在 `CharacterDialogFieldExcelTable.json`。每个 `GroupId` 是一段独立会话，因此这里**按段落输出**，不会像 `Momotalk_message` 那样按角色合并。

执行：

```bash
python script/free_dialog/generate_free_dialog.py
```

或使用统一入口：

```bash
python script/generate.py --free-dialog-only
```

输出目录：

```text
result/free_dialog/
├── free_dialog_text/
│   ├── 84301200140.txt
│   └── ...
└── reports/
```

每个 TXT 包含：

- `GroupId`、`FieldDateId` 和可解析到的场景资源
- 每个阶段的 `TargetIndex`、对话类型和中文内容
- “谁说什么”的对白记录；`CharacterDialogFieldExcelTable` 本身没有角色名字段，但会通过 `FieldDateExcelTable` 的角色图标（如 `CH0070`）关联 `ScenarioCharacterNameExcelTable`，输出 `关联角色：圣亚（CH0070）`，同时保留 `TargetIndex`
- `LocalizeTW` 转换后的简体中文；若繁中为空则回退到 `LocalizeKR`

例如 `84301200140.txt` 会提取“今天又会发生什么事呢～”、汗的表情和“根本上不了课……”，并按阶段保留为同一段自由会话。它会从 `FieldDateId=84301` 找到 `CH0070`，再映射为“圣亚”；`TargetIndex` 仍会保留，因为原表没有直接声明每个阶段的说话人姓名。`843` 已标记为“千年EXPO”；其他未建立中文名称映射的 Field 会显示原始 `FieldSeasonId`。

报告目录包含：

- `free_dialog_summary.json`：源记录、段落数量和场景关联统计
- `free_dialog_manifest.json`：每个 GroupId 的文件、阶段和场景关联清单

重复运行只会清理 `.free_dialog.generated` 记录过的 TXT，不会删除输出目录中的其他文件。也可以覆盖输入和输出路径：

```bash
python script/free_dialog/generate_free_dialog.py \
  --input path/to/CharacterDialogFieldExcelTable.json \
  --output-dir path/to/free_dialog_text \
  --report-dir path/to/reports
```

## 一键入口

如果需要运行完整的历史转换模式，可以执行：

```bash
python script/generate.py
```

只生成 Scenario：

```bash
python script/generate.py --scenario-only
```

只运行完整的 Momotalk 转换流水线：

```bash
python script/generate.py --momotalk-only
```

只生成羁绊剧情：

```bash
python script/generate.py --bond-story-only
```

只生成 Field 自由会话：

```bash
python script/generate.py --free-dialog-only
```

如果只需要本项目重点结果，建议直接使用前面的专项命令，以避免生成其他可选的 Momotalk 表示形式。

## 目录说明

```text
script/
├── Momotalk/
│   └── academy_messanger_to_txt.py
├── scenario/
│   ├── split_scenario_groups.py
│   ├── convert_scenario_to_txt.py
│   └── requirements.txt
├── bond_story/
│   └── generate_bond_stories.py
├── free_dialog/
│   └── generate_free_dialog.py
└── generate.py
```

- `raw/`：本地原始数据，始终忽略
- `result/scenario/all_scenarios/`：Scenario 中间 JSON，忽略
- `result/scenario/scenario_texts/`：Scenario 最终 TXT，作为备份提交
- `result/Momotalk/Momotalk_message/`：Momotalk 最终 TXT，作为备份提交
- `result/bond_story/bond_story_text/`：羁绊剧情 TXT，作为备份提交
- `result/bond_story/reports/`：羁绊剧情生成报告，作为备份提交
- `result/free_dialog/free_dialog_text/`：按 GroupId 分段的 Field 自由会话 TXT，作为备份提交
- `result/free_dialog/reports/`：自由会话生成报告，作为备份提交
- 其他 `result/` 子目录：忽略
- `script/`：可提交的转换脚本和文档

## Git 说明

根目录 `.gitignore` 会忽略原始数据和大多数生成目录：

```text
/raw/
/result/*
```

仅以下重点结果目录例外，会作为仓库备份提交：

```text
/result/Momotalk/Momotalk_message/
/result/scenario/scenario_texts/
/result/bond_story/bond_story_text/
/result/bond_story/reports/
/result/free_dialog/free_dialog_text/
/result/free_dialog/reports/
```

首次使用时需要先准备 `raw/ba-data-global/`，再运行生成命令。重新生成后，如果需要更新备份，执行：

```bash
git add result/Momotalk/Momotalk_message result/scenario/scenario_texts result/bond_story result/free_dialog
git commit -m "Update generated text backup"
git push
```

## 相关说明

AI 压缩通讯稿的详细格式和保留规则见：

```text
script/Momotalk/Momotalk-message-spec.md
```
