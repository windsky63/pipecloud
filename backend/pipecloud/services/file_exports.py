from io import BytesIO
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile

import pandas as pd

from pipecloud.models import DataSourceFile, PlanRecord
from pipecloud.services.db_storage import (
    ARRIVAL_MODELS,
    INITIALIZATION_MATERIAL_MODELS,
    INITIALIZATION_MODELS,
    LIBRARY_MODELS,
    PLAN_FILE_MODELS,
    PRE_SCHEDULE_MODELS,
    dataframe_payload,
    table_payload,
)
from pipecloud.services.prefab_database import (
    derived_plan_file_payload,
    derived_plan_files_sheets,
    _plan_file_models,
)


SOURCE_GROUPS = {
    'initialization': ('initialization', '初始化数据'),
    'idf-material': ('idf-material', 'IDF解析材料'),
    'library': ('library', '库管理'),
    'arrival': ('arrival', '入库单'),
    'pre-schedule': ('pre-schedule', '中间结果'),
    'plan': ('plan', '排产计划'),
}

PLAN_NAMES = {
    'anti-corrosion': '防腐计划',
    'cutting': '下料计划',
    'welding': '焊接计划',
}


def _display_date(value):
    text = str(value or '').strip().replace('-', '')
    if len(text) == 8 and text.isdigit():
        return f'{text[:4]}-{text[4:6]}-{text[6:]}'
    return str(value or '').strip()


def _dated_file_name(file_name, plan_date):
    name = str(file_name or '')
    date_text = _display_date(plan_date)
    if not date_text:
        return name
    path = Path(name)
    return f'{path.stem}-{date_text}{path.suffix}'


def _safe_part(value, fallback='未命名'):
    text = str(value or '').strip()
    for character in '<>:"/\\|?*':
        text = text.replace(character, '_')
    return text.strip('. ') or fallback


def _source_models(source):
    if source.source_type == 'initialization':
        return INITIALIZATION_MODELS
    if source.source_type == 'idf-material':
        return INITIALIZATION_MATERIAL_MODELS
    if source.source_type == 'library':
        return LIBRARY_MODELS.get(source.source_key)
    if source.source_type == 'arrival':
        return ARRIVAL_MODELS
    if source.source_type == 'pre-schedule':
        return PRE_SCHEDULE_MODELS
    if source.source_type in {'plan', 'plan-stage'}:
        return _plan_file_models(source.display_name)
    return None


def _source_leaf(source):
    file_name = source.display_name or Path(source.relative_path or '').name or f'数据文件-{source.id}.xlsx'
    export_parts = [SOURCE_GROUPS[source.source_type][1]]
    display_name = file_name
    if source.source_type == 'plan':
        parts = str(source.source_key or '').split(':', 2)
        if len(parts) == 3:
            export_parts.extend([PLAN_NAMES.get(parts[0], parts[0]), parts[1]])
            if parts[0] in {'cutting', 'welding'}:
                display_name = _dated_file_name(file_name, parts[1])
    export_parts.append(file_name)
    return {
        'id': f'source:{source.id}',
        'type': 'file',
        'name': display_name,
        'sourceType': source.source_type,
        'path': source.relative_path,
        'sheets': list(source.sheet_names or []),
        'updatedAt': source.file_updated_at,
        'exportPath': '/'.join(_safe_part(part) for part in export_parts),
        '_source': source,
    }


def _derived_leaf(project, record, file_name):
    plan_name = PLAN_NAMES.get(record.plan_key, record.plan_name or record.plan_key)
    display_name = (
        _dated_file_name(file_name, record.plan_folder)
        if record.plan_key in {'cutting', 'welding'}
        else file_name
    )
    return {
        'id': f'derived:{record.id}:{file_name}',
        'type': 'file',
        'name': display_name,
        'sourceType': 'plan-derived',
        'path': f'database://plan-derived/{record.plan_key}/{record.plan_folder}/{file_name}',
        'sheets': [],
        'updatedAt': record.folder_updated_at,
        'exportPath': '/'.join([
            '排产计划',
            _safe_part(plan_name),
            _safe_part(record.plan_folder),
            _safe_part(file_name),
        ]),
        '_derived': {
            'project': project,
            'record': record,
            'file_name': file_name,
        },
    }


