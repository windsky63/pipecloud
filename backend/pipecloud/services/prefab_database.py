from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from itertools import chain
from pathlib import Path
import re
import sys
import uuid

import pandas as pd
from django.db import transaction
from django.utils import timezone

from pipecloud.models import (
    AntiCorrosionMaterialOrderRow,
    ArrivalMaterialRow,
    DataSourceFile,
    FittingMaterialRow,
    MaterialMatchDetailRow,
    MasterScheduleRow,
    PipeMaterialRow,
    PlanRecord,
    ProjectSchedulePolicy,
    WeldingPlanRow,
    WeldCommonData,
    WeldLibraryRow,
    WeldPreScheduleRow,
    InitializationWeldRow,
    InitializationWeldExtraData,
)
from pipecloud.services.db_storage import (
    LIBRARY_MODELS,
    PLAN_FILE_MODELS,
    PRE_SCHEDULE_MODELS,
    apply_weld_status_to_dataframe,
    _sync_weld_common_data_many,
    _sync_weld_status_values,
    coerce_boolean,
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
    ANTI_CORROSION_STOCK_QTY_COL,
    ANTI_CORROSION_STATUS_COL,
    ARRIVAL_DATE_COL,
    COATED_LOCKED_QTY_COL,
    LOCKED_QTY_COL,
    SOURCE_FILE_COL,
    STOCK_QTY_COL,
    PIPE_STOCK_QTY_COL,
    UNIT_AREA_COL,
    ANTI_CORROSION_AREA_COL,
    USED_QTY_COL,
    UNCOATED_LOCKED_QTY_COL,
    add_anti_corrosion_area,
    build_fitting_flange_material_library,
    build_pipe_material_library,
    split_arrival_materials_by_anti_corrosion,
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
    build_anti_corrosion_commission_from_pre_schedule,
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
CUTTING_PRIMARY_PLAN_FILE_NAME = '下料排产单.xlsx'
ANTI_CORROSION_MATERIAL_ORDER_FILE_NAME = '防腐材料单.xlsx'
ANTI_CORROSION_WELD_ORDER_FILE_NAME = '防腐焊口单.xlsx'
ANTI_CORROSION_MATERIAL_ORDER_SHEET_NAME = '防腐材料单'
ANTI_CORROSION_WELD_ORDER_SHEET_NAME = '防腐焊口单'
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
CUTTING_PLAN_FILE_NAMES = [CUTTING_PRIMARY_PLAN_FILE_NAME, *sorted(CUTTING_DERIVED_FILE_NAMES)]
CUTTING_HIDDEN_DATA_COLUMNS = {
    '计划文件夹',
    '计划日期',
    future_schedule.WELD_ORDER_NO_COL,
    future_schedule.WELD_DATE_COL,
}
WELDING_HIDDEN_DATA_COLUMNS = {
    '计划文件夹',
    '计划日期',
    future_schedule.SOURCE_SHEET_COL,
    future_schedule.CUT_ORDER_NO_COL,
    future_schedule.CUT_DATE_COL,
}
MATERIAL_UNIT_COLUMNS = ('单位1', '单位2')
DEFAULT_MASTER_ANTI_CORROSION_AREA = 1500
DEFAULT_MASTER_CUTTING_WELDING_DIAMETER = 260
MATERIAL_LIBRARY_EXCLUDED_COLUMNS = {
    'pipe-library': {
        ANTI_CORROSION_STATUS_COL,
        UNIT_AREA_COL,
        ANTI_CORROSION_AREA_COL,
        ANTI_CORROSION_STOCK_QTY_COL,
        COATED_LOCKED_QTY_COL,
        UNCOATED_LOCKED_QTY_COL,
    },
    'fitting-library': {
        UNIT_AREA_COL,
        ANTI_CORROSION_AREA_COL,
        ANTI_CORROSION_STOCK_QTY_COL,
        COATED_LOCKED_QTY_COL,
        UNCOATED_LOCKED_QTY_COL,
    },
    'anti-pipe-library': {ANTI_CORROSION_STATUS_COL, LOCKED_QTY_COL},
    'anti-fitting-library': {LOCKED_QTY_COL},
}


PLAN_STAGE_FIELDS = {
    'anti-corrosion': 'anti_corrosion_date',
    'cutting': 'cut_date',
    'welding': 'weld_date',
}

STAGED_PLAN_WORKBOOKS = {}
STAGED_PLAN_TTL = timedelta(hours=2)
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
ANTI_CORROSION_WELD_ORDER_COLUMNS = [
    '防腐委托单号',
    '委托日期',
    '防腐面积',
    '库序号',
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
} | set(model_field_labels(MasterScheduleRow).values()) | set(model_field_labels(WeldCommonData).values())
ANTI_CORROSION_STAGE_COLUMNS = {'防腐面积', '材料油漆', '材料油漆1', '材料油漆2'}
PLAN_STAGE_EXCLUDED_COLUMNS = {'计划文件夹', '计划日期'}
# Backward-compatible import for callers that still use the old name.
CUTTING_STAGE_EXCLUDED_COLUMNS = PLAN_STAGE_EXCLUDED_COLUMNS
MASTER_BOOLEAN_STATUS_FIELDS = {
    'material_arrival_status',
    'material_anti_corrosion_status',
    'material_cutting_status',
    'completed_flag',
}


def _drop_unused_material_unit_columns(project, dataframe):
    # 单位1、单位2是焊口公共字段。即使当前项目尚无值也保留列，保证初始化、
    # 各阶段计划和公共表使用一致的字段结构。
    return dataframe


def _fill_material_units(dataframe):
    out = dataframe.copy()
    for side in (1, 2):
        unit_column = f'单位{side}'
        mark_column = COLUMNS[f'material_no_{side}']
        generated = (
            out[mark_column].map(future_schedule._material_units_for_side)
            if mark_column in out.columns
            else pd.Series('', index=out.index)
        )
        if unit_column not in out.columns:
            out[unit_column] = generated
            continue
        empty_mask = out[unit_column].fillna('').astype(str).str.strip().eq('')
        out.loc[empty_mask, unit_column] = generated.loc[empty_mask]
    return out


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
        dataframe = apply_weld_status_to_dataframe(project, pd.DataFrame(rows, columns=columns))
        return _drop_unused_material_unit_columns(project, dataframe)
    dataframe = apply_weld_status_to_dataframe(project, pd.DataFrame(rows, columns=list(labels.values())))
    return _drop_unused_material_unit_columns(project, dataframe)


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


def _sync_library_dataframe(project, source_key, display_name, dataframe, differential=False):
    dataframe = dataframe.drop(
        columns=MATERIAL_LIBRARY_EXCLUDED_COLUMNS.get(source_key, set()),
        errors='ignore',
    )
    existing_source = None
    if isinstance(getattr(project, 'pk', None), int):
        existing_source = DataSourceFile.objects.filter(
            project=project,
            source_type='library',
            source_key=source_key,
        ).order_by('-id').first()
    relative_path = existing_source.relative_path if existing_source is not None else f'database://library/{source_key}'
    model = LIBRARY_MODELS[source_key].get('Sheet1') or LIBRARY_MODELS[source_key].get('*')
    sheet_name = 'Sheet1'
    if existing_source is not None:
        existing_sheet = model.objects.filter(source_file=existing_source).values_list('sheet_name', flat=True).first()
        if existing_sheet is not None:
            sheet_name = existing_sheet
    source = sync_dataframes(
        project,
        'library',
        source_key,
        display_name,
        relative_path,
        {sheet_name: dataframe},
        LIBRARY_MODELS[source_key],
        differential=differential,
    )
    source.sheet_columns = {
        sheet_name: [
            column
            for column in model_field_labels(model).values()
            if column not in MATERIAL_LIBRARY_EXCLUDED_COLUMNS.get(source_key, set())
        ],
    }
    source.save(update_fields=['sheet_columns'])
    return source


def _inherit_material_inventory_state(dataframe, existing_dataframe, key_columns, state_columns):
    """Preserve database-maintained inventory counters when rebuilding from arrivals."""
    if dataframe is None or dataframe.empty or existing_dataframe is None or existing_dataframe.empty:
        return dataframe
    out = dataframe.copy()
    existing_by_key = {}
    for _, row in existing_dataframe.fillna('').iterrows():
        key = tuple(_clean_text_key(row.get(column, '')) for column in key_columns)
        if any(key):
            existing_by_key[key] = row
    for index, row in out.fillna('').iterrows():
        key = tuple(_clean_text_key(row.get(column, '')) for column in key_columns)
        existing = existing_by_key.get(key)
        if existing is None:
            continue
        for column in state_columns:
            if column in existing.index and existing.get(column, '') not in (None, ''):
                out.at[index, column] = existing.get(column)
    return out


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


def _row_boolean(row, *columns):
    for column in columns:
        if column not in row:
            continue
        value = row.get(column)
        if value in (None, ''):
            continue
        return coerce_boolean(value)
    return None


def _date_value(value):
    return _text_value(value).replace('-', '')[:8]


def _stage_payload_for_row(row, plan_key):
    if plan_key == 'anti-corrosion':
        allowed = ANTI_CORROSION_STAGE_COLUMNS
    else:
        allowed = None
    excluded = PLAN_STAGE_EXCLUDED_COLUMNS
    payload = {}
    for key, value in row.items():
        text_key = str(key)
        if text_key.startswith('_') or text_key in MASTER_COMMON_STAGE_COLUMNS or text_key in excluded:
            continue
        if allowed is not None and text_key not in allowed:
            continue
        payload[text_key] = _text_value(value)
    return {plan_key: payload}


def _master_defaults_from_row(row, plan_key, plan_date):
    defaults = {
        'source_sheet': _row_first(row, future_schedule.SOURCE_SHEET_COL, '_source_sheet_name'),
        'priority': _row_first(row, '优先级'),
        'material_arrival_status': _row_boolean(row, COLUMNS['material_arrival_status'], '材料到货状态', '到货状态'),
        'material_anti_corrosion_status': _row_boolean(row, COLUMNS['material_anti_corrosion_status'], '材料防腐状态', '防腐状态'),
        'material_cutting_status': _row_boolean(row, COLUMNS['material_cutting_status'], '材料下料状态', '下料状态'),
        'unit': _row_first(row, COLUMNS['unit']),
        'pipeline': _row_first(row, COLUMNS['pipeline']),
        'segment_no': _row_first(row, COLUMNS['segment_no']),
        'weld_no_start': _row_first(row, COLUMNS['weld_no_start']),
        'weld_no_final': _row_first(row, COLUMNS['weld_no_final']),
        'diameter': _row_first(row, COLUMNS['diameter']),
        'wall_thickness': _row_first(row, COLUMNS['thickness']),
        'material': _row_first(row, COLUMNS['material']),
        'completed_flag': _row_boolean(row, COLUMNS['completed_flag'], '是否完成'),
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
    prepared_rows = []
    for _, source_row in dataframe.fillna('').iterrows():
        row = source_row.to_dict()
        row['_project'] = project
        library_seq = _row_first(row, '库序号')
        if not library_seq:
            continue
        defaults = _master_defaults_from_row(row, plan_key, str(plan_date or ''))
        prepared_rows.append((library_seq, row, defaults))

    if not prepared_rows:
        return 0

    common_data_by_seq = _sync_weld_common_data_many(
        project,
        [row for _, row, _ in prepared_rows],
    )
    _sync_weld_status_values(project, [
        {
            'library_seq': library_seq,
            'priority': defaults.get('priority', ''),
            'material_arrival_status': defaults.get('material_arrival_status', ''),
            'material_anti_corrosion_status': defaults.get('material_anti_corrosion_status', ''),
            'material_cutting_status': defaults.get('material_cutting_status', ''),
            'completed_flag': defaults.get('completed_flag', ''),
        }
        for library_seq, _, defaults in prepared_rows
    ])

    library_seqs = {library_seq for library_seq, _, _ in prepared_rows}
    records_by_seq = {
        record.library_seq: record
        for record in MasterScheduleRow.objects.filter(
            project=project,
            library_seq__in=library_seqs,
        )
    }
    existing_seqs = set(records_by_seq)
    create_rows = []
    update_rows_by_seq = {}
    update_fields = set()
    updated_at = timezone.now()

    for library_seq, _, defaults in prepared_rows:
        defaults['common_data'] = common_data_by_seq.get(library_seq)
        if plan_key == start_stage:
            defaults['production_start_stage'] = plan_key
            defaults['production_start_date'] = defaults.get(PLAN_STAGE_FIELDS[plan_key], '')
        record = records_by_seq.get(library_seq)
        if record is None:
            create_defaults = {
                field_name: False if field_name in MASTER_BOOLEAN_STATUS_FIELDS and value is None else value
                for field_name, value in defaults.items()
            }
            record = MasterScheduleRow(project=project, library_seq=library_seq, **create_defaults)
            records_by_seq[library_seq] = record
            create_rows.append(record)
        else:
            merged = _merge_master_defaults(record, defaults)
            if not record.production_start_stage and plan_key == start_stage:
                merged['production_start_stage'] = plan_key
                merged['production_start_date'] = defaults.get(PLAN_STAGE_FIELDS[plan_key], '')
            for field_name, value in merged.items():
                setattr(record, field_name, value)
            if library_seq in existing_seqs:
                record.updated_at = updated_at
                update_rows_by_seq[library_seq] = record
                update_fields.update(merged)

    if create_rows:
        MasterScheduleRow.objects.bulk_create(create_rows, batch_size=500)
    if update_rows_by_seq and update_fields:
        MasterScheduleRow.objects.bulk_update(
            list(update_rows_by_seq.values()),
            [*sorted(update_fields), 'updated_at'],
            batch_size=500,
        )
    return len(prepared_rows)


def _merge_master_schedule_frames(dataframes):
    """Collapse staged workbook rows so each library row is synchronized once."""
    combined = pd.concat(dataframes, ignore_index=True, sort=False).fillna('')
    if combined.empty or '库序号' not in combined.columns:
        return combined

    def latest_non_empty(values):
        for value in reversed(values.tolist()):
            if value not in (None, ''):
                return value
        return ''

    return combined.groupby('库序号', sort=False, as_index=False).agg(latest_non_empty)


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
        row.save(update_fields=[*clear_fields, 'stage_payload', 'production_start_stage', 'production_start_date', 'updated_at'])
        cleared_master_rows += 1
    return {
        'librarySeqs': sorted(affected_seqs),
        'planFolders': {plan_key: [plan_folder]},
        'deletedSources': deleted_sources,
        'deletedRecords': deleted_records,
        'clearedMasterRows': cleared_master_rows,
        'deletedMasterRows': deleted_master_rows,
    }


def _library_seqs_from_anti_corrosion_material_rows(rows):
    library_seqs = set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        for column in ('关联库序号', '库序号'):
            for value in _split_joined_values(row.get(column, '')):
                text = _clean_text_key(value)
                if text:
                    library_seqs.add(text)
    return library_seqs


def _clear_anti_corrosion_stage_rows(project, queryset):
    cleared_master_rows = 0
    deleted_master_rows = 0
    for row in queryset:
        row.anti_corrosion_order_no = ''
        row.anti_corrosion_date = ''
        payload = dict(row.stage_payload or {})
        payload.pop('anti-corrosion', None)
        row.stage_payload = payload
        if row.production_start_stage == 'anti-corrosion':
            row.production_start_stage = ''
            row.production_start_date = ''
        if row.cut_date or row.weld_date:
            row.save(update_fields=[
                'anti_corrosion_order_no',
                'anti_corrosion_date',
                'stage_payload',
                'production_start_stage',
                'production_start_date',
                'updated_at',
            ])
            cleared_master_rows += 1
        else:
            row.delete()
            deleted_master_rows += 1
    return cleared_master_rows, deleted_master_rows


def reconcile_anti_corrosion_material_order_plan(project, plan_folder, rows):
    plan_folder = str(plan_folder or '').strip()
    if not plan_folder:
        return {
            'deletedSources': 0,
            'deletedRecords': 0,
            'clearedMasterRows': 0,
            'deletedMasterRows': 0,
        }
    if not rows:
        return delete_plan_stage(project, 'anti-corrosion', plan_folder)

    retained_seqs = _library_seqs_from_anti_corrosion_material_rows(rows)
    stale_queryset = MasterScheduleRow.objects.filter(
        project=project,
        anti_corrosion_date=plan_folder,
    )
    if retained_seqs:
        stale_queryset = stale_queryset.exclude(library_seq__in=retained_seqs)
    cleared_master_rows, deleted_master_rows = _clear_anti_corrosion_stage_rows(project, stale_queryset)
    if not MasterScheduleRow.objects.filter(project=project, anti_corrosion_date=plan_folder).exists():
        deleted_sources, _ = DataSourceFile.objects.filter(
            project=project,
            source_type='plan',
            source_key__startswith=f'anti-corrosion:{plan_folder}:',
        ).delete()
        deleted_records, _ = PlanRecord.objects.filter(
            project=project,
            plan_key='anti-corrosion',
            plan_folder=plan_folder,
        ).delete()
    else:
        deleted_sources = 0
        deleted_records = 0
    return {
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
    normalized_file_names = _plan_record_file_names(plan_key, file_names)
    files = [
        {
            'name': file_name,
            'path': f'{folder_name}/{plan_date}/{file_name}',
            'size': 0,
            'updatedAt': now_ts,
        }
        for file_name in normalized_file_names
    ]
    record, _ = PlanRecord.objects.update_or_create(
        project=project,
        plan_key=plan_key,
        plan_folder=plan_date,
        defaults={
            'plan_name': plan_name,
            'plan_date': plan_date,
            'relative_path': f'database://plan/{plan_key}/{plan_date}',
            'file_count': len(normalized_file_names),
            'folder_updated_at': now_ts,
            'files': files,
            'summary': summary or {},
        },
    )
    return record


def _plan_record_file_names(plan_key, file_names):
    names = [
        str(file_name or '').strip()
        for file_name in (file_names or [])
        if str(file_name or '').strip()
    ]
    if plan_key == 'anti-corrosion':
        order = {
            ANTI_CORROSION_MATERIAL_ORDER_FILE_NAME: 0,
            ANTI_CORROSION_WELD_ORDER_FILE_NAME: 1,
        }
        names = sorted(names, key=lambda name: (order.get(name, 99), name))
    return list(dict.fromkeys(names))


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
                .filter(
                    project=project,
                    source_file__source_type='plan',
                    **{date_field: record.plan_date},
                )
                .values('library_seq', 'cut_order_no', 'weld_order_no', 'diameter')
            )
            if not rows:
                continue
            unique_rows = {}
            for index, row in enumerate(rows):
                library_seq = str(row.get('library_seq') or '').strip()
                unique_rows.setdefault(library_seq or f'__row_{index}', row)
            rows = list(unique_rows.values())
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
            summary = {
                'orderNumbers': order_numbers,
                'relatedOrderNumbers': related_order_numbers,
                'orderCount': len(order_numbers),
                'weldCount': len(rows),
                'diameterTotal': round(diameter_total, 3),
            }
            if record.summary != summary:
                record.summary = summary
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


def strip_cutting_plan_columns(columns, rows, project=None):
    hidden_columns = set(CUTTING_HIDDEN_DATA_COLUMNS)
    visible_columns = [
        column for column in (columns or [])
        if column not in hidden_columns
    ]
    if len(visible_columns) == len(columns or []):
        return visible_columns, rows
    return visible_columns, [
        {column: row.get(column, '') for column in visible_columns}
        for row in (rows or [])
    ]


def strip_welding_plan_columns(project, columns, rows):
    rows = _fill_welding_plan_anti_corrosion_references(project, rows)
    hidden_columns = set(WELDING_HIDDEN_DATA_COLUMNS)
    visible_columns = [column for column in (columns or []) if column not in hidden_columns]
    if len(visible_columns) == len(columns or []):
        return visible_columns, rows
    return visible_columns, [
        {column: row.get(column, '') for column in visible_columns}
        for row in (rows or [])
    ]


def _fill_welding_plan_anti_corrosion_references(project, rows):
    sequences = {
        str(row.get(COLUMNS['library_seq']) or '').strip()
        for row in (rows or [])
        if str(row.get(COLUMNS['library_seq']) or '').strip()
    }
    if not sequences:
        return rows
    references = {
        row['library_seq']: row
        for row in MasterScheduleRow.objects.filter(project=project, library_seq__in=sequences).values(
            'library_seq', 'anti_corrosion_order_no', 'anti_corrosion_date'
        )
    }
    enriched = []
    for source_row in rows:
        row = dict(source_row)
        reference = references.get(str(row.get(COLUMNS['library_seq']) or '').strip(), {})
        if not str(row.get('防腐委托单号') or '').strip():
            row['防腐委托单号'] = reference.get('anti_corrosion_order_no', '')
        if not str(row.get('防腐日期') or '').strip():
            row['防腐日期'] = reference.get('anti_corrosion_date', '')
        enriched.append(row)
    return enriched


def _is_anti_corrosion_commission_file(file_name):
    return str(file_name or '') == ANTI_CORROSION_WELD_ORDER_FILE_NAME


def _is_anti_corrosion_material_order_file(file_name):
    return str(file_name or '') == ANTI_CORROSION_MATERIAL_ORDER_FILE_NAME


def _is_anti_corrosion_plan_workbook_file(file_name):
    return _is_anti_corrosion_commission_file(file_name) or _is_anti_corrosion_material_order_file(file_name)


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
        if file_name and file_name != ANTI_CORROSION_WELD_ORDER_FILE_NAME:
            continue
        row = {column: payload.get(column, '') for column in ANTI_CORROSION_WELD_ORDER_COLUMNS}
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
        *ANTI_CORROSION_WELD_ORDER_COLUMNS,
        *[column for row in rows for column in row.keys()],
    ]))
    return pd.DataFrame(rows, columns=columns)


