# BA Script CN Extract

从 Blue Archive 的文本数据中提取中文剧情文本，重点生成两类结果：

- `Momotalk_message`：按角色整理的 AI 友好型 Academy Messenger 通讯稿
- `scenario_texts`：按剧情 `GroupId` 整理的 Scenario 中文剧情稿

原始数据不包含在本仓库中，生成结果也不会提交到 Git。数据来自：

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

如果只需要本项目重点结果，建议直接使用前面的两个专项命令，以避免生成其他可选的 Momotalk 表示形式。

## 目录说明

```text
script/
├── Momotalk/
│   └── academy_messanger_to_txt.py
├── scenario/
│   ├── split_scenario_groups.py
│   ├── convert_scenario_to_txt.py
│   └── requirements.txt
└── generate.py
```

- `raw/`：本地原始数据，已加入 Git 忽略
- `result/`：本地生成结果，已加入 Git 忽略
- `script/`：可提交的转换脚本和文档

## Git 说明

根目录 `.gitignore` 会忽略：

```text
/raw/
/result/
```

因此 GitHub 仓库只保存脚本、说明和配置，不保存体积较大的游戏数据及生成结果。首次使用时需要先准备 `raw/ba-data-global/`，再运行生成命令。

## 相关说明

AI 压缩通讯稿的详细格式和保留规则见：

```text
script/Momotalk/Momotalk-message-spec.md
```
