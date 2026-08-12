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

## 输出目录

- `result/scenario/all_scenarios/`：从 `ScenarioScriptExcelTable1/2/3.json` 按 `GroupId` 切分的 JSON
- `result/scenario/scenario_texts/`：Scenario JSON 对应的中文 TXT
- `result/scenario/scenario_text_reports/`：Scenario 转换诊断报告
- `result/Momotalk/Momotalk_message/`：面向 AI 的逐角色压缩通讯稿
- `result/Momotalk/academy_messanger_character_stories/`：完整逐角色羁绊通讯稿
- `result/Momotalk/` 下的其他目录：其他 Academy Messenger 转换模式的输出
- `result/bond_story/bond_story_text/`：按角色汇总的羁绊剧情文本；章节中的场景地点来自 ScenarioScript 的 `#place` 标记
- `result/bond_story/reports/`：羁绊剧情生成报告

## 单独运行

```bash
python script/scenario/split_scenario_groups.py --all
python script/scenario/convert_scenario_to_txt.py --all
python script/Momotalk/academy_messanger_to_txt.py --Momotalk_message
python script/bond_story/generate_bond_stories.py
```

所有转换器都支持命令行参数覆盖默认输入、输出和报告目录；默认值始终指向仓库内的 `raw/` 与 `result/`。