def _anti_corrosion_plan_summary(project, plan_date):
    rows = list(
        MasterScheduleRow.objects
        .filter(project=project, anti_corrosion_date=str(plan_date or ''))
        .values('anti_corrosion_order_no', 'diameter', 'stage_payload')
    )
    commission_numbers = set()
    commission_area = 0.0
    diameter_total = 0.0
    for row in rows:
        payload = dict((row.get('stage_payload') or {}).get('anti-corrosion') or {})
        commission_no = str(payload.get('防腐委托单号') or row.get('anti_corrosion_order_no') or '').strip()
        if commission_no:
            commission_numbers.add(commission_no)
        area = pd.to_numeric(payload.get('防腐面积'), errors='coerce')
        if pd.notna(area):
            commission_area += float(area)
        diameter = pd.to_numeric(row.get('diameter'), errors='coerce')
        if pd.notna(diameter):
            diameter_total += float(diameter)

    material_orders = list(
        AntiCorrosionMaterialOrderRow.objects
        .filter(
            project=project,
            source_file__source_type='plan',
            commission_date=str(plan_date or ''),
        )
        .values('anti_corrosion_order_no', 'commission_area')
    )
    if material_orders:
        commission_numbers = {
            str(row.get('anti_corrosion_order_no') or '').strip()
            for row in material_orders
            if str(row.get('anti_corrosion_order_no') or '').strip()
        }
        commission_area = sum(
            float(row.get('commission_area') or 0)
            for row in material_orders
        )
    return {
        'orderNumbers': sorted(commission_numbers),
        'orderCount': len(commission_numbers),
        'commissionCount': len(commission_numbers),
        'commissionArea': round(commission_area, 4),
        'weldCount': len(rows),
        'diameterTotal': round(diameter_total, 3),
    }


def refresh_plan_record_summaries(project):
    """Refresh chip summaries from the current plan tables, including legacy records."""
    updated = backfill_plan_record_summaries(project)
    ensure_project_tables(project)
    with using_project_tables(project):
        records = list(PlanRecord.objects.filter(project=project, plan_key='anti-corrosion'))
        for record in records:
            summary = _anti_corrosion_plan_summary(project, record.plan_date)
            if record.summary != summary:
                record.summary = summary
                record.save(update_fields=['summary', 'updated_at'])
                updated += 1
    return updated


def _sync_plan_output_files(project, output_files):
    record_groups = {}
    for output_file in output_files:
        file_name = output_file['file_name']
        plan_key = output_file['plan_key']
        plan_date = output_file['plan_date']
        sheet_models = _plan_file_models(file_name)
        if sheet_models is None:
            if plan_key != 'anti-corrosion' or not _is_anti_corrosion_plan_workbook_file(file_name):
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
        sync_to_master = output_file.get('master', True)
        if plan_key == 'anti-corrosion' and not _is_anti_corrosion_commission_file(file_name):
            sync_to_master = False
        if sync_to_master and plan_key in {'anti-corrosion', 'cutting', 'welding'}:
            frames = _workbook_frames(output_file.get('sheets'))
            if frames:
                _sync_master_schedule_rows(project, plan_key, plan_date, pd.concat(frames, ignore_index=True, sort=False))
        if output_file.get('record', True):
            record_key = (plan_key, output_file['plan_name'], plan_date)
            record_files = record_groups.setdefault(record_key, [])
            if plan_key == 'cutting' and file_name == CUTTING_PRIMARY_PLAN_FILE_NAME:
                record_files.extend(CUTTING_PLAN_FILE_NAMES)
            else:
                record_files.append(file_name)

    for (plan_key, plan_name, plan_date), file_names in record_groups.items():
        summary = _anti_corrosion_plan_summary(project, plan_date) if plan_key == 'anti-corrosion' else None
        _sync_plan_record(
            project,
            plan_key,
            plan_name,
            plan_date,
            list(dict.fromkeys(file_names)),
            summary=summary,
        )


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


def _cutting_plan_dataframe(project, plan_folder=None):
    """Read the independent cutting order instead of borrowing welding orders."""
    labels = model_field_labels(WeldingPlanRow)
    field_names = list(labels.keys())
    queryset = WeldingPlanRow.objects.filter(
        project=project,
        source_file__source_type='plan',
        source_file__display_name=CUTTING_PRIMARY_PLAN_FILE_NAME,
        source_file__source_key__startswith='cutting:',
    )
    if plan_folder:
        queryset = queryset.filter(
            source_file__source_key=f'cutting:{plan_folder}:{CUTTING_PRIMARY_PLAN_FILE_NAME}'
        )
    queryset = queryset.order_by('source_file_id', 'sheet_name', 'row_index')
    rows = [
        {labels[field_name]: row.get(field_name, '') for field_name in field_names}
        for row in queryset.values(*field_names)
    ]
    return pd.DataFrame(rows, columns=list(labels.values()))


def cutting_primary_plan_payload_from_master(project, plan_folder, sheet_name=None):
    """Rebuild cutting-plan worksheets retained in the master schedule."""
    records = list(
        MasterScheduleRow.objects
        .filter(project=project, cut_date=str(plan_folder or ''))
        .exclude(source_sheet='')
        .select_related('common_data')
        .order_by('source_sheet', 'id')
    )
    if not records:
        return None

    def sheet_sort_key(value):
        text = str(value or '')
        return (0, int(text)) if text.isdigit() else (1, text)

    sheet_names = sorted({str(record.source_sheet) for record in records}, key=sheet_sort_key)
    selected_sheet = sheet_name if sheet_name in sheet_names else sheet_names[0]
    plan_labels = model_field_labels(WeldingPlanRow)
    common_labels = model_field_labels(WeldCommonData)
    master_labels = model_field_labels(MasterScheduleRow)
    rows = []
    for record in records:
        if str(record.source_sheet) != selected_sheet:
            continue
        row = dict((record.stage_payload or {}).get('cutting') or {})
        if record.common_data is not None:
            for field_name, label in common_labels.items():
                row[label] = getattr(record.common_data, field_name, '')
        for field_name, label in master_labels.items():
            if field_name != 'stage_payload':
                row[label] = getattr(record, field_name, '')
        row[plan_labels['plan_folder']] = str(plan_folder or '')
        row[plan_labels['plan_date']] = str(plan_folder or '')
        rows.append(row)

    columns = list(plan_labels.values())
    return {
        'sheet': selected_sheet,
        'sheets': sheet_names,
        'total': len(rows),
        'columns': columns,
        'rows': [{column: row.get(column, '') for column in columns} for row in rows],
    }


def _anti_corrosion_commission_dataframe(project, plan_folder=None):
    return _anti_corrosion_commission_dataframe_from_master(project, plan_folder=plan_folder)


def _anti_corrosion_material_order_dataframe_from_master(project, plan_folder=None):
    commission_df = _anti_corrosion_commission_dataframe_from_master(project, plan_folder=plan_folder)
    if commission_df.empty:
        return pd.DataFrame()
    detail_df = _anti_corrosion_match_detail_dataframe(project)
    pipe_df, _, _ = _source_dataframe(project, 'library', 'pipe-library', PipeMaterialRow)
    fitting_df, _, _ = _source_dataframe(project, 'library', 'fitting-library', FittingMaterialRow)
    anti_pipe_df, _, _ = _source_dataframe(project, 'library', 'anti-pipe-library', PipeMaterialRow)
    anti_fitting_df, _, _ = _source_dataframe(project, 'library', 'anti-fitting-library', FittingMaterialRow)
    if pipe_df.empty:
        pipe_df = _model_dataframe(PipeMaterialRow, project, source_file__source_key='pipe-library')
    if fitting_df.empty:
        fitting_df = _model_dataframe(FittingMaterialRow, project, source_file__source_key='fitting-library')
    if anti_pipe_df.empty:
        anti_pipe_df = _model_dataframe(PipeMaterialRow, project, source_file__source_key='anti-pipe-library')
    if anti_fitting_df.empty:
        anti_fitting_df = _model_dataframe(FittingMaterialRow, project, source_file__source_key='anti-fitting-library')
    material_df, _, _ = _build_anti_corrosion_material_and_weld_orders(
        commission_df,
        detail_df,
        pipe_df,
        fitting_df,
        anti_pipe_df,
        anti_fitting_df,
        preserve_commissions=True,
    )
    return material_df


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


def _clean_text_key(value):
    text = str(value or '').strip()
    return '' if text.lower() == 'nan' else text


def _clean_joined(values):
    cleaned = []
    for value in values or []:
        text = _clean_text_key(value)
        if text and text not in cleaned:
            cleaned.append(text)
    return '、'.join(cleaned)


def _first_positive_number(row, columns, fallback=0.0):
    for column in columns:
        value = _numeric_value(row.get(column), 0)
        if value > 0:
            return value
    return _numeric_value(fallback, 0)


def _rows_by_key(dataframe, column):
    if dataframe is None or dataframe.empty or column not in dataframe.columns:
        return {}
    rows = {}
    for _, row in dataframe.iterrows():
        key = _clean_text_key(row.get(column, ''))
        if key and key not in rows:
            rows[key] = row.to_dict()
    return rows


def _key_set(dataframe, column):
    if dataframe is None or dataframe.empty or column not in dataframe.columns:
        return set()
    return {
        _clean_text_key(value)
        for value in dataframe[column]
        if _clean_text_key(value)
    }


def _material_order_key_text(key):
    return '\x1f'.join(_clean_text_key(part) for part in key)


def _numeric_value(value, default=0.0):
    try:
        if value is None or value == '':
            raise InvalidOperation
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        number = Decimal(str(default or 0))
    return number


def _add_numeric_field(row, column, value):
    row[column] = _numeric_value(row.get(column), 0.0) + _numeric_value(value, 0.0)


def _format_decimal_value(value, decimal_places=4):
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return ''
    quant = Decimal('1').scaleb(-decimal_places)
    number = number.quantize(quant, rounding=ROUND_HALF_UP)
    text = format(number, 'f')
    return text.rstrip('0').rstrip('.') if '.' in text else text


