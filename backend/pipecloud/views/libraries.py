from .common import *
from pipecloud.models import MasterScheduleRow, WeldCommonData
from pipecloud.services.db_storage import (
    LIBRARY_MODELS,
    PLAN_FILE_MODELS,
    WELD_STATUS_FIELD_LABELS,
    apply_weld_status_to_dataframe,
    latest_source,
    model_field_labels,
    replace_source_rows,
    table_payload,
)
from pipecloud.services.prefab_database import (
    PLAN_STAGE_EXCLUDED_COLUMNS,
    CUTTING_DERIVED_FILE_NAMES,
    MASTER_DERIVED_FILE_NAME,
    WELDING_DERIVED_FILE_NAMES,
    derived_plan_file_payload,
)


PLAN_LIBRARY_SPECS = {
    'master-schedule-library': {
        'name': '排产计划库',
        'plan_key': 'all',
        'file_name': '排产计划库.xlsx',
    },
}

BUSINESS_PRIMARY_FIELD_NAMES = {'library_seq'}
BUSINESS_PRIMARY_FIELD_NAMES_BY_MODEL = {
    PipeMaterialRow: {'pipe_no'},
    FittingMaterialRow: {'material_code'},
}
BUSINESS_PRIMARY_COLUMN = '库序号'
LIBRARY_HIDDEN_COLUMNS = {}
MASTER_STAGE_LABELS = {
    'anti-corrosion': '防腐',
    'cutting': '下料',
    'welding': '焊接',
}
MASTER_LIBRARY_EXCLUDED_FIELDS = {'stage_payload'}
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
    '到货状态',
    '材料防腐状态',
    '防腐状态',
    '材料下料状态',
    '下料状态',
    '材料焊接状态',
    '是否完成',
    '完成状态',
    '焊接状态',
} | set(model_field_labels(MasterScheduleRow).values()) | set(model_field_labels(WeldCommonData).values())
ANTI_CORROSION_STAGE_COLUMNS = {'防腐面积', '材料油漆', '材料油漆1', '材料油漆2'}
STATUS_COLUMNS = set(WELD_STATUS_FIELD_LABELS.values())


def _visible_library_columns(library_key, columns):
    hidden = LIBRARY_HIDDEN_COLUMNS.get(library_key, set())
    return [column for column in columns if column not in hidden]


def _model_columns_for_field_names(model, field_names):
    labels = model_field_labels(model)
    return [
        label
        for field_name, label in labels.items()
        if field_name in field_names
    ]


def _model_primary_key_columns(model):
    field_names = BUSINESS_PRIMARY_FIELD_NAMES_BY_MODEL.get(model, BUSINESS_PRIMARY_FIELD_NAMES)
    columns = _model_columns_for_field_names(model, field_names)
    return [column for column in columns if column]


def _model_library_columns(model):
    return list(model_field_labels(model).values()) if model is not None else []


def _visible_stage_payload_columns(stage_key, stage_payload):
    if stage_key == 'anti-corrosion':
        allowed = ANTI_CORROSION_STAGE_COLUMNS
    else:
        allowed = None
    excluded = PLAN_STAGE_EXCLUDED_COLUMNS
    for column_name, value in stage_payload.items():
        if column_name in MASTER_COMMON_STAGE_COLUMNS or column_name in excluded:
            continue
        if allowed is not None and column_name not in allowed:
            continue
        yield column_name, value


def _master_schedule_library_dataframe(project):
    labels = model_field_labels(MasterScheduleRow)
    common_labels = model_field_labels(WeldCommonData)
    base_field_names = [
        field_name
        for field_name in labels.keys()
        if field_name not in MASTER_LIBRARY_EXCLUDED_FIELDS
    ]
    base_column_labels = {labels[field_name] for field_name in base_field_names}
    common_field_names = [
        field_name for field_name, label in common_labels.items()
        if field_name != 'library_seq' and label not in base_column_labels
    ]
    rows = []
    stage_columns = []
    queryset = MasterScheduleRow.objects.filter(project=project).select_related('common_data').order_by('library_seq')
    fallback_common_by_seq = {
        row.library_seq: row
        for row in WeldCommonData.objects.filter(
            project=project,
            library_seq__in=queryset.values_list('library_seq', flat=True),
        )
    }
    for record in queryset:
        values = {labels[field_name]: getattr(record, field_name, '') for field_name in base_field_names}
        common_data = record.common_data or fallback_common_by_seq.get(record.library_seq)
        for field_name in common_field_names:
            values[common_labels[field_name]] = getattr(common_data, field_name, '') if common_data else ''
        payload = record.stage_payload or {}
        for stage_key, stage_label in MASTER_STAGE_LABELS.items():
            stage_payload = payload.get(stage_key) or {}
            if not isinstance(stage_payload, dict):
                continue
            for column_name, value in _visible_stage_payload_columns(stage_key, stage_payload):
                column = f'{stage_label}/{column_name}'
                values[column] = value
                if column not in stage_columns:
                    stage_columns.append(column)
        rows.append(values)
    columns = [
        *[labels[field_name] for field_name in base_field_names],
        *[common_labels[field_name] for field_name in common_field_names],
        *stage_columns,
    ]
    return apply_weld_status_to_dataframe(project, pd.DataFrame(rows, columns=columns)), stage_columns


