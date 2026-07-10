from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
import sys
import uuid

import pandas as pd
from django.db import transaction

from pipecloud.models import (
    ArrivalMaterialRow,
    DataSourceFile,
    FittingMaterialRow,
    MaterialMatchDetailRow,
    MasterScheduleRow,
    PipeMaterialRow,
    PlanRecord,
    ProjectSchedulePolicy,
    WeldingPlanRow,
    WeldLibraryRow,
    WeldPreScheduleRow,
    InitializationWeldRow,
    InitializationWeldExtraData,
)
from pipecloud.services.db_storage import (
    LIBRARY_MODELS,
    PLAN_FILE_MODELS,
    PRE_SCHEDULE_MODELS,
    dataframe_payload,
    initialization_rows_with_compatibility,
    model_field_labels,
    sync_dataframes,
    table_payload,
)
from pipecloud.services.project_constraints import project_process_sequence
from pipecloud.services.project_tables import ensure_project_tables, using_project_tables


BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
PREFAB_ROOT = BACKEND_DIR / 'prefab_schedule'
AUTO_WELD_DIR = PREFAB_ROOT / 'welding' / 'auto_weld_schedule'
INIT_AUTO_WELD_SPLIT_DIR = PREFAB_ROOT / 'initialization' / 'auto_weld_split'
for path in (PREFAB_ROOT, AUTO_WELD_DIR, INIT_AUTO_WELD_SPLIT_DIR, PREFAB_ROOT / 'cutting', PREFAB_ROOT / 'arrival'):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from arrival.material_library_maintenance import (
    ARRIVAL_DATE_COL,
    SOURCE_FILE_COL,
    STOCK_QTY_COL,
    PIPE_STOCK_QTY_COL,
    add_anti_corrosion_area,
    build_fitting_flange_material_library,
    build_pipe_material_library,
)
from initialization.weld_library_maintenance import (
    apply_completed_to_library,
    apply_extra_pipe_material_qty,
    apply_priority_to_library,
    build_unified_weld_library,
    ensure_priority_column,
)
from initialization.data_utils import filter_data, sort_grouped_pipelines
from initialization.init_config import (
    AUTO_WELD_FILTERS,
    COLUMNS as INIT_COLUMNS,
    PREFAB_WELD_FILTERS,
)
from initialization.auto_weld_split.link_process import process_all_groups
from initialization.auto_weld_split.link_result_filter import LinkResultFilter
from anti_corrosion.main import (
    build_anti_corrosion_commission_file_sheets,
    build_anti_corrosion_commission_from_pre_schedule,
    build_anti_corrosion_material_detail,
    build_anti_corrosion_material_summary,
    split_commission_files,
)
from anti_corrosion import pre_schedule_matcher as anti_pre_matcher
from cutting import weld_pre_schedule_matcher as pre_matcher
from cutting.cutting_config import MATCHED_STATUS, STATUS_COL
from welding.weld_config import COLUMNS, EXTRACT, get_weld_schedule_date
from extract_welds import (
    extract_welds_multiple_times,
    generate_schedule_order_no,
    generate_segment_list_for_sheet,
    sort_and_clean_data,
)
from generate_material_detail import _aggregate_pick_list, generate_material_details_for_sheet
import schedule as future_schedule


WELDING_PRIMARY_PLAN_FILE_NAME = '管段焊口表.xlsx'
WELDING_DERIVED_FILE_NAMES = {
    '管段清单.xlsx',
    '材料明细表.xlsx',
    '管子领料单.xlsx',
    '管件法兰领料单.xlsx',
}
CUTTING_DERIVED_FILE_NAMES = {'切管明细表.xlsx', '切管汇总表.xlsx'}
ANTI_CORROSION_DERIVED_FILE_NAMES = {'防腐材料汇总表.xlsx', '防腐材料明细表.xlsx'}
MASTER_DERIVED_FILE_NAME = '总排产计划.xlsx'
SEGMENT_LIST_COLUMNS = ['单元号', '管线号', '管段号', '管段总寸径']
CUTTING_DETAIL_COLUMNS = [
    '下料排产单号', '焊接排产单号', '下料日期', '焊接日期', '来源工作表', '材料侧', '材料唯一码',
    '材料代码', '材料代号', '设计切割长度', '单位', '材料油漆', '描述', COLUMNS['completed_flag'], '单元号',
    '管线号', '管段号', '初始焊口号', '最终焊口号', '寸径', '壁厚', '材质',
]
MATERIAL_DETAIL_COLUMNS = [
    '下料排产单号', '焊接排产单号', '下料日期', '焊接日期', '来源工作表', '材料侧', '材料唯一码',
    '设计数量', '需领料数量', '材料代码', '材料代号', '设计切割长度', '单位', '材料油漆', '描述',
    COLUMNS['completed_flag'], '单元号', '管线号', '管段号', '初始焊口号', '最终焊口号', '寸径', '壁厚', '材质',
]
PICK_LIST_COLUMNS = ['材料代码', '材料油漆', '材料代号', '单位', '描述', '设计数量', '需领料数量', '管线号', '管段号']
MASTER_SCHEDULE_COLUMNS = ['下料日期', '焊接日期', '焊接排产单号', '抽取次数', '焊口数量', '直径总和', '目标值', '下料完成要求']
WELDING_PLAN_FILE_NAMES = [
    WELDING_PRIMARY_PLAN_FILE_NAME,
    *sorted(WELDING_DERIVED_FILE_NAMES),
]
CUTTING_PLAN_FILE_NAMES = sorted(CUTTING_DERIVED_FILE_NAMES)


PLAN_STAGE_FIELDS = {
    'anti-corrosion': 'anti_corrosion_date',
    'cutting': 'cut_date',
    'welding': 'weld_date',
}

STAGED_PLAN_WORKBOOKS = {}
ANTI_CORROSION_COMMISSION_COLUMNS = [
    '防腐委托单号',
    '委托日期',
    '预排产序号',
    '防腐面积',
    '库序号',
    '单元号',
    '单元名称',
    '管线号',
    '管段号',
    '接头类型',
    '壁厚',
    '壁厚号',
    '寸径',
    '外径',
    '焊接区域',
    '材质',
    '材质代号',
    '初始焊口号',
    '最终焊口号',
    '材料代号1',
    '材料代号2',
    '材料唯一码1',
    '材料唯一码2',
    '材料代码1',
    '材料代码2',
    '材料油漆1',
    '材料油漆2',
    '数量1',
    '数量2',
    '描述1',
    '描述2',
    '焊接方式',
    '材料到货状态',
    '材料防腐状态',
    '材料下料状态',
    '材料焊接状态',
    '优先级',
    '预排产状态',
    '不可预排产原因',
]
MASTER_COMMON_STAGE_COLUMNS = {
    '库序号',
    '来源工作表',
    '单元号',
    '管线号',
    '管段号',
    '初始焊口号',
    '最终焊口号',
    '寸径',
    '壁厚',
    '材质',
    '优先级',
    '材料到货状态',
    '材料防腐状态',
    '材料下料状态',
    '材料焊接状态',
    '是否完成',
    COLUMNS['unit'],
    COLUMNS['pipeline'],
    COLUMNS['segment_no'],
    COLUMNS['weld_no_start'],
    COLUMNS['weld_no_final'],
    COLUMNS['diameter'],
    COLUMNS['thickness'],
    COLUMNS['material'],
    COLUMNS['completed_flag'],
    COLUMNS['material_arrival_status'],
    COLUMNS['material_anti_corrosion_status'],
    COLUMNS['material_cutting_status'],
}
ANTI_CORROSION_STAGE_COLUMNS = {'防腐面积', '材料油漆', '材料油漆1', '材料油漆2'}


def _model_dataframe(model, project, **filters):
    labels = model_field_labels(model)
    rows = []
    queryset = model.objects.filter(project=project, **filters).order_by('source_file_id', 'sheet_name', 'row_index')
    if model is InitializationWeldRow:
        queryset = queryset.select_related('extra_data')
    for item in queryset:
        row = {label: getattr(item, field_name, '') for field_name, label in labels.items()}
        if model is InitializationWeldRow:
            try:
                row.update(item.extra_data.custom_fields or {})
            except InitializationWeldExtraData.DoesNotExist:
                pass
        rows.append(row)
    if model is InitializationWeldRow:
        rows = initialization_rows_with_compatibility(rows)
        columns = list(dict.fromkeys(
            column
            for row in rows
            for column in row
        ))
        return pd.DataFrame(rows, columns=columns)
    return pd.DataFrame(rows, columns=list(labels.values()))


def _arrival_material_dataframe(project):
    labels = model_field_labels(ArrivalMaterialRow)
    rows = []
    queryset = (
        ArrivalMaterialRow.objects
        .filter(project=project)
        .select_related('source_file')
        .order_by('source_file_id', 'sheet_name', 'row_index')
    )
    for item in queryset:
        row = {label: getattr(item, field_name, '') for field_name, label in labels.items()}
        source_name = item.source_file.display_name if item.source_file_id else ''
        row[SOURCE_FILE_COL] = source_name
        row[ARRIVAL_DATE_COL] = Path(source_name).stem if source_name else ''
        rows.append(row)
    return pd.DataFrame(rows, columns=[*list(labels.values()), SOURCE_FILE_COL, ARRIVAL_DATE_COL])


def _source_dataframe(project, source_type, source_key, model, sheet_name=None):
    source = DataSourceFile.objects.filter(
        project=project,
        source_type=source_type,
        source_key=source_key,
    ).order_by('-file_updated_at', '-id').first()
    if source is None:
        return pd.DataFrame(columns=list(model_field_labels(model).values())), None, ''
    selected_sheet, _, _, columns, rows = table_payload(source, {'*': model}, sheet_name)
    return pd.DataFrame(rows, columns=columns), source, selected_sheet


def _sync_library_dataframe(project, source_key, display_name, dataframe):
    source = sync_dataframes(
        project,
        'library',
        source_key,
        display_name,
        f'database://library/{source_key}/{display_name}',
        {'Sheet1': dataframe},
        LIBRARY_MODELS[source_key],
    )
    model = LIBRARY_MODELS[source_key].get('Sheet1') or LIBRARY_MODELS[source_key].get('*')
    source.sheet_columns = {
        'Sheet1': list(model_field_labels(model).values()),
    }
    source.save(update_fields=['sheet_columns'])
    return source


def _coerce_filter_columns(dataframe, filters):
    out = dataframe.copy()
    for column, condition in filters.items():
        if column not in out.columns:
            continue
        if isinstance(condition, tuple) and len(condition) == 3 and condition[0] == 'between':
            out[column] = pd.to_numeric(out[column], errors='coerce')
    return out


def _drop_empty_segment_no(dataframe):
    segment_no_col = INIT_COLUMNS['segment_no']
    if dataframe is None or dataframe.empty or segment_no_col not in dataframe.columns:
        return dataframe
    mask = dataframe[segment_no_col].notna() & dataframe[segment_no_col].astype(str).str.strip().ne('')
    return dataframe.loc[mask].copy()


def _text_value(value):
    text = str(value or '').strip()
    return '' if text.lower() == 'nan' else text


def _row_first(row, *columns):
    for column in columns:
        if column in row:
            value = _text_value(row.get(column, ''))
            if value:
                return value
    return ''


def _date_value(value):
    return _text_value(value).replace('-', '')[:8]