def _normalize_material_order_numbers(dataframe):
    if dataframe is None or dataframe.empty:
        return dataframe
    out = dataframe.copy()
    for column in ['委托数量', '焊口需求数量', '匹配数量', '委托面积', '已完成面积']:
        if column in out.columns:
            out[column] = out[column].map(lambda value: _format_decimal_value(value, 4))
    if '单位面积' in out.columns:
        out['单位面积'] = out['单位面积'].map(lambda value: _format_decimal_value(value, 6))
    if '防腐面积' in out.columns:
        out['防腐面积'] = out['防腐面积'].map(lambda value: _format_decimal_value(value, 4))
    return out


def _merge_material_order_detail_quantities(row, detail, include_commission_qty=False):
    demand_qty = _numeric_value(detail.get('需求数量'), 0)
    matched_qty = _numeric_value(detail.get('匹配数量'), 0)
    if demand_qty:
        _add_numeric_field(row, '焊口需求数量', demand_qty)
    if matched_qty:
        _add_numeric_field(row, '匹配数量', matched_qty)
        if include_commission_qty:
            _add_numeric_field(row, '委托数量', matched_qty)


def _demand_identity(demands):
    identity = {
        'codes': set(),
        'uniques': set(),
        'pairs': set(),
    }
    for demand in demands:
        material_code = _clean_text_key(demand.get(pre_matcher.MATERIAL_CODE_COL, ''))
        material_unique = _clean_text_key(demand.get(pre_matcher.MATERIAL_UNIQUE_COL, ''))
        if material_code:
            identity['codes'].add(material_code)
        if material_unique:
            identity['uniques'].add(material_unique)
        if material_code or material_unique:
            identity['pairs'].add((material_code, material_unique))
    return identity


def _anti_corrosion_demand_identity(row):
    pipe_demands, fitting_demands = anti_pre_matcher._anti_corrosion_demands(row)
    return _demand_identity(pipe_demands), _demand_identity(fitting_demands)


def _has_demand_identity(identity):
    return bool(identity.get('codes') or identity.get('uniques'))


def _detail_matches_demand_identity(detail, identity):
    material_code = _clean_text_key(detail.get(pre_matcher.MATERIAL_CODE_COL, ''))
    material_unique = _clean_text_key(detail.get(pre_matcher.MATERIAL_UNIQUE_COL, ''))
    pairs = identity.get('pairs', set())
    if material_unique and ((material_code, material_unique) in pairs or material_unique in identity.get('uniques', set())):
        return True
    return bool(material_code and material_code in identity.get('codes', set()))


def _indexed_detail_rows(detail_df):
    if detail_df is None or detail_df.empty:
        return {}, {}

    work_df = detail_df.copy()
    if pre_matcher.MATCH_RESULT_COL in work_df.columns:
        work_df = work_df.loc[
            work_df[pre_matcher.MATCH_RESULT_COL].fillna('').astype(str).str.strip().eq(MATCHED_STATUS)
        ].copy()
    if work_df.empty:
        return {}, {}

    by_library_seq = {}
    by_pre_schedule_seq = {}
    records = work_df.fillna('').to_dict('records')
    for record in records:
        library_seq = _clean_text_key(record.get('库序号', ''))
        pre_schedule_seq = _clean_text_key(record.get(pre_matcher.MATCH_SEQ_COL, record.get('预排产序号', '')))
        if library_seq:
            by_library_seq.setdefault(library_seq, []).append(record)
        if pre_schedule_seq:
            by_pre_schedule_seq.setdefault(pre_schedule_seq, []).append(record)
    return by_library_seq, by_pre_schedule_seq


def _detail_records_for_weld(detail_by_library_seq, detail_by_pre_schedule_seq, row):
    library_seq = _clean_text_key(row.get('库序号', ''))
    pre_schedule_seq = _clean_text_key(row.get(pre_matcher.MATCH_SEQ_COL, row.get('预排产序号', '')))
    records = []
    seen = set()
    for record in detail_by_library_seq.get(library_seq, []):
        marker = id(record)
        if marker in seen:
            continue
        seen.add(marker)
        records.append(record)
    for record in detail_by_pre_schedule_seq.get(pre_schedule_seq, []):
        marker = id(record)
        if marker in seen:
            continue
        seen.add(marker)
        records.append(record)
    return records


def _material_order_row_from_pipe(pipe_row, detail, row, pipe_no):
    out = dict(pipe_row or {})
    material_code = _clean_text_key(out.get(pre_matcher.MATERIAL_CODE_COL, detail.get(pre_matcher.MATERIAL_CODE_COL, '')))
    matched_qty = _numeric_value(detail.get('匹配数量'), 0)
    demand_qty = _numeric_value(detail.get('需求数量'), 0)
    full_qty = _first_positive_number(
        out,
        ['原始米数', '库存数量（米）', pre_matcher.REMAINING_LENGTH_COL],
        fallback=matched_qty or demand_qty,
    )
    out.update({
        '材料类型': '管子',
        '材料库类型': '管子材料库',
        pre_matcher.MATERIAL_CODE_COL: material_code,
        pre_matcher.MATERIAL_UNIQUE_COL: _clean_text_key(detail.get(pre_matcher.MATERIAL_UNIQUE_COL, '')),
        '委托数量': full_qty,
        '焊口需求数量': demand_qty,
        '匹配数量': matched_qty,
        pre_matcher.MATCHED_RESOURCE_COL: pipe_no,
        '已完成面积': Decimal('0'),
    })
    return out


def _material_order_row_from_fitting(fitting_row, detail, row):
    out = dict(fitting_row or {})
    material_code = _clean_text_key(out.get(pre_matcher.MATERIAL_CODE_COL, detail.get(pre_matcher.MATERIAL_CODE_COL, '')))
    matched_qty = _numeric_value(detail.get('匹配数量'), 0)
    demand_qty = _numeric_value(detail.get('需求数量'), 0)
    qty = matched_qty if matched_qty > 0 else demand_qty
    out.update({
        '材料类型': '管件法兰',
        '材料库类型': '管件法兰材料库',
        pre_matcher.MATERIAL_CODE_COL: material_code,
        pre_matcher.MATERIAL_UNIQUE_COL: _clean_text_key(detail.get(pre_matcher.MATERIAL_UNIQUE_COL, '')),
        '委托数量': qty,
        '焊口需求数量': demand_qty,
        '匹配数量': qty,
        pre_matcher.MATCHED_RESOURCE_COL: material_code,
        '已完成面积': Decimal('0'),
    })
    return out


def _finalize_anti_corrosion_material_rows(material_rows):
    if not material_rows:
        return pd.DataFrame()
    normalized_rows = []
    for row in material_rows:
        out = dict(row)
        out['关联库序号'] = _clean_joined(out.pop('_related_library_seqs', []))
        out['关联预排产序号'] = _clean_joined(out.pop('_related_pre_schedule_seqs', []))
        out.pop('_related_weld_rows', None)
        normalized_rows.append(out)
    material_df = pd.DataFrame(normalized_rows)
    material_df = material_df.drop(columns=[pre_matcher.PIPE_UNIQUE_CODE_COL, '管子唯一编号'], errors='ignore')
    material_df = add_anti_corrosion_area(material_df, '委托数量')
    if '防腐面积' in material_df.columns:
        material_df['委托面积'] = material_df['防腐面积']
    if '已完成面积' not in material_df.columns:
        material_df['已完成面积'] = 0.0
    leading_cols = [
        '防腐委托单号',
        '委托日期',
        '材料类型',
        pre_matcher.MATERIAL_CODE_COL,
        pre_matcher.MATERIAL_UNIQUE_COL,
        '委托数量',
        '焊口需求数量',
        '匹配数量',
        '单位面积',
        '委托面积',
        '已完成面积',
        '关联库序号',
        '关联预排产序号',
        pre_matcher.MATCHED_RESOURCE_COL,
        '材料库类型',
    ]
    leading_cols = [column for column in leading_cols if column in material_df.columns]
    remaining_cols = [column for column in material_df.columns if column not in leading_cols]
    return _normalize_material_order_numbers(material_df[leading_cols + remaining_cols])


