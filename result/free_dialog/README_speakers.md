# free_dialog 说话人解析结果

## 结论

`CharacterDialogFieldExcelTable.json` 本身不含说话人字段（说话人由场景运行时决定）。
真正的映射在 **野外活动（Field Season 833 / 843）设计关卡场景** 中：

- 场景 bundle（GL_RawData/Bundle）内每个 `DialogTrigger_*` 物体挂有
  `FieldDialogBehavior` 组件（MXField.Dialog），其序列化数据 **偏移 40 处的 int64 即 `dialogGroupId`**。
- 组件的 `targets` 引用列表（偏移 76 起、12 字节步进，全部指向外部脚本的 `FieldDialogActor`）
  按顺序指向 `NPCs/<编组>/NPC_<角色>` GameObject，**列表顺序 = 表内 `TargetIndex` 顺序**
  （已用 84300300310 验证：T0=宁瑠、T1=莉央）。

## 说话人判定规则（每行台词只有一个说话人；没有老师参与，只有主角角色和互动角色）

每个触发器实例按优先级解析出唯一说话人：

1. **targets**：组件显式指向的 NPC（互动角色），按 TargetIndex 精确到人；
2. **parent**：无 targets 时，触发器直接挂在某 `NPC_*` 物体下 → 该 NPC；
3. **ambient**：通用池（GroupId 99xxx）/`Common`/`BubbleTalk` 环境气泡 → 互动路人（随机）；
4. **name**：触发器名自带角色标注（`02_DialogTrigger_Neru`、`CH0280CH0158`、`susang` 等）；
5. **protagonist**：其余空 targets 触发器为活动主角的探索独白 →
   `FieldDateExcelTable` 关联主角（833 全季=阳奈/Hina；843 大部分日期=圣亚/CH0070，
   84302/84304/84307=宁瑠/CH0280）。台词语气可交叉验证
   （84304100610“肯定是那些家伙。好，这次我不会错过的。”即宁瑠）。

同一 GroupId 在多个场景摆放且说话人不一致时，**主角实例优先**、每个 TargetIndex 槽位只保留一个名字。
其余未解析（未摆放入场景的 17 个通用池/测试组）回退 `TargetIndex N`。

## 数据源

| 文件 | 说明 |
|---|---|
| `field-scenes-designlevel-field833-..._1764168122.bundle` | 833 季全部设计关卡（689 个组件） |
| `field-scenes-designlevel-field843-..._3027871138.bundle` | 843 季全部设计关卡（253 个组件） |

位于 `F:\data_collection\...\GL_RawData\Bundle\`（解包 schema 见 GL_Extracted/Dumps/dump.cs）。

## 覆盖率

- 表内 583 个 GroupId：**566 个（97%）在场景中定位到挂载点，说话人全部解析（未确定为 0）**；
  生成的 TXT 正文每行 `角色: 台词` 只含一个说话人。
- 17 个表内 GroupId 未出现在这两个 bundle：`1`/`2`（测试）、`83305100310`、`83306060510`、
  `84300200150`，以及通用池 `83399000024/26/32/33`、`84399000003/05/07/11~15`（未被场景摆放）。
- 另有 9 个场景存在但表内已删除的 GroupId（83307030510、84303300180~182 等），一并在 JSON 中保留。

## 说话人分布（按 GroupId 数，前 20）

阳奈 125、风纪委员士兵(SG) 64、互动路人 52、圣亚 52、千年学生 38、宁瑠 24、
莉央 23、亚子 18、实现正义部成员 18、三一学生 17、千夏 14、伊织 14、伊吕波 13、
绘里香 13、绮罗罗 12、飞车党少女(SR) 11、飞车党少女(SMG) 10、伊吹 9、茱莉 8、爱丽丝 8。

（主角独白类：833 季以阳奈为主，843 季以圣亚为主、84302/04/07 为宁瑠。）

角色代号 → 中文名来自 `ScenarioCharacterNameExcelTable`（spine 匹配）、
`CharacterExcelTable` + `LocalizeEtcExcelTable`（CH0281=明日奈(制服)、CH0282=花凛(制服)），
繁转简用 OpenCC tw2sp。

## 产物

- `free_dialog_speakers.json`：`groups.<GroupId>` →
  `in_table` / `speakers_cn`（去重聚合）/ `speaker_by_target_index`（TargetIndex→唯一人名）/
  `instances`（scene、trigger、method=判定来源、speakers_raw，可审计每个摆放点）。
- 提取脚本：`script/free_dialog/extract_field_speakers.py`（依赖 UnityPy、opencc）。

## 与生成器的整合

`script/free_dialog/generate_free_dialog.py` 已读取本 JSON：正文输出 `角色: 台词`，
说话人优先取 `speaker_by_target_index`（按 TargetIndex，唯一人名），缺失时用 `speakers_cn` 聚合、
再回退 FieldDate 推断，最后才显示 `TargetIndex N`。相关 CLI 参数：`--speakers`。