def _stage_payload_for_row(row, plan_key):
    if plan_key == 'anti-corrosion':
        allowed = ANTI_CORROSION_STAGE_COLUMNS
    else:
        allowed = None
    payload = {}
    for key, value in row.items():
        text_key = str(key)
        if text_key.startswith('_') or text_key in MASTER_COMMON_STAGE_COLUMNS:
            continue
        if allowed is not None and text_key not in allowed:
            continue
        payload[text_key] = _text_value(value)
    return {plan_key: payload}


def _master_defaults_from_row(row, plan_key, plan_date):
    defaults = {
        'source_sheet': _row_first(row, future_schedule.SOURCE_SHEET_COL, '_source_sheet_name'),
        'priority': _row_first(row, '优先级'),
        'material_arrival_status': _row_first(row, COLUMNS['material_arrival_status'], '材料到货状态', '到货状态'),
        'material_anti_corrosion_status': _row_first(row, COLUMNS['material_anti_corrosion_status'], '材料防腐状态', '防腐状态'),
        'material_cutting_status': _row_first(row, COLUMNS['material_cutting_status'], '材料下料状态', '下料状态'),
        'unit': _row_first(row, COLUMNS['unit']),
        'pipeline': _row_first(row, COLUMNS['pipeline']),
        'segment_no': _row_first(row, COLUMNS['segment_no']),
        'weld_no_start': _row_first(row, COLUMNS['weld_no_start']),
        'weld_no_final': _row_first(row, COLUMNS['weld_no_final']),
        'diameter': _row_first(row, COLUMNS['diameter']),
        'wall_thickness': _row_first(row, COLUMNS['thickness']),
        'material': _row_first(row, COLUMNS['material']),
        'completed_flag': _row_first(row, COLUMNS['completed_flag'], '是否完成'),
    }
    if plan_key == 'anti-corrosion':
        defaults.update({
            'anti_corrosion_order_no': _row_first(row, '防腐委托单号'),
            'anti_corrosion_date': _date_value(_row_first(row, '委托日期') or plan_date),
        })
    if plan_key == 'cutting':
        defaults.update({
            'cut_order_no': _row_first(row, future_schedule.CUT_ORDER_NO_COL),
            'cut_date': _date_value(_row_first(row, future_schedule.CUT_DATE_COL) or plan_date),
        })
    if plan_key == 'welding':
        defaults.update({
            'cut_order_no': _row_first(row, future_schedule.CUT_ORDER_NO_COL),
            'cut_date': _date_value(_row_first(row, future_schedule.CUT_DATE_COL)),
            'weld_order_no': _row_first(row, future_schedule.WELD_ORDER_NO_COL),
            'weld_date': _date_value(_row_first(row, future_schedule.WELD_DATE_COL) or plan_date),
        })
    stage_payload = _stage_payload_for_row(row, plan_key)
    defaults['stage_payload'] = stage_payload
    return defaults


def _merge_master_defaults(existing, defaults):
    merged = {}
    for key, value in defaults.items():
        if key == 'stage_payload':
            payload = dict(existing.stage_payload or {})
            payload.update(value or {})
            merged[key] = payload
            continue
        current = getattr(existing, key, '')
        merged[key] = value if value not in (None, '') else current
    return merged


def _sync_master_schedule_rows(project, plan_key, plan_date, dataframe):
    if dataframe is None or dataframe.empty or '库序号' not in dataframe.columns:
        return 0
    process_sequence = project_process_sequence(project)
    start_stage = 'anti-corrosion' if process_sequence == 'coating_before_welding' else 'cutting'
    updated = 0
    for _, source_row in dataframe.fillna('').iterrows():
        row = source_row.to_dict()
        row['_project'] = project
        library_seq = _row_first(row, '库序号')
        if not library_seq:
            continue
        defaults = _master_defaults_from_row(row, plan_key, str(plan_date or ''))
        if plan_key == start_stage:
            defaults['production_start_stage'] = plan_key
            defaults['production_start_date'] = defaults.get(PLAN_STAGE_FIELDS[plan_key], '')
        record = MasterScheduleRow.objects.filter(project=project, library_seq=library_seq).first()
        if record is None:
            MasterScheduleRow.objects.create(project=project, library_seq=library_seq, **defaults)
        else:
            merged = _merge_master_defaults(record, defaults)
            if not record.production_start_stage and plan_key == start_stage:
                merged['production_start_stage'] = plan_key
                merged['production_start_date'] = defaults.get(PLAN_STAGE_FIELDS[plan_key], '')
            for field_name, value in merged.items():
                setattr(record, field_name, value)
            record.save(update_fields=[*merged.keys(), 'updated_at'])
        updated += 1
    return updated


def _planned_library_seqs(project, required_field, missing_field=None):
    queryset = MasterScheduleRow.objects.filter(project=project).exclude(**{required_field: ''})
    if missing_field:
        queryset = queryset.filter(**{missing_field: ''})
    return set(queryset.values_list('library_seq', flat=True))


def _filter_dataframe_to_library_seqs(dataframe, library_seqs):
    if dataframe.empty or not library_seqs or '库序号' not in dataframe.columns:
        return dataframe.iloc[0:0].copy()
    return dataframe.loc[dataframe['库序号'].fillna('').astype(str).str.strip().isin(library_seqs)].copy()


def delete_plan_stage(project, plan_key, plan_folder):
    stage_date_field = PLAN_STAGE_FIELDS[plan_key]
    affected_seqs = set(
        MasterScheduleRow.objects
        .filter(project=project, **{stage_date_field: plan_folder})
        .values_list('library_seq', flat=True)
    )
    deleted_sources, _ = DataSourceFile.objects.filter(
        project=project,
        source_type='plan',
        source_key__startswith=f'{plan_key}:{plan_folder}:',
    ).delete()
    deleted_records, _ = PlanRecord.objects.filter(
        project=project,
        plan_key=plan_key,
        plan_folder=plan_folder,
    ).delete()

    cleared_master_rows = 0
    deleted_master_rows = 0
    stage_payload_key = plan_key
    clear_fields = {
        'anti-corrosion': [
            'anti_corrosion_order_no',
            'anti_corrosion_date',
        ],
        'cutting': [
            'cut_order_no',
            'cut_date',
        ],
        'welding': [
            'weld_order_no',
            'weld_date',
        ],
    }[plan_key]
    for row in MasterScheduleRow.objects.filter(project=project, library_seq__in=affected_seqs):
        for field_name in clear_fields:
            setattr(row, field_name, '')
        payload = dict(row.stage_payload or {})
        payload.pop(stage_payload_key, None)
        row.stage_payload = payload
        if row.production_start_stage == plan_key:
            row.production_start_stage = ''
            row.production_start_date = ''
        has_any_stage = any([
            row.anti_corrosion_date,
            row.cut_date,
            row.weld_date,
        ])
        if has_any_stage:
            row.save(update_fields=[*clear_fields, 'stage_payload', 'production_start_stage', 'production_start_date', 'updated_at'])
            cleared_master_rows += 1
        else:
            row.delete()
            deleted_master_rows += 1
    return {
        'librarySeqs': sorted(affected_seqs),
        'planFolders': {plan_key: [plan_folder]},
        'deletedSources': deleted_sources,
        'deletedRecords': deleted_records,
        'clearedMasterRows': cleared_master_rows,
        'deletedMasterRows': deleted_master_rows,
    }


def _link_division_dataframe(results):
    rows = []
    for result in results or []:
        if result['division']:
            if result['division_type'] == '直接符合':
                division_display = result['shape_sequence']
                detailed_display = result['shape_sequence']
                if 'matched_pattern' in result:
                    detailed_display = f"{detailed_display} [匹配模式: {result['matched_pattern']}]"
            else:
                division_parts = []
                detailed_parts = []
                for sub_path in result['sub_paths']:
                    division_parts.append(sub_path['sub_sequence'])
                    sub_match_info = f"[匹配: {sub_path['matched_pattern']}]" if 'matched_pattern' in sub_path else ''
                    detailed_parts.append(
                        f"{sub_path['sub_sequence']}({'->'.join(sub_path['sub_path'])}){sub_match_info}"
                    )
                division_display = ' -> '.join(division_parts)
                detailed_display = ' ; '.join(detailed_parts)
        else:
            division_display = '无法划分'
            detailed_display = ''

        rows.append({
            '组名称': result['group'],
            '链路序号': result['path_index'],
            '原始链路序号': result.get('original_path_index', ''),
            '切分序号': result.get('split_index', ''),
            '切分原因': result.get('split_by', '无'),
            '是否切分': '是' if result.get('was_split', False) else '否',
            '链路类型': result.get('path_type', ''),
            '链路路径': result['path'],
            '节点数': len(result['path_nodes']),
            '形状序列': result['shape_sequence'],
            '形状序列长度': len(result['shape_sequence'].split('-')),
            'P总长度': result.get('total_p_length', 0),
            'P长度限制': result.get('p_length_limit', 12),
            '划分结果': division_display,
            '详细划分': detailed_display,
            '状态': result['division_type'],
            '匹配模式': result.get('matched_pattern', '') if result.get('is_valid') else '',
            '舍弃节点数': len(result.get('discarded_nodes', [])),
            '舍弃节点索引': ','.join(map(str, result.get('discarded_nodes', []))) if result.get('discarded_nodes') else '',
            '有效子路径数': len(result.get('sub_paths', [])),
        })
    return pd.DataFrame(rows)


def _auto_weld_dataframe(auto_filter_df):
    if auto_filter_df is None or auto_filter_df.empty:
        return pd.DataFrame(columns=list(auto_filter_df.columns) if auto_filter_df is not None else [])

    sorted_auto_df, _, _ = sort_grouped_pipelines(auto_filter_df)
    if sorted_auto_df is None or sorted_auto_df.empty:
        return pd.DataFrame(columns=list(auto_filter_df.columns))

    link_results = process_all_groups(sorted_auto_df)
    link_df = _link_division_dataframe(link_results)
    if link_df.empty:
        return pd.DataFrame(columns=list(sorted_auto_df.columns))

    filter_tool = LinkResultFilter('', '')
    filter_tool.link_results_df = link_df
    filter_tool.filtered_data_df = sorted_auto_df
    filter_tool.analyze_link_results()
    filtered_df = filter_tool.filter_weld_data()
    return filtered_df if filtered_df is not None else pd.DataFrame(columns=list(sorted_auto_df.columns))


def _sync_plan_record(project, plan_key, plan_name, plan_date, file_names, summary=None):
    now_ts = datetime.now().timestamp()
    folder_names = {
        'anti-corrosion': '防腐委托单',
        'cutting': '下料排产单',
        'welding': '焊接排产单',
    }
    folder_name = folder_names.get(plan_key, f'{plan_name}排产单')
    files = [
        {
            'name': file_name,
            'path': f'{folder_name}/{plan_date}/{file_name}',
            'size': 0,
            'updatedAt': now_ts,
        }
        for file_name in file_names
    ]
    record, _ = PlanRecord.objects.update_or_create(
        project=project,
        plan_key=plan_key,
        plan_folder=plan_date,
        defaults={
            'plan_name': plan_name,
            'plan_date': plan_date,
            'relative_path': f'database://plan/{plan_key}/{plan_date}',
            'file_count': len(file_names),
            'folder_updated_at': now_ts,
            'files': files,
            'summary': summary or {},
        },
    )
    return record


