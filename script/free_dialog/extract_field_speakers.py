# -*- coding: utf-8 -*-
"""CharacterDialogField GroupId -> 说话人（从 GL designlevel 场景 bundle 提取）
数据源: field-scenes-designlevel-field833 / field843 两个 bundle
判定规则（每实例只取一个确定说话人，没有老师参与，只有主角角色和互动角色）:
  1. targets   : FieldDialogBehavior(dialogGroupId@raw40) 的 targets PPtr 指向的 NPC（顺序=TargetIndex）
  2. parent    : 无 targets 时，触发器直接挂在某 NPC_* 物体下 -> 该 NPC
  3. name      : 触发器名自带角色（CH0070/Seia/Neru/susang 等）
  4. ambient   : 通用池(99xxx)/Common/BubbleTalk 环境气泡 -> 互动路人（随机）
  5. protagonist: 其余空 targets 触发器为活动主角独白 -> FieldDate 关联主角（833=阳奈, 843=圣亚/宁瑠）
"""
import UnityPy, json, struct, collections, re, os
from opencc import OpenCC
cc = OpenCC('tw2sp')

BUNDLES = [
    r"F:\data_collection\Blue-Archive-Asset-Downloader-2.3.0\Blue-Archive-Asset-Downloader-2.3.0\GL_RawData\Bundle\field-scenes-designlevel-field833-_mxload-2024-11-18_assets_all_1764168122.bundle",
    r"F:\data_collection\Blue-Archive-Asset-Downloader-2.3.0\Blue-Archive-Asset-Downloader-2.3.0\GL_RawData\Bundle\field-scenes-designlevel-field843-_mxload-2025-02-18_assets_all_3027871138.bundle",
]
TABLE  = r"F:\git\BA_Script_CN_Extract\raw\ba-data-global\Excel\CharacterDialogFieldExcelTable.json"
NAMETAB= r"F:\git\BA_Script_CN_Extract\raw\ba-data-global\DB\ScenarioCharacterNameExcelTable.json"
CHARTAB= r"F:\git\BA_Script_CN_Extract\raw\ba-data-global\DB\CharacterExcelTable.json"
ETCTAB = r"F:\git\BA_Script_CN_Extract\raw\ba-data-global\DB\LocalizeEtcExcelTable.json"
DATETAB= r"F:\git\BA_Script_CN_Extract\raw\ba-data-global\Excel\FieldDateExcelTable.json"
OUT    = r"F:\git\BA_Script_CN_Extract\result\free_dialog\free_dialog_speakers.json"

AMBIENT_TOKEN = 'Ambient_Random_NPC'

dialog = json.load(open(TABLE, encoding='utf-8-sig'))['DataList']
all_gids = collections.defaultdict(list)
for r in dialog:
    all_gids[r['GroupId']].append(r)

date_rows = json.load(open(DATETAB, encoding='utf-8-sig'))['DataList']
date_index = {
    (str(r.get('SeasonId')), str(r.get('UniqueId'))): r
    for r in date_rows
    if r.get('SeasonId') is not None and r.get('UniqueId') is not None
}

def max_target_count(gid: int, table: dict) -> int:
    """该 GroupId 在对话表中使用到的最大 TargetIndex + 1。"""
    rows = table.get(gid) or []
    return max((int(r.get('TargetIndex') or 0) for r in rows), default=0) + 1

# ---- 名称解析 ----
name_rows = json.load(open(NAMETAB, encoding='utf-8-sig'))['DataList']
spine2name, en2name = {}, {}
for r in name_rows:
    tw = r.get('NameTW') or ''
    sp = os.path.basename(r.get('SpinePrefabName') or '')
    if sp and sp not in spine2name and tw:
        spine2name[sp.replace('CharacterSpine_', '')] = tw
    en = r.get('NameEN') or ''
    if en and en not in en2name and tw:
        en2name[en] = tw