def _preserve_primary_key_values(rows, current_rows, primary_key_columns):
    if not primary_key_columns:
        return rows
    current_values_by_column = {
        column: {
            str(row.get(column, '')).strip()
            for row in current_rows
            if str(row.get(column, '')).strip()
        }
        for column in primary_key_columns
    }
    preserved_rows = []
    for index, row in enumerate(rows):
        preserved = dict(row)
        current = current_rows[index] if index < len(current_rows) else {}
        for column in primary_key_columns:
            submitted_value = str(row.get(column, '')).strip()
            if submitted_value and submitted_value in current_values_by_column.get(column, set()):
                preserved[column] = row.get(column, '')
            elif column in current and str(current.get(column, '')).strip():
                preserved[column] = current.get(column, '')
        preserved_rows.append(preserved)
    return preserved_rows


def _library_catalog():
    return {
        **_library_files(PROJECT_DATA_ROOT),
        **PLAN_LIBRARY_SPECS,
    }


def _plan_library_sources(project, library):
    if library.get('plan_key') == 'all':
        return DataSourceFile.objects.none()
    return DataSourceFile.objects.filter(
        project=project,
        source_type='plan',
        source_key__startswith=f'{library["plan_key"]}:',
        display_name=library['file_name'],
    ).order_by('-file_updated_at', '-id')


def _plan_library_dataframe(project, library, sheet_models):
    if library.get('plan_key') == 'all':
        dataframe, _ = _master_schedule_library_dataframe(project)
        return dataframe, 'database://library/master-schedule-library/排产计划库.xlsx'

    source_qs = _plan_library_sources(project, library)
    file_name = library['file_name']
    if not source_qs.exists() and file_name not in CUTTING_DERIVED_FILE_NAMES | WELDING_DERIVED_FILE_NAMES | {MASTER_DERIVED_FILE_NAME}:
        return None, ''

    if file_name in CUTTING_DERIVED_FILE_NAMES | WELDING_DERIVED_FILE_NAMES | {MASTER_DERIVED_FILE_NAME}:
        records = PlanRecord.objects.filter(project=project, plan_key=library['plan_key']).order_by('-folder_updated_at', '-id')
        frames = []
        path = f'database://plan-library/{library["plan_key"]}/{file_name}'
        for record in records:
            payload = derived_plan_file_payload(project, library['plan_key'], record.plan_folder, file_name)
            if not payload:
                continue
            frame = pd.DataFrame(payload['rows'], columns=payload['columns'])
            if frame.empty:
                continue
            frame['_plan_folder'] = record.plan_folder
            frame['_source_path'] = payload['path']
            frames.append(frame)
            path = payload['path']
        if not frames:
            return None, ''
        return apply_weld_status_to_dataframe(project, pd.concat(frames, ignore_index=True)), path

    row_model = sheet_models.get('*')
    if row_model is None:
        return None, ''

    rows = []
    for source in source_qs:
        source_key = str(source.source_key or '')
        parts = source_key.split(':', 2)
        plan_folder = parts[1] if len(parts) >= 2 else ''
        for item in row_model.objects.filter(project=project, source_file=source).order_by('row_index'):
            row = {
                label: getattr(item, field_name, '')
                for field_name, label in model_field_labels(row_model).items()
            }
            row['_plan_folder'] = plan_folder
            row['_source_path'] = source.relative_path
            rows.append(row)

    if not rows:
        return None, ''

    dataframe = apply_weld_status_to_dataframe(project, pd.DataFrame(rows))
    return dataframe, source_qs.first().relative_path


def _ordered_library_columns(columns, primary_key_columns):
    ordered = [column for column in primary_key_columns if column in columns]
    ordered.extend(column for column in columns if column not in ordered)
    return ordered


def _empty_library_rows_payload(library_key, library, path=''):
    sheet_models = LIBRARY_MODELS.get(library_key, {})
    model = sheet_models.get('*')
    columns = _visible_library_columns(library_key, _model_library_columns(model))
    primary_key_columns = _model_primary_key_columns(model) if model is not None else []
    return {
        'key': library_key,
        'name': library['name'],
        'path': path or f'database://library/{library_key}/{library["name"]}.xlsx',
        'total': 0,
        'columns': columns,
        'primaryKeyColumns': primary_key_columns,
        'readonlyColumns': primary_key_columns,
        'stageColumns': [],
        'statusColumns': [column for column in columns if column in STATUS_COLUMNS],
        'rows': [],
    }