def _schedule_plan_summary(plan_key, plan_date, all_extractions):
    order_numbers = []
    related_order_numbers = []
    weld_count = 0
    diameter_total = 0.0
    for extraction in all_extractions:
        info = extraction.get('info') or {}
        extraction_data = extraction.get('data')
        extraction_row_count = len(extraction_data) if extraction_data is not None else 0
        sheet_name = str(info.get('抽取次数') or '').strip()
        weld_order_no = str(info.get('排产单号') or '').strip()
        if plan_key == 'cutting':
            order_no = f'QG-{plan_date}-{sheet_name}' if sheet_name else ''
            if weld_order_no:
                related_order_numbers.append(weld_order_no)
        else:
            order_no = weld_order_no
        if order_no:
            order_numbers.append(order_no)
        weld_count += int(info.get('焊口数量') or extraction_row_count)
        diameter_total += float(info.get('直径总和') or 0)
    return {
        'orderNumbers': list(dict.fromkeys(order_numbers)),
        'relatedOrderNumbers': list(dict.fromkeys(related_order_numbers)),
        'orderCount': len(set(order_numbers)),
        'weldCount': weld_count,
        'diameterTotal': round(diameter_total, 3),
    }


def backfill_plan_record_summaries(project):
    ensure_project_tables(project)
    updated = 0
    with using_project_tables(project):
        records = list(
            PlanRecord.objects
            .filter(project=project, plan_key__in=['cutting', 'welding'])
        )
        for record in records:
            date_field = 'cut_date' if record.plan_key == 'cutting' else 'weld_date'
            rows = list(
                WeldingPlanRow.objects
                .filter(project=project, **{date_field: record.plan_date})
                .values('cut_order_no', 'weld_order_no', 'diameter')
            )
            if not rows:
                continue
            order_field = 'cut_order_no' if record.plan_key == 'cutting' else 'weld_order_no'
            order_numbers = list(dict.fromkeys(
                str(row.get(order_field) or '').strip()
                for row in rows
                if str(row.get(order_field) or '').strip()
            ))
            related_order_numbers = []
            if record.plan_key == 'cutting':
                related_order_numbers = list(dict.fromkeys(
                    str(row.get('weld_order_no') or '').strip()
                    for row in rows
                    if str(row.get('weld_order_no') or '').strip()
                ))
            diameter_total = sum(
                float(pd.to_numeric(row.get('diameter'), errors='coerce') or 0)
                for row in rows
                if pd.notna(pd.to_numeric(row.get('diameter'), errors='coerce'))
            )
            record.summary = {
                'orderNumbers': order_numbers,
                'relatedOrderNumbers': related_order_numbers,
                'orderCount': len(order_numbers),
                'weldCount': len(rows),
                'diameterTotal': round(diameter_total, 3),
            }
            record.save(update_fields=['summary', 'updated_at'])
            updated += 1
    return updated


def _plan_source_path(plan_key, plan_date, file_name):
    folder_names = {
        'cutting': '下料排产单',
        'welding': '焊接排产单',
        'anti-corrosion': '防腐委托单',
    }
    return f'database://plan/{folder_names.get(plan_key, plan_key)}/{plan_date}/{file_name}'


def _plan_stage_source_path(stage_token, plan_key, plan_date, file_name):
    folder_names = {
        'cutting': '下料排产单',
        'welding': '焊接排产单',
        'anti-corrosion': '防腐委托单',
    }
    return f'database://plan-stage/{stage_token}/{folder_names.get(plan_key, plan_key)}/{plan_date}/{file_name}'


def _parse_stage_source_key(source_key):
    parts = str(source_key or '').split(':', 3)
    if len(parts) != 4:
        return None
    stage_token, plan_key, plan_date, file_name = parts
    if not stage_token or not plan_key or not plan_date or not file_name:
        return None
    return stage_token, plan_key, plan_date, file_name


def _plan_file_models(file_name):
    models = PLAN_FILE_MODELS.get(file_name)
    if models is not None:
        return models
    return None


def _is_anti_corrosion_commission_file(file_name):
    text = str(file_name or '')
    return text == '防腐委托单.xlsx' or (text.startswith('防腐委托单-') and text.endswith('.xlsx'))


def _workbook_frames(workbook_payload):
    return [
        dataframe
        for dataframe in (workbook_payload or {}).values()
        if dataframe is not None and not dataframe.empty
    ]


def staged_plan_workbook_payload(source_key):
    return STAGED_PLAN_WORKBOOKS.get(source_key) or {}


def _anti_corrosion_commission_dataframe_from_master(project, plan_folder=None, file_name=None):
    queryset = MasterScheduleRow.objects.filter(project=project).exclude(anti_corrosion_date='')
    if plan_folder:
        queryset = queryset.filter(anti_corrosion_date=str(plan_folder))
    rows = []
    for record in queryset.order_by('anti_corrosion_date', 'anti_corrosion_order_no', 'library_seq'):
        payload = dict((record.stage_payload or {}).get('anti-corrosion') or {})
        if not payload:
            payload = {}
        if file_name and file_name != '防腐委托单.xlsx':
            expected = f"{payload.get('防腐委托单号') or record.anti_corrosion_order_no}.xlsx"
            legacy_expected = f"防腐委托单-{payload.get('防腐委托单号') or record.anti_corrosion_order_no}.xlsx"
            if expected != file_name and legacy_expected != file_name:
                continue
        row = {column: payload.get(column, '') for column in ANTI_CORROSION_COMMISSION_COLUMNS}
        row['防腐委托单号'] = row.get('防腐委托单号') or record.anti_corrosion_order_no
        row['委托日期'] = row.get('委托日期') or record.anti_corrosion_date
        row['库序号'] = row.get('库序号') or record.library_seq
        row['单元号'] = row.get('单元号') or record.unit
        row['管线号'] = row.get('管线号') or record.pipeline
        row['管段号'] = row.get('管段号') or record.segment_no
        row['初始焊口号'] = row.get('初始焊口号') or record.weld_no_start
        row['最终焊口号'] = row.get('最终焊口号') or record.weld_no_final
        row['寸径'] = row.get('寸径') or record.diameter
        row['壁厚'] = row.get('壁厚') or record.wall_thickness
        row['材质'] = row.get('材质') or record.material
        row['优先级'] = row.get('优先级') or record.priority
        row['材料到货状态'] = row.get('材料到货状态') or record.material_arrival_status
        row['材料防腐状态'] = row.get('材料防腐状态') or record.material_anti_corrosion_status
        row['材料下料状态'] = row.get('材料下料状态') or record.material_cutting_status
        row['材料焊接状态'] = row.get('材料焊接状态') or record.completed_flag
        rows.append(row)
    columns = list(dict.fromkeys([
        *ANTI_CORROSION_COMMISSION_COLUMNS,
        *[column for row in rows for column in row.keys()],
    ]))
    return pd.DataFrame(rows, columns=columns)


def _sync_plan_output_files(project, output_files):
    record_groups = {}
    for output_file in output_files:
        file_name = output_file['file_name']
        plan_key = output_file['plan_key']
        plan_date = output_file['plan_date']
        sheet_models = _plan_file_models(file_name)
        if sheet_models is None:
            if plan_key != 'anti-corrosion' or not _is_anti_corrosion_commission_file(file_name):
                raise ValueError(f'{file_name} 是由管段焊口表派生的计划文件，不再单独写入数据库')
        else:
            sync_dataframes(
                project,
                'plan',
                f'{plan_key}:{plan_date}:{file_name}',
                file_name,
                _plan_source_path(plan_key, plan_date, file_name),
                output_file['sheets'] or {'Sheet1': pd.DataFrame()},
                sheet_models,
            )
        if plan_key in {'anti-corrosion', 'welding'}:
            frames = _workbook_frames(output_file.get('sheets'))
            if frames:
                _sync_master_schedule_rows(project, plan_key, plan_date, pd.concat(frames, ignore_index=True, sort=False))
        if output_file.get('record', True):
            record_key = (plan_key, output_file['plan_name'], plan_date)
            record_groups.setdefault(record_key, []).append(file_name)
            if plan_key == 'anti-corrosion':
                record_groups[record_key].extend(sorted(ANTI_CORROSION_DERIVED_FILE_NAMES))

    for (plan_key, plan_name, plan_date), file_names in record_groups.items():
        _sync_plan_record(project, plan_key, plan_name, plan_date, list(dict.fromkeys(file_names)))


def _source_to_dataframe(source, sheet_models, sheet_name=None):
    sheet_names = source.sheet_names or []
    selected_names = [sheet_name] if sheet_name else sheet_names
    frames = []
    for current_sheet in selected_names:
        selected_sheet, _, _, columns, rows = table_payload(source, sheet_models, current_sheet)
        if not selected_sheet:
            continue
        frame = pd.DataFrame(rows, columns=columns)
        if not frame.empty:
            frame['_source_sheet_name'] = selected_sheet
            frame['_source_path'] = source.relative_path
        frames.append(frame)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _welding_plan_sources(project, plan_folder=None):
    queryset = DataSourceFile.objects.filter(
        project=project,
        source_type='plan',
        display_name=WELDING_PRIMARY_PLAN_FILE_NAME,
        source_key__startswith='welding:',
    )
    if plan_folder:
        queryset = queryset.filter(source_key=f'welding:{plan_folder}:{WELDING_PRIMARY_PLAN_FILE_NAME}')
    return queryset.order_by('source_key', 'id')


def _welding_plan_dataframe(project, plan_folder=None, cut_date=None):
    labels = model_field_labels(WeldingPlanRow)
    field_names = list(labels.keys())
    queryset = WeldingPlanRow.objects.filter(
        project=project,
        source_file__source_type='plan',
        source_file__display_name=WELDING_PRIMARY_PLAN_FILE_NAME,
        source_file__source_key__startswith='welding:',
    )
    if plan_folder:
        queryset = queryset.filter(
            source_file__source_key=f'welding:{plan_folder}:{WELDING_PRIMARY_PLAN_FILE_NAME}'
        )
    if cut_date:
        queryset = queryset.filter(cut_date=str(cut_date))
    queryset = queryset.order_by('source_file_id', 'sheet_name', 'row_index')
    rows = [
        {labels[field_name]: row.get(field_name, '') for field_name in field_names}
        for row in queryset.values(*field_names)
    ]
    return pd.DataFrame(rows, columns=list(labels.values()))


def _anti_corrosion_commission_dataframe(project, plan_folder=None):
    return _anti_corrosion_commission_dataframe_from_master(project, plan_folder=plan_folder)


def _anti_corrosion_match_detail_dataframe(project):
    labels = model_field_labels(MaterialMatchDetailRow)
    field_names = list(labels.keys())
    queryset = MaterialMatchDetailRow.objects.filter(
        project=project,
        source_file__source_type='pre-schedule',
        source_file__source_key='material-locking',
        sheet_name='材料匹配明细',
    ).order_by('source_file_id', 'sheet_name', 'row_index')
    rows = [
        {labels[field_name]: row.get(field_name, '') for field_name in field_names}
        for row in queryset.values(*field_names)
    ]
    return pd.DataFrame(rows, columns=list(labels.values()))


def _sheet_name_for_plan_row(row):
    for column in (future_schedule.SOURCE_SHEET_COL, '_source_sheet_name', future_schedule.WELD_ORDER_NO_COL):
        value = row.get(column, '')
        text = str(value or '').strip()
        if text:
            return text[:31]
    return 'Sheet1'