def _split_anti_corrosion_order_by_material_area(
    material_df,
    commission_area,
    options,
):
    assigned_df = build_anti_corrosion_commission_from_pre_schedule(
        material_df,
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
    if assigned_df.empty:
        return assigned_df
    rename_map = {}
    if '防腐面积' in assigned_df.columns and '委托面积' not in assigned_df.columns:
        rename_map['防腐面积'] = '委托面积'
    assigned_df = assigned_df.rename(columns=rename_map)
    return assigned_df


def _build_anti_corrosion_material_and_weld_orders(
    pre_df,
    detail_df,
    pipe_df,
    fitting_df,
    anti_pipe_df,
    anti_fitting_df,
    commission_area=1500,
    preserve_commissions=False,
    options=None,
):
    options = options or {}
    if pre_df is None or pre_df.empty:
        return pd.DataFrame(), pd.DataFrame(), 0

    detail_by_library_seq, detail_by_pre_schedule_seq = _indexed_detail_rows(detail_df)
    # 防腐库表示“需要防腐”的材料池，而不是“已经防腐”的材料池。生成委托时
    # 应优先从防腐库取得材料属性，不能因为材料已进入防腐库就将其排除。
    pipe_by_no = {
        **_rows_by_key(pipe_df, pre_matcher.PIPE_UNIQUE_CODE_COL),
        **_rows_by_key(anti_pipe_df, pre_matcher.PIPE_UNIQUE_CODE_COL),
    }
    fitting_by_code = {
        **_rows_by_key(fitting_df, pre_matcher.MATERIAL_CODE_COL),
        **_rows_by_key(anti_fitting_df, pre_matcher.MATERIAL_CODE_COL),
    }

    material_by_key = {}
    material_unique_to_key = {}
    missing_detail_count = 0
    pre_records = pre_df.fillna('').to_dict('records')
    for row in pre_records:
        pipe_identity, fitting_identity = _anti_corrosion_demand_identity(row)
        if not _has_demand_identity(pipe_identity) and not _has_demand_identity(fitting_identity):
            continue
        row_details = _detail_records_for_weld(detail_by_library_seq, detail_by_pre_schedule_seq, row)
        if not row_details:
            missing_detail_count += 1
            continue
        library_seq = _clean_text_key(row.get('库序号', ''))
        pre_schedule_seq = _clean_text_key(row.get(pre_matcher.MATCH_SEQ_COL, row.get('预排产序号', '')))
        commission_no = _clean_text_key(row.get('防腐委托单号', '')) if preserve_commissions else ''
        commission_date = _clean_text_key(row.get('委托日期', '')) if preserve_commissions else ''

        for detail in row_details:
            material_type = _clean_text_key(detail.get(pre_matcher.MATCH_TYPE_COL, ''))
            material_code = _clean_text_key(detail.get(pre_matcher.MATERIAL_CODE_COL, ''))
            material_unique = _clean_text_key(detail.get(pre_matcher.MATERIAL_UNIQUE_COL, ''))
            if '管子' in material_type:
                if not _detail_matches_demand_identity(detail, pipe_identity):
                    continue
                pipe_no = _clean_text_key(detail.get(pre_matcher.MATCHED_RESOURCE_COL, ''))
                if not pipe_no:
                    continue
                key = ('pipe', pipe_no, commission_no, commission_date) if preserve_commissions else ('pipe', pipe_no)
                unique_key = ('pipe', material_unique) if material_unique else None
                if unique_key and unique_key in material_unique_to_key and material_unique_to_key[unique_key] in material_by_key:
                    target = material_by_key[material_unique_to_key[unique_key]]
                else:
                    if key not in material_by_key:
                        material_by_key[key] = _material_order_row_from_pipe(pipe_by_no.get(pipe_no, {}), detail, row, pipe_no)
                        material_by_key[key]['_material_order_key'] = _material_order_key_text(key)
                    else:
                        _merge_material_order_detail_quantities(material_by_key[key], detail, include_commission_qty=False)
                    if unique_key:
                        material_unique_to_key[unique_key] = key
                    target = material_by_key[key]
            elif '管件法兰' in material_type:
                if not _detail_matches_demand_identity(detail, fitting_identity):
                    continue
                key = ('fitting', material_code, commission_no, commission_date) if preserve_commissions else ('fitting', material_code)
                unique_key = ('fitting', material_unique) if material_unique else None
                if unique_key and unique_key in material_unique_to_key and material_unique_to_key[unique_key] in material_by_key:
                    target = material_by_key[material_unique_to_key[unique_key]]
                else:
                    if key not in material_by_key:
                        material_by_key[key] = _material_order_row_from_fitting(fitting_by_code.get(material_code, {}), detail, row)
                        material_by_key[key]['_material_order_key'] = _material_order_key_text(key)
                    else:
                        _merge_material_order_detail_quantities(material_by_key[key], detail, include_commission_qty=True)
                    if unique_key:
                        material_unique_to_key[unique_key] = key
                    target = material_by_key[key]
            else:
                continue

            target.setdefault('_related_library_seqs', []).append(library_seq)
            target.setdefault('_related_pre_schedule_seqs', []).append(pre_schedule_seq)
            target.setdefault('_related_weld_rows', []).append(row)
            if preserve_commissions:
                target['防腐委托单号'] = commission_no
                target['委托日期'] = commission_date

    material_rows = list(material_by_key.values())
    material_df = _finalize_anti_corrosion_material_rows(material_rows)
    if material_df.empty:
        return material_df, pd.DataFrame(), missing_detail_count

    if preserve_commissions:
        assigned_material_df = material_df.copy()
    else:
        assigned_material_df = _split_anti_corrosion_order_by_material_area(material_df, commission_area, options)

    weld_rows = []
    if not assigned_material_df.empty:
        material_related_welds = {
            _clean_text_key(row.get('_material_order_key', '')): list(row.get('_related_weld_rows', []))
            for row in material_by_key.values()
            if _clean_text_key(row.get('_material_order_key', ''))
        }
        for _, material_row in assigned_material_df.iterrows():
            commission_no = _clean_text_key(material_row.get('防腐委托单号', ''))
            commission_date = _clean_text_key(material_row.get('委托日期', ''))
            seen_in_group = {
                _clean_text_key(row.get('库序号', ''))
                for row in weld_rows
                if _clean_text_key(row.get('防腐委托单号', '')) == commission_no
                and _clean_text_key(row.get('委托日期', '')) == commission_date
            }
            material_key = _clean_text_key(material_row.get('_material_order_key', ''))
            for weld_row in material_related_welds.get(material_key, []):
                library_seq = _clean_text_key(weld_row.get('库序号', ''))
                if library_seq in seen_in_group:
                    continue
                out = dict(weld_row)
                out['防腐委托单号'] = commission_no
                out['委托日期'] = commission_date
                out[COLUMNS['material_anti_corrosion_status']] = out.get(COLUMNS['material_anti_corrosion_status']) or False
                weld_rows.append(out)
                seen_in_group.add(library_seq)

    assigned_material_df = assigned_material_df.drop(columns=['_material_order_key'], errors='ignore')

    weld_df = pd.DataFrame(weld_rows)
    if not weld_df.empty:
        if '防腐面积' in weld_df.columns:
            weld_df['防腐面积'] = weld_df['防腐面积'].map(lambda value: _format_decimal_value(value, 4))
        leading_cols = [
            '防腐委托单号',
            '委托日期',
            '预排产序号',
            '防腐面积',
            '库序号',
        ]
        leading_cols = [column for column in leading_cols if column in weld_df.columns]
        remaining_cols = [column for column in weld_df.columns if column not in leading_cols]
        weld_df = weld_df[leading_cols + remaining_cols]
    return assigned_material_df, weld_df, missing_detail_count


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
            sheet_name = (
                ANTI_CORROSION_WELD_ORDER_SHEET_NAME
                if file_name == ANTI_CORROSION_WELD_ORDER_FILE_NAME
                else '防腐委托单'
            )
            result[file_name] = {
                sheet_name: _anti_corrosion_commission_dataframe_from_master(
                    project,
                    plan_folder=plan_folder,
                    file_name=file_name,
                ),
            }
    if plan_key == 'anti-corrosion' and ANTI_CORROSION_MATERIAL_ORDER_FILE_NAME in requested:
        result[ANTI_CORROSION_MATERIAL_ORDER_FILE_NAME] = {
            ANTI_CORROSION_MATERIAL_ORDER_SHEET_NAME: _anti_corrosion_material_order_dataframe_from_master(
                project,
                plan_folder=plan_folder,
            ),
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
        cutting_df = _cutting_plan_dataframe(project, plan_folder=plan_folder)
        # Compatibility for historical plans created before cutting orders were
        # stored independently.
        if cutting_df.empty:
            cutting_df = _welding_plan_dataframe(project, cut_date=plan_folder)
        detail_sheets = {
            sheet_name: dataframe.drop(columns=list(CUTTING_HIDDEN_DATA_COLUMNS), errors='ignore')
            for sheet_name, dataframe in _cutting_detail_sheets_from_welding_plan(cutting_df).items()
        }
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
    cleanup_expired_staged_plan_outputs(project)
    stage_token = uuid.uuid4().hex
    staged_files = []
    for output_file in output_files:
        file_name = output_file['file_name']
        plan_key = output_file['plan_key']
        plan_date = output_file['plan_date']
        sheet_models = _plan_file_models(file_name)
        if sheet_models is None:
            if plan_key != 'anti-corrosion' or not _is_anti_corrosion_plan_workbook_file(file_name):
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


def _delete_staged_sources(queryset):
    sources = list(queryset.only('source_key'))
    if not sources:
        return 0
    queryset.delete()
    for source in sources:
        STAGED_PLAN_WORKBOOKS.pop(source.source_key, None)
    return len(sources)


def discard_staged_plan_outputs(project, stage_token):
    token = str(stage_token or '').strip()
    if not token:
        return 0
    ensure_project_tables(project)
    with using_project_tables(project), transaction.atomic():
        return _delete_staged_sources(DataSourceFile.objects.filter(
            project=project,
            source_type='plan-stage',
            source_key__startswith=f'{token}:',
        ))


def cleanup_expired_staged_plan_outputs(project, ttl=STAGED_PLAN_TTL):
    cutoff = (timezone.now() - ttl).timestamp()
    ensure_project_tables(project)
    with using_project_tables(project), transaction.atomic():
        return _delete_staged_sources(DataSourceFile.objects.filter(
            project=project,
            source_type='plan-stage',
            file_updated_at__lt=cutoff,
        ))


def commit_staged_plan_outputs(project, stage_token):
    cleanup_expired_staged_plan_outputs(project)
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
        master_sync_frames = {}
        for source in sources:
            parsed = _parse_stage_source_key(source.source_key)
            if not parsed:
                continue
            _, plan_key, plan_date, file_name = parsed
            sheet_models = _plan_file_models(file_name)
            workbook_payload = {}
            if sheet_models is None:
                if plan_key != 'anti-corrosion' or not _is_anti_corrosion_plan_workbook_file(file_name):
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
            should_sync_master = plan_key in {'anti-corrosion', 'cutting', 'welding'}
            if plan_key == 'anti-corrosion' and not _is_anti_corrosion_commission_file(file_name):
                should_sync_master = False
            if frames and should_sync_master:
                master_sync_frames.setdefault((plan_key, plan_date), []).extend(frames)
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
                welding_frame = pd.concat(frames, ignore_index=True, sort=False)
                for cut_date in cut_dates:
                    frame = welding_frame
                    frame = frame.loc[frame[future_schedule.CUT_DATE_COL].fillna('').astype(str).str.strip().eq(cut_date)].copy()
                    master_sync_frames.setdefault(('cutting', cut_date), []).append(frame)
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
            elif plan_key == 'cutting' and file_name == CUTTING_PRIMARY_PLAN_FILE_NAME:
                record_groups.setdefault(record_key, set()).update(CUTTING_PLAN_FILE_NAMES)
            else:
                record_groups.setdefault(record_key, set()).add(file_name)
        for (plan_key, plan_date), dataframes in master_sync_frames.items():
            _sync_master_schedule_rows(
                project,
                plan_key,
                plan_date,
                _merge_master_schedule_frames(dataframes),
            )

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
        normalized_file_names = _plan_record_file_names(plan_key, sorted(file_names))
        summary = _anti_corrosion_plan_summary(project, plan_date) if plan_key == 'anti-corrosion' else None
        _sync_plan_record(
            project,
            plan_key,
            plan_name,
            plan_date,
            normalized_file_names,
            summary=summary,
        )
        for file_name in normalized_file_names:
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
        ordinary_arrival_df, anti_arrival_df = split_arrival_materials_by_anti_corrosion(arrival_df)
        existing_pipe_df = _model_dataframe(PipeMaterialRow, project, source_file__source_key='pipe-library')
        existing_fitting_df = _model_dataframe(FittingMaterialRow, project, source_file__source_key='fitting-library')
        existing_anti_pipe_df = _model_dataframe(PipeMaterialRow, project, source_file__source_key='anti-pipe-library')
        existing_anti_fitting_df = _model_dataframe(FittingMaterialRow, project, source_file__source_key='anti-fitting-library')

        pipe_df = build_pipe_material_library(ordinary_arrival_df)
        fitting_df = build_fitting_flange_material_library(ordinary_arrival_df)
        anti_pipe_df = add_anti_corrosion_area(build_pipe_material_library(anti_arrival_df), PIPE_STOCK_QTY_COL)
        anti_fitting_df = add_anti_corrosion_area(build_fitting_flange_material_library(anti_arrival_df), STOCK_QTY_COL)

        ordinary_pipe_state_columns = [
            PIPE_STOCK_QTY_COL, LOCKED_QTY_COL, USED_QTY_COL, pre_matcher.REMAINING_LENGTH_COL,
            pre_matcher.CUT_LENGTHS_COL, pre_matcher.CUT_LOSSES_COL, pre_matcher.CONSUMED_LENGTHS_COL,
        ]
        ordinary_fitting_state_columns = [STOCK_QTY_COL, LOCKED_QTY_COL, USED_QTY_COL]
        anti_pipe_state_columns = [
            PIPE_STOCK_QTY_COL, ANTI_CORROSION_STOCK_QTY_COL,
            COATED_LOCKED_QTY_COL, UNCOATED_LOCKED_QTY_COL, USED_QTY_COL,
            pre_matcher.REMAINING_LENGTH_COL, pre_matcher.CUT_LENGTHS_COL,
            pre_matcher.CUT_LOSSES_COL, pre_matcher.CONSUMED_LENGTHS_COL,
        ]
        anti_fitting_state_columns = [
            STOCK_QTY_COL, ANTI_CORROSION_STOCK_QTY_COL,
            COATED_LOCKED_QTY_COL, UNCOATED_LOCKED_QTY_COL, USED_QTY_COL,
        ]
        pipe_df = _inherit_material_inventory_state(
            pipe_df, existing_pipe_df, [pre_matcher.PIPE_UNIQUE_CODE_COL], ordinary_pipe_state_columns
        )
        fitting_df = _inherit_material_inventory_state(
            fitting_df, existing_fitting_df, [pre_matcher.MATERIAL_CODE_COL], ordinary_fitting_state_columns
        )
        anti_pipe_df = _inherit_material_inventory_state(
            anti_pipe_df, existing_anti_pipe_df, [pre_matcher.PIPE_UNIQUE_CODE_COL], anti_pipe_state_columns
        )
        anti_fitting_df = _inherit_material_inventory_state(
            anti_fitting_df, existing_anti_fitting_df, [pre_matcher.MATERIAL_CODE_COL], anti_fitting_state_columns
        )
        _sync_library_dataframe(project, 'pipe-library', '管子材料库.xlsx', pipe_df)
        _sync_library_dataframe(project, 'fitting-library', '管件法兰材料库.xlsx', fitting_df)
        _sync_library_dataframe(project, 'anti-pipe-library', '防腐管子材料库.xlsx', anti_pipe_df)
        _sync_library_dataframe(project, 'anti-fitting-library', '防腐管件法兰材料库.xlsx', anti_fitting_df)
        return {
            'pipe_count': len(pipe_df),
            'fitting_count': len(fitting_df),
            'anti_pipe_count': len(anti_pipe_df),
            'anti_fitting_count': len(anti_fitting_df),
        }


class InitializationCancelledError(RuntimeError):
    pass


INITIALIZATION_FILTER_DEFAULTS = {
    'prefabWeldArea': True,
    'prefabMaterialType': True,
    'autoJointType': True,
    'autoWallThickness': True,
    'autoDiameter': True,
    'autoSegmentNo': True,
}


def maintain_weld_library_from_database(
    project,
    fill_material_units=True,
    initialization_filters=None,
    cancellation_check=None,
):
    def check_cancelled():
        if cancellation_check and cancellation_check():
            raise InitializationCancelledError('初始化任务已取消，数据变更已回滚')

    ensure_project_tables(project)
    with using_project_tables(project), transaction.atomic():
        check_cancelled()
        init_df = _model_dataframe(InitializationWeldRow, project)
        if init_df.empty:
            raise ValueError('数据库中没有焊口初始化数据，无法生成预制焊口库')
        if fill_material_units:
            init_df = _fill_material_units(init_df)

        check_cancelled()
        enabled_filters = {**INITIALIZATION_FILTER_DEFAULTS, **(initialization_filters or {})}
        prefab_filter_keys = {
            INIT_COLUMNS['weld_area']: 'prefabWeldArea',
            INIT_COLUMNS['material_type']: 'prefabMaterialType',
        }
        auto_filter_keys = {
            INIT_COLUMNS['joint_type']: 'autoJointType',
            INIT_COLUMNS['thickness']: 'autoWallThickness',
            INIT_COLUMNS['diameter']: 'autoDiameter',
        }
        prefab_filters = {
            column: condition
            for column, condition in PREFAB_WELD_FILTERS.items()
            if enabled_filters[prefab_filter_keys[column]]
        }
        auto_filters = {
            column: condition
            for column, condition in AUTO_WELD_FILTERS.items()
            if enabled_filters[auto_filter_keys[column]]
        }

        prefab_work_df = _coerce_filter_columns(init_df, prefab_filters)
        prefab_df, _ = filter_data(prefab_work_df, prefab_filters)
        if prefab_df is None or prefab_df.empty:
            raise ValueError('没有满足可预制规则的焊口初始化数据，无法生成预制焊口库')

        check_cancelled()
        auto_work_df = _coerce_filter_columns(prefab_df, auto_filters)
        auto_filter_df, _ = filter_data(auto_work_df, auto_filters)
        if enabled_filters['autoSegmentNo']:
            auto_filter_df = _drop_empty_segment_no(auto_filter_df)
        check_cancelled()
        auto_df = _auto_weld_dataframe(auto_filter_df)

        check_cancelled()
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

        check_cancelled()
        _sync_library_dataframe(project, 'weld-library', '预制焊口库.xlsx', library_df)
        check_cancelled()
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


def _number_value(value):
    number = pd.to_numeric(value, errors='coerce')
    return float(number) if pd.notna(number) else 0.0


def _add_inventory_value(dataframe, index, column, delta, precision=3):
    value = round(_number_value(dataframe.at[index, column]) + float(delta), precision)
    dataframe.at[index, column] = f'{value:g}'


def _apply_locked_quantity_deltas(before_df, after_df, is_pipe, track_corrosion=False):
    """Move quantities removed by matching into the explicit locked counter."""
    out = after_df.copy()
    if out.empty:
        return out
    if not track_corrosion and LOCKED_QTY_COL not in out.columns:
        out[LOCKED_QTY_COL] = 0
    if track_corrosion:
        for column in (COATED_LOCKED_QTY_COL, UNCOATED_LOCKED_QTY_COL):
            if column not in out.columns:
                out[column] = 0
    if is_pipe:
        for index in out.index.intersection(before_df.index):
            before = _number_value(before_df.at[index, pre_matcher.REMAINING_LENGTH_COL])
            after = _number_value(out.at[index, pre_matcher.REMAINING_LENGTH_COL])
            if before > after:
                delta = before - after
                if track_corrosion:
                    anti_available = _number_value(out.at[index, ANTI_CORROSION_STOCK_QTY_COL]) if ANTI_CORROSION_STOCK_QTY_COL in out else 0
                    coated_delta = min(anti_available, delta)
                    uncoated_delta = delta - coated_delta
                    if coated_delta > 0:
                        _add_inventory_value(out, index, COATED_LOCKED_QTY_COL, coated_delta)
                        out.at[index, ANTI_CORROSION_STOCK_QTY_COL] = f'{round(anti_available - coated_delta, 3):g}'
                    if uncoated_delta > 0:
                        _add_inventory_value(out, index, UNCOATED_LOCKED_QTY_COL, uncoated_delta)
                else:
                    _add_inventory_value(out, index, LOCKED_QTY_COL, delta)
        return out
    for index in out.index.intersection(before_df.index):
        before = _number_value(before_df.at[index, STOCK_QTY_COL])
        after = _number_value(out.at[index, STOCK_QTY_COL])
        if before > after:
            delta = before - after
            anti_available = _number_value(out.at[index, ANTI_CORROSION_STOCK_QTY_COL]) if ANTI_CORROSION_STOCK_QTY_COL in out else 0
            if track_corrosion:
                coated_delta = min(anti_available, delta)
                uncoated_delta = delta - coated_delta
                if coated_delta > 0:
                    _add_inventory_value(out, index, COATED_LOCKED_QTY_COL, coated_delta)
                    out.at[index, ANTI_CORROSION_STOCK_QTY_COL] = f'{round(anti_available - coated_delta, 3):g}'
                if uncoated_delta > 0:
                    _add_inventory_value(out, index, UNCOATED_LOCKED_QTY_COL, uncoated_delta)
            else:
                _add_inventory_value(out, index, LOCKED_QTY_COL, delta)
    return out


def _corroded_anti_material_library_seqs(detail_df, anti_pipe_df, anti_fitting_df):
    if detail_df is None or detail_df.empty:
        return set()
    pipe_stock = {}
    for _, row in anti_pipe_df.iterrows():
        resource = str(row.get(pre_matcher.PIPE_UNIQUE_CODE_COL, '') or '').strip()
        pipe_stock[resource] = _number_value(row.get(ANTI_CORROSION_STOCK_QTY_COL, 0))
    fitting_stock = {
        str(row.get(pre_matcher.MATERIAL_CODE_COL, '') or '').strip(): _number_value(
            row.get(ANTI_CORROSION_STOCK_QTY_COL, 0)
        )
        for _, row in anti_fitting_df.iterrows()
    }
    readiness = {}
    for detail in detail_df.fillna('').to_dict('records'):
        seq = str(detail.get(COLUMNS['library_seq'], '') or '').strip()
        if not seq:
            continue
        material_type = str(detail.get(pre_matcher.MATCH_TYPE_COL, '') or '')
        if not material_type.startswith(pre_matcher.ANTI_CORROSION_POOL):
            continue
        matched = str(detail.get(pre_matcher.MATCH_RESULT_COL, '') or '').strip() == MATCHED_STATUS
        ready = matched
        if '管子' in material_type:
            resource = str(detail.get(pre_matcher.MATCHED_RESOURCE_COL, '') or '').strip()
            demand_qty = _number_value(detail.get('需求数量'))
            consumed_qty = _parse_pipe_consumption_from_reason(
                detail.get(pre_matcher.MATCH_REASON_COL, ''), demand_qty
            )
            available = pipe_stock.get(resource, 0)
            ready = matched and consumed_qty > 0 and available >= consumed_qty
            if ready:
                pipe_stock[resource] = available - consumed_qty
        elif '管件法兰' in material_type:
            code = str(detail.get(pre_matcher.MATERIAL_CODE_COL, '') or '').strip()
            quantity = _number_value(detail.get('匹配数量'))
            current_stock = fitting_stock.get(code, 0)
            ready = (
                matched
                and quantity > 0
                and current_stock >= quantity
            )
            if ready:
                fitting_stock[code] = current_stock - quantity
        readiness[seq] = readiness.get(seq, True) and ready
    return {seq for seq, ready in readiness.items() if ready}


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


def _set_no_anti_corrosion_placeholders(project, library_seqs):
    library_seqs = {str(value or '').strip() for value in library_seqs if str(value or '').strip()}
    if not library_seqs:
        return 0
    return MasterScheduleRow.objects.filter(
        project=project,
        library_seq__in=library_seqs,
    ).update(
        anti_corrosion_order_no='/',
        anti_corrosion_date='/',
        updated_at=timezone.now(),
    )


RELEASED_MATERIAL_STATUS = '已释放材料'
RELEASED_MATERIAL_REASON = '用户释放材料锁定'


def _matched_detail_rows_for_library_seqs(detail_df, library_seqs):
    if detail_df.empty or COLUMNS['library_seq'] not in detail_df.columns:
        return detail_df.iloc[0:0].copy()
    seqs = {str(value or '').strip() for value in library_seqs if str(value or '').strip()}
    if not seqs:
        return detail_df.iloc[0:0].copy()
    matched_mask = detail_df[COLUMNS['library_seq']].fillna('').astype(str).str.strip().isin(seqs)
    if pre_matcher.MATCH_RESULT_COL in detail_df.columns:
        matched_mask &= detail_df[pre_matcher.MATCH_RESULT_COL].fillna('').astype(str).str.strip().eq(MATCHED_STATUS)
    return detail_df.loc[matched_mask].copy()


def _parse_pipe_consumption_from_reason(reason_text, demand_qty):
    match = re.search(r'占用\s*([0-9]+(?:\.[0-9]+)?)\s*米', str(reason_text or ''))
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass
    return float(demand_qty)


def _remove_pipe_allocation_from_row(row, demand_qty, consumed_qty, precision=3):
    cut_list = pre_matcher.cutting_main._parse_cut_lengths(row.get(pre_matcher.CUT_LENGTHS_COL, '[]'))
    loss_list = pre_matcher.cutting_main._parse_cut_lengths(row.get(pre_matcher.CUT_LOSSES_COL, '[]'))
    consumed_list = pre_matcher.cutting_main._parse_cut_lengths(row.get(pre_matcher.CONSUMED_LENGTHS_COL, '[]'))
    if not consumed_list:
        return row, 0.0

    demand_qty = round(float(demand_qty), precision)
    consumed_qty = round(float(consumed_qty), precision)
    remove_index = None
    for index, consumed in enumerate(consumed_list):
        cut_value = cut_list[index] if index < len(cut_list) else consumed
        if round(float(cut_value), precision) == demand_qty and round(float(consumed), precision) == consumed_qty:
            remove_index = index
            break
    if remove_index is None:
        for index, cut_value in enumerate(cut_list):
            if round(float(cut_value), precision) == demand_qty:
                remove_index = index
                break
    if remove_index is None:
        remove_index = len(consumed_list) - 1

    restored_consumed = float(consumed_list.pop(remove_index))
    if remove_index < len(cut_list):
        cut_list.pop(remove_index)
    if remove_index < len(loss_list):
        loss_list.pop(remove_index)
    current_remaining = pd.to_numeric(row.get(pre_matcher.REMAINING_LENGTH_COL), errors='coerce')
    row[pre_matcher.CUT_LENGTHS_COL] = pre_matcher.cutting_main._format_cut_lengths(cut_list)
    row[pre_matcher.CUT_LOSSES_COL] = pre_matcher.cutting_main._format_cut_lengths(loss_list)
    row[pre_matcher.CONSUMED_LENGTHS_COL] = pre_matcher.cutting_main._format_cut_lengths(consumed_list)
    row[pre_matcher.REMAINING_LENGTH_COL] = round(
        (float(current_remaining) if pd.notna(current_remaining) else 0.0) + restored_consumed,
        precision,
    )
    return row, restored_consumed


def _remove_pipe_allocations_from_row(row, allocations, precision=3):
    cut_list = pre_matcher.cutting_main._parse_cut_lengths(row.get(pre_matcher.CUT_LENGTHS_COL, '[]'))
    loss_list = pre_matcher.cutting_main._parse_cut_lengths(row.get(pre_matcher.CUT_LOSSES_COL, '[]'))
    consumed_list = pre_matcher.cutting_main._parse_cut_lengths(row.get(pre_matcher.CONSUMED_LENGTHS_COL, '[]'))
    if not consumed_list:
        return row, 0.0, 0

    restored_consumed = 0.0
    released_count = 0
    for demand_qty, consumed_qty in allocations:
        if not consumed_list:
            break
        demand_qty = round(float(demand_qty), precision)
        consumed_qty = round(float(consumed_qty), precision)
        remove_index = None
        for index, consumed in enumerate(consumed_list):
            cut_value = cut_list[index] if index < len(cut_list) else consumed
            if round(float(cut_value), precision) == demand_qty and round(float(consumed), precision) == consumed_qty:
                remove_index = index
                break
        if remove_index is None:
            for index, cut_value in enumerate(cut_list):
                if round(float(cut_value), precision) == demand_qty:
                    remove_index = index
                    break
        if remove_index is None:
            remove_index = len(consumed_list) - 1

        restored_consumed += float(consumed_list.pop(remove_index))
        if remove_index < len(cut_list):
            cut_list.pop(remove_index)
        if remove_index < len(loss_list):
            loss_list.pop(remove_index)
        released_count += 1

    current_remaining = pd.to_numeric(row.get(pre_matcher.REMAINING_LENGTH_COL), errors='coerce')
    row[pre_matcher.CUT_LENGTHS_COL] = pre_matcher.cutting_main._format_cut_lengths(cut_list)
    row[pre_matcher.CUT_LOSSES_COL] = pre_matcher.cutting_main._format_cut_lengths(loss_list)
    row[pre_matcher.CONSUMED_LENGTHS_COL] = pre_matcher.cutting_main._format_cut_lengths(consumed_list)
    row[pre_matcher.REMAINING_LENGTH_COL] = round(
        (float(current_remaining) if pd.notna(current_remaining) else 0.0) + restored_consumed,
        precision,
    )
    return row, restored_consumed, released_count


def _restore_locked_materials_from_details(pipe_df, fitting_df, detail_df):
    updated_pipe_df = pre_matcher._normalize_pipe_library_or_empty(pipe_df)
    updated_fitting_df = pre_matcher._normalize_fitting_library_or_empty(fitting_df)
    pipe_release_count = 0
    fitting_release_count = 0

    pipe_indexes_by_resource = {}
    if pre_matcher.PIPE_UNIQUE_CODE_COL in updated_pipe_df.columns:
        for index, value in updated_pipe_df[pre_matcher.PIPE_UNIQUE_CODE_COL].items():
            resource = str(value or '').strip()
            if resource:
                pipe_indexes_by_resource.setdefault(resource, index)

    fitting_indexes_by_code = {}
    if pre_matcher.MATERIAL_CODE_COL in updated_fitting_df.columns:
        for index, value in updated_fitting_df[pre_matcher.MATERIAL_CODE_COL].items():
            material_code = str(value or '').strip()
            if material_code:
                fitting_indexes_by_code.setdefault(material_code, index)

    pipe_allocations = {}
    fitting_quantities = {}
    fitting_counts = {}
    for detail in detail_df.to_dict('records'):
        material_type = str(detail.get(pre_matcher.MATCH_TYPE_COL, '') or '')
        material_code = str(detail.get(pre_matcher.MATERIAL_CODE_COL, '') or '').strip()
        resource = str(detail.get(pre_matcher.MATCHED_RESOURCE_COL, '') or '').strip()
        matched_qty = pd.to_numeric(detail.get('匹配数量'), errors='coerce')
        demand_qty = pd.to_numeric(detail.get('需求数量'), errors='coerce')
        if pd.isna(matched_qty) or float(matched_qty) <= 0:
            continue

        if '管子' in material_type:
            demand = float(demand_qty) if pd.notna(demand_qty) else float(matched_qty)
            consumed = _parse_pipe_consumption_from_reason(detail.get(pre_matcher.MATCH_REASON_COL, ''), demand)
            pipe_allocations.setdefault(resource, []).append((demand, consumed))
            continue

        if '管件法兰' in material_type:
            fitting_quantities[material_code] = fitting_quantities.get(material_code, 0.0) + float(matched_qty)
            fitting_counts[material_code] = fitting_counts.get(material_code, 0) + 1

    for resource, allocations in pipe_allocations.items():
        row_index = pipe_indexes_by_resource.get(resource)
        if row_index is None:
            continue
        row, restored, released_count = _remove_pipe_allocations_from_row(
            updated_pipe_df.loc[row_index].copy(),
            allocations,
        )
        updated_pipe_df.loc[row_index, row.index] = row
        if restored > 0:
            pipe_release_count += released_count

    for material_code, restored_quantity in fitting_quantities.items():
        row_index = fitting_indexes_by_code.get(material_code)
        if row_index is None:
            continue
        current_qty = pd.to_numeric(updated_fitting_df.at[row_index, pre_matcher.FITTING_STOCK_QTY_COL], errors='coerce')
        updated_fitting_df.at[row_index, pre_matcher.FITTING_STOCK_QTY_COL] = (
            float(current_qty) if pd.notna(current_qty) else 0.0
        ) + restored_quantity
        fitting_release_count += fitting_counts[material_code]

    return updated_pipe_df, updated_fitting_df, pipe_release_count, fitting_release_count


def _completed_anti_corrosion_resources(project):
    pipe_resources = set()
    fitting_codes = set()
    for row in AntiCorrosionMaterialOrderRow.objects.filter(project=project):
        if _number_value(row.commission_area) <= 0 or _number_value(row.commission_area) != _number_value(row.completed_area):
            continue
        if '管子' in str(row.material_type or ''):
            pipe_resources.add(str(row.matched_resource or '').strip())
        elif '管件法兰' in str(row.material_type or ''):
            fitting_codes.add(str(row.material_code or '').strip())
    return pipe_resources, fitting_codes


def _decrease_released_locked_quantities(
    pipe_df, fitting_df, detail_df, completed_resources=None, track_corrosion=False
):
    pipe_out = pipe_df.copy()
    fitting_out = fitting_df.copy()
    completed_pipe_resources, completed_fitting_codes = completed_resources or (set(), set())
    for detail in detail_df.fillna('').to_dict('records'):
        matched_qty = _number_value(detail.get('匹配数量'))
        if matched_qty <= 0:
            continue
        material_type = str(detail.get(pre_matcher.MATCH_TYPE_COL, ''))
        if '管子' in material_type:
            resource = str(detail.get(pre_matcher.MATCHED_RESOURCE_COL, '')).strip()
            mask = pipe_out[pre_matcher.PIPE_UNIQUE_CODE_COL].fillna('').astype(str).str.strip().eq(resource)
            if mask.any():
                index = pipe_out.index[mask][0]
                consumed = _parse_pipe_consumption_from_reason(
                    detail.get(pre_matcher.MATCH_REASON_COL, ''), matched_qty
                )
                if track_corrosion:
                    coated = min(_number_value(pipe_out.at[index, COATED_LOCKED_QTY_COL]), consumed)
                    if coated <= 0 and resource in completed_pipe_resources:
                        coated = consumed
                    uncoated = max(consumed - coated, 0)
                    pipe_out.at[index, COATED_LOCKED_QTY_COL] = f'{round(max(_number_value(pipe_out.at[index, COATED_LOCKED_QTY_COL]) - coated, 0), 3):g}'
                    pipe_out.at[index, UNCOATED_LOCKED_QTY_COL] = f'{round(max(_number_value(pipe_out.at[index, UNCOATED_LOCKED_QTY_COL]) - uncoated, 0), 3):g}'
                    if coated > 0:
                        _add_inventory_value(pipe_out, index, ANTI_CORROSION_STOCK_QTY_COL, coated)
                elif LOCKED_QTY_COL in pipe_out.columns:
                    pipe_out.at[index, LOCKED_QTY_COL] = f'{round(max(_number_value(pipe_out.at[index, LOCKED_QTY_COL]) - consumed, 0), 3):g}'
            continue
        if '管件法兰' in material_type:
            code = str(detail.get(pre_matcher.MATERIAL_CODE_COL, '')).strip()
            mask = fitting_out[pre_matcher.MATERIAL_CODE_COL].fillna('').astype(str).str.strip().eq(code)
            if mask.any():
                index = fitting_out.index[mask][0]
                if track_corrosion:
                    coated = min(_number_value(fitting_out.at[index, COATED_LOCKED_QTY_COL]), matched_qty)
                    if coated <= 0 and code in completed_fitting_codes:
                        coated = matched_qty
                    uncoated = max(matched_qty - coated, 0)
                    fitting_out.at[index, COATED_LOCKED_QTY_COL] = f'{round(max(_number_value(fitting_out.at[index, COATED_LOCKED_QTY_COL]) - coated, 0), 3):g}'
                    fitting_out.at[index, UNCOATED_LOCKED_QTY_COL] = f'{round(max(_number_value(fitting_out.at[index, UNCOATED_LOCKED_QTY_COL]) - uncoated, 0), 3):g}'
                    if coated > 0:
                        _add_inventory_value(fitting_out, index, ANTI_CORROSION_STOCK_QTY_COL, coated)
                elif LOCKED_QTY_COL in fitting_out.columns:
                    fitting_out.at[index, LOCKED_QTY_COL] = f'{round(max(_number_value(fitting_out.at[index, LOCKED_QTY_COL]) - matched_qty, 0), 3):g}'
    return pipe_out, fitting_out


def _restore_material_inventory_pools(
    pipe_df, fitting_df, anti_pipe_df, anti_fitting_df, detail_df, project=None
):
    material_types = detail_df.get(pre_matcher.MATCH_TYPE_COL, pd.Series('', index=detail_df.index))
    anti_mask = material_types.fillna('').astype(str).str.strip().str.startswith(pre_matcher.ANTI_CORROSION_POOL)
    ordinary_details = detail_df.loc[~anti_mask].copy()
    anti_details = detail_df.loc[anti_mask].copy()
    pipe_out, fitting_out, ordinary_pipe_count, ordinary_fitting_count = _restore_locked_materials_from_details(
        pipe_df, fitting_df, ordinary_details
    )
    anti_pipe_out, anti_fitting_out, anti_pipe_count, anti_fitting_count = _restore_locked_materials_from_details(
        anti_pipe_df, anti_fitting_df, anti_details
    )
    pipe_out, fitting_out = _decrease_released_locked_quantities(pipe_out, fitting_out, ordinary_details)
    anti_pipe_out, anti_fitting_out = _decrease_released_locked_quantities(
        anti_pipe_out,
        anti_fitting_out,
        anti_details,
        _completed_anti_corrosion_resources(project) if project is not None else None,
        track_corrosion=True,
    )
    return (
        pipe_out,
        fitting_out,
        anti_pipe_out,
        anti_fitting_out,
        ordinary_pipe_count + anti_pipe_count,
        ordinary_fitting_count + anti_fitting_count,
    )


def _locked_material_library_seqs(result_df):
    if result_df is None or result_df.empty or COLUMNS['library_seq'] not in result_df.columns:
        return set()
    mask = pd.Series(True, index=result_df.index)
    if STATUS_COL in result_df.columns:
        mask &= result_df[STATUS_COL].fillna('').astype(str).str.strip().eq(MATCHED_STATUS)
    return {
        str(value or '').strip()
        for value in result_df.loc[mask, COLUMNS['library_seq']]
        if str(value or '').strip()
    }


def _cutting_started_library_seqs(weld_df):
    if weld_df is None or weld_df.empty or COLUMNS['library_seq'] not in weld_df.columns:
        return set()
    cutting_col = COLUMNS['material_cutting_status']
    if cutting_col not in weld_df.columns:
        return set()
    cutting_mask = pre_matcher._to_bool_series(weld_df[cutting_col])
    return {
        str(value or '').strip()
        for value in weld_df.loc[cutting_mask, COLUMNS['library_seq']]
        if str(value or '').strip()
    }


def _release_reusable_material_locks_before_matching(
    project, weld_df, pipe_df, fitting_df, anti_pipe_df, anti_fitting_df
):
    result_df, _, _ = _source_dataframe(
        project,
        'pre-schedule',
        'material-locking',
        WeldPreScheduleRow,
        sheet_name='预排产匹配结果',
    )
    detail_df, _, _ = _source_dataframe(
        project,
        'pre-schedule',
        'material-locking',
        MaterialMatchDetailRow,
        sheet_name='材料匹配明细',
    )
    locked_seqs = _locked_material_library_seqs(result_df)
    if not locked_seqs:
        return pipe_df, fitting_df, anti_pipe_df, anti_fitting_df, set(), 0, 0, 0

    cutting_started_seqs = _cutting_started_library_seqs(weld_df)
    releasable_seqs = locked_seqs - cutting_started_seqs
    if not releasable_seqs:
        return (
            pipe_df, fitting_df, anti_pipe_df, anti_fitting_df,
            set(), 0, 0, len(locked_seqs & cutting_started_seqs),
        )

    release_details = _matched_detail_rows_for_library_seqs(detail_df, releasable_seqs)
    (
        updated_pipe_df, updated_fitting_df, updated_anti_pipe_df, updated_anti_fitting_df,
        pipe_release_count, fitting_release_count,
    ) = _restore_material_inventory_pools(
        pipe_df, fitting_df, anti_pipe_df, anti_fitting_df, release_details, project=project
    )
    return (
        updated_pipe_df,
        updated_fitting_df,
        updated_anti_pipe_df,
        updated_anti_fitting_df,
        releasable_seqs,
        pipe_release_count,
        fitting_release_count,
        len(locked_seqs & cutting_started_seqs),
    )


def release_material_locks_from_database(project, selected_library_seqs):
    selected_values = {
        str(value or '').strip()
        for value in (selected_library_seqs or [])
        if str(value or '').strip()
    }
    if not selected_values:
        raise ValueError('请至少选择一条材料匹配锁定结果')

    ensure_project_tables(project)
    with using_project_tables(project):
        result_df, source, _ = _source_dataframe(
            project,
            'pre-schedule',
            'material-locking',
            WeldPreScheduleRow,
            sheet_name='预排产匹配结果',
        )
        detail_df, _, _ = _source_dataframe(
            project,
            'pre-schedule',
            'material-locking',
            MaterialMatchDetailRow,
            sheet_name='材料匹配明细',
        )
        if source is None or result_df.empty:
            raise ValueError('数据库中没有材料匹配锁定结果，无法释放材料')
        seq_col = COLUMNS['library_seq']
        if seq_col not in result_df.columns:
            raise ValueError('材料匹配锁定结果缺少库序号，无法释放材料')

        weld_df, _, _ = _source_dataframe(project, 'library', 'weld-library', WeldLibraryRow)
        pipe_df, _, _ = _source_dataframe(project, 'library', 'pipe-library', PipeMaterialRow)
        fitting_df, _, _ = _source_dataframe(project, 'library', 'fitting-library', FittingMaterialRow)
        anti_pipe_df, _, _ = _source_dataframe(project, 'library', 'anti-pipe-library', PipeMaterialRow)
        anti_fitting_df, _, _ = _source_dataframe(project, 'library', 'anti-fitting-library', FittingMaterialRow)
        if weld_df.empty:
            weld_df = _model_dataframe(WeldLibraryRow, project, source_file__source_key='weld-library')
        if pipe_df.empty:
            pipe_df = _model_dataframe(PipeMaterialRow, project, source_file__source_key='pipe-library')
        if fitting_df.empty:
            fitting_df = _model_dataframe(FittingMaterialRow, project, source_file__source_key='fitting-library')
        if anti_pipe_df.empty:
            anti_pipe_df = _model_dataframe(PipeMaterialRow, project, source_file__source_key='anti-pipe-library')
        if anti_fitting_df.empty:
            anti_fitting_df = _model_dataframe(FittingMaterialRow, project, source_file__source_key='anti-fitting-library')

        cutting_started_seqs = _cutting_started_library_seqs(weld_df)
        releasable_seqs = selected_values - cutting_started_seqs
        if not releasable_seqs:
            return {
                'selected_count': len(selected_values),
                'released_count': 0,
                'skipped_completed_count': len(selected_values & cutting_started_seqs),
                'pipe_release_count': 0,
                'fitting_release_count': 0,
            }

        release_details = _matched_detail_rows_for_library_seqs(detail_df, releasable_seqs)
        (
            updated_pipe_df,
            updated_fitting_df,
            updated_anti_pipe_df,
            updated_anti_fitting_df,
            pipe_release_count,
            fitting_release_count,
        ) = _restore_material_inventory_pools(
            pipe_df,
            fitting_df,
            anti_pipe_df,
            anti_fitting_df,
            release_details,
            project=project,
        )
        _sync_library_dataframe(project, 'pipe-library', '管子材料库', updated_pipe_df)
        _sync_library_dataframe(project, 'fitting-library', '管件法兰材料库', updated_fitting_df)
        _sync_library_dataframe(project, 'anti-pipe-library', '防腐管子材料库', updated_anti_pipe_df)
        _sync_library_dataframe(project, 'anti-fitting-library', '防腐管件法兰材料库', updated_anti_fitting_df)

        result_df = result_df.copy()
        release_mask = result_df[seq_col].fillna('').astype(str).str.strip().isin(releasable_seqs)
        locked_release_mask = release_mask
        if STATUS_COL in result_df.columns:
            locked_release_mask &= result_df[STATUS_COL].fillna('').astype(str).str.strip().eq(MATCHED_STATUS)
            result_df.loc[locked_release_mask, STATUS_COL] = RELEASED_MATERIAL_STATUS
        if pre_matcher.MATCH_SEQ_COL in result_df.columns:
            result_df.loc[locked_release_mask, pre_matcher.MATCH_SEQ_COL] = ''
        if pre_matcher.REASON_COL in result_df.columns:
            result_df.loc[locked_release_mask, pre_matcher.REASON_COL] = RELEASED_MATERIAL_REASON
        released_count = int(locked_release_mask.sum())

        if not detail_df.empty and seq_col in detail_df.columns:
            keep_mask = ~detail_df[seq_col].fillna('').astype(str).str.strip().isin(releasable_seqs)
            detail_df = detail_df.loc[keep_mask].copy()

        sync_dataframes(
            project,
            'pre-schedule',
            'material-locking',
            '材料匹配锁定结果.xlsx',
            'database://pre-schedule/material-locking/材料匹配锁定结果.xlsx',
            {'预排产匹配结果': result_df, '材料匹配明细': detail_df},
            PRE_SCHEDULE_MODELS,
        )

        _sync_weld_status_values(project, [
            {
                'library_seq': library_seq,
                'material_arrival_status': False,
                'material_anti_corrosion_status': False,
            }
            for library_seq in releasable_seqs
        ])

        return {
            'selected_count': len(selected_values),
            'released_count': released_count,
            'skipped_completed_count': len(selected_values & cutting_started_seqs),
            'pipe_release_count': pipe_release_count,
            'fitting_release_count': fitting_release_count,
        }


def match_and_lock_materials_from_database(
    project,
    only_auto_weld=False,
    concentration_dimension=None,
    concentration_threshold_percent=None,
    selection_mode='auto',
    selected_library_seqs=None,
):
    ensure_project_tables(project)
    with using_project_tables(project):
        weld_df, _, _ = _source_dataframe(project, 'library', 'weld-library', WeldLibraryRow)
        pipe_df, _, _ = _source_dataframe(project, 'library', 'pipe-library', PipeMaterialRow)
        fitting_df, _, _ = _source_dataframe(project, 'library', 'fitting-library', FittingMaterialRow)
        anti_pipe_df, _, _ = _source_dataframe(project, 'library', 'anti-pipe-library', PipeMaterialRow)
        anti_fitting_df, _, _ = _source_dataframe(project, 'library', 'anti-fitting-library', FittingMaterialRow)
        if weld_df.empty:
            weld_df = _model_dataframe(WeldLibraryRow, project, source_file__source_key='weld-library')
        if pipe_df.empty:
            pipe_df = _model_dataframe(PipeMaterialRow, project, source_file__source_key='pipe-library')
        if fitting_df.empty:
            fitting_df = _model_dataframe(FittingMaterialRow, project, source_file__source_key='fitting-library')
        if anti_pipe_df.empty:
            anti_pipe_df = _model_dataframe(PipeMaterialRow, project, source_file__source_key='anti-pipe-library')
        if anti_fitting_df.empty:
            anti_fitting_df = _model_dataframe(FittingMaterialRow, project, source_file__source_key='anti-fitting-library')
        if weld_df.empty:
            raise ValueError('数据库中预制焊口库为空，无法进行材料匹配锁定')
        if pipe_df.empty and fitting_df.empty and anti_pipe_df.empty and anti_fitting_df.empty:
            raise ValueError('数据库中没有可用材料库存，无法进行材料匹配锁定')

        (
            pipe_df,
            fitting_df,
            anti_pipe_df,
            anti_fitting_df,
            reusable_released_seqs,
            reusable_pipe_release_count,
            reusable_fitting_release_count,
            skipped_cutting_started_count,
        ) = _release_reusable_material_locks_before_matching(
            project, weld_df, pipe_df, fitting_df, anti_pipe_df, anti_fitting_df
        )

        pipe_df = pre_matcher._normalize_pipe_library_or_empty(pipe_df)
        fitting_df = pre_matcher._normalize_fitting_library_or_empty(fitting_df)
        anti_pipe_df = pre_matcher._normalize_pipe_library_or_empty(anti_pipe_df)
        anti_fitting_df = pre_matcher._normalize_fitting_library_or_empty(anti_fitting_df)
        pipe_states_by_pool = {
            pre_matcher.ORDINARY_POOL: pre_matcher._build_pipe_states(pipe_df),
            pre_matcher.ANTI_CORROSION_POOL: pre_matcher._build_pipe_states(anti_pipe_df),
        }
        fitting_stock_by_pool = {
            pre_matcher.ORDINARY_POOL: pre_matcher._build_fitting_stock(fitting_df),
            pre_matcher.ANTI_CORROSION_POOL: pre_matcher._build_fitting_stock(anti_fitting_df),
        }

        selection_mode = str(selection_mode or 'auto').strip().lower()
        if selection_mode not in {'auto', 'manual'}:
            raise ValueError('材料匹配选择方式无效')
        selected_values = {
            str(value or '').strip()
            for value in (selected_library_seqs or [])
            if str(value or '').strip()
        }

        candidate_df = pre_matcher._prepare_uncompleted_welds(weld_df, only_auto_weld=only_auto_weld)
        cutting_col = COLUMNS['material_cutting_status']
        if cutting_col in candidate_df.columns:
            candidate_df = candidate_df.loc[~pre_matcher._to_bool_series(candidate_df[cutting_col])].copy()
        seq_col = COLUMNS['library_seq']
        if selection_mode == 'manual':
            if not selected_values:
                raise ValueError('手动选择模式下请至少选择一条预制焊口记录')
            if seq_col not in candidate_df.columns:
                raise ValueError('预制焊口库缺少库序号，无法按手动选择匹配材料')
            candidate_df = candidate_df.loc[
                candidate_df[seq_col].fillna('').astype(str).str.strip().isin(selected_values)
            ].copy()
            if candidate_df.empty:
                raise ValueError('选中的预制焊口没有可匹配的未完成记录')

        accepted_rows = []
        rejected_rows = []
        all_rows = []
        detail_rows = []
        match_seq = 1
        group_cols = [pre_matcher.COLUMNS['unit'], pre_matcher.COLUMNS['pipeline']]
        for _, group_df in candidate_df.groupby(group_cols, sort=False, dropna=False):
            group_result = pre_matcher._simulate_group_matches_by_inventory(
                group_df,
                pipe_states_by_pool,
                fitting_stock_by_pool,
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
            for pool, updates in group_result['pipe_state_updates_by_pool'].items():
                pipe_states_by_pool[pool].update(updates)
            for pool, updates in group_result['fitting_stock_updates_by_pool'].items():
                fitting_stock_by_pool[pool].update(updates)
            match_seq = group_result['next_seq']

        result_df = pd.DataFrame(all_rows)
        no_anti_corrosion_seqs = {
            str(row.get(seq_col, '')).strip()
            for row in accepted_rows
            if str(row.get(seq_col, '')).strip() and not _weld_requires_anti_corrosion(row)
        }
        if not result_df.empty:
            result_df['防腐委托单号'] = result_df.get('防腐委托单号', '')
            result_df['防腐日期'] = result_df.get('防腐日期', '')
            no_anti_mask = result_df[seq_col].fillna('').astype(str).str.strip().isin(no_anti_corrosion_seqs)
            result_df.loc[no_anti_mask, ['防腐委托单号', '防腐日期']] = '/'
        detail_df = pd.DataFrame(detail_rows, columns=pre_matcher.PRE_SCHEDULE_DETAIL_COLUMNS)
        corroded_anti_seqs = _corroded_anti_material_library_seqs(
            detail_df, anti_pipe_df, anti_fitting_df
        )
        updated_pipe_df = pre_matcher._apply_pipe_states_to_df(
            pipe_df, pipe_states_by_pool[pre_matcher.ORDINARY_POOL]
        )
        updated_fitting_df = pre_matcher._apply_fitting_stock_to_df(
            fitting_df, fitting_stock_by_pool[pre_matcher.ORDINARY_POOL]
        )
        updated_anti_pipe_df = pre_matcher._apply_pipe_states_to_df(
            anti_pipe_df, pipe_states_by_pool[pre_matcher.ANTI_CORROSION_POOL]
        )
        updated_anti_fitting_df = pre_matcher._apply_fitting_stock_to_df(
            anti_fitting_df, fitting_stock_by_pool[pre_matcher.ANTI_CORROSION_POOL]
        )
        updated_pipe_df = _apply_locked_quantity_deltas(pipe_df, updated_pipe_df, is_pipe=True)
        updated_fitting_df = _apply_locked_quantity_deltas(fitting_df, updated_fitting_df, is_pipe=False)
        updated_anti_pipe_df = _apply_locked_quantity_deltas(
            anti_pipe_df, updated_anti_pipe_df, is_pipe=True, track_corrosion=True
        )
        updated_anti_fitting_df = _apply_locked_quantity_deltas(
            anti_fitting_df, updated_anti_fitting_df, is_pipe=False, track_corrosion=True
        )

        weld_df = _ensure_weld_material_status_columns(weld_df)
        accepted_seqs = {
            str(row.get(seq_col, '')).strip()
            for row in accepted_rows
            if str(row.get(seq_col, '')).strip()
        }
        arrival_col = COLUMNS['material_arrival_status']
        anti_col = COLUMNS['material_anti_corrosion_status']
        arrived_count = 0
        pending_count = 0
        status_rows = [
            {
                'library_seq': library_seq,
                'material_arrival_status': False,
                'material_anti_corrosion_status': False,
            }
            for library_seq in reusable_released_seqs
        ]
        for _, row in weld_df.iterrows():
            library_seq = str(row.get(seq_col, '')).strip()
            if selection_mode == 'manual' and library_seq not in selected_values:
                continue
            if library_seq and library_seq in accepted_seqs:
                anti_status = not _weld_requires_anti_corrosion(row) or library_seq in corroded_anti_seqs
                status_rows.append({
                    'library_seq': library_seq,
                    'material_arrival_status': True,
                    'material_anti_corrosion_status': anti_status,
                })
                arrived_count += 1
            else:
                if library_seq:
                    status_rows.append({
                        'library_seq': library_seq,
                        'material_arrival_status': False,
                        'material_anti_corrosion_status': False,
                    })
                pending_count += 1
        with transaction.atomic():
            sync_dataframes(
                project,
                'pre-schedule',
                'material-locking',
                '材料匹配锁定结果.xlsx',
                'database://pre-schedule/material-locking/材料匹配锁定结果.xlsx',
                {'预排产匹配结果': result_df, '材料匹配明细': detail_df},
                PRE_SCHEDULE_MODELS,
                differential=True,
                update_common_data=False,
                sync_status=False,
            )
            _sync_library_dataframe(
                project,
                'pipe-library',
                '管子材料库.xlsx',
                updated_pipe_df,
                differential=True,
            )
            _sync_library_dataframe(
                project,
                'fitting-library',
                '管件法兰材料库.xlsx',
                updated_fitting_df,
                differential=True,
            )
            _sync_library_dataframe(
                project, 'anti-pipe-library', '防腐管子材料库', updated_anti_pipe_df, differential=True
            )
            _sync_library_dataframe(
                project, 'anti-fitting-library', '防腐管件法兰材料库', updated_anti_fitting_df, differential=True
            )
            _sync_weld_status_values(project, status_rows)
            _set_no_anti_corrosion_placeholders(project, no_anti_corrosion_seqs)

        return {
            'candidate_count': len(candidate_df),
            'locked_count': len(accepted_rows),
            'rejected_count': len(rejected_rows),
            'detail_count': len(detail_df),
            'arrived_count': arrived_count,
            'pending_count': pending_count,
            'pipe_count': len(updated_pipe_df),
            'fitting_count': len(updated_fitting_df),
            'released_previous_lock_count': len(reusable_released_seqs),
            'released_previous_pipe_count': reusable_pipe_release_count,
            'released_previous_fitting_count': reusable_fitting_release_count,
            'skipped_cutting_started_lock_count': skipped_cutting_started_count,
        }


def update_weld_material_arrival_status_from_database(project):
    result = match_and_lock_materials_from_database(project)
    return {
        'weld_count': result.get('candidate_count', 0),
        'arrived_count': result.get('arrived_count', 0),
        'pending_count': result.get('pending_count', 0),
        **result,
    }


def generate_anti_corrosion_schedule_from_database(
    project,
    commission_area=1500,
    selected_library_seqs=None,
    selection_mode='auto',
    persist=True,
    **options,
):
    ensure_project_tables(project)
    with using_project_tables(project):
        pre_df = options.pop('pre_schedule_dataframe', None)
        if pre_df is None:
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
        selection_mode = str(selection_mode or 'auto').strip().lower()
        if selection_mode not in {'auto', 'manual'}:
            raise ValueError('防腐委托选择方式无效')
        if selection_mode == 'manual' and not selected_values:
            raise ValueError('手动选择模式下请至少选择一条防腐预排产记录')
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

        detail_df = _anti_corrosion_match_detail_dataframe(project)
        pipe_df, _, _ = _source_dataframe(project, 'library', 'pipe-library', PipeMaterialRow)
        fitting_df, _, _ = _source_dataframe(project, 'library', 'fitting-library', FittingMaterialRow)
        anti_pipe_df, _, _ = _source_dataframe(project, 'library', 'anti-pipe-library', PipeMaterialRow)
        anti_fitting_df, _, _ = _source_dataframe(project, 'library', 'anti-fitting-library', FittingMaterialRow)
        if pipe_df.empty:
            pipe_df = _model_dataframe(PipeMaterialRow, project, source_file__source_key='pipe-library')
        if fitting_df.empty:
            fitting_df = _model_dataframe(FittingMaterialRow, project, source_file__source_key='fitting-library')
        if anti_pipe_df.empty:
            anti_pipe_df = _model_dataframe(PipeMaterialRow, project, source_file__source_key='anti-pipe-library')
        if anti_fitting_df.empty:
            anti_fitting_df = _model_dataframe(FittingMaterialRow, project, source_file__source_key='anti-fitting-library')

        material_df, weld_order_df, missing_detail_count = _build_anti_corrosion_material_and_weld_orders(
            pre_df,
            detail_df,
            pipe_df,
            fitting_df,
            anti_pipe_df,
            anti_fitting_df,
            commission_area=commission_area,
            options=options,
        )
        if material_df.empty:
            if missing_detail_count:
                raise ValueError('选中的防腐焊口缺少材料匹配明细，请先执行材料匹配与锁定')
            raise ValueError('选中的防腐焊口对应材料已在防腐库中，无需生成防腐委托')
        if weld_order_df.empty:
            raise ValueError('未找到材料单对应的焊口记录，无法生成防腐焊口单')

        output_files = []
        commission_dates = [
            value
            for value in material_df.get('委托日期', pd.Series(dtype=str)).fillna('').astype(str).str.strip().tolist()
            if value
        ]
        for commission_date in dict.fromkeys(commission_dates):
            material_part = material_df.loc[
                material_df['委托日期'].fillna('').astype(str).str.strip().eq(commission_date)
            ].copy()
            weld_part = weld_order_df.loc[
                weld_order_df['委托日期'].fillna('').astype(str).str.strip().eq(commission_date)
            ].copy()
            output_files.append({
                'plan_key': 'anti-corrosion',
                'plan_name': '防腐',
                'plan_date': commission_date or datetime.now().strftime('%Y%m%d'),
                'file_name': ANTI_CORROSION_MATERIAL_ORDER_FILE_NAME,
                'sheets': {ANTI_CORROSION_MATERIAL_ORDER_SHEET_NAME: material_part},
                'record': True,
                'master': False,
            })
            output_files.append({
                'plan_key': 'anti-corrosion',
                'plan_name': '防腐',
                'plan_date': commission_date or datetime.now().strftime('%Y%m%d'),
                'file_name': ANTI_CORROSION_WELD_ORDER_FILE_NAME,
                'sheets': {ANTI_CORROSION_WELD_ORDER_SHEET_NAME: weld_part},
                'record': True,
                'master': True,
            })
        if persist:
            _sync_plan_output_files(project, output_files)
        result = {
            'pre_schedule_count': len(pre_df),
            'summary_count': len(weld_order_df),
            'material_count': len(material_df),
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
    persist=True,
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
        if persist:
            sync_dataframes(
                project,
                'pre-schedule',
                'anti-corrosion-pre-schedule',
                '防腐预排产匹配结果.xlsx',
                'database://pre-schedule/anti-corrosion-pre-schedule/防腐预排产匹配结果.xlsx',
                {
                    '预排产匹配结果': result['result_df'],
                },
                PRE_SCHEDULE_MODELS,
            )
        payload = {
            key: value
            for key, value in result.items()
            if key not in {'result_df'}
        }
        if not persist:
            payload['_result_df'] = result['result_df']
        return payload


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
    enriched_extractions = _enrich_extractions_with_anti_corrosion_references(project, all_extractions)
    _sync_plan_output_files(project, _welding_primary_output_files(plan_date, enriched_extractions, cut_date=cut_date))
    _sync_plan_record(
        project,
        'welding',
        '焊接',
        plan_date,
        WELDING_PLAN_FILE_NAMES,
        summary=_schedule_plan_summary('welding', plan_date, all_extractions),
    )


def _enrich_extractions_with_anti_corrosion_references(project, all_extractions):
    sequences = {
        str(value or '').strip()
        for extraction in (all_extractions or [])
        for value in extraction.get('data', pd.DataFrame()).get(COLUMNS['library_seq'], [])
        if str(value or '').strip()
    }
    if not sequences:
        return all_extractions
    references = {
        row['library_seq']: row
        for row in MasterScheduleRow.objects.filter(project=project, library_seq__in=sequences).values(
            'library_seq', 'anti_corrosion_order_no', 'anti_corrosion_date'
        )
    }
    enriched = []
    for extraction in all_extractions:
        item = dict(extraction)
        dataframe = extraction.get('data')
        if dataframe is None or dataframe.empty:
            enriched.append(item)
            continue
        dataframe = dataframe.copy()
        order_numbers = []
        dates = []
        for value in dataframe[COLUMNS['library_seq']]:
            reference = references.get(str(value or '').strip(), {})
            order_numbers.append(reference.get('anti_corrosion_order_no', ''))
            dates.append(reference.get('anti_corrosion_date', ''))
        dataframe['防腐委托单号'] = order_numbers
        dataframe['防腐日期'] = dates
        item['data'] = dataframe
        enriched.append(item)
    return enriched


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


def _anti_corrosion_output_files(commission_date, all_extractions, commission_area=1500):
    frames = []
    order_index = 1
    limit = max(float(commission_area or 1500), 0.0)
    for extraction in all_extractions:
        sheet_name = str(extraction['info']['抽取次数'])
        df = extraction['data'].copy()
        if '防腐面积' in df.columns and limit > 0:
            running_area = 0.0
            order_numbers = []
            for _, row in df.iterrows():
                area = pd.to_numeric(row.get('防腐面积'), errors='coerce')
                area = float(area) if pd.notna(area) else 0.0
                if order_numbers and running_area > 0 and running_area + area > limit:
                    order_index += 1
                    running_area = 0.0
                order_numbers.append(f"AC{str(commission_date).replace('-', '')}-{order_index:03d}")
                running_area += area
            df['防腐委托单号'] = order_numbers
            order_index += 1
        else:
            df['防腐委托单号'] = f"AC{str(commission_date).replace('-', '')}-{order_index:03d}"
            order_index += 1
        df['委托日期'] = str(commission_date).replace('-', '')
        df['委托单防腐面积'] = limit
        df[future_schedule.SOURCE_SHEET_COL] = sheet_name
        frames.append(df)
    weld_df = pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()
    return [{
        'plan_key': 'anti-corrosion',
        'plan_name': '防腐',
        'plan_date': str(commission_date).replace('-', ''),
        'file_name': ANTI_CORROSION_WELD_ORDER_FILE_NAME,
        'sheets': {ANTI_CORROSION_WELD_ORDER_SHEET_NAME: weld_df},
        'record': True,
        'master': True,
    }]


def _cutting_output_files(cut_date, weld_date, all_extractions):
    plan_sheets = {
        str(item['info']['抽取次数']): future_schedule._build_welding_plan_for_sheet(
            str(item['info']['抽取次数']),
            item['data'],
            future_schedule._parse_schedule_date(cut_date),
            future_schedule._parse_schedule_date(weld_date),
        )
        for item in all_extractions
    }
    detail_sheets = {}
    summary_sheets = {}
    for extraction in all_extractions:
        sheet_name = str(extraction['info']['抽取次数'])
        detail_df = future_schedule._build_cut_detail_for_sheet(sheet_name, extraction['data'], cut_date, weld_date)
        detail_sheets[sheet_name] = detail_df
        summary_sheets[sheet_name] = future_schedule._build_cut_summary(detail_df)
    files = {
        CUTTING_PRIMARY_PLAN_FILE_NAME: plan_sheets,
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


def _cutting_schedule_source_from_master(project, pre_schedule_df):
    """Use the master schedule as the base and fill missing weld/material fields from pre-schedule rows."""
    if pre_schedule_df is None or pre_schedule_df.empty or COLUMNS['library_seq'] not in pre_schedule_df.columns:
        return pre_schedule_df.copy() if pre_schedule_df is not None else pd.DataFrame()

    sequence_column = COLUMNS['library_seq']
    sequences = [
        str(value or '').strip()
        for value in pre_schedule_df[sequence_column]
        if str(value or '').strip()
    ]
    field_labels = model_field_labels(MasterScheduleRow)
    excluded_fields = {'cut_order_no', 'cut_date', 'weld_order_no', 'weld_date', 'stage_payload'}
    reference_fields = [
        field_name
        for field_name in field_labels
        if field_name not in excluded_fields
    ]
    master_by_sequence = {
        str(row.get('library_seq') or '').strip(): {
            field_labels[field_name]: row.get(field_name)
            for field_name in reference_fields
        }
        for row in MasterScheduleRow.objects
        .filter(project=project, library_seq__in=sequences)
        .values(*reference_fields)
    }
    status_columns = {
        COLUMNS['material_arrival_status'],
        COLUMNS['material_anti_corrosion_status'],
        COLUMNS['material_cutting_status'],
        COLUMNS['completed_flag'],
    }
    rows = []
    for pre_schedule_row in pre_schedule_df.fillna('').to_dict('records'):
        sequence = str(pre_schedule_row.get(sequence_column) or '').strip()
        merged = dict(master_by_sequence.get(sequence) or {})
        for column, value in pre_schedule_row.items():
            current = merged.get(column)
            if column in status_columns or current in (None, '') or str(current).strip().lower() == 'nan':
                merged[column] = value
        rows.append(merged)
    return pd.DataFrame(rows)


def _build_cutting_plan_for_sheet(sheet_name, weld_df, cut_date):
    out = weld_df.copy()
    if out.empty:
        return out

    out = out.drop(columns=[
        '排产单号',
        *CUTTING_HIDDEN_DATA_COLUMNS,
    ], errors='ignore')
    out[future_schedule.CUT_ORDER_NO_COL] = f"QG-{future_schedule._date_text(cut_date)}-{sheet_name}"
    out[future_schedule.CUT_DATE_COL] = future_schedule._date_text(cut_date)
    out[future_schedule.SOURCE_SHEET_COL] = str(sheet_name)
    for side in (1, 2):
        unit_column = f'单位{side}'
        if unit_column not in out.columns:
            continue
        mark_column = COLUMNS[f'material_no_{side}']
        if mark_column not in out.columns:
            continue
        generated = out[mark_column].map(future_schedule._material_units_for_side)
        empty_mask = out[unit_column].fillna('').astype(str).str.strip().eq('')
        out.loc[empty_mask, unit_column] = generated.loc[empty_mask]

    leading_columns = [
        future_schedule.CUT_ORDER_NO_COL,
        future_schedule.CUT_DATE_COL,
        future_schedule.SOURCE_SHEET_COL,
    ]
    return out[[*leading_columns, *[column for column in out.columns if column not in leading_columns]]]


def _cutting_primary_output_files(cut_date, weld_date, all_extractions):
    plan_sheets = {
        str(item['info']['抽取次数']): _build_cutting_plan_for_sheet(
            str(item['info']['抽取次数']),
            item['data'],
            future_schedule._parse_schedule_date(cut_date),
        )
        for item in all_extractions
    }
    return [{
        'plan_key': 'cutting',
        'plan_name': '下料',
        'plan_date': cut_date,
        'file_name': CUTTING_PRIMARY_PLAN_FILE_NAME,
        'sheets': plan_sheets or {'Sheet1': pd.DataFrame()},
        'record': True,
    }]


def _sync_cutting_outputs(project, cut_date, weld_date, all_extractions):
    _sync_plan_output_files(project, [
        output_file
        for output_file in _cutting_output_files(cut_date, weld_date, all_extractions)
        if output_file['file_name'] == CUTTING_PRIMARY_PLAN_FILE_NAME
    ])
    _sync_master_schedule_rows(project, 'cutting', cut_date, _plan_rows_from_extractions(weld_date, all_extractions, cut_date=cut_date))
    _sync_plan_record(
        project,
        'cutting',
        '下料',
        cut_date,
        CUTTING_PLAN_FILE_NAMES,
        summary=_schedule_plan_summary('cutting', cut_date, all_extractions),
    )


def generate_cutting_schedule_from_database(project, cut_date=None, target_diameter=None, orders_per_day=None, persist=True, **options):
    ensure_project_tables(project)
    with using_project_tables(project):
        pre_df, _, _ = _source_dataframe(
            project,
            'pre-schedule',
            'weld-pre-schedule',
            WeldPreScheduleRow,
            sheet_name='预排产匹配结果',
        )
        if pre_df.empty:
            raise ValueError('数据库中没有下料预排产结果，请先生成下料预排产')
        if STATUS_COL in pre_df.columns:
            pre_df = pre_df.loc[pre_df[STATUS_COL].fillna('').astype(str).str.strip().eq(MATCHED_STATUS)].copy()
        if pre_df.empty:
            raise ValueError('数据库中没有可生成下料排产的预排产焊口')
        selection_mode = str(options.get('selection_mode') or options.get('selectionMode') or 'auto').strip().lower()
        if selection_mode not in {'auto', 'manual'}:
            raise ValueError('下料排产选择方式无效')
        selected_values = {
            str(value or '').strip()
            for value in (options.get('selected_library_seqs') or options.get('selectedLibrarySeqs') or [])
            if str(value or '').strip()
        }
        if selection_mode == 'manual':
            if not selected_values:
                raise ValueError('手动选择模式下请至少选择一条下料预排产记录')
            seq_col = COLUMNS['library_seq']
            if seq_col not in pre_df.columns:
                raise ValueError('下料预排产结果缺少库序号，无法按选中记录生成下料排产单')
            pre_df = pre_df.loc[
                pre_df[seq_col].fillna('').astype(str).str.strip().isin(selected_values)
            ].copy()
            if pre_df.empty:
                raise ValueError('选中的下料预排产记录不存在或不可排产')

        date_mode = str(options.get('dateMode') or 'auto').strip().lower()
        skip_holidays = future_schedule._to_bool(options.get('skipHolidays'))
        holidays = set(future_schedule._split_date_list(options.get('holidayDates')))
        canceled_weekends = set(future_schedule._split_date_list(options.get('canceledWeekendDates')))
        max_days = options.get('maxDays')
        if str(max_days or '').strip() == '':
            max_days = None
        if date_mode == 'manual':
            cut_dates = future_schedule._manual_weld_dates(options.get('manualWeldDates'), skip_holidays, holidays, canceled_weekends)
            if not cut_dates:
                raise ValueError('手动选择日期为空，或已全部被节假日规则过滤')
        else:
            start_value = options.get('weldStartDate') or cut_date
            cut_start = future_schedule._parse_schedule_date(start_value) if start_value else datetime.now().date()
            cut_dates = future_schedule._auto_weld_dates(cut_start, max_days, skip_holidays, holidays, canceled_weekends)

        target = float(target_diameter or EXTRACT['target_diameter'])
        orders = int(orders_per_day or EXTRACT['num_extractions'])
        schedule_source_df = _cutting_schedule_source_from_master(project, pre_df)
        work_df = sort_and_clean_data(schedule_source_df, COLUMNS['diameter'], COLUMNS['completed_flag'])
        output_files = []
        total_order_count = 0
        total_weld_count = 0
        planned_dates = []
        for cut_date_value in cut_dates:
            cut_text = future_schedule._date_text(cut_date_value)
            all_extractions = extract_welds_multiple_times(
                work_df,
                num_extractions=orders,
                target_diameter=target,
                diameter_column=COLUMNS['diameter'],
                completed_flag_column=COLUMNS['completed_flag'],
                order_date=cut_text,
            )
            if not all_extractions:
                break
            output_files.extend(_cutting_primary_output_files(cut_text, cut_text, all_extractions))
            total_order_count += len(all_extractions)
            total_weld_count += int(sum(len(item['data']) for item in all_extractions))
            planned_dates.append(cut_text)
            remaining_count = int(((work_df['_run_picked'] == False) & (work_df[COLUMNS['completed_flag']] == False)).sum())
            if remaining_count == 0:
                break
        if not output_files:
            raise ValueError('没有可抽取焊口')

        if persist:
            _sync_plan_output_files(project, output_files)
        return {
            'plan_dates': planned_dates,
            'planned_day_count': len(planned_dates),
            'order_count': total_order_count,
            'weld_count': total_weld_count,
            **({'_output_files': output_files} if not persist else {}),
        }


def _master_welding_date_values(project):
    values = (
        MasterScheduleRow.objects
        .filter(project=project)
        .exclude(weld_date='')
        .filter(weld_order_no='')
        .order_by('weld_date')
        .values_list('weld_date', flat=True)
    )
    dates = []
    seen = set()
    for value in values:
        text = str(value or '').strip()
        if not text or text in seen:
            continue
        seen.add(text)
        dates.append(future_schedule._parse_schedule_date(text))
    return dates


def _filter_pre_schedule_for_master_weld_date(project, pre_df, weld_date_text):
    if pre_df.empty or COLUMNS['library_seq'] not in pre_df.columns:
        return pre_df
    seqs = set(
        MasterScheduleRow.objects
        .filter(project=project, weld_date=weld_date_text, weld_order_no='')
        .values_list('library_seq', flat=True)
    )
    if not seqs:
        return pre_df.iloc[0:0].copy()
    return _filter_dataframe_to_library_seqs(pre_df, seqs)


def generate_welding_schedule_from_database(
    project,
    weld_date=None,
    target_diameter=None,
    orders_per_day=None,
    persist=True,
    **options,
):
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

        target = float(target_diameter or EXTRACT['target_diameter'])
        orders = int(orders_per_day or EXTRACT['num_extractions'])
        date_mode = str(options.get('dateMode') or 'auto').strip().lower()
        skip_holidays = future_schedule._to_bool(options.get('skipHolidays'))
        holidays = set(future_schedule._split_date_list(options.get('holidayDates')))
        canceled_weekends = set(future_schedule._split_date_list(options.get('canceledWeekendDates')))
        max_days = options.get('maxDays')

        master_dates = _master_welding_date_values(project)
        if date_mode == 'manual':
            weld_dates = future_schedule._manual_weld_dates(options.get('manualWeldDates'), skip_holidays, holidays, canceled_weekends)
            if not weld_dates:
                raise ValueError('手动选择日期为空，或已全部被节假日规则过滤')
        elif master_dates:
            start_value = options.get('weldStartDate') or weld_date
            start_date = future_schedule._parse_schedule_date(start_value) if start_value else None
            weld_dates = [date for date in master_dates if start_date is None or date >= start_date]
            if max_days not in (None, ''):
                weld_dates = weld_dates[:int(max_days)]
        else:
            start_value = options.get('weldStartDate') or weld_date
            weld_start = future_schedule._parse_schedule_date(start_value) if start_value else datetime.now().date()
            weld_dates = future_schedule._auto_weld_dates(weld_start, max_days, skip_holidays, holidays, canceled_weekends)

        output_files = []
        planned_dates = []
        total_order_count = 0
        total_weld_count = 0
        work_df = sort_and_clean_data(pre_df, COLUMNS['diameter'], COLUMNS['completed_flag'])
        for weld_date_value in weld_dates:
            plan_date = future_schedule._date_text(weld_date_value)
            day_df = _filter_pre_schedule_for_master_weld_date(project, work_df, plan_date) if master_dates else work_df
            if day_df.empty:
                continue
            all_extractions = extract_welds_multiple_times(
                day_df,
                num_extractions=orders,
                target_diameter=target,
                diameter_column=COLUMNS['diameter'],
                completed_flag_column=COLUMNS['completed_flag'],
                order_date=plan_date,
            )
            if not all_extractions:
                continue
            if persist:
                _sync_welding_outputs(project, plan_date, all_extractions)
            else:
                output_files.extend(_welding_primary_output_files(plan_date, all_extractions))
            planned_dates.append(plan_date)
            total_order_count += len(all_extractions)
            total_weld_count += int(sum(len(item['data']) for item in all_extractions))
            if not master_dates:
                remaining_count = int(((work_df['_run_picked'] == False) & (work_df[COLUMNS['completed_flag']] == False)).sum())
                if remaining_count == 0:
                    break

        if not planned_dates:
            raise ValueError('没有可抽取焊口')
        return {
            'plan_date': planned_dates[0],
            'plan_dates': planned_dates,
            'planned_day_count': len(planned_dates),
            'order_count': total_order_count,
            'weld_count': total_weld_count,
            **({'_output_files': output_files} if not persist else {}),
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


def _future_schedule_candidate_welds(project, selected_library_seqs=None, selection_mode='auto'):
    weld_df, _, _ = _source_dataframe(project, 'library', 'weld-library', WeldLibraryRow)
    if weld_df.empty:
        weld_df = _model_dataframe(WeldLibraryRow, project, source_file__source_key='weld-library')
    if weld_df.empty:
        raise ValueError('数据库中预制焊口库为空，无法生成总排产计划')
    arrival_col = COLUMNS['material_arrival_status']
    if arrival_col not in weld_df.columns:
        return weld_df.iloc[0:0].copy()
    candidate_df = pre_matcher._filter_truthy_statuses(weld_df, [arrival_col])
    completed_col = COLUMNS['completed_flag']
    if completed_col not in candidate_df.columns:
        return candidate_df.iloc[0:0].copy()
    candidate_df = candidate_df.loc[~pre_matcher._to_bool_series(candidate_df[completed_col])].copy()

    selection_mode = str(selection_mode or 'auto').strip().lower()
    selected_values = {
        str(value or '').strip()
        for value in (selected_library_seqs or [])
        if str(value or '').strip()
    }
    if selection_mode == 'manual':
        if not selected_values:
            raise ValueError('手动选择模式下请至少选择一条材料已到货且尚未焊接的焊口')
        seq_col = COLUMNS['library_seq']
        if seq_col not in candidate_df.columns:
            raise ValueError('预制焊口库缺少库序号，无法按选中焊口生成总排产计划')
        candidate_df = candidate_df.loc[candidate_df[seq_col].fillna('').astype(str).str.strip().isin(selected_values)].copy()
    return candidate_df


def generate_future_schedule_from_database(project, persist=True, **options):
    ensure_project_tables(project)
    with using_project_tables(project):
        pre_df = _future_schedule_candidate_welds(
            project,
            selected_library_seqs=options.get('selectedLibrarySeqs'),
            selection_mode=options.get('selectionMode', 'auto'),
        )
        if pre_df.empty:
            raise ValueError('数据库中没有材料到货状态为真且材料焊接状态不为真的可排产焊口')
        completed_keys = _completed_weld_keys_from_database(project)
        available_df, completed_count = future_schedule._remove_completed_welds(pre_df, completed_keys)
        available_df = future_schedule._ensure_completed_column(available_df)
        work_df = sort_and_clean_data(available_df, COLUMNS['diameter'], COLUMNS['completed_flag'])

        weld_start = future_schedule._parse_schedule_date(options.get('weldStartDate')) if options.get('weldStartDate') else datetime.now().date() + timedelta(days=1)
        # 总排产的拆单规则彼此独立：防腐按面积，下料和焊接按寸径。
        # 不复用单阶段运行时配置，避免修改单阶段默认值时悄然改变总排产。
        target = float(options.get('targetDiameter') or DEFAULT_MASTER_CUTTING_WELDING_DIAMETER)
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
        anti_corrosion_lead_days = options.get('antiCorrosionLeadDays')
        anti_corrosion_lead_days = 1 if anti_corrosion_lead_days in (None, '') else max(int(anti_corrosion_lead_days), 0)

        if date_mode == 'manual':
            weld_dates = future_schedule._manual_weld_dates(options.get('manualWeldDates'), skip_holidays, holidays, canceled_weekends)
            if not weld_dates:
                raise ValueError('手动选择日期为空，或已全部被节假日规则过滤')
        else:
            weld_dates = future_schedule._auto_weld_dates(weld_start, max_days, skip_holidays, holidays, canceled_weekends)
        weld_date_iter = iter(weld_dates)
        first_weld_date = next(weld_date_iter, None)
        if first_weld_date is None:
            raise ValueError('没有可用于总排产的焊接日期')
        # 自动日期在未设置最大天数时是一个按需生成的无限迭代器。这里只预取
        # 首日供防腐/下料倒推使用，主循环仍按天消费，直到焊口全部排完。
        weld_dates = chain((first_weld_date,), weld_date_iter)

        master_rows = []
        planned_days = 0
        output_files = []
        schedule_batches = []
        deferred_anti_output_files = []
        process_sequence = project_process_sequence(project)

        # 防腐阶段必须与独立“生成防腐委托”使用同一套预排产、材料拆单和
        # 文件结构。阶段间状态只写入本次运行的临时 dataframe，不提前污染材料库。
        anti_status_col = COLUMNS['material_anti_corrosion_status']
        anti_completed = (
            pre_matcher._to_bool_series(available_df[anti_status_col])
            if anti_status_col in available_df.columns
            else pd.Series(False, index=available_df.index)
        )
        needs_anti_df = available_df.loc[~anti_completed].copy()
        if not needs_anti_df.empty:
            anti_pre_result = match_anti_corrosion_pre_schedule_from_database(project, persist=False)
            anti_pre_df = anti_pre_result.pop('_result_df', pd.DataFrame())
            selected_seqs = needs_anti_df[COLUMNS['library_seq']].fillna('').astype(str).str.strip().tolist()
            if process_sequence == 'coating_before_welding':
                first_cut_date = future_schedule._previous_schedule_date(
                    first_weld_date,
                    days=cutting_lead_days,
                    skip_holidays=skip_holidays,
                    holiday_dates=holidays,
                    canceled_weekend_dates=canceled_weekends,
                )
                first_anti_date = future_schedule._previous_schedule_date(
                    first_cut_date,
                    days=anti_corrosion_lead_days,
                    skip_holidays=skip_holidays,
                    holiday_dates=holidays,
                    canceled_weekend_dates=canceled_weekends,
                )
            else:
                first_anti_date = first_weld_date
            anti_result = generate_anti_corrosion_schedule_from_database(
                project,
                commission_area=options.get('commissionArea') or DEFAULT_MASTER_ANTI_CORROSION_AREA,
                selected_library_seqs=selected_seqs,
                selection_mode='manual',
                persist=False,
                pre_schedule_dataframe=anti_pre_df,
                dateMode='auto',
                weldStartDate=future_schedule._date_text(first_anti_date),
                maxDays=max_days,
                skipHolidays=skip_holidays,
                holidayDates=options.get('holidayDates'),
                canceledWeekendDates=options.get('canceledWeekendDates'),
            )
            anti_output_files = anti_result.pop('_output_files', [])
            if process_sequence == 'coating_before_welding':
                if persist:
                    _sync_plan_output_files(project, anti_output_files)
                else:
                    output_files.extend(anti_output_files)
            else:
                deferred_anti_output_files = anti_output_files
            # 防腐委托生成成功即允许本次内存工作流继续下料，但不改写焊口的
            # 材料防腐状态；该实际完成状态只能由定时同步任务更新。
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
            schedule_batches.append((cut_text, weld_text, all_extractions))
            future_schedule._append_master_rows(master_rows, all_extractions, cut_date, weld_date, cutting_lead_days)
            planned_days += 1
            remaining_count = int(((work_df['_run_picked'] == False) & (work_df[COLUMNS['completed_flag']] == False)).sum())
            if remaining_count == 0:
                break

        # 下料阶段全部生成完毕后，再把下料视为已完成并生成焊接阶段，避免
        # 同一天循环内交叉生成两种计划造成阶段依赖混乱。
        for cut_text, weld_text, all_extractions in schedule_batches:
            if persist:
                _sync_cutting_outputs(project, cut_text, weld_text, all_extractions)
            else:
                output_files.extend(_cutting_primary_output_files(cut_text, weld_text, all_extractions))
        for cut_text, weld_text, all_extractions in schedule_batches:
            # 下料计划生成成功即允许继续生成焊接计划，但计划数据保持原始状态，
            # 不把“材料下料状态”伪装成实际完成。
            if persist:
                _sync_welding_outputs(project, weld_text, all_extractions, cut_date=cut_text)
            else:
                output_files.extend(_welding_primary_output_files(weld_text, all_extractions, cut_date=cut_text))
        if deferred_anti_output_files:
            if persist:
                _sync_plan_output_files(project, deferred_anti_output_files)
            else:
                output_files.extend(deferred_anti_output_files)

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
                    'anti_corrosion_lead_days': anti_corrosion_lead_days,
                },
            )
        if not persist:
            result['_output_files'] = output_files
        return result
