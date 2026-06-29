from .common import *
from pipecloud.services.db_storage import LIBRARY_MODELS, PLAN_FILE_MODELS, latest_source, model_field_labels, replace_source_rows, table_payload
from pipecloud.services.prefab_database import (
    CUTTING_DERIVED_FILE_NAMES,
    MASTER_DERIVED_FILE_NAME,
    WELDING_PRIMARY_PLAN_FILE_NAME,
    WELDING_DERIVED_FILE_NAMES,
    derived_plan_file_payload,
)


PLAN_LIBRARY_SPECS = {
    'master-schedule-library': {
        'name': '排产计划库',
        'plan_key': 'welding',
        'file_name': WELDING_PRIMARY_PLAN_FILE_NAME,
    },
}


def _library_catalog():
    return {
        **_library_files(PROJECT_DATA_ROOT),
        **PLAN_LIBRARY_SPECS,
    }


def _plan_library_sources(project, library):
    return DataSourceFile.objects.filter(
        project=project,
        source_type='plan',
        source_key__startswith=f'{library["plan_key"]}:',
        display_name=library['file_name'],
    ).order_by('-file_updated_at', '-id')


def _plan_library_dataframe(project, library, sheet_models):
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
        return pd.concat(frames, ignore_index=True), path

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

    dataframe = pd.DataFrame(rows)
    return dataframe, source_qs.first().relative_path


def _plan_library_info(project, library_key, library):
    source_qs = _plan_library_sources(project, library)
    derived_file_names = CUTTING_DERIVED_FILE_NAMES | WELDING_DERIVED_FILE_NAMES | {MASTER_DERIVED_FILE_NAME}
    if not source_qs.exists() and library['file_name'] not in derived_file_names:
        return {
            'key': library_key,
            'name': library['name'],
            'path': f'database://plan-library/{library_key}/{library["file_name"]}',
            'exists': False,
            'size': None,
            'updatedAt': None,
            'sheets': [],
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
        'sheets': ['Sheet1'],
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
    return JsonResponse({
        'libraries': [_database_library_info(project, key, library) for key, library in _library_catalog().items()],
    }, json_dumps_params={'ensure_ascii': False})


@require_GET
def library_rows(request, library_key):
    project, _, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)
    library = _library_catalog().get(library_key)
    if library is None:
        return HttpResponseBadRequest(json.dumps({'error': '未知库文件'}, ensure_ascii=False), content_type='application/json')

    sheet_name = request.GET.get('sheet') or None

    try:
        if library_key in LIBRARY_MODELS:
            sheet_models = LIBRARY_MODELS[library_key]
            source = latest_source(project, 'library', library_key)
        else:
            sheet_models = PLAN_FILE_MODELS.get(library['file_name'])
            if sheet_models is None:
                sheet_models = {}
            dataframe, source_path = _plan_library_dataframe(project, library, sheet_models)
            if dataframe is None:
                raise ValueError(f'数据库中没有{library["name"]}')
            columns = [column for column in dataframe.columns if not str(column).startswith('_')]
            rows = dataframe[columns].to_dict(orient='records')
            return JsonResponse({
                'key': library_key,
                'name': library['name'],
                'path': source_path,
                'sheet': 'Sheet1',
                'sheets': ['Sheet1'],
                'total': len(rows),
                'columns': columns,
                'rows': rows,
            }, json_dumps_params={'ensure_ascii': False})
        if source is None:
            raise ValueError(f'数据库中没有{library["name"]}')
        selected_sheet, sheets, total, columns, rows = table_payload(source, sheet_models, sheet_name)
    except Exception as error:
        return HttpResponseBadRequest(json.dumps({'error': f'读取库数据失败：{error}'}, ensure_ascii=False), content_type='application/json')

    return JsonResponse({
        'key': library_key,
        'name': library['name'],
        'path': source.relative_path,
        'sheet': selected_sheet,
        'sheets': sheets,
        'total': total,
        'columns': columns,
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
        sheet_name = payload['sheet'] or 'Sheet1'
        synced_count = 0
        if library_key in LIBRARY_MODELS:
            source = replace_source_rows(
                project,
                'library',
                library_key,
                f'{library["name"]}.xlsx',
                f'database://library/{library_key}/{library["name"]}.xlsx',
                {sheet_name: {'columns': payload['columns'], 'rows': payload['rows']}},
                LIBRARY_MODELS[library_key],
            )
            selected_sheet, _, total, _, _ = table_payload(source, LIBRARY_MODELS[library_key], sheet_name)
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
        'sheet': selected_sheet,
        'total': total,
        'backupPath': '',
        'syncedWeldCount': synced_count,
    }, json_dumps_params={'ensure_ascii': False})


def _database_library_info(project, library_key, library):
    if library_key in LIBRARY_MODELS:
        source = latest_source(project, 'library', library_key)
        if source is None:
            return {
                'key': library_key,
                'name': library['name'],
                'path': f'database://library/{library_key}/{library["name"]}.xlsx',
                'exists': False,
                'size': None,
                'updatedAt': None,
                'sheets': [],
                'rowCount': 0,
            }
        sheet_models = LIBRARY_MODELS[library_key]
        selected_sheet, sheets, total, _, _ = table_payload(source, sheet_models, None)
        return {
            'key': library_key,
            'name': library['name'],
            'path': source.relative_path,
            'exists': True,
            'size': source.file_size,
            'updatedAt': source.file_updated_at,
            'sheets': sheets,
            'rowCount': total if selected_sheet else 0,
        }
    return _plan_library_info(project, library_key, library)