def _split_joined_values(value):
    text = str(value or '').strip()
    if not text or text.lower() == 'nan':
        return []
    return [item.strip() for item in text.replace(',', '、').split('、') if item.strip()]


def _row_material_items(row):
    side_columns = ('材料唯一码', '材料代码', '材料代号', '数量', '单位', '材料油漆', '描述')
    if any(str(row.get(f'{column}{side}', '') or '').strip() for side in (1, 2) for column in side_columns):
        for side in (1, 2):
            yield {
                'side': str(side),
                'unique': row.get(f'材料唯一码{side}', ''),
                'code': row.get(f'材料代码{side}', ''),
                'mark': row.get(f'材料代号{side}', ''),
                'qty': row.get(f'数量{side}', ''),
                'unit': row.get(f'单位{side}', ''),
                'paint': row.get(f'材料油漆{side}', ''),
                'description': row.get(f'描述{side}', ''),
            }
        return

    sides = _split_joined_values(row.get('材料侧', ''))
    uniques = _split_joined_values(row.get('材料唯一码', ''))
    codes = _split_joined_values(row.get('材料代码', ''))
    marks = _split_joined_values(row.get('材料代号', ''))
    lengths = _split_joined_values(row.get('设计切割长度', ''))
    units = _split_joined_values(row.get('单位', ''))
    paints = _split_joined_values(row.get('材料油漆', ''))
    descriptions = _split_joined_values(row.get('描述', ''))
    count = max(len(sides), len(uniques), len(codes), len(marks), len(lengths), len(units), len(paints), len(descriptions), 1)
    for index in range(count):
        yield {
            'side': sides[index] if index < len(sides) else '',
            'unique': uniques[index] if index < len(uniques) else '',
            'code': codes[index] if index < len(codes) else '',
            'mark': marks[index] if index < len(marks) else '',
            'qty': lengths[index] if index < len(lengths) else '',
            'unit': units[index] if index < len(units) else '',
            'paint': paints[index] if index < len(paints) else '',
            'description': descriptions[index] if index < len(descriptions) else '',
        }


def _welding_plan_sheet_map(dataframe):
    if dataframe.empty:
        return {'Sheet1': dataframe}
    sheets = {}
    for _, row in dataframe.iterrows():
        sheet_name = _sheet_name_for_plan_row(row)
        sheets.setdefault(sheet_name, []).append(row.to_dict())
    return {sheet: pd.DataFrame(rows).drop(columns=[col for col in ('_source_sheet_name', '_source_path') if col in pd.DataFrame(rows).columns]) for sheet, rows in sheets.items()}


def _segment_list_sheets(welding_df):
    sheets = {}
    columns = SEGMENT_LIST_COLUMNS
    for sheet_name, frame in _welding_plan_sheet_map(welding_df).items():
        if frame.empty:
            sheets[sheet_name] = pd.DataFrame(columns=columns)
            continue
        group_cols = [COLUMNS['unit'], COLUMNS['pipeline'], COLUMNS['segment_no']]
        existing = [col for col in group_cols if col in frame.columns]
        if not existing:
            sheets[sheet_name] = pd.DataFrame(columns=columns)
            continue
        work = frame.copy()
        work[COLUMNS['diameter']] = pd.to_numeric(work.get(COLUMNS['diameter'], 0), errors='coerce').fillna(0)
        rows = []
        for keys, group in work.groupby(existing, sort=False, dropna=False):
            if not isinstance(keys, tuple):
                keys = (keys,)
            row = {column: '' for column in columns}
            for column, value in zip(existing, keys):
                row[column] = value
            row['管段总寸径'] = format(float(group[COLUMNS['diameter']].sum()), 'g')
            rows.append(row)
        sheets[sheet_name] = pd.DataFrame(rows, columns=columns)
    return sheets


def _material_detail_sheets_from_welding_plan(welding_df):
    detail_sheets = {}
    pipe_pick_sheets = {}
    fitting_pick_sheets = {}
    detail_columns = MATERIAL_DETAIL_COLUMNS
    for sheet_name, frame in _welding_plan_sheet_map(welding_df).items():
        detail_rows = []
        for _, row in frame.iterrows():
            for item in _row_material_items(row):
                if not any(item.values()):
                    continue
                detail_rows.append({
                    future_schedule.CUT_ORDER_NO_COL: row.get(future_schedule.CUT_ORDER_NO_COL, ''),
                    future_schedule.WELD_ORDER_NO_COL: row.get(future_schedule.WELD_ORDER_NO_COL, ''),
                    future_schedule.CUT_DATE_COL: row.get(future_schedule.CUT_DATE_COL, ''),
                    future_schedule.WELD_DATE_COL: row.get(future_schedule.WELD_DATE_COL, ''),
                    future_schedule.SOURCE_SHEET_COL: row.get(future_schedule.SOURCE_SHEET_COL, sheet_name),
                    '材料侧': item['side'],
                    '材料唯一码': item['unique'],
                    '设计数量': item['qty'],
                    '需领料数量': item['qty'],
                    '材料代码': item['code'],
                    '材料代号': item['mark'],
                    '设计切割长度': item['qty'],
                    '单位': item['unit'],
                    '材料油漆': item['paint'],
                    '描述': item['description'],
                    COLUMNS['completed_flag']: row.get(COLUMNS['completed_flag'], ''),
                    COLUMNS['unit']: row.get(COLUMNS['unit'], ''),
                    COLUMNS['pipeline']: row.get(COLUMNS['pipeline'], ''),
                    COLUMNS['segment_no']: row.get(COLUMNS['segment_no'], ''),
                    COLUMNS['weld_no_start']: row.get(COLUMNS['weld_no_start'], ''),
                    COLUMNS['weld_no_final']: row.get(COLUMNS['weld_no_final'], ''),
                    COLUMNS['diameter']: row.get(COLUMNS['diameter'], ''),
                    COLUMNS['thickness']: row.get(COLUMNS['thickness'], ''),
                    COLUMNS['material']: row.get(COLUMNS['material'], ''),
                })
        detail_df = pd.DataFrame(detail_rows, columns=detail_columns)
        detail_sheets[sheet_name] = detail_df
        if detail_df.empty or '材料代号' not in detail_df.columns:
            pipe_pick_sheets[sheet_name] = pd.DataFrame(columns=PICK_LIST_COLUMNS)
            fitting_pick_sheets[sheet_name] = pd.DataFrame(columns=PICK_LIST_COLUMNS)
            continue
        mark_series = detail_df['材料代号'].astype(str).str.upper().str.strip()
        pipe_pick_sheets[sheet_name] = _aggregate_pick_list(detail_df[mark_series == 'P'].copy())
        fitting_pick_sheets[sheet_name] = _aggregate_pick_list(detail_df[mark_series != 'P'].copy())
    return detail_sheets, pipe_pick_sheets, fitting_pick_sheets


def _cutting_detail_sheets_from_welding_plan(welding_df):
    sheets = {}
    columns = CUTTING_DETAIL_COLUMNS
    for sheet_name, frame in _welding_plan_sheet_map(welding_df).items():
        rows = []
        for _, row in frame.iterrows():
            for item in _row_material_items(row):
                if str(item.get('mark') or '').strip().upper() != 'P':
                    continue
                rows.append({
                    future_schedule.CUT_ORDER_NO_COL: row.get(future_schedule.CUT_ORDER_NO_COL, ''),
                    future_schedule.WELD_ORDER_NO_COL: row.get(future_schedule.WELD_ORDER_NO_COL, ''),
                    future_schedule.CUT_DATE_COL: row.get(future_schedule.CUT_DATE_COL, ''),
                    future_schedule.WELD_DATE_COL: row.get(future_schedule.WELD_DATE_COL, ''),
                    future_schedule.SOURCE_SHEET_COL: row.get(future_schedule.SOURCE_SHEET_COL, sheet_name),
                    '材料侧': item['side'],
                    '材料唯一码': item['unique'],
                    '材料代码': item['code'],
                    '材料代号': item['mark'],
                    '设计切割长度': item['qty'],
                    '单位': item['unit'] or '米',
                    '材料油漆': item['paint'],
                    '描述': item['description'],
                    COLUMNS['completed_flag']: row.get(COLUMNS['completed_flag'], ''),
                    COLUMNS['unit']: row.get(COLUMNS['unit'], ''),
                    COLUMNS['pipeline']: row.get(COLUMNS['pipeline'], ''),
                    COLUMNS['segment_no']: row.get(COLUMNS['segment_no'], ''),
                    COLUMNS['weld_no_start']: row.get(COLUMNS['weld_no_start'], ''),
                    COLUMNS['weld_no_final']: row.get(COLUMNS['weld_no_final'], ''),
                    COLUMNS['diameter']: row.get(COLUMNS['diameter'], ''),
                    COLUMNS['thickness']: row.get(COLUMNS['thickness'], ''),
                    COLUMNS['material']: row.get(COLUMNS['material'], ''),
                })
        sheets[sheet_name] = pd.DataFrame(rows, columns=columns)
    return sheets


def _cutting_summary_sheets_from_welding_plan(welding_df):
    return {
        sheet_name: future_schedule._build_cut_summary(detail_df)
        for sheet_name, detail_df in _cutting_detail_sheets_from_welding_plan(welding_df).items()
    }