char_rows = json.load(open(CHARTAB, encoding='utf-8-sig'))['DataList']
etc_rows = json.load(open(ETCTAB, encoding='utf-8-sig'))['DataList']
etc = {r['Key']: r for r in etc_rows}
dev2name = {}
for r in char_rows:
    dev = r.get('DevName') or ''
    if re.fullmatch(r'CH\d{4}', dev) and dev not in dev2name:
        loc = etc.get(r.get('LocalizeEtcId'))
        if loc and loc.get('NameTw'):
            dev2name[dev] = loc['NameTw']

WEAPONS = {'SG': 'SG', 'SMG': 'SMG', 'SR': 'SR', 'HMG': 'HMG', 'AR': 'AR', 'GL': 'GL', 'RL': 'RL'}

def clean_token(tok):
    t = tok
    t = re.sub(r'\(.*?\)', '', t)                       # (MA)/(Doc:TrinityB) 等标注
    t = re.sub(r'_NoHalo$', '', t)
    t = re.sub(r'_(Field|Original|Weapon|NonWeapon|Watcher)$', '', t)
    t = re.sub(r'(_\d+)+$', '', t)                      # 实例编号（可叠加 _1v/_x2v 尾巴）
    t = re.sub(r'_(x\d+v|[a-z]\d?|\d+[a-z])$', '', t)
    t = re.sub(r'_+\d*$', '', t)
    t = re.sub(r'_(Field|Original|Weapon|NonWeapon)$', '', t)
    return t.strip('_')

def cn(tok):
    if tok == AMBIENT_TOKEN:
        return '互动路人'
    t = clean_token(tok)
    if t in ('Basic', 'Common', 'BubbleTalk', 'Location', 'Exception'):
        return None
    m = re.search(r'(?<![A-Za-z])(SG|SMG|SR|HMG|AR|GL|RL)(?![A-Za-z])', tok)
    wpn = f'({m.group(1)})' if m else ''
    rules = [
        ('Sukeban', f'飛車黨少女{wpn}'),
        ('Fuuki', f'風紀委員士兵{wpn}'),
        ('OnsenDev', f'溫泉開發部士兵{wpn}'),
        ('RedHelmet', f'紅盔士兵{wpn}'),
        ('Helmet', f'頭盔士兵{wpn}'),
        ('Millennium', '千年學生'), ('Millenium', '千年學生'),
        ('Trinity', '三一學生'),
        ('Justice', '實現正義部成員'),
        ('Soldier', '士兵'),
        ('RiosBot', '里奧斯機器人'),
        ('Cat', '貓'),
        ('PanPan', '潘潘'),
    ]
    # 按 _ 分词精确匹配，避免 'Location' 里的 'cat' 之类子串误判
    parts = [re.sub(r'\d+$', '', p).lower() for p in t.split('_')]
    for kw, name in rules:
        if kw.lower() in parts:
            return name
    m = re.search(r'(CH\d{4}|NP\d{4})', t)
    if m:
        code = m.group(1)
        if code in spine2name:
            return spine2name[code]
        if code in dev2name:
            return dev2name[code]
    # 纯英文名
    if t in en2name:
        return en2name[t]
    for part in t.split('_'):
        if part in en2name:
            return en2name[part]
    return t