def _public_node(node):
    return {
        key: value
        for key, value in node.items()
        if not key.startswith('_') and key != 'exportPath'
    }


def build_project_file_tree(project):
    grouped = {key: [] for key, _ in SOURCE_GROUPS.values()}
    leaf_map = {}
    plan_source_keys = set()

    sources = (
        DataSourceFile.objects
        .filter(project=project, source_type__in=SOURCE_GROUPS)
        .order_by('source_type', 'source_key', 'display_name', 'id')
    )
    for source in sources:
        if _source_models(source) is None:
            continue
        leaf = _source_leaf(source)
        grouped[SOURCE_GROUPS[source.source_type][0]].append(leaf)
        leaf_map[leaf['id']] = leaf
        if source.source_type == 'plan':
            plan_source_keys.add(source.source_key)

    records = PlanRecord.objects.filter(project=project).order_by('plan_key', 'plan_folder', 'id')
    for record in records:
        for file_info in record.files or []:
            file_name = str(file_info.get('name') or '').strip()
            if not file_name:
                continue
            source_key = f'{record.plan_key}:{record.plan_folder}:{file_name}'
            if source_key in plan_source_keys:
                continue
            leaf = _derived_leaf(project, record, file_name)
            if leaf is None:
                continue
            grouped['plan'].append(leaf)
            leaf_map[leaf['id']] = leaf

    tree = []
    for source_type, (key, title) in SOURCE_GROUPS.items():
        leaves = grouped[key]
        if not leaves:
            continue
        if source_type != 'plan':
            children = [_public_node(leaf) for leaf in leaves]
        else:
            plan_groups = {}
            for leaf in leaves:
                parts = leaf['exportPath'].split('/')
                plan_name = parts[1] if len(parts) > 1 else '其他计划'
                plan_date = parts[2] if len(parts) > 2 else '未分类'
                plan_groups.setdefault(plan_name, {}).setdefault(plan_date, []).append(_public_node(leaf))
            children = [
                {
                    'id': f'folder:plan:{index}',
                    'type': 'folder',
                    'name': plan_name,
                    'children': [
                        {
                            'id': f'folder:plan:{index}:{date_index}',
                            'type': 'folder',
                            'name': _display_date(plan_date) or plan_date,
                            'children': plan_leaves,
                        }
                        for date_index, (plan_date, plan_leaves) in enumerate(plan_dates.items(), start=1)
                    ],
                }
                for index, (plan_name, plan_dates) in enumerate(plan_groups.items(), start=1)
            ]
        tree.append({
            'id': f'folder:{key}',
            'type': 'folder',
            'name': title,
            'children': children,
        })

    return tree, leaf_map


def _source_workbook(source):
    sheet_models = _source_models(source)
    workbook = {}
    for sheet_name in source.sheet_names or []:
        selected, _, _, columns, rows = table_payload(source, sheet_models, sheet_name)
        workbook[selected or sheet_name or 'Sheet1'] = (columns, rows)
    if not workbook:
        selected, _, _, columns, rows = table_payload(source, sheet_models, None)
        workbook[selected or 'Sheet1'] = (columns, rows)
    return workbook


def _leaf_workbook(leaf, prepared_workbook=None):
    if prepared_workbook is not None:
        return prepared_workbook
    source = leaf.get('_source')
    if source is not None:
        return _source_workbook(source)
    derived = leaf['_derived']
    record = derived['record']
    payload = derived_plan_file_payload(
        derived['project'],
        record.plan_key,
        record.plan_folder,
        derived['file_name'],
    )
    if payload is None:
        raise ValueError(f'无法生成派生文件：{derived["file_name"]}')
    return {
        payload.get('sheet') or 'Sheet1': (
            payload.get('columns') or [],
            payload.get('rows') or [],
        ),
    }


