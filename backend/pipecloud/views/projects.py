from .common import *
from pipecloud.services.db_storage import INITIALIZATION_MODELS, latest_source, replace_source_with_workbook, table_payload
from pipecloud.services.project_constraints import project_constraints_payload, update_project_constraints
from pipecloud.services.project_tables import ensure_project_tables


@csrf_exempt
def projects(request):
    if request.method == 'GET':
        project_list = list(Project.objects.all())
        rows = [_project_payload(project) for project in project_list]
        return JsonResponse({
            'columns': PROJECT_COLUMNS,
            'total': len(rows),
            'rows': rows,
        }, json_dumps_params={'ensure_ascii': False})

    if request.method == 'POST':
        values, error = _parse_project_payload(request)
        if error:
            return HttpResponseBadRequest(json.dumps({'error': error}, ensure_ascii=False), content_type='application/json')
        project = Project.objects.create(**values)
        ensure_project_tables(project)
        return JsonResponse(_project_payload(project), json_dumps_params={'ensure_ascii': False})

    return HttpResponseBadRequest(json.dumps({'error': '请求方法无效'}, ensure_ascii=False), content_type='application/json')


@csrf_exempt
def project_detail(request, project_id):
    project, error = _project_or_error(project_id)
    if error:
        return HttpResponseBadRequest(json.dumps({'error': error}, ensure_ascii=False), content_type='application/json')

    if request.method in {'PUT', 'PATCH'}:
        values, error = _parse_project_payload(request)
        if error:
            return HttpResponseBadRequest(json.dumps({'error': error}, ensure_ascii=False), content_type='application/json')
        for field, value in values.items():
            setattr(project, field, value)
        project.save()
        return JsonResponse(_project_payload(project), json_dumps_params={'ensure_ascii': False})

    if request.method == 'DELETE':
        project.delete()
        return JsonResponse({'deleted': project_id}, json_dumps_params={'ensure_ascii': False})

    return HttpResponseBadRequest(json.dumps({'error': '请求方法无效'}, ensure_ascii=False), content_type='application/json')


@csrf_exempt
def project_constraints(request, project_id):
    project, error = _project_or_error(project_id)
    if error:
        return HttpResponseBadRequest(json.dumps({'error': error}, ensure_ascii=False), content_type='application/json')

    if request.method == 'GET':
        return JsonResponse(project_constraints_payload(project), json_dumps_params={'ensure_ascii': False})

    if request.method in {'PUT', 'PATCH'}:
        try:
            payload = json.loads(request.body or b'{}')
            if not isinstance(payload, dict):
                raise ValueError('项目约束请求格式无效')
            result = update_project_constraints(project, payload.get('rules'))
        except (json.JSONDecodeError, ValueError) as error:
            return HttpResponseBadRequest(
                json.dumps({'error': str(error)}, ensure_ascii=False),
                content_type='application/json',
            )
        return JsonResponse(result, json_dumps_params={'ensure_ascii': False})

    return HttpResponseBadRequest(json.dumps({'error': '请求方法无效'}, ensure_ascii=False), content_type='application/json')


@require_GET
def export_projects(request):
    return _project_file_response()


@require_GET
def project_weld_rows(request, project_id):
    project, error = _project_or_error(project_id)
    if error:
        return HttpResponseBadRequest(json.dumps({'error': error}, ensure_ascii=False), content_type='application/json')

    try:
        page = max(int(request.GET.get('page') or 1), 1)
        page_size = max(min(int(request.GET.get('page_size') or request.GET.get('pageSize') or 100), 500), 1)
    except ValueError:
        return HttpResponseBadRequest(json.dumps({'error': '分页参数无效'}, ensure_ascii=False), content_type='application/json')

    sheet_name = request.GET.get('sheet') or None
    try:
        source = latest_source(project, 'initialization', 'welds')
        if source is None:
            selected_sheet, sheets, total, columns, rows = '', [], 0, [], []
        else:
            selected_sheet, sheets, total, columns, rows = table_payload(source, INITIALIZATION_MODELS, sheet_name)
    except Exception as error:
        return HttpResponseBadRequest(json.dumps({'error': f'读取项目焊口初始化数据失败：{error}'}, ensure_ascii=False), content_type='application/json')

    total_pages = (total + page_size - 1) // page_size if total else 0
    if total_pages and page > total_pages:
        page = total_pages
    start = (page - 1) * page_size
    paged_rows = rows[start:start + page_size]

    return JsonResponse({
        'projectId': project.id,
        'projectName': project.project_name,
        'dataPath': f'database://project/{project.id}',
        'file': _data_source_payload(source, '焊口初始化数据.xlsx') if source else None,
        'sheet': selected_sheet,
        'sheets': sheets,
        'total': total,
        'page': page,
        'pageSize': page_size,
        'totalPages': total_pages,
        'columns': columns,
        'rows': paged_rows,
    }, json_dumps_params={'ensure_ascii': False})