def _master_schedule_sheets_from_welding_plan(welding_df):
    columns = MASTER_SCHEDULE_COLUMNS
    if welding_df.empty:
        return {'Sheet1': pd.DataFrame(columns=columns)}
    group_cols = [
        future_schedule.CUT_DATE_COL,
        future_schedule.WELD_DATE_COL,
        future_schedule.WELD_ORDER_NO_COL,
        future_schedule.SOURCE_SHEET_COL,
    ]
    existing = [col for col in group_cols if col in welding_df.columns]
    rows = []
    work = welding_df.copy()
    work[COLUMNS['diameter']] = pd.to_numeric(work.get(COLUMNS['diameter'], 0), errors='coerce').fillna(0)
    for keys, group in work.groupby(existing, sort=False, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        values = dict(zip(existing, keys))
        rows.append({
            future_schedule.CUT_DATE_COL: values.get(future_schedule.CUT_DATE_COL, ''),
            future_schedule.WELD_DATE_COL: values.get(future_schedule.WELD_DATE_COL, ''),
            future_schedule.WELD_ORDER_NO_COL: values.get(future_schedule.WELD_ORDER_NO_COL, ''),
            '抽取次数': values.get(future_schedule.SOURCE_SHEET_COL, ''),
            '焊口数量': str(len(group)),
            '直径总和': format(float(group[COLUMNS['diameter']].sum()), 'g'),
            '目标值': '',
            '下料完成要求': '',
        })
    return {'Sheet1': pd.DataFrame(rows, columns=columns)}


def derived_plan_files_sheets(project, plan_key, plan_folder, file_names):
    requested = {str(file_name or '') for file_name in file_names or []}
    result = {}
    anti_commission_files = {
        file_name for file_name in requested if _is_anti_corrosion_commission_file(file_name)
    }
    if plan_key == 'anti-corrosion' and anti_commission_files:
        for file_name in anti_commission_files:
            result[file_name] = {
                '防腐委托单': _anti_corrosion_commission_dataframe_from_master(
                    project,
                    plan_folder=plan_folder,
                    file_name=file_name,
                ),
            }
    if plan_key == 'anti-corrosion' and requested.intersection(ANTI_CORROSION_DERIVED_FILE_NAMES):
        commission_df = _anti_corrosion_commission_dataframe(project, plan_folder=plan_folder)
        match_detail_df = _anti_corrosion_match_detail_dataframe(project)
        if '防腐材料汇总表.xlsx' in requested:
            result['防腐材料汇总表.xlsx'] = {
                'Sheet1': build_anti_corrosion_material_summary(commission_df, match_detail_df),
            }
        if '防腐材料明细表.xlsx' in requested:
            result['防腐材料明细表.xlsx'] = {
                'Sheet1': build_anti_corrosion_material_detail(commission_df, match_detail_df),
            }
    if plan_key == 'welding' and requested.intersection(WELDING_DERIVED_FILE_NAMES):
        welding_df = _welding_plan_dataframe(project, plan_folder=plan_folder)
        if '管段清单.xlsx' in requested:
            result['管段清单.xlsx'] = _segment_list_sheets(welding_df)
        material_names = {'材料明细表.xlsx', '管子领料单.xlsx', '管件法兰领料单.xlsx'}
        if requested.intersection(material_names):
            material_sheets, pipe_pick_sheets, fitting_pick_sheets = _material_detail_sheets_from_welding_plan(welding_df)
            result.update({
                '材料明细表.xlsx': material_sheets,
                '管子领料单.xlsx': pipe_pick_sheets,
                '管件法兰领料单.xlsx': fitting_pick_sheets,
            })
    if plan_key == 'cutting' and requested.intersection(CUTTING_DERIVED_FILE_NAMES):
        welding_df = _welding_plan_dataframe(project, cut_date=plan_folder)
        detail_sheets = _cutting_detail_sheets_from_welding_plan(welding_df)
        if '切管明细表.xlsx' in requested:
            result['切管明细表.xlsx'] = detail_sheets
        if '切管汇总表.xlsx' in requested:
            result['切管汇总表.xlsx'] = {
                sheet_name: future_schedule._build_cut_summary(detail_df)
                for sheet_name, detail_df in detail_sheets.items()
            }
    if plan_key == 'welding' and MASTER_DERIVED_FILE_NAME in requested:
        result[MASTER_DERIVED_FILE_NAME] = _master_schedule_sheets_from_welding_plan(
            _welding_plan_dataframe(project)
        )
    return {file_name: result[file_name] for file_name in requested if file_name in result}


def derived_plan_file_sheets(project, plan_key, plan_folder, file_name):
    return derived_plan_files_sheets(
        project,
        plan_key,
        plan_folder,
        [file_name],
    ).get(file_name)


def derived_plan_file_payload(project, plan_key, plan_folder, file_name, sheet_name=None):
    sheets = derived_plan_file_sheets(project, plan_key, plan_folder, file_name)
    if sheets is None:
        return None
    sheet_names = list(sheets.keys()) or ['Sheet1']
    selected_sheet = sheet_name if sheet_name in sheet_names else sheet_names[0]
    dataframe = sheets.get(selected_sheet)
    payload = dataframe_payload(dataframe)
    return {
        'path': _plan_source_path(plan_key, plan_folder, file_name),
        'name': file_name,
        'sheet': selected_sheet,
        'sheets': sheet_names,
        'total': len(payload['rows']),
        'columns': payload['columns'],
        'rows': payload['rows'],
    }


def stage_plan_output_files(project, output_files):
    stage_token = uuid.uuid4().hex
    staged_files = []
    for output_file in output_files:
        file_name = output_file['file_name']
        plan_key = output_file['plan_key']
        plan_date = output_file['plan_date']
        sheet_models = _plan_file_models(file_name)
        if sheet_models is None:
            if plan_key != 'anti-corrosion' or not _is_anti_corrosion_commission_file(file_name):
                raise ValueError(f'{file_name} 是由管段焊口表派生的计划文件，不再单独暂存')
        source_key = f'{stage_token}:{plan_key}:{plan_date}:{file_name}'
        if sheet_models is None:
            workbook_payload = {
                str(sheet_name): dataframe.copy()
                for sheet_name, dataframe in (output_file.get('sheets') or {'Sheet1': pd.DataFrame()}).items()
            }
            STAGED_PLAN_WORKBOOKS[source_key] = workbook_payload
            source, _ = DataSourceFile.objects.update_or_create(
                project=project,
                source_type='plan-stage',
                source_key=source_key,
                defaults={
                    'display_name': file_name,
                    'relative_path': _plan_stage_source_path(stage_token, plan_key, plan_date, file_name),
                    'file_size': 0,
                    'file_updated_at': datetime.now().timestamp(),
                    'sheet_names': list(workbook_payload.keys()),
                    'sheet_columns': {
                        sheet_name: [str(column) for column in dataframe.columns]
                        for sheet_name, dataframe in workbook_payload.items()
                    },
                },
            )
        else:
            sync_dataframes(
                project,
                'plan-stage',
                source_key,
                file_name,
                _plan_stage_source_path(stage_token, plan_key, plan_date, file_name),
                output_file['sheets'] or {'Sheet1': pd.DataFrame()},
                sheet_models,
            )
            source = DataSourceFile.objects.filter(
                project=project,
                source_type='plan-stage',
                source_key=source_key,
            ).order_by('-file_updated_at', '-id').first()
        staged_files.append({
            'path': f'{plan_key}:{plan_date}:{file_name}',
            'sourceKey': source_key,
            'name': file_name,
            'planKey': plan_key,
            'planName': output_file['plan_name'],
            'planDate': plan_date,
            'weldDate': output_file.get('weld_date') or plan_date,
            'cutDate': output_file.get('cut_date') or '',
            'fileName': file_name,
            'record': output_file.get('record', True),
            'size': source.file_size if source else 0,
            'updatedAt': source.file_updated_at if source else 0,
        })
    return stage_token, staged_files


def commit_staged_plan_outputs(project, stage_token):
    stage_prefix = f'{str(stage_token or "").strip()}:'
    if stage_prefix == ':':
        raise ValueError('暂存令牌无效')

    ensure_project_tables(project)
    with using_project_tables(project), transaction.atomic():
        sources = list(
            DataSourceFile.objects.filter(
                project=project,
                source_type='plan-stage',
                source_key__startswith=stage_prefix,
            ).order_by('file_updated_at', 'id')
        )
        if not sources:
            raise FileNotFoundError('暂存计划不存在或已失效')

        record_groups = {}
        anti_commission_frames = []
        for source in sources:
            parsed = _parse_stage_source_key(source.source_key)
            if not parsed:
                continue
            _, plan_key, plan_date, file_name = parsed
            sheet_models = _plan_file_models(file_name)
            workbook_payload = {}
            if sheet_models is None:
                if plan_key != 'anti-corrosion' or not _is_anti_corrosion_commission_file(file_name):
                    continue
                workbook_payload = {
                    sheet_name: dataframe.copy()
                    for sheet_name, dataframe in (STAGED_PLAN_WORKBOOKS.get(source.source_key) or {}).items()
                }
            else:
                for sheet_name in source.sheet_names or []:
                    selected_sheet, _, _, columns, rows = table_payload(source, sheet_models, sheet_name)
                    workbook_payload[selected_sheet or sheet_name] = pd.DataFrame(rows, columns=columns)
            if not workbook_payload:
                continue
            if sheet_models is not None:
                sync_dataframes(
                    project,
                    'plan',
                    f'{plan_key}:{plan_date}:{file_name}',
                    file_name,
                    _plan_source_path(plan_key, plan_date, file_name),
                    workbook_payload,
                    sheet_models,
                )
            frames = [
                dataframe
                for dataframe in workbook_payload.values()
                if dataframe is not None and not dataframe.empty
            ]
            if frames and plan_key in {'anti-corrosion', 'welding'}:
                _sync_master_schedule_rows(project, plan_key, plan_date, pd.concat(frames, ignore_index=True, sort=False))
            if frames and plan_key == 'welding':
                cut_dates = set()
                for dataframe in frames:
                    if future_schedule.CUT_DATE_COL not in dataframe.columns:
                        continue
                    cut_dates.update(
                        text
                        for text in dataframe[future_schedule.CUT_DATE_COL].fillna('').astype(str).str.strip()
                        if text
                    )
                for cut_date in cut_dates:
                    frame = pd.concat(frames, ignore_index=True, sort=False)
                    frame = frame.loc[frame[future_schedule.CUT_DATE_COL].fillna('').astype(str).str.strip().eq(cut_date)].copy()
                    _sync_master_schedule_rows(project, 'cutting', cut_date, frame)
            if plan_key == 'anti-corrosion':
                summary_df = workbook_payload.get('防腐委托单')
                if summary_df is None:
                    summary_df = next(iter(workbook_payload.values()), pd.DataFrame())
                if summary_df is not None and not summary_df.empty:
                    anti_commission_frames.append(summary_df)
            record_key = (plan_key, plan_date)
            if plan_key == 'welding' and file_name == WELDING_PRIMARY_PLAN_FILE_NAME:
                record_groups.setdefault(record_key, set()).update(WELDING_PLAN_FILE_NAMES)
                cut_dates = set()
                for dataframe in workbook_payload.values():
                    if future_schedule.CUT_DATE_COL not in dataframe.columns:
                        continue
                    cut_dates.update(
                        text
                        for text in dataframe[future_schedule.CUT_DATE_COL].fillna('').astype(str).str.strip()
                        if text
                    )
                for cut_date in cut_dates:
                    record_groups.setdefault(('cutting', cut_date), set()).update(CUTTING_PLAN_FILE_NAMES)
            else:
                record_groups.setdefault(record_key, set()).add(file_name)
                if plan_key == 'anti-corrosion':
                    record_groups[record_key].update(ANTI_CORROSION_DERIVED_FILE_NAMES)

        if anti_commission_frames:
            anti_commission_df = pd.concat(anti_commission_frames, ignore_index=True, sort=False)
            if project_process_sequence(project) == 'coating_before_welding':
                lock_anti_corrosion_materials_from_dataframe(project, anti_commission_df)

        DataSourceFile.objects.filter(
            project=project,
            source_type='plan-stage',
            source_key__startswith=stage_prefix,
        ).delete()
        for source_key in [source.source_key for source in sources]:
            STAGED_PLAN_WORKBOOKS.pop(source_key, None)

    saved_files = []
    for (plan_key, plan_date), file_names in record_groups.items():
        plan_name = {
            'cutting': '下料',
            'welding': '焊接',
            'anti-corrosion': '防腐',
        }.get(plan_key, plan_key)
        _sync_plan_record(project, plan_key, plan_name, plan_date, sorted(file_names))
        for file_name in sorted(file_names):
            saved_files.append({
                'planKey': plan_key,
                'planDate': plan_date,
                'fileName': file_name,
            })
    return saved_files


def commit_plan_stage_from_manifest(project, stage_root, manifest):
    output_files = []
    changed_files = manifest.get('changedFiles') or []
    for item in changed_files:
        if not isinstance(item, dict):
            continue
        relative_path = str(item.get('path') or '')
        if not relative_path:
            continue
        file_path = (stage_root / relative_path).resolve()
        file_path.relative_to(stage_root.resolve())
        if not file_path.exists() or not file_path.is_file():
            raise FileNotFoundError(f'暂存计划文件不存在：{relative_path}')
        sheets = pd.read_excel(file_path, sheet_name=None)
        output_files.append({
            'plan_key': item.get('planKey') or '',
            'plan_name': item.get('planName') or '',
            'plan_date': item.get('planDate') or '',
            'file_name': item.get('fileName') or file_path.name,
            'sheets': sheets,
            'record': item.get('record', True),
        })
    _sync_plan_output_files(project, output_files)
    return output_files


def maintain_material_libraries_from_database(project):
    ensure_project_tables(project)
    with using_project_tables(project):
        arrival_df = _arrival_material_dataframe(project)
        if arrival_df.empty:
            raise ValueError('数据库中没有入库单明细，无法生成材料库')
        pipe_df = add_anti_corrosion_area(
            build_pipe_material_library(arrival_df),
            PIPE_STOCK_QTY_COL,
        )
        fitting_df = add_anti_corrosion_area(
            build_fitting_flange_material_library(arrival_df),
            STOCK_QTY_COL,
        )
        _sync_library_dataframe(project, 'pipe-library', '管子材料库.xlsx', pipe_df)
        _sync_library_dataframe(project, 'fitting-library', '管件法兰材料库.xlsx', fitting_df)
        return {
            'pipe_count': len(pipe_df),
            'fitting_count': len(fitting_df),
            'anti_pipe_count': 0,
            'anti_fitting_count': 0,
        }


def maintain_weld_library_from_database(project):
    ensure_project_tables(project)
    with using_project_tables(project):
        init_df = _model_dataframe(InitializationWeldRow, project)
        if init_df.empty:
            raise ValueError('数据库中没有焊口初始化数据，无法生成预制焊口库')

        prefab_work_df = _coerce_filter_columns(init_df, PREFAB_WELD_FILTERS)
        prefab_df, _ = filter_data(prefab_work_df, PREFAB_WELD_FILTERS)
        if prefab_df is None or prefab_df.empty:
            raise ValueError('没有满足可预制规则的焊口初始化数据，无法生成预制焊口库')

        auto_work_df = _coerce_filter_columns(prefab_df, AUTO_WELD_FILTERS)
        auto_filter_df, _ = filter_data(auto_work_df, AUTO_WELD_FILTERS)
        auto_filter_df = _drop_empty_segment_no(auto_filter_df)
        auto_df = _auto_weld_dataframe(auto_filter_df)

        library_df = build_unified_weld_library(prefab_df.copy(), auto_df.copy())
        if library_df.empty:
            raise ValueError('焊口初始化数据为空，无法生成预制焊口库')
        library_df, _ = apply_extra_pipe_material_qty(library_df)
        library_df = _ensure_weld_material_status_columns(library_df)
        library_df = ensure_priority_column(library_df)

        existing_df, _, _ = _source_dataframe(project, 'library', 'weld-library', WeldLibraryRow)
        if not existing_df.empty:
            library_df, _ = apply_priority_to_library(library_df, existing_df)

        completed_df = _model_dataframe(WeldingPlanRow, project)
        if not completed_df.empty:
            library_df, _ = apply_completed_to_library(library_df, completed_df)

        _sync_library_dataframe(project, 'weld-library', '预制焊口库.xlsx', library_df)
        return {
            'weld_count': len(library_df),
            'prefab_filter_count': len(prefab_df),
            'auto_filter_count': 0 if auto_filter_df is None else len(auto_filter_df),
            'auto_weld_count': len(auto_df),
        }


def _ensure_weld_material_status_columns(dataframe):
    dataframe = dataframe.copy()
    for column in (
        COLUMNS['material_arrival_status'],
        COLUMNS['material_anti_corrosion_status'],
        COLUMNS['material_cutting_status'],
    ):
        if column not in dataframe.columns:
            dataframe[column] = False
        else:
            dataframe[column] = pre_matcher._to_bool_series(dataframe[column]).astype(bool)
    return dataframe


def _material_stock_by_code(dataframe):
    stock = {}
    if dataframe is None or dataframe.empty:
        return stock
    for _, row in dataframe.iterrows():
        code = str(row.get('材料代码') or '').strip()
        if not code:
            continue
        quantity = pd.to_numeric(row.get('库存数量（米）'), errors='coerce')
        if pd.isna(quantity):
            quantity = pd.to_numeric(row.get('库存数量'), errors='coerce')
        if pd.isna(quantity) or quantity <= 0:
            continue
        stock[code] = stock.get(code, Decimal('0')) + Decimal(str(quantity))
    return stock


def _weld_row_material_requirements(row, pipe_codes, fitting_codes):
    requirements = []
    for side in (1, 2):
        code = str(row.get(f'材料代码{side}') or '').strip()
        if not code:
            continue
        mark = str(row.get(f'材料代号{side}') or '').strip().upper()
        material_type = 'pipe' if mark == 'P' or (not mark and code in pipe_codes and code not in fitting_codes) else 'other'
        quantity = pd.to_numeric(row.get(f'数量{side}'), errors='coerce')
        if pd.isna(quantity) or quantity <= 0:
            continue
        requirements.append((material_type, code, Decimal(str(quantity))))
    return requirements


def _weld_requires_anti_corrosion(row):
    pipe_demands, fitting_demands = pre_matcher._build_weld_material_demands(row)
    demands = list(pipe_demands or []) + list(fitting_demands or [])
    return any(demand.get(pre_matcher.INVENTORY_POOL_KEY) == pre_matcher.ANTI_CORROSION_POOL for demand in demands)


def match_and_lock_materials_from_database(
    project,
    only_auto_weld=False,
    concentration_dimension=None,
    concentration_threshold_percent=None,
):
    ensure_project_tables(project)
    with using_project_tables(project), transaction.atomic():
        weld_df, _, _ = _source_dataframe(project, 'library', 'weld-library', WeldLibraryRow)
        pipe_df, _, _ = _source_dataframe(project, 'library', 'pipe-library', PipeMaterialRow)
        fitting_df, _, _ = _source_dataframe(project, 'library', 'fitting-library', FittingMaterialRow)
        if weld_df.empty:
            weld_df = _model_dataframe(WeldLibraryRow, project, source_file__source_key='weld-library')
        if pipe_df.empty:
            pipe_df = _model_dataframe(PipeMaterialRow, project, source_file__source_key='pipe-library')
        if fitting_df.empty:
            fitting_df = _model_dataframe(FittingMaterialRow, project, source_file__source_key='fitting-library')
        if weld_df.empty:
            raise ValueError('数据库中预制焊口库为空，无法进行材料匹配锁定')
        if pipe_df.empty and fitting_df.empty:
            raise ValueError('数据库中没有管子材料库或管件法兰材料库，无法进行材料匹配锁定')

        pipe_df = pre_matcher._normalize_pipe_library_or_empty(pipe_df)
        fitting_df = pre_matcher._normalize_fitting_library_or_empty(fitting_df)
        pipe_states = pre_matcher._build_pipe_states(pipe_df)
        fitting_stock = pre_matcher._build_fitting_stock(fitting_df)

        candidate_df = pre_matcher._prepare_uncompleted_welds(weld_df, only_auto_weld=only_auto_weld)
        cutting_col = COLUMNS['material_cutting_status']
        if cutting_col in candidate_df.columns:
            candidate_df = candidate_df.loc[~pre_matcher._to_bool_series(candidate_df[cutting_col])].copy()

        accepted_rows = []
        rejected_rows = []
        all_rows = []
        detail_rows = []
        match_seq = 1
        group_cols = [pre_matcher.COLUMNS['unit'], pre_matcher.COLUMNS['pipeline']]
        for _, group_df in candidate_df.groupby(group_cols, sort=False, dropna=False):
            group_result = pre_matcher._simulate_group_matches(
                group_df,
                pipe_states,
                fitting_stock,
                match_seq,
            )
            detail_rows.extend(group_result['detail_rows'])
            if pre_matcher._group_should_be_rejected(group_result):
                group_rejected_rows, group_all_rows = pre_matcher._reject_group_rows(group_result)
                rejected_rows.extend(group_rejected_rows)
                all_rows.extend(group_all_rows)
                continue
            if not pre_matcher._meets_pipeline_concentration(
                group_result['all_rows'],
                concentration_dimension,
                concentration_threshold_percent,
            ):
                group_rejected_rows, group_all_rows = pre_matcher._reject_pipeline_rows(group_result['all_rows'])
                rejected_rows.extend(group_rejected_rows)
                all_rows.extend(group_all_rows)
                continue

            accepted_rows.extend(group_result['accepted_rows'])
            rejected_rows.extend(group_result['rejected_rows'])
            all_rows.extend(group_result['all_rows'])
            pipe_states = group_result['pipe_states']
            fitting_stock = group_result['fitting_stock']
            match_seq = group_result['next_seq']

        result_df = pd.DataFrame(all_rows)
        detail_df = pd.DataFrame(detail_rows, columns=pre_matcher.PRE_SCHEDULE_DETAIL_COLUMNS)
        sync_dataframes(
            project,
            'pre-schedule',
            'material-locking',
            '材料匹配锁定结果.xlsx',
            'database://pre-schedule/material-locking/材料匹配锁定结果.xlsx',
            {'预排产匹配结果': result_df, '材料匹配明细': detail_df},
            PRE_SCHEDULE_MODELS,
        )

        updated_pipe_df = pre_matcher._apply_pipe_states_to_df(pipe_df, pipe_states)
        updated_fitting_df = pre_matcher._apply_fitting_stock_to_df(fitting_df, fitting_stock)
        _sync_library_dataframe(project, 'pipe-library', '管子材料库.xlsx', updated_pipe_df)
        _sync_library_dataframe(project, 'fitting-library', '管件法兰材料库.xlsx', updated_fitting_df)

        weld_df = _ensure_weld_material_status_columns(weld_df)
        seq_col = COLUMNS['library_seq']
        accepted_seqs = {
            str(row.get(seq_col, '')).strip()
            for row in accepted_rows
            if str(row.get(seq_col, '')).strip()
        }
        arrival_col = COLUMNS['material_arrival_status']
        anti_col = COLUMNS['material_anti_corrosion_status']
        arrived_count = 0
        pending_count = 0
        for index, row in weld_df.iterrows():
            library_seq = str(row.get(seq_col, '')).strip()
            if library_seq and library_seq in accepted_seqs:
                weld_df.at[index, arrival_col] = True
                weld_df.at[index, anti_col] = not _weld_requires_anti_corrosion(row)
                arrived_count += 1
            else:
                weld_df.at[index, arrival_col] = False
                weld_df.at[index, anti_col] = False
                pending_count += 1
        _sync_library_dataframe(project, 'weld-library', '预制焊口库.xlsx', weld_df)

        return {
            'candidate_count': len(candidate_df),
            'locked_count': len(accepted_rows),
            'rejected_count': len(rejected_rows),
            'detail_count': len(detail_df),
            'arrived_count': arrived_count,
            'pending_count': pending_count,
            'pipe_count': len(updated_pipe_df),
            'fitting_count': len(updated_fitting_df),
        }


def update_weld_material_arrival_status_from_database(project):
    result = match_and_lock_materials_from_database(project)
    return {
        'weld_count': result.get('candidate_count', 0),
        'arrived_count': result.get('arrived_count', 0),
        'pending_count': result.get('pending_count', 0),
        **result,
    }


def confirm_pre_schedule_from_database(project):
    ensure_project_tables(project)
    with using_project_tables(project), transaction.atomic():
        ordinary_pipe_df, _, _ = _source_dataframe(project, 'library', 'pending-pipe-library', PipeMaterialRow)
        ordinary_fitting_df, _, _ = _source_dataframe(project, 'library', 'pending-fitting-library', FittingMaterialRow)
        pipe_df, _, _ = _source_dataframe(project, 'library', 'pending-anti-pipe-library', PipeMaterialRow)
        fitting_df, _, _ = _source_dataframe(project, 'library', 'pending-anti-fitting-library', FittingMaterialRow)
        if ordinary_pipe_df.empty and ordinary_fitting_df.empty and pipe_df.empty and fitting_df.empty:
            raise ValueError('数据库中没有待确认材料库，无法确认同步')
        _sync_library_dataframe(project, 'pipe-library', '管子材料库.xlsx', ordinary_pipe_df)
        _sync_library_dataframe(project, 'fitting-library', '管件法兰材料库.xlsx', ordinary_fitting_df)
        _sync_library_dataframe(project, 'anti-pipe-library', '防腐管子材料库.xlsx', pipe_df)
        _sync_library_dataframe(project, 'anti-fitting-library', '防腐管件法兰材料库.xlsx', fitting_df)
        return {
            'ordinary_pipe_count': len(ordinary_pipe_df),
            'ordinary_fitting_count': len(ordinary_fitting_df),
            'anti_pipe_count': len(pipe_df),
            'anti_fitting_count': len(fitting_df),
        }


def generate_anti_corrosion_schedule_from_database(
    project,
    commission_area=400,
    selected_library_seqs=None,
    persist=True,
    **options,
):
    ensure_project_tables(project)
    with using_project_tables(project):
        pre_df, _, _ = _source_dataframe(
            project,
            'pre-schedule',
            'anti-corrosion-pre-schedule',
            WeldPreScheduleRow,
            sheet_name='预排产匹配结果',
        )
        if pre_df.empty:
            raise ValueError('数据库中没有防腐预排产匹配结果，无法生成防腐委托')
        selected_values = [
            str(value or '').strip()
            for value in (selected_library_seqs or [])
            if str(value or '').strip()
        ]
        if selected_values:
            if '库序号' not in pre_df.columns:
                raise ValueError('防腐预排产匹配结果缺少库序号，无法按选中记录生成防腐委托')
            selected_set = set(selected_values)
            pre_df = pre_df.loc[
                pre_df['库序号'].fillna('').astype(str).str.strip().isin(selected_set)
            ].copy()
        if pre_df.empty:
            raise ValueError('选中的预排产记录不存在，无法生成防腐委托')
        if '预排产状态' in pre_df.columns:
            schedulable_mask = pre_df['预排产状态'].fillna('').astype(str).str.strip().eq(MATCHED_STATUS)
            pre_df = pre_df.loc[schedulable_mask].copy()
        if pre_df.empty:
            raise ValueError('没有可生成委托的可预排产记录')
        summary_df = build_anti_corrosion_commission_from_pre_schedule(
            pre_df,
            commission_area=commission_area,
            split_by_area=True,
            date_mode=options.get('dateMode', 'auto'),
            commission_start_date=options.get('weldStartDate'),
            manual_commission_dates=options.get('manualWeldDates'),
            max_days=options.get('maxDays'),
            skip_holidays=options.get('skipHolidays', False),
            holiday_dates=options.get('holidayDates'),
            canceled_weekend_dates=options.get('canceledWeekendDates'),
        )
        if summary_df.empty:
            raise ValueError('选中的预排产记录中没有可生成委托的可预排产记录')
        output_files = []
        for item in split_commission_files(summary_df):
            output_files.append({
                'plan_key': 'anti-corrosion',
                'plan_name': '防腐',
                'plan_date': item['commission_date'] or datetime.now().strftime('%Y%m%d'),
                'file_name': item['file_name'],
                'sheets': build_anti_corrosion_commission_file_sheets(item['dataframe']),
                'record': True,
            })
        if persist:
            if project_process_sequence(project) == 'coating_before_welding':
                lock_anti_corrosion_materials_from_dataframe(project, summary_df)
            _sync_plan_output_files(project, output_files)
        result = {
            'pre_schedule_count': len(pre_df),
            'summary_count': len(summary_df),
            'commission_area': commission_area,
            'commission_file_count': len(output_files),
            'commission_dates': list(dict.fromkeys(item['plan_date'] for item in output_files)),
        }
        if not persist:
            result['_output_files'] = output_files
        return result


def lock_anti_corrosion_materials_from_dataframe(project, commission_df):
    if commission_df is None or commission_df.empty:
        return {'locked_count': 0}
    ensure_project_tables(project)
    with using_project_tables(project):
        selected_seqs = {
            str(value or '').strip()
            for value in commission_df.get('库序号', [])
            if str(value or '').strip()
        }
        if not selected_seqs:
            return {'locked_count': 0}

        weld_df, _, _ = _source_dataframe(project, 'library', 'weld-library', WeldLibraryRow)
        if weld_df.empty:
            weld_df = _model_dataframe(WeldLibraryRow, project, source_file__source_key='weld-library')
        if weld_df.empty or '库序号' not in weld_df.columns:
            return {'locked_count': 0}

        weld_df = _ensure_weld_material_status_columns(weld_df)
        mask = weld_df['库序号'].fillna('').astype(str).str.strip().isin(selected_seqs)
        updated_count = int(mask.sum())
        if updated_count:
            weld_df.loc[mask, COLUMNS['material_anti_corrosion_status']] = True
            _sync_library_dataframe(project, 'weld-library', '预制焊口库.xlsx', weld_df)

        return {
            'locked_count': updated_count,
        }


def match_anti_corrosion_pre_schedule_from_database(
    project,
    only_auto_weld=False,
    concentration_dimension=None,
    concentration_threshold_percent=None,
):
    ensure_project_tables(project)
    with using_project_tables(project):
        weld_df, _, _ = _source_dataframe(project, 'library', 'weld-library', WeldLibraryRow)
        pipe_df, _, _ = _source_dataframe(project, 'library', 'pipe-library', PipeMaterialRow)
        fitting_df, _, _ = _source_dataframe(project, 'library', 'fitting-library', FittingMaterialRow)
        if weld_df.empty:
            weld_df = _model_dataframe(WeldLibraryRow, project, source_file__source_key='weld-library')
        if pipe_df.empty:
            pipe_df = _model_dataframe(PipeMaterialRow, project, source_file__source_key='pipe-library')
        if fitting_df.empty:
            fitting_df = _model_dataframe(FittingMaterialRow, project, source_file__source_key='fitting-library')
        if weld_df.empty:
            raise ValueError('数据库中预制焊口库为空，无法生成防腐预排产')

        result = anti_pre_matcher.match_anti_corrosion_pre_schedule_dataframes(
            weld_df,
            pipe_df,
            fitting_df,
            only_auto_weld=only_auto_weld,
            concentration_dimension=concentration_dimension,
            concentration_threshold_percent=concentration_threshold_percent,
        )
        if project_process_sequence(project) == 'welding_before_coating':
            planned_seqs = _planned_library_seqs(project, 'weld_date', 'anti_corrosion_date')
            if planned_seqs:
                result['result_df'] = _filter_dataframe_to_library_seqs(result['result_df'], planned_seqs)
            if not result['detail_df'].empty and '库序号' in result['detail_df'].columns:
                result['detail_df'] = _filter_dataframe_to_library_seqs(
                    result['detail_df'],
                    set(result['result_df'].get('库序号', [])),
                )
        sync_dataframes(
            project,
            'pre-schedule',
            'anti-corrosion-pre-schedule',
            '防腐预排产匹配结果.xlsx',
            'database://pre-schedule/anti-corrosion-pre-schedule/防腐预排产匹配结果.xlsx',
            {
                '预排产匹配结果': result['result_df'],
                '材料匹配明细': result['detail_df'],
            },
            PRE_SCHEDULE_MODELS,
        )
        return {
            key: value
            for key, value in result.items()
            if key not in {'result_df', 'detail_df'}
        }


def match_weld_pre_schedule_from_database(
    project,
    only_auto_weld=None,
    ignore_anti_corrosion_status=False,
    concentration_dimension=None,
    concentration_threshold_percent=None,
):
    ensure_project_tables(project)
    with using_project_tables(project):
        weld_df, _, _ = _source_dataframe(project, 'library', 'weld-library', WeldLibraryRow)
        if weld_df.empty:
            raise ValueError('数据库中预制焊口库为空，无法生成预排产')

        candidate_df = pre_matcher._prepare_uncompleted_welds(weld_df, only_auto_weld=False)
        if project_process_sequence(project) == 'coating_before_welding':
            planned_seqs = _planned_library_seqs(project, 'anti_corrosion_date', 'cut_date')
            if planned_seqs:
                candidate_df = _filter_dataframe_to_library_seqs(candidate_df, planned_seqs)
        candidate_df = pre_matcher._filter_truthy_statuses(candidate_df, [
            COLUMNS['material_arrival_status'],
            COLUMNS['material_anti_corrosion_status'],
        ])
        cutting_col = COLUMNS['material_cutting_status']
        if cutting_col not in candidate_df.columns:
            candidate_df = candidate_df.iloc[0:0].copy()
        else:
            candidate_df = candidate_df.loc[~pre_matcher._to_bool_series(candidate_df[cutting_col])].copy()
        all_df = candidate_df.copy()
        all_df[pre_matcher.MATCH_SEQ_COL] = range(1, len(all_df) + 1)
        all_df[pre_matcher.STATUS_COL] = MATCHED_STATUS
        all_df[pre_matcher.REASON_COL] = ''

        sync_dataframes(
            project,
            'pre-schedule',
            'weld-pre-schedule',
            '焊口预排产匹配结果.xlsx',
            'database://pre-schedule/weld-pre-schedule/焊口预排产匹配结果.xlsx',
            {'预排产匹配结果': all_df},
            PRE_SCHEDULE_MODELS,
        )
        return {
            'candidate_count': len(candidate_df),
            'pre_schedule_count': len(all_df),
            'rejected_count': 0,
            'detail_count': 0,
        }


def match_welding_pre_schedule_from_database(project):
    ensure_project_tables(project)
    with using_project_tables(project):
        weld_df, _, _ = _source_dataframe(project, 'library', 'weld-library', WeldLibraryRow)
        if weld_df.empty:
            raise ValueError('数据库中预制焊口库为空，无法生成焊接预排产')

        candidate_df = pre_matcher._prepare_uncompleted_welds(weld_df, only_auto_weld=False)
        planned_seqs = _planned_library_seqs(project, 'cut_date', 'weld_date')
        if planned_seqs:
            candidate_df = _filter_dataframe_to_library_seqs(candidate_df, planned_seqs)
        candidate_df = pre_matcher._filter_truthy_statuses(candidate_df, [
            COLUMNS['material_arrival_status'],
            COLUMNS['material_anti_corrosion_status'],
            COLUMNS['material_cutting_status'],
        ])
        result_df = candidate_df.copy()
        result_df[pre_matcher.MATCH_SEQ_COL] = range(1, len(result_df) + 1)
        result_df[pre_matcher.STATUS_COL] = MATCHED_STATUS
        result_df[pre_matcher.REASON_COL] = ''

        sync_dataframes(
            project,
            'pre-schedule',
            'welding-pre-schedule',
            '焊接预排产结果.xlsx',
            'database://pre-schedule/welding-pre-schedule/焊接预排产结果.xlsx',
            {'预排产匹配结果': result_df},
            PRE_SCHEDULE_MODELS,
        )
        return {
            'candidate_count': len(candidate_df),
            'pre_schedule_count': len(result_df),
            'rejected_count': 0,
        }


def _material_detail_sheets(all_extractions):
    material_details = {}
    pipe_pick = {}
    fitting_pick = {}
    for extraction in all_extractions:
        sheet_name = str(extraction['info']['抽取次数'])
        material_df = generate_material_details_for_sheet(sheet_name, extraction['data'])
        if material_df is None or material_df.empty:
            continue
        material_details[sheet_name] = material_df
        if '材料代号' not in material_df.columns:
            continue
        code_series = material_df['材料代号'].astype(str).str.upper().str.strip()
        pipe_pick[sheet_name] = _aggregate_pick_list(material_df[code_series == 'P'].copy())
        fitting_pick[sheet_name] = _aggregate_pick_list(material_df[code_series != 'P'].copy())
    return material_details, pipe_pick, fitting_pick


def _welding_output_files(plan_date, all_extractions, cut_date=None):
    weld_date_value = future_schedule._parse_schedule_date(plan_date)
    cut_date_value = (
        future_schedule._parse_schedule_date(cut_date)
        if cut_date
        else future_schedule._previous_schedule_date(
            weld_date_value,
            days=future_schedule.DEFAULT_CUTTING_LEAD_DAYS,
        )
    )
    extraction_sheets = {
        str(item['info']['抽取次数']): future_schedule._build_welding_plan_for_sheet(
            str(item['info']['抽取次数']),
            item['data'],
            cut_date_value,
            weld_date_value,
        )
        for item in all_extractions
    }
    files = {
        '管段焊口表.xlsx': extraction_sheets,
    }
    return [
        {
            'plan_key': 'welding',
            'plan_name': '焊接',
            'plan_date': plan_date,
            'weld_date': future_schedule._date_text(weld_date_value),
            'cut_date': future_schedule._date_text(cut_date_value),
            'file_name': file_name,
            'sheets': sheets or {'Sheet1': pd.DataFrame()},
            'record': True,
        }
        for file_name, sheets in files.items()
    ]


def _welding_primary_output_files(plan_date, all_extractions, cut_date=None):
    return [
        output_file
        for output_file in _welding_output_files(plan_date, all_extractions, cut_date=cut_date)
        if output_file['file_name'] == WELDING_PRIMARY_PLAN_FILE_NAME
    ]


def _sync_welding_outputs(project, plan_date, all_extractions, cut_date=None):
    _sync_plan_output_files(project, _welding_primary_output_files(plan_date, all_extractions, cut_date=cut_date))
    _sync_plan_record(
        project,
        'welding',
        '焊接',
        plan_date,
        WELDING_PLAN_FILE_NAMES,
        summary=_schedule_plan_summary('welding', plan_date, all_extractions),
    )


def _plan_rows_from_extractions(plan_date, all_extractions, cut_date=None):
    output_files = _welding_primary_output_files(plan_date, all_extractions, cut_date=cut_date)
    frames = []
    for output_file in output_files:
        frames.extend(
            dataframe
            for dataframe in (output_file.get('sheets') or {}).values()
            if dataframe is not None and not dataframe.empty
        )
    return pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()


def _cutting_output_files(cut_date, weld_date, all_extractions):
    detail_sheets = {}
    summary_sheets = {}
    for extraction in all_extractions:
        sheet_name = str(extraction['info']['抽取次数'])
        detail_df = future_schedule._build_cut_detail_for_sheet(sheet_name, extraction['data'], cut_date, weld_date)
        detail_sheets[sheet_name] = detail_df
        summary_sheets[sheet_name] = future_schedule._build_cut_summary(detail_df)
    files = {
        '切管明细表.xlsx': detail_sheets,
        '切管汇总表.xlsx': summary_sheets,
    }
    return [
        {
            'plan_key': 'cutting',
            'plan_name': '下料',
            'plan_date': cut_date,
            'file_name': file_name,
            'sheets': sheets or {'Sheet1': pd.DataFrame()},
            'record': True,
        }
        for file_name, sheets in files.items()
    ]


def _sync_cutting_outputs(project, cut_date, weld_date, all_extractions):
    _sync_master_schedule_rows(project, 'cutting', cut_date, _plan_rows_from_extractions(weld_date, all_extractions, cut_date=cut_date))
    _sync_plan_record(
        project,
        'cutting',
        '下料',
        cut_date,
        CUTTING_PLAN_FILE_NAMES,
        summary=_schedule_plan_summary('cutting', cut_date, all_extractions),
    )


def generate_welding_schedule_from_database(project, weld_date=None, target_diameter=None, orders_per_day=None):
    ensure_project_tables(project)
    with using_project_tables(project):
        pre_df, _, _ = _source_dataframe(
            project,
            'pre-schedule',
            'welding-pre-schedule',
            WeldPreScheduleRow,
            sheet_name='预排产匹配结果',
        )
        if pre_df.empty:
            raise ValueError('数据库中没有焊接预排产结果，请先生成焊接预排产')
        if STATUS_COL in pre_df.columns:
            pre_df = pre_df.loc[pre_df[STATUS_COL].fillna('').astype(str).str.strip().eq(MATCHED_STATUS)].copy()
        if pre_df.empty:
            raise ValueError('数据库中没有可生成焊接排产的预排产焊口')
        plan_date = get_weld_schedule_date(weld_date)
        target = float(target_diameter or EXTRACT['target_diameter'])
        orders = int(orders_per_day or EXTRACT['num_extractions'])
        work_df = sort_and_clean_data(pre_df, COLUMNS['diameter'], COLUMNS['completed_flag'])
        all_extractions = extract_welds_multiple_times(
            work_df,
            num_extractions=orders,
            target_diameter=target,
            diameter_column=COLUMNS['diameter'],
            completed_flag_column=COLUMNS['completed_flag'],
            order_date=plan_date,
        )
        if not all_extractions:
            raise ValueError('没有可抽取焊口')
        _sync_welding_outputs(project, plan_date, all_extractions)
        return {
            'plan_date': plan_date,
            'order_count': len(all_extractions),
            'weld_count': int(sum(len(item['data']) for item in all_extractions)),
        }


def _completed_weld_keys_from_database(project):
    completed_keys = set()
    completed_col = COLUMNS['completed_flag']
    for source in DataSourceFile.objects.filter(project=project, source_type='plan', source_key__startswith='welding:'):
        for sheet in source.sheet_names or []:
            _, _, _, columns, rows = table_payload(source, {'*': WeldingPlanRow}, sheet)
            df = pd.DataFrame(rows, columns=columns)
            if df.empty or completed_col not in df.columns:
                continue
            completed_df = df.loc[future_schedule._to_bool_series(df[completed_col])].copy()
            if not completed_df.empty:
                completed_keys.update(future_schedule._build_weld_key(completed_df))
    return completed_keys


def generate_future_schedule_from_database(project, persist=True, **options):
    ensure_project_tables(project)
    with using_project_tables(project):
        pre_df = _model_dataframe(WeldPreScheduleRow, project, pre_schedule_status=MATCHED_STATUS)
        if pre_df.empty:
            raise ValueError('数据库中没有可预排产焊口')
        completed_keys = _completed_weld_keys_from_database(project)
        available_df, completed_count = future_schedule._remove_completed_welds(pre_df, completed_keys)
        available_df = future_schedule._ensure_completed_column(available_df)
        work_df = sort_and_clean_data(available_df, COLUMNS['diameter'], COLUMNS['completed_flag'])

        weld_start = future_schedule._parse_schedule_date(options.get('weldStartDate')) if options.get('weldStartDate') else datetime.now().date() + timedelta(days=1)
        target = float(options.get('targetDiameter') or EXTRACT['target_diameter'])
        if target > 300:
            raise ValueError('每张工作表目标寸径不能超过滚动计划最大值 300')
        orders = int(options.get('ordersPerDay') or EXTRACT['num_extractions'])
        date_mode = str(options.get('dateMode') or 'auto').strip().lower()
        max_days = options.get('maxDays')
        skip_holidays = future_schedule._to_bool(options.get('skipHolidays'))
        holidays = set(future_schedule._split_date_list(options.get('holidayDates')))
        canceled_weekends = set(future_schedule._split_date_list(options.get('canceledWeekendDates')))
        cutting_lead_days = options.get('cuttingLeadDays')
        cutting_lead_days = future_schedule.DEFAULT_CUTTING_LEAD_DAYS if cutting_lead_days in (None, '') else max(int(cutting_lead_days), 0)

        if date_mode == 'manual':
            weld_dates = future_schedule._manual_weld_dates(options.get('manualWeldDates'), skip_holidays, holidays, canceled_weekends)
            if not weld_dates:
                raise ValueError('手动选择日期为空，或已全部被节假日规则过滤')
        else:
            weld_dates = future_schedule._auto_weld_dates(weld_start, max_days, skip_holidays, holidays, canceled_weekends)

        master_rows = []
        planned_days = 0
        output_files = []
        for weld_date in weld_dates:
            cut_date = future_schedule._previous_schedule_date(
                weld_date,
                days=cutting_lead_days,
                skip_holidays=skip_holidays,
                holiday_dates=holidays,
                canceled_weekend_dates=canceled_weekends,
            )
            all_extractions = extract_welds_multiple_times(
                work_df,
                num_extractions=orders,
                target_diameter=target,
                diameter_column=COLUMNS['diameter'],
                completed_flag_column=COLUMNS['completed_flag'],
                order_date=future_schedule._date_text(weld_date),
            )
            if not all_extractions:
                break
            weld_text = future_schedule._date_text(weld_date)
            cut_text = future_schedule._date_text(cut_date)
            if persist:
                _sync_cutting_outputs(project, cut_text, weld_text, all_extractions)
                _sync_welding_outputs(project, weld_text, all_extractions, cut_date=cut_text)
            else:
                output_files.extend(_welding_primary_output_files(weld_text, all_extractions, cut_date=cut_text))
            future_schedule._append_master_rows(master_rows, all_extractions, cut_date, weld_date, cutting_lead_days)
            planned_days += 1
            remaining_count = int(((work_df['_run_picked'] == False) & (work_df[COLUMNS['completed_flag']] == False)).sum())
            if remaining_count == 0:
                break

        master_df = pd.DataFrame(master_rows)
        result = {
            'pre_schedule_count': len(pre_df),
            'completed_weld_count': completed_count,
            'planned_weld_count': int(sum(row.get('焊口数量', 0) for row in master_rows)),
            'planned_day_count': planned_days,
        }
        if persist:
            ProjectSchedulePolicy.objects.update_or_create(
                project=project,
                defaults={
                    'target_diameter': target,
                    'rollover_max_diameter': Decimal('300'),
                    'orders_per_day': orders,
                    'skip_holidays': skip_holidays,
                    'holiday_dates': [
                        future_schedule._date_text(value)
                        for value in sorted(holidays)
                    ],
                    'canceled_weekend_dates': [
                        future_schedule._date_text(value)
                        for value in sorted(canceled_weekends)
                    ],
                    'cutting_lead_days': cutting_lead_days,
                },
            )
        if not persist:
            result['_output_files'] = output_files
        return result