def _plan_library_info(project, library_key, library):
    source_qs = _plan_library_sources(project, library)
    if library.get('plan_key') == 'all':
        total = MasterScheduleRow.objects.filter(project=project).count()
        latest = MasterScheduleRow.objects.filter(project=project).order_by('-updated_at', '-id').first()
        return {
            'key': library_key,
            'name': library['name'],
            'path': f'database://library/{library_key}/{library["file_name"]}',
            'exists': total > 0,
            'size': 0,
            'updatedAt': latest.updated_at.timestamp() if latest else None,
            'rowCount': total,
            'fileName': library['file_name'],
            'planKey': library['plan_key'],
            'planFolder': '',
        }
    derived_file_names = CUTTING_DERIVED_FILE_NAMES | WELDING_DERIVED_FILE_NAMES | {MASTER_DERIVED_FILE_NAME}
    if not source_qs.exists() and library['file_name'] not in derived_file_names:
        return {
            'key': library_key,
            'name': library['name'],
            'path': f'database://plan-library/{library_key}/{library["file_name"]}',
            'exists': False,
            'size': None,
            'updatedAt': None,
            'rowCount': 0,
            'fileName': library['file_name'],
            'planKey': library['plan_key'],
            'planFolder': '',
        }

    sheet_models = PLAN_FILE_MODELS.get(library['file_name'], {})
    dataframe, path = _plan_library_dataframe(project, library, sheet_models)
    total = 0 if dataframe is None else len(dataframe)
    plan_folder = ''
    first_source = source_qs.first()
    if first_source is not None:
        parts = str(first_source.source_key or '').split(':', 2)
        if len(parts) >= 2:
            plan_folder = parts[1]

    return {
        'key': library_key,
        'name': library['name'],
        'path': path,
        'exists': True,
        'size': sum(source.file_size for source in source_qs) if source_qs.exists() else 0,
        'updatedAt': source_qs.first().file_updated_at if source_qs.exists() else None,
        'rowCount': total,
        'fileName': library['file_name'],
        'planKey': library['plan_key'],
        'planFolder': plan_folder,
    }


@require_GET
def libraries(request):
    project, _, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)
    catalog = _library_catalog()
    library_infos = []
    for key, library in catalog.items():
        try:
            library_infos.append(_database_library_info(project, key, library))
        except Exception:
            library_infos.append({
                'key': key,
                'name': library['name'],
                'path': (
                    f'database://plan-library/{key}/{library["file_name"]}'
                    if key in PLAN_LIBRARY_SPECS
                    else f'database://library/{key}/{library["name"]}.xlsx'
                ),
                'exists': False,
                'size': None,
                'updatedAt': None,
                'rowCount': 0,
            })
    return JsonResponse({
        'libraries': library_infos,
    }, json_dumps_params={'ensure_ascii': False})


@require_GET
def library_rows(request, library_key):
    project, _, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)
    library = _library_catalog().get(library_key)
    if library is None:
        return HttpResponseBadRequest(json.dumps({'error': '未知库文件'}, ensure_ascii=False), content_type='application/json')

    try:
        if library_key in LIBRARY_MODELS and library_key not in PLAN_LIBRARY_SPECS:
            sheet_models = LIBRARY_MODELS[library_key]
            source = latest_source(project, 'library', library_key)
            if source is None:
                return JsonResponse(
                    _empty_library_rows_payload(library_key, library),
                    json_dumps_params={'ensure_ascii': False},
                )
        else:
            sheet_models = {'*': MasterScheduleRow} if library_key == 'master-schedule-library' else PLAN_FILE_MODELS.get(library['file_name'])
            if sheet_models is None:
                sheet_models = {}
            stage_columns = []
            if library_key == 'master-schedule-library':
                dataframe, stage_columns = _master_schedule_library_dataframe(project)
                source_path = 'database://library/master-schedule-library/排产计划库.xlsx'
            else:
                dataframe, source_path = _plan_library_dataframe(project, library, sheet_models)
            if dataframe is None:
                raise ValueError(f'数据库中没有{library["name"]}')
            model = sheet_models.get('*')
            primary_key_columns = _model_primary_key_columns(model) if model is not None else []
            if not primary_key_columns and BUSINESS_PRIMARY_COLUMN in dataframe.columns:
                primary_key_columns = [BUSINESS_PRIMARY_COLUMN]
            columns = _ordered_library_columns(
                [column for column in dataframe.columns if not str(column).startswith('_')],
                primary_key_columns,
            )
            columns = _visible_library_columns(library_key, columns)
            rows = dataframe[columns].to_dict(orient='records')
            return JsonResponse({
                'key': library_key,
                'name': library['name'],
                'path': source_path,
                'total': len(rows),
                'columns': columns,
                'primaryKeyColumns': primary_key_columns,
                'readonlyColumns': primary_key_columns,
                'stageColumns': stage_columns,
                'statusColumns': [column for column in columns if column in STATUS_COLUMNS],
                'rows': rows,
            }, json_dumps_params={'ensure_ascii': False})
        selected_sheet, _, total, columns, rows = table_payload(source, sheet_models, None)
        model = sheet_models.get(selected_sheet) or sheet_models.get('*')
        if model is not None:
            primary_key_columns = _model_primary_key_columns(model)
            columns = _visible_library_columns(library_key, _model_library_columns(model))
            rows = [
                {column: row.get(column, '') for column in columns}
                for row in rows
            ]
        else:
            primary_key_columns = []
    except Exception as error:
        return HttpResponseBadRequest(json.dumps({'error': f'读取库数据失败：{error}'}, ensure_ascii=False), content_type='application/json')

    return JsonResponse({
        'key': library_key,
        'name': library['name'],
        'path': source.relative_path,
        'total': total,
        'columns': columns,
        'primaryKeyColumns': primary_key_columns,
        'readonlyColumns': primary_key_columns,
        'stageColumns': [],
        'statusColumns': [column for column in columns if column in STATUS_COLUMNS],
        'rows': rows,
    }, json_dumps_params={'ensure_ascii': False})