def scan_bundle(path):
    env = UnityPy.load(path)
    objs = list(env.objects)
    by_pid = {o.path_id: o for o in objs}
    fdb_pids = {o.path_id for o in objs if o.type.name == 'MonoScript' and b'FieldDialogBehavior' in o.get_raw_data()}
    children = collections.defaultdict(list)
    go_of_tr, tr_of_go = {}, {}
    for o in objs:
        if o.type.name == 'Transform':
            try:
                tr = o.read()
            except Exception:
                continue
            go_of_tr[o.path_id] = tr.m_GameObject.path_id
            tr_of_go[tr.m_GameObject.path_id] = o.path_id
            children[tr.m_Father.path_id].append(o.path_id)
    def name_of_go(gp):
        g = by_pid.get(gp)
        if g is None:
            return None
        try:
            return g.read().m_Name
        except Exception:
            return None
    def scene_root(gp):
        cur = tr_of_go.get(gp); prev = None; guard = 0
        while cur is not None and guard < 300:
            guard += 1; prev = cur
            t = by_pid.get(cur)
            if t is None:
                break
            try:
                f = t.read().m_Father.path_id
            except Exception:
                break
            cur = f if f else None
        nm = name_of_go(go_of_tr.get(prev)) if prev is not None else '?'
        return (nm or '?').replace('Field_DesignLevel_', '')

    # FieldDate 关联主角（空 targets 的通用触发器为该角色的独白）
    def date_protagonist(gid):
        gs = str(gid)
        if not (gs.isdigit() and len(gs) >= 5):
            return None
        season, date_id = gs[:3], gs[:5]
        row = date_index.get((season, date_id))
        if row is None:
            same = [r for (s, d), r in date_index.items() if d == date_id]
            if len(same) == 1:
                row = same[0]
        if row is None:
            return None
        for field, prefix in (
            ('CharacterIconPath', 'Field_Student_Portrait_'),
            ('DateResultSpinePath', 'CharacterSpine_'),
        ):
            value = str(row.get(field) or '')
            if prefix in value:
                token = value.split(prefix, 1)[1].split('/', 1)[0]
                if token:
                    return token
        return None

    rows = []
    for o in objs:
        if o.type.name != 'MonoBehaviour':
            continue
        raw = o.get_raw_data()
        if len(raw) < 48 or struct.unpack('<q', raw[20:28])[0] not in fdb_pids:
            continue
        gid = struct.unpack('<q', raw[40:48])[0]
        go_pid = struct.unpack('<q', raw[4:12])[0]
        gname = name_of_go(go_pid) or '?'
        # targets: 扫描组件数据中指向 NPC_* GameObject 的本地 MonoBehaviour 引用（按偏移序）
        targets = []
        for base in range(48, min(len(raw) - 12, 200)):
            fid = struct.unpack('<i', raw[base:base+4])[0]
            pid = struct.unpack('<q', raw[base+4:base+12])[0]
            if fid != 0 or pid not in by_pid:
                continue
            t = by_pid[pid]
            if t.type.name != 'MonoBehaviour' or len(t.get_raw_data()) < 12:
                continue
            tgp = struct.unpack('<q', t.get_raw_data()[4:12])[0]
            tn = name_of_go(tgp)
            if tn and tn.startswith('NPC_'):
                targets.append(tn[4:])
        # 直接父节点（挂在某 NPC 物体下时该 NPC 即说话人）
        parent_name = None
        tr_pid = tr_of_go.get(go_pid)
        if tr_pid is not None:
            try:
                father = by_pid[tr_pid].read().m_Father.path_id
                pn = name_of_go(go_of_tr.get(father))
                if pn and pn.startswith('NPC_'):
                    parent_name = pn[4:]
            except Exception:
                pass
        # 触发器名中的角色标注
        name_hint = None
        m = re.match(r'^\d*_?DialogTrigger_(?:Basic_[\d_]+)?(.+)$', gname)
        if m and m.group(1) and not re.fullmatch(r'[\d_]+', m.group(1)):
            name_hint = m.group(1)
        is_ambient = ('Common' in gname or gname == 'BubbleTalk'
                      or re.search(r'990\d{4}|99901', str(gid)) is not None)
        rows.append({'gid': gid, 'scene': scene_root(go_pid), 'trigger': gname,
                     'targets': targets, 'parent_npc': parent_name,
                     'name_hint': name_hint, 'is_ambient': is_ambient,
                     'protagonist': None if is_ambient else date_protagonist(gid)})
    return rows

all_rows = []
for b in BUNDLES:
    rows = scan_bundle(b)
    print(os.path.basename(b)[:46], '->', len(rows), 'components')
    all_rows.extend(rows)

# ---- 每实例解析出唯一说话人 ----
# 触发器名中的角色标注白名单（en2name 之外的策划昵称）
NAME_HINT_EXTRA = {'susang', 'Zunko'}