def _normalize_spool_info_paths(payload):
    files = payload.get('files') or {}
    for file_info in files.values():
        raw_path = file_info.get('path')
        if raw_path:
            file_info['path'] = _relative_path(Path(raw_path))
    project_root = payload.get('projectRoot')
    if project_root:
        payload['projectRoot'] = _relative_path(Path(project_root))
    return payload


@require_GET
def project_spool_info(request, project_id):
    project, error = _project_or_error(project_id)
    if error:
        return HttpResponseBadRequest(json.dumps({'error': error}, ensure_ascii=False), content_type='application/json')

    weld_source = request.GET.get('weld_source') or request.GET.get('weldSource') or 'prefab'
    structure_spool = request.GET.get('structure_spool') or request.GET.get('structureSpool') or '__first__'
    include_model = str(request.GET.get('include_model') or request.GET.get('includeModel') or '').strip().lower() in {'1', 'true', 'yes', 'y'}
    try:
        payload = read_project_spool_info_from_database(project, None, weld_source, structure_spool, include_model=include_model)
    except Exception as error:
        return HttpResponseBadRequest(json.dumps({'error': f'读取管段校验数据失败：{error}'}, ensure_ascii=False), content_type='application/json')

    return JsonResponse(payload, json_dumps_params={'ensure_ascii': False})


@csrf_exempt
@require_POST
def upload_project_weld_file(request, project_id):
    project, error = _project_or_error(project_id)
    if error:
        return HttpResponseBadRequest(json.dumps({'error': error}, ensure_ascii=False), content_type='application/json')

    upload_file = request.FILES.get('file')
    if upload_file is None:
        return HttpResponseBadRequest(json.dumps({'error': '未选择焊口初始化数据文件'}, ensure_ascii=False), content_type='application/json')

    file_name = Path(upload_file.name).name
    suffix = Path(file_name).suffix.lower()
    if file_name.startswith('~$') or suffix not in {'.xlsx', '.xlsm'}:
        return HttpResponseBadRequest(json.dumps({'error': '仅支持上传 .xlsx 或 .xlsm 焊口初始化数据'}, ensure_ascii=False), content_type='application/json')
    if not file_name.startswith('焊口初始化数据'):
        file_name = f'焊口初始化数据-{file_name}'

    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        upload_dir = FILE_PARSER_ROOT / timestamp
        upload_dir.mkdir(parents=True, exist_ok=True)
        staged_path = upload_dir / file_name
        with staged_path.open('wb') as target_file:
            for chunk in upload_file.chunks():
                target_file.write(chunk)
        source = replace_source_with_workbook(
            project,
            'initialization',
            'welds',
            file_name,
            f'database://initialization/{project.id}/{file_name}',
            staged_path,
            INITIALIZATION_MODELS,
        )
    except Exception as error:
        return HttpResponseBadRequest(json.dumps({'error': f'保存焊口初始化数据失败：{error}'}, ensure_ascii=False), content_type='application/json')

    return JsonResponse({
        'projectId': project.id,
        'dataPath': f'database://project/{project.id}',
        'file': _data_source_payload(source, file_name),
        'backupPaths': [],
    }, json_dumps_params={'ensure_ascii': False})


@csrf_exempt
@require_POST
def import_projects(request):
    upload_file = request.FILES.get('file')
    if upload_file is None:
        return HttpResponseBadRequest(json.dumps({'error': '未选择项目文件'}, ensure_ascii=False), content_type='application/json')

    file_name = Path(upload_file.name).name
    if file_name.startswith('~$') or Path(file_name).suffix.lower() not in {'.xlsx', '.xlsm'}:
        return HttpResponseBadRequest(json.dumps({'error': '仅支持上传 .xlsx 或 .xlsm 项目文件'}, ensure_ascii=False), content_type='application/json')

    try:
        dataframe = pd.read_excel(upload_file)
    except Exception as error:
        return HttpResponseBadRequest(json.dumps({'error': f'读取项目文件失败：{error}'}, ensure_ascii=False), content_type='application/json')

    imported = 0
    for _, row in dataframe.iterrows():
        values = {}
        for title, field in PROJECT_TITLE_TO_FIELD.items():
            value = row.get(title, '')
            values[field] = '' if pd.isna(value) else str(value).strip()
        if any(values.values()):
            error = _validate_project_values(values)
            if error:
                return HttpResponseBadRequest(
                    json.dumps({'error': f'第 {imported + 1} 条项目数据无效：{error}'}, ensure_ascii=False),
                    content_type='application/json',
                )
            project = Project.objects.create(**values)
            ensure_project_tables(project)
            imported += 1

    return JsonResponse({
        'imported': imported,
        'total': Project.objects.count(),
    }, json_dumps_params={'ensure_ascii': False})