def _prepare_selected_derived_workbooks(selected, leaf_map, progress_callback=None):
    groups = {}
    for leaf_id in selected:
        leaf = leaf_map[leaf_id]
        derived = leaf.get('_derived')
        if derived is None:
            continue
        record = derived['record']
        key = (record.plan_key, record.plan_folder)
        groups.setdefault(key, {
            'project': derived['project'],
            'items': [],
        })['items'].append((leaf_id, derived['file_name']))

    prepared = {}
    group_items = list(groups.items())
    for group_index, ((plan_key, plan_folder), group) in enumerate(group_items, start=1):
        if progress_callback:
            progress_callback(
                5 + round((group_index - 1) / max(len(group_items), 1) * 40),
                f'正在准备派生文件（{group_index}/{len(group_items)}）',
            )
        items = group['items']
        files = derived_plan_files_sheets(
            group['project'],
            plan_key,
            plan_folder,
            [file_name for _, file_name in items],
        )
        for leaf_id, file_name in items:
            sheets = files.get(file_name)
            if sheets is None:
                raise ValueError(f'无法生成派生文件：{file_name}')
            workbook = {}
            for sheet_name, dataframe in sheets.items():
                payload = dataframe_payload(dataframe)
                workbook[sheet_name] = (payload['columns'], payload['rows'])
            prepared[leaf_id] = workbook
    if progress_callback and group_items:
        progress_callback(45, '派生文件数据准备完成')
    return prepared


def _workbook_bytes(workbook):
    output = BytesIO()
    used_names = set()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for index, (sheet_name, (columns, rows)) in enumerate(workbook.items(), start=1):
            safe_name = _safe_part(sheet_name, f'Sheet{index}')[:31]
            candidate = safe_name
            suffix = 2
            while candidate in used_names:
                suffix_text = f'-{suffix}'
                candidate = f'{safe_name[:31 - len(suffix_text)]}{suffix_text}'
                suffix += 1
            used_names.add(candidate)
            pd.DataFrame(rows, columns=columns).to_excel(writer, sheet_name=candidate, index=False)
    return output.getvalue()


def export_project_files(project, selected_ids, progress_callback=None):
    _, leaf_map = build_project_file_tree(project)
    if progress_callback:
        progress_callback(5, '文件清单校验完成')
    selected = list(dict.fromkeys(str(value) for value in selected_ids or []))
    if not selected:
        raise ValueError('请至少选择一个文件')
    missing = [value for value in selected if value not in leaf_map]
    if missing:
        raise ValueError('所选文件不存在或已失效，请刷新文件树')

    prepared_derived = _prepare_selected_derived_workbooks(
        selected,
        leaf_map,
        progress_callback=progress_callback,
    )
    output = BytesIO()
    used_paths = set()
    # XLSX 本身已经是 ZIP 容器，再次压缩收益很小但会显著增加 CPU 时间。
    with ZipFile(output, 'w', compression=ZIP_STORED) as archive:
        for file_index, leaf_id in enumerate(selected, start=1):
            leaf = leaf_map[leaf_id]
            if progress_callback:
                progress_callback(
                    45 + round((file_index - 1) / len(selected) * 50),
                    f'正在生成文件（{file_index}/{len(selected)}）',
                )
            path = leaf['exportPath']
            stem = path[:-5] if path.lower().endswith('.xlsx') else path
            candidate = f'{stem}.xlsx'
            suffix = 2
            while candidate in used_paths:
                candidate = f'{stem}-{suffix}.xlsx'
                suffix += 1
            used_paths.add(candidate)
            archive.writestr(
                candidate,
                _workbook_bytes(_leaf_workbook(leaf, prepared_derived.get(leaf_id))),
            )
    if progress_callback:
        progress_callback(98, '正在整理压缩包')
    output.seek(0)
    return output.getvalue()