@csrf_exempt
@require_POST
def save_library_rows(request, library_key):
    project, _, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)
    library = _library_catalog().get(library_key)
    if library is None:
        return HttpResponseBadRequest(json.dumps({'error': '未知库文件'}, ensure_ascii=False), content_type='application/json')

    payload, error = _parse_library_save_payload(request)
    if error:
        return HttpResponseBadRequest(json.dumps({'error': error}, ensure_ascii=False), content_type='application/json')

    try:
        sheet_name = 'Sheet1'
        synced_count = 0
        if library_key in LIBRARY_MODELS and library_key not in PLAN_LIBRARY_SPECS:
            sheet_models = LIBRARY_MODELS[library_key]
            existing_source = latest_source(project, 'library', library_key)
            existing_rows = []
            primary_key_columns = []
            if existing_source is not None:
                selected_sheet, _, _, _, existing_rows = table_payload(existing_source, sheet_models, sheet_name)
                model = sheet_models.get(selected_sheet) or sheet_models.get('*')
                if model is not None:
                    primary_key_columns = _model_primary_key_columns(model)
            rows = _preserve_primary_key_values(payload['rows'], existing_rows, primary_key_columns)
            columns = _visible_library_columns(library_key, payload['columns'])
            rows = [
                {column: row.get(column, '') for column in columns}
                for row in rows
            ]
            source = replace_source_rows(
                project,
                'library',
                library_key,
                f'{library["name"]}.xlsx',
                f'database://library/{library_key}/{library["name"]}.xlsx',
                {sheet_name: {'columns': columns, 'rows': rows}},
                sheet_models,
            )
            _, _, total, _, _ = table_payload(source, sheet_models, sheet_name)
        else:
            raise ValueError('计划库为汇总视图，暂不支持直接保存')
        if library_key == 'weld-library':
            _update_project_weld_metrics(project, None)
    except Exception as error:
        return HttpResponseBadRequest(json.dumps({'error': f'写入库数据失败：{error}'}, ensure_ascii=False), content_type='application/json')

    return JsonResponse({
        'key': library_key,
        'name': library['name'],
        'path': source.relative_path,
        'total': total,
        'backupPath': '',
        'syncedWeldCount': synced_count,
    }, json_dumps_params={'ensure_ascii': False})


def _database_library_info(project, library_key, library):
    if library_key in LIBRARY_MODELS and library_key not in PLAN_LIBRARY_SPECS:
        source = latest_source(project, 'library', library_key)
        if source is None:
            return {
                'key': library_key,
                'name': library['name'],
                'path': f'database://library/{library_key}/{library["name"]}.xlsx',
                'exists': False,
                'size': None,
                'updatedAt': None,
                'rowCount': 0,
            }
        sheet_models = LIBRARY_MODELS[library_key]
        selected_sheet, _, total, _, _ = table_payload(source, sheet_models, None)
        return {
            'key': library_key,
            'name': library['name'],
            'path': source.relative_path,
            'exists': True,
            'size': source.file_size,
            'updatedAt': source.file_updated_at,
            'rowCount': total if selected_sheet else 0,
        }
    return _plan_library_info(project, library_key, library)