def resolve_instance(r):
    """返回 (speakers, method)。每实例只取一个确定来源。"""
    if r['targets']:
        return list(r['targets']), 'targets'
    if r['parent_npc']:
        return [r['parent_npc']], 'parent'
    if r['is_ambient']:
        return [AMBIENT_TOKEN], 'ambient'
    if r['name_hint']:
        tokens = re.findall(r'CH\d{4}|NP\d{4}|[A-Za-z]+', r['name_hint'])
        tokens = [
            s for s in tokens
            if s not in ('DialogTrigger', 'Basic')
            and (s in en2name or s in NAME_HINT_EXTRA or re.fullmatch(r'(CH|NP)\d{4}', s))
        ]
        if tokens:
            return tokens, 'name'
    if r['protagonist']:
        return [r['protagonist']], 'protagonist'
    return [], 'unknown'

agg = collections.defaultdict(list)
for r in all_rows:
    speakers, method = resolve_instance(r)
    agg[r['gid']].append({**r, 'speakers': speakers, 'method': method})

out = {'meta': {
    'source_bundles': [os.path.basename(b) for b in BUNDLES],
    'dialog_groups_in_table': len(all_gids),
    'dialog_groups_found_in_scenes': sum(1 for g in agg if g in all_gids),
    'note': '每个实例只解析一个确定说话人：targets 精确 NPC(顺序=TargetIndex) > 父节点 NPC > '
            '触发器名标注 > 通用池/环境气泡(互动路人) > FieldDate 关联主角(活动主角独白)。'
            '没有老师参与；名称由 ScenarioCharacterName/CharacterExcel/LocalizeEtc 映射。'},
       'groups': {}}
for g in sorted(agg):
    insts = agg[g]
    is_pool = re.search(r'990\d{4}|99901', str(g)) is not None
    # 主角实例优先：同一 GroupId 在多处摆放且说话人不一致时，以活动主角独白为准
    insts_ordered = sorted(insts, key=lambda i: i['method'] != 'protagonist')
    by_idx: dict[str, str] = {}
    for i in insts_ordered:
        if i['targets']:
            for idx, s in enumerate(i['targets']):
                name = cc.convert(cn(s)) if cn(s) else None
                if name and str(idx) not in by_idx:
                    by_idx[str(idx)] = name
        elif i['speakers']:
            first = i['speakers'][0]
            name = '互动路人' if first == AMBIENT_TOKEN else (cc.convert(cn(first)) if cn(first) else None)
            if name:
                for idx in range(max_target_count(g, all_gids)):
                    if str(idx) not in by_idx:
                        by_idx[str(idx)] = name
    spk_cn = []
    for idx in sorted(by_idx, key=int):
        if by_idx[idx] not in spk_cn:
            spk_cn.append(by_idx[idx])
    if not spk_cn:
        for i in insts_ordered:
            for s in i['speakers']:
                name = '互动路人' if s == AMBIENT_TOKEN else (cc.convert(cn(s)) if cn(s) else None)
                if name and name not in spk_cn:
                    spk_cn.append(name)
    if is_pool:
        # 通用池语义为随机互动 NPC 的环境气泡，不逐一列举各摆放点的目标
        spk_cn = ['互动路人'] if spk_cn else []
        by_idx = {str(idx): '互动路人' for idx in range(max_target_count(g, all_gids))}
    out['groups'][str(g)] = {
        'in_table': g in all_gids,
        'speakers_cn': spk_cn if spk_cn else ['(未确定)'],
        'speaker_by_target_index': dict(sorted(by_idx.items())),
        'instances': [{'scene': i['scene'], 'trigger': i['trigger'], 'method': i['method'],
                       'speakers_raw': i['speakers']} for i in insts],
    }
json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

found = sum(1 for g in agg if g in all_gids)
unresolved = [g for g in sorted(set(agg) & set(all_gids))
              if out['groups'][str(g)]['speakers_cn'] == ['(未确定)']]
print(f'table gids: {len(all_gids)}, found: {found}, unresolved-speaker: {len(unresolved)}')
multi = [g for g in sorted(set(agg) & set(all_gids)) if len(out['groups'][str(g)]['speakers_cn']) > 1]
print('multi-speaker gids:', len(multi), multi[:10])
print('missing in scenes:', sorted(set(all_gids) - set(agg)))
print('scene-only gids:', sorted(set(agg) - set(all_gids)))
print('written:', OUT)
