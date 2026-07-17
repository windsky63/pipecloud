import threading

from .common import *
from pipecloud.services.db_storage import (
    ARRIVAL_MODELS,
    INITIALIZATION_MODELS,
    PRE_SCHEDULE_MODELS,
    LIBRARY_MODELS,
    PLAN_FILE_MODELS,
    dataframe_payload,
    latest_source,
    replace_source_with_workbook,
    table_payload,
)
from pipecloud.services.prefab_database import (
    cleanup_expired_staged_plan_outputs,
    discard_staged_plan_outputs,
    commit_staged_plan_outputs,
    generate_anti_corrosion_schedule_from_database,
    generate_cutting_schedule_from_database,
    generate_future_schedule_from_database,
    generate_welding_schedule_from_database,
    match_and_lock_materials_from_database,
    maintain_weld_library_from_database,
    maintain_material_libraries_from_database,
    match_anti_corrosion_pre_schedule_from_database,
    match_welding_pre_schedule_from_database,
    match_weld_pre_schedule_from_database,
    release_material_locks_from_database,
    stage_plan_output_files,
    staged_plan_workbook_payload,
    strip_cutting_plan_columns,
    strip_welding_plan_columns,
    update_weld_material_arrival_status_from_database,
    _plan_file_models,
)


_INITIALIZATION_TASKS = {}
_INITIALIZATION_TASKS_LOCK = threading.Lock()


def _register_initialization_task(task_id):
    if not task_id:
        return None
    with _INITIALIZATION_TASKS_LOCK:
        event = threading.Event()
        _INITIALIZATION_TASKS[task_id] = event
        return event


def _finish_initialization_task(task_id):
    if not task_id:
        return
    with _INITIALIZATION_TASKS_LOCK:
        _INITIALIZATION_TASKS.pop(task_id, None)


@csrf_exempt
@require_POST
def cancel_initialization(request):
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except (UnicodeDecodeError, json.JSONDecodeError):
        return HttpResponseBadRequest(json.dumps({'error': '请求内容不是有效 JSON'}, ensure_ascii=False), content_type='application/json')
    task_id = str(payload.get('taskId') or '').strip()
    with _INITIALIZATION_TASKS_LOCK:
        event = _INITIALIZATION_TASKS.get(task_id)
        if event:
            event.set()
    return JsonResponse({'ok': True, 'cancelled': bool(event), 'taskId': task_id})


def _truthy_payload_value(value):
    if isinstance(value, bool):
        return value
    return str(value or '').strip().lower() in {'1', 'true', 'yes', 'y', 'on'}


def _pre_schedule_action_options(payload, allow_only_auto_weld=True, allow_ignore_anti_corrosion_status=False):
    action_options = {}
    if 'onlyAutoWeld' in payload:
        only_auto_weld = payload.get('onlyAutoWeld')
        if not isinstance(only_auto_weld, bool):
            raise ValueError('参数格式无效：onlyAutoWeld')
        if allow_only_auto_weld:
            action_options['onlyAutoWeld'] = only_auto_weld

    if 'ignoreAntiCorrosionStatus' in payload:
        ignore_status = payload.get('ignoreAntiCorrosionStatus')
        if not isinstance(ignore_status, bool):
            raise ValueError('参数格式无效：ignoreAntiCorrosionStatus')
        if allow_ignore_anti_corrosion_status:
            action_options['ignoreAntiCorrosionStatus'] = ignore_status

    if 'concentrationDimension' in payload:
        dimension = str(payload.get('concentrationDimension') or '').strip()
        if dimension not in {'segment', 'weld'}:
            raise ValueError('参数格式无效：concentrationDimension')
        action_options['concentrationDimension'] = dimension

    if 'concentrationThresholdPercent' in payload:
        raw_value = payload.get('concentrationThresholdPercent')
        try:
            threshold = float(raw_value)
        except (TypeError, ValueError) as error:
            raise ValueError('参数格式无效：concentrationThresholdPercent') from error
        if threshold < 0 or threshold > 100:
            raise ValueError('参数必须在 0 到 100 之间：concentrationThresholdPercent')
        action_options['concentrationThresholdPercent'] = threshold

    return action_options


def _selected_library_seq_options(payload):
    selected_library_seqs = payload.get('selectedLibrarySeqs')
    if selected_library_seqs is not None and not isinstance(selected_library_seqs, list):
        raise ValueError('参数格式无效：selectedLibrarySeqs')
    return [
        str(value or '').strip()
        for value in (selected_library_seqs or [])
        if str(value or '').strip()
    ]


def _stage_plan_outputs(project, result, output_files):
    return stage_plan_output_files(project, output_files)


PRE_SCHEDULE_RESULT_SHEET = '预排产匹配结果'


def _pre_schedule_result_only_payload(source, requested_sheet=None):
    selected_sheet, _, total, columns, rows = table_payload(
        source,
        PRE_SCHEDULE_MODELS,
        PRE_SCHEDULE_RESULT_SHEET if requested_sheet != PRE_SCHEDULE_RESULT_SHEET else requested_sheet,
    )
    return selected_sheet, [PRE_SCHEDULE_RESULT_SHEET] if selected_sheet else [], total, columns, rows


@require_GET
def summary(request):
    project, data_root, error = _request_project_context(request)
    if error:
        return _project_bad_request(error)
    if project:
        cleanup_expired_staged_plan_outputs(project)
    return JsonResponse({
        'root': _relative_path(PREFAB_ROOT),
        'dataRoot': _relative_path(data_root),
        'projectId': project.id if project else None,
        'modules': [_module_payload(module, data_root, project) for module in _modules_for_project(project)],
        'actions': [_action_payload(key) for key in ACTIONS],
    }, json_dumps_params={'ensure_ascii': False})


@require_GET
def files(request):
    project, data_root, error = _request_project_context(request)
    if error:
        return _project_bad_request(error)
    all_files = []
    for module in _modules_for_project(project):
        for file_name in module['files']:
            item = _database_module_file_info(project, file_name, data_root)
            item['module'] = module['name']
            all_files.append(item)
    return JsonResponse({'files': all_files}, json_dumps_params={'ensure_ascii': False})


@require_GET
def initialization_stats(request):
    project, data_root, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)
    try:
        payload = _initialization_stats_payload(project, data_root)
    except Exception as error:
        return HttpResponseBadRequest(
            json.dumps({'error': f'读取初始化统计失败：{error}'}, ensure_ascii=False),
            content_type='application/json',
        )
    return JsonResponse(payload, json_dumps_params={'ensure_ascii': False})


@csrf_exempt
@require_POST
def sync_initialization_data(request):
    project, data_root, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)

    try:
        source = latest_source(project, 'initialization', 'welds')
        if source is None:
            return _project_bad_request('当前项目暂无焊口初始化数据')
        selected_sheet, sheets, total, columns, rows = table_payload(source, INITIALIZATION_MODELS, None)
        stats = _initialization_stats_payload(project, data_root, force_refresh=True)
    except Exception as error:
        return HttpResponseBadRequest(
            json.dumps({'error': str(error)}, ensure_ascii=False),
            content_type='application/json',
        )

    return JsonResponse({
        'ok': True,
        'projectId': project.id,
        'dataRoot': _relative_path(data_root),
        'file': _data_source_payload(source, '焊口初始化数据.xlsx'),
        'sheet': selected_sheet,
        'sheets': sheets,
        'total': total,
        'columns': columns,
        'summary': [_module_payload(module, data_root, project) for module in _modules_for_project(project)],
        'stats': stats,
    }, json_dumps_params={'ensure_ascii': False})


@csrf_exempt
@require_POST
def update_initialization_project_metrics(request):
    project, data_root, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)

    try:
        changed = _update_project_weld_metrics(project, data_root)
    except Exception as error:
        return HttpResponseBadRequest(
            json.dumps({'error': f'更新项目字段失败：{error}'}, ensure_ascii=False),
            content_type='application/json',
        )

    return JsonResponse({
        'ok': True,
        'changed': changed,
        'project': _project_payload(project),
        'summary': [_module_payload(module, data_root, project) for module in _modules_for_project(project)],
    }, json_dumps_params={'ensure_ascii': False})


@require_GET
def welding_dashboard(request):
    project, data_root, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)
    try:
        payload = _welding_dashboard_payload(project, data_root)
    except Exception as error:
        return HttpResponseBadRequest(
            json.dumps({'error': f'读取焊接排产完成统计失败：{error}'}, ensure_ascii=False),
            content_type='application/json',
        )
    return JsonResponse(payload, json_dumps_params={'ensure_ascii': False})


@require_GET
def arrival_dashboard(request):
    project, data_root, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)
    try:
        payload = _arrival_material_dashboard_payload(project)
    except Exception as error:
        return HttpResponseBadRequest(
            json.dumps({'error': f'读取到货材料统计失败：{error}'}, ensure_ascii=False),
            content_type='application/json',
        )
    return JsonResponse(payload, json_dumps_params={'ensure_ascii': False})


@require_GET
def anti_corrosion_dashboard(request):
    project, data_root, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)
    try:
        payload = _anti_corrosion_dashboard_payload(project, data_root)
    except Exception as error:
        return HttpResponseBadRequest(
            json.dumps({'error': f'读取防腐排产统计失败：{error}'}, ensure_ascii=False),
            content_type='application/json',
        )
    return JsonResponse(payload, json_dumps_params={'ensure_ascii': False})


@require_GET
def cutting_dashboard(request):
    project, data_root, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)
    try:
        payload = _cutting_dashboard_payload(project, data_root)
    except Exception as error:
        return HttpResponseBadRequest(
            json.dumps({'error': f'读取下料排产统计失败：{error}'}, ensure_ascii=False),
            content_type='application/json',
        )
    return JsonResponse(payload, json_dumps_params={'ensure_ascii': False})


@require_GET
def arrival_files(request):
    project, data_root, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)
    ensure_project_tables(project)
    with using_project_tables(project):
        sources = list(DataSourceFile.objects.filter(project=project, source_type='arrival').order_by('-file_updated_at', '-id'))
    files = [{
        'name': source.display_name,
        'path': source.relative_path,
        'size': source.file_size,
        'updatedAt': source.file_updated_at,
    } for source in sources]
    return JsonResponse({
        'path': 'database://arrival',
        'total': len(files),
        'files': files,
    }, json_dumps_params={'ensure_ascii': False})


@require_GET
def arrival_today(request):
    project, data_root, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)

    today_text = datetime.now().strftime('%Y%m%d')

    try:
        ensure_project_tables(project)
        with using_project_tables(project):
            source = DataSourceFile.objects.filter(
                project=project,
                source_type='arrival',
                display_name=f'{today_text}.xlsx',
            ).order_by('-file_updated_at', '-id').first()
        if source is None:
            return JsonResponse({
                'date': today_text,
                'file': None,
                'sheet': '',
                'sheets': [],
                'total': 0,
                'columns': [],
                'rows': [],
                'summary': _arrival_rows_summary([]),
            }, json_dumps_params={'ensure_ascii': False})
        selected_sheet, sheets, total, columns, rows = table_payload(source, ARRIVAL_MODELS, 'Sheet2')
    except Exception as error:
        return HttpResponseBadRequest(
            json.dumps({'error': f'读取今日到货详情失败：{error}'}, ensure_ascii=False),
            content_type='application/json',
        )

    return JsonResponse({
        'date': today_text,
        'file': {
            'name': source.display_name,
            'path': source.relative_path,
            'size': source.file_size,
            'updatedAt': source.file_updated_at,
        },
        'sheet': selected_sheet,
        'sheets': sheets,
        'total': total,
        'columns': columns,
        'rows': rows,
        'summary': _arrival_rows_summary(rows),
    }, json_dumps_params={'ensure_ascii': False})


@require_GET
def arrival_file_rows(request):
    project, data_root, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)

    file_name = request.GET.get('file') or ''
    safe_name = Path(str(file_name or '')).name
    if not safe_name:
        return _project_bad_request('请选择入库单文件')

    sheet_name = request.GET.get('sheet') or None
    try:
        ensure_project_tables(project)
        with using_project_tables(project):
            source = DataSourceFile.objects.filter(
                project=project,
                source_type='arrival',
                display_name=safe_name,
            ).order_by('-file_updated_at', '-id').first()
        if source is None:
            raise ValueError(f'数据库中没有入库单：{safe_name}')
        selected_sheet, sheets, total, columns, rows = table_payload(source, ARRIVAL_MODELS, sheet_name)
    except Exception as error:
        return HttpResponseBadRequest(
            json.dumps({'error': f'读取数据库入库单失败：{error}'}, ensure_ascii=False),
            content_type='application/json',
        )

    return JsonResponse({
        'file': {
            'name': source.display_name,
            'path': source.relative_path,
            'size': source.file_size,
            'updatedAt': source.file_updated_at,
        },
        'sheet': selected_sheet,
        'sheets': sheets,
        'total': total,
        'columns': columns,
        'rows': rows,
        'summary': _arrival_rows_summary(rows),
    }, json_dumps_params={'ensure_ascii': False})


@require_GET
def cutting_visualization(request):
    project, data_root, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)

    try:
        ensure_project_tables(project)
        source_specs = [
            ('pipe-library', '普通', LIBRARY_MODELS['pipe-library']),
            ('anti-pipe-library', '防腐', LIBRARY_MODELS['anti-pipe-library']),
        ]
        frames = []
        source_paths = []
        with using_project_tables(project):
            for source_key, inventory_type, model_map in source_specs:
                source = DataSourceFile.objects.filter(
                    project=project,
                    source_type='library',
                    source_key=source_key,
                ).order_by('-file_updated_at', '-id').first()
                if source is None:
                    continue
                _, _, _, _, pipe_rows = table_payload(source, model_map, None)
                frame = pd.DataFrame(pipe_rows)
                if not frame.empty:
                    frame['库存类型'] = inventory_type
                    frames.append(frame)
                source_paths.append(source.relative_path)
        if not source_paths:
            raise ValueError('数据库中没有管子材料库，请先生成材料库')
        pipe_df = pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()
    except Exception as error:
        return HttpResponseBadRequest(
            json.dumps({'error': f'读取数据库管子材料库失败：{error}'}, ensure_ascii=False),
            content_type='application/json',
        )

    required_columns = [
        CUTTING_COLUMNS['material_code'],
        CUTTING_COLUMNS['pipe_no'],
        CUTTING_COLUMNS['cut_lengths'],
        CUTTING_COLUMNS['remaining_length'],
    ]
    missing_columns = [column for column in required_columns if column not in pipe_df.columns]
    if missing_columns:
        return HttpResponseBadRequest(
            json.dumps({'error': f'管子材料库缺少列：{", ".join(missing_columns)}'}, ensure_ascii=False),
            content_type='application/json',
        )

    rows = [_cutting_pipe_payload(row) for _, row in pipe_df.iterrows()]
    rows = [row for row in rows if row['originalLength'] > 0 and row['cutCount'] > 0]
    rows.sort(key=lambda item: (item['materialCode'], item['pipeNo']))

    total_original = round(sum(row['originalLength'] for row in rows), 3)
    total_used = round(sum(row['usedLength'] for row in rows), 3)
    total_remaining = round(sum(row['remainingLength'] for row in rows), 3)

    return JsonResponse({
        'path': '、'.join(source_paths),
        'source': 'cutting',
        'total': len(rows),
        'totalOriginalLength': total_original,
        'totalUsedLength': total_used,
        'totalRemainingLength': total_remaining,
        'averageUtilization': round(total_used / total_original * 100, 1) if total_original > 0 else 0,
        'rows': rows,
    }, json_dumps_params={'ensure_ascii': False})


@require_GET
def anti_corrosion_cutting_visualization(request):
    project, data_root, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)

    try:
        ensure_project_tables(project)
        with using_project_tables(project):
            source = DataSourceFile.objects.filter(
                project=project,
                source_type='library',
                source_key='anti-pipe-library',
            ).order_by('-file_updated_at', '-id').first()
            if source is None:
                raise ValueError('数据库中没有防腐管子材料库')
            _, _, _, _, pipe_rows = table_payload(source, LIBRARY_MODELS['anti-pipe-library'], None)
            pipe_df = pd.DataFrame(pipe_rows)
            if not pipe_df.empty:
                pipe_df['库存类型'] = '防腐'
    except Exception as error:
        return HttpResponseBadRequest(
            json.dumps({'error': f'读取数据库防腐管子材料库失败：{error}'}, ensure_ascii=False),
            content_type='application/json',
        )

    required_columns = [
        CUTTING_COLUMNS['material_code'],
        CUTTING_COLUMNS['pipe_no'],
        CUTTING_COLUMNS['cut_lengths'],
        CUTTING_COLUMNS['remaining_length'],
    ]
    missing_columns = [column for column in required_columns if column not in pipe_df.columns]
    if missing_columns:
        return HttpResponseBadRequest(
            json.dumps({'error': f'防腐管子材料库缺少列：{", ".join(missing_columns)}'}, ensure_ascii=False),
            content_type='application/json',
        )

    rows = [_cutting_pipe_payload(row) for _, row in pipe_df.iterrows()]
    rows = [row for row in rows if row['originalLength'] > 0 and row['cutCount'] > 0]
    rows.sort(key=lambda item: (item['materialCode'], item['pipeNo']))

    total_original = round(sum(row['originalLength'] for row in rows), 3)
    total_used = round(sum(row['usedLength'] for row in rows), 3)
    total_remaining = round(sum(row['remainingLength'] for row in rows), 3)

    return JsonResponse({
        'path': source.relative_path,
        'source': 'anti-corrosion',
        'total': len(rows),
        'totalOriginalLength': total_original,
        'totalUsedLength': total_used,
        'totalRemainingLength': total_remaining,
        'averageUtilization': round(total_used / total_original * 100, 1) if total_original > 0 else 0,
        'rows': rows,
    }, json_dumps_params={'ensure_ascii': False})


@require_GET
def cutting_pre_schedule_rows(request):
    project, data_root, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)

    sheet_name = request.GET.get('sheet') or None
    try:
        ensure_project_tables(project)
        with using_project_tables(project):
            source = DataSourceFile.objects.filter(
                project=project,
                source_type='pre-schedule',
                source_key='weld-pre-schedule',
            ).order_by('-file_updated_at', '-id').first()
            if source is None:
                return JsonResponse({
                    'path': '', 'sheet': '', 'sheets': [], 'total': 0, 'columns': [], 'rows': [],
                }, json_dumps_params={'ensure_ascii': False})
        selected_sheet, sheets, total, columns, rows = _pre_schedule_result_only_payload(source, sheet_name)
    except Exception as error:
        return HttpResponseBadRequest(
            json.dumps({'error': f'读取数据库焊口预排产匹配结果失败：{error}'}, ensure_ascii=False),
            content_type='application/json',
        )

    return JsonResponse({
        'path': source.relative_path,
        'sheet': selected_sheet,
        'sheets': sheets,
        'total': total,
        'columns': columns,
        'rows': rows,
    }, json_dumps_params={'ensure_ascii': False})


@csrf_exempt
@require_POST
def upload_arrival_file(request):
    project, data_root, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)

    upload_files = request.FILES.getlist('files') or request.FILES.getlist('file')
    upload_file = request.FILES.get('file')
    if not upload_files and upload_file is not None:
        upload_files = [upload_file]
    if not upload_files:
        return HttpResponseBadRequest(json.dumps({'error': '未选择入库单文件'}, ensure_ascii=False), content_type='application/json')

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    arrival_root = FILE_PARSER_ROOT / timestamp / 'arrival'
    arrival_root.mkdir(parents=True, exist_ok=True)
    imported_files = []
    try:
        for upload_file in upload_files:
            file_name = _safe_upload_name(upload_file.name)
            if file_name.startswith('~$') or Path(file_name).suffix.lower() != '.xlsx':
                raise ValueError(f'仅支持上传 .xlsx 入库单：{file_name}')
            target_path = arrival_root / file_name
            with target_path.open('wb') as target_file:
                for chunk in upload_file.chunks():
                    target_file.write(chunk)
            imported_files.append(_arrival_file_payload(target_path))
    except Exception as error:
        return HttpResponseBadRequest(json.dumps({'error': f'暂存入库单失败：{error}'}, ensure_ascii=False), content_type='application/json')

    return _arrival_import_success_response(project, data_root, imported_files, [])


def _arrival_import_success_response(project, data_root, imported_files, backup_paths):
    for file_info in imported_files:
        file_path = (BACKEND_DIR / file_info['path']).resolve()
        file_path.relative_to(BACKEND_DIR.resolve())
        replace_source_with_workbook(
            project,
            'arrival',
            file_path.name,
            file_path.name,
            f'database://arrival/{project.id}/{file_path.name}',
            file_path,
            ARRIVAL_MODELS,
        )

    try:
        result = maintain_material_libraries_from_database(project)
    except Exception as error:
        return HttpResponseBadRequest(json.dumps({
            'error': '入库单已导入，但更新材料库失败',
            'stderr': str(error),
        }, ensure_ascii=False), content_type='application/json')

    return JsonResponse({
        'file': imported_files[-1] if imported_files else None,
        'files': imported_files,
        'backupPaths': backup_paths,
        'libraryUpdate': {
            'ok': True,
            'returnCode': 0,
            'stdout': (
                f'已从数据库分流生成材料库：普通管子 {result["pipe_count"]} 条，'
                f'普通管件法兰 {result["fitting_count"]} 条，'
                f'防腐管子 {result["anti_pipe_count"]} 条，'
                f'防腐管件法兰 {result["anti_fitting_count"]} 条'
            ),
            'stderr': '',
        },
        'summary': [_module_payload(module, data_root, project) for module in _modules_for_project(project)],
    }, json_dumps_params={'ensure_ascii': False})


@require_GET
def anti_corrosion_pre_schedule_rows(request):
    project, data_root, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)

    sheet_name = request.GET.get('sheet') or None
    try:
        ensure_project_tables(project)
        with using_project_tables(project):
            source = DataSourceFile.objects.filter(
                project=project,
                source_type='pre-schedule',
                source_key='anti-corrosion-pre-schedule',
            ).order_by('-file_updated_at', '-id').first()
            if source is None:
                return JsonResponse({
                    'path': '', 'sheet': '', 'sheets': [], 'total': 0, 'columns': [], 'rows': [],
                }, json_dumps_params={'ensure_ascii': False})
        selected_sheet, sheets, total, columns, rows = _pre_schedule_result_only_payload(source, sheet_name)
    except Exception as error:
        return HttpResponseBadRequest(
            json.dumps({'error': f'读取数据库防腐预排产匹配结果失败：{error}'}, ensure_ascii=False),
            content_type='application/json',
        )

    return JsonResponse({
        'path': source.relative_path,
        'sheet': selected_sheet,
        'sheets': sheets,
        'total': total,
        'columns': columns,
        'rows': rows,
    }, json_dumps_params={'ensure_ascii': False})


@require_GET
def material_locking_rows(request):
    project, data_root, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)

    sheet_name = request.GET.get('sheet') or None
    try:
        ensure_project_tables(project)
        with using_project_tables(project):
            source = DataSourceFile.objects.filter(
                project=project,
                source_type='pre-schedule',
                source_key='material-locking',
            ).order_by('-file_updated_at', '-id').first()
            if source is None:
                return JsonResponse({
                    'path': '',
                    'sheet': '',
                    'sheets': [],
                    'total': 0,
                    'columns': [],
                    'rows': [],
                }, json_dumps_params={'ensure_ascii': False})
        selected_sheet, sheets, total, columns, rows = table_payload(source, PRE_SCHEDULE_MODELS, sheet_name)
    except Exception as error:
        return HttpResponseBadRequest(
            json.dumps({'error': f'读取数据库材料匹配锁定结果失败：{error}'}, ensure_ascii=False),
            content_type='application/json',
        )

    return JsonResponse({
        'path': source.relative_path,
        'sheet': selected_sheet,
        'sheets': sheets,
        'total': total,
        'columns': columns,
        'rows': rows,
    }, json_dumps_params={'ensure_ascii': False})


@csrf_exempt
@require_POST
def release_material_locking(request):
    project, data_root, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)
    try:
        payload = json.loads(request.body.decode('utf-8')) if request.body else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        return HttpResponseBadRequest(json.dumps({'error': '请求内容不是有效 JSON'}, ensure_ascii=False), content_type='application/json')
    if not isinstance(payload, dict):
        return HttpResponseBadRequest(json.dumps({'error': '请求内容格式无效'}, ensure_ascii=False), content_type='application/json')
    try:
        selected_library_seqs = _selected_library_seq_options(payload)
        result = release_material_locks_from_database(project, selected_library_seqs)
    except Exception as error:
        return HttpResponseBadRequest(
            json.dumps({'error': f'释放材料失败：{error}'}, ensure_ascii=False),
            content_type='application/json',
        )
    return JsonResponse({
        'ok': True,
        'projectId': project.id,
        'dataRoot': _relative_path(data_root),
        'result': result,
        'summary': [_module_payload(module, data_root, project) for module in _modules_for_project(project)],
    }, json_dumps_params={'ensure_ascii': False})


@require_GET
def welding_pre_schedule_rows(request):
    project, data_root, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)

    sheet_name = request.GET.get('sheet') or None
    try:
        ensure_project_tables(project)
        with using_project_tables(project):
            source = DataSourceFile.objects.filter(
                project=project,
                source_type='pre-schedule',
                source_key='welding-pre-schedule',
            ).order_by('-file_updated_at', '-id').first()
            if source is None:
                return JsonResponse({
                    'path': '', 'sheet': '', 'sheets': [], 'total': 0, 'columns': [], 'rows': [],
                }, json_dumps_params={'ensure_ascii': False})
        selected_sheet, sheets, total, columns, rows = _pre_schedule_result_only_payload(source, sheet_name)
    except Exception as error:
        return HttpResponseBadRequest(
            json.dumps({'error': f'读取数据库焊接预排产结果失败：{error}'}, ensure_ascii=False),
            content_type='application/json',
        )

    return JsonResponse({
        'path': source.relative_path,
        'sheet': selected_sheet,
        'sheets': sheets,
        'total': total,
        'columns': columns,
        'rows': rows,
    }, json_dumps_params={'ensure_ascii': False})


def _sync_project_database_tables(project, data_root):
    return []


@csrf_exempt
@require_POST
def confirm_arrival_import(request):
    project, data_root, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)

    try:
      payload = json.loads(request.body.decode('utf-8') or '{}')
      staged_paths = payload.get('stagedPaths') or ([payload.get('stagedPath')] if payload.get('stagedPath') else [])
      if not staged_paths:
          raise ValueError
      source_paths = [_resolve_parser_file(path) for path in staged_paths]
    except FileNotFoundError as error:
        return HttpResponseBadRequest(json.dumps({'error': str(error)}, ensure_ascii=False), content_type='application/json')
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return HttpResponseBadRequest(json.dumps({'error': '确认导入参数无效'}, ensure_ascii=False), content_type='application/json')

    imported_files = []
    try:
        for source_path in source_paths:
            file_name = re.sub(r'^\d{3}-', '', _safe_upload_name(source_path.name))
            if Path(file_name).suffix.lower() != '.xlsx':
                raise ValueError(f'仅支持导入 .xlsx 入库单：{file_name}')
            imported_files.append(_arrival_file_payload(source_path))
    except Exception as error:
        return HttpResponseBadRequest(json.dumps({'error': f'确认入库单导入失败：{error}'}, ensure_ascii=False), content_type='application/json')

    return _arrival_import_success_response(project, data_root, imported_files, [])


@csrf_exempt
@require_POST
def generate_future_schedule(request):
    project, data_root, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)

    action = ACTIONS['future-schedule']
    try:
        payload = json.loads(request.body.decode('utf-8')) if request.body else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        return HttpResponseBadRequest(json.dumps({'error': '请求内容不是有效 JSON'}, ensure_ascii=False), content_type='application/json')
    if not isinstance(payload, dict):
        return HttpResponseBadRequest(json.dumps({'error': '请求内容格式无效'}, ensure_ascii=False), content_type='application/json')

    schedule_options = {}
    option_specs = {
        'weldStartDate': str,
        'maxDays': int,
        'targetDiameter': float,
        'ordersPerDay': int,
        'dateMode': str,
        'manualWeldDates': str,
        'holidayDates': str,
        'canceledWeekendDates': str,
        'cuttingLeadDays': int,
        'antiCorrosionLeadDays': int,
        'commissionArea': float,
    }
    for key, caster in option_specs.items():
        raw_value = payload.get(key)
        if raw_value is None or raw_value == '':
            continue
        try:
            value = caster(raw_value)
        except (TypeError, ValueError):
            return HttpResponseBadRequest(json.dumps({'error': f'参数格式无效：{key}'}, ensure_ascii=False), content_type='application/json')
        if key == 'dateMode':
            value = value.strip().lower()
        if key in {'maxDays', 'ordersPerDay'} and value <= 0:
            return HttpResponseBadRequest(json.dumps({'error': f'参数必须大于 0：{key}'}, ensure_ascii=False), content_type='application/json')
        if key == 'targetDiameter' and value <= 0:
            return HttpResponseBadRequest(json.dumps({'error': f'参数必须大于 0：{key}'}, ensure_ascii=False), content_type='application/json')
        if key == 'dateMode' and value not in {'auto', 'manual'}:
            return HttpResponseBadRequest(json.dumps({'error': f'参数格式无效：{key}'}, ensure_ascii=False), content_type='application/json')
        if key in {'cuttingLeadDays', 'antiCorrosionLeadDays'} and value < 0:
            return HttpResponseBadRequest(json.dumps({'error': f'参数不能小于 0：{key}'}, ensure_ascii=False), content_type='application/json')
        if key == 'commissionArea' and value <= 0:
            return HttpResponseBadRequest(json.dumps({'error': f'参数必须大于 0：{key}'}, ensure_ascii=False), content_type='application/json')
        schedule_options[key] = value

    if payload.get('skipHolidays') is not None:
        if not isinstance(payload.get('skipHolidays'), bool):
            return HttpResponseBadRequest(json.dumps({'error': '参数格式无效：skipHolidays'}, ensure_ascii=False), content_type='application/json')
        schedule_options['skipHolidays'] = payload.get('skipHolidays')

    if schedule_options.get('dateMode') == 'manual' and not str(schedule_options.get('manualWeldDates', '')).strip():
        return HttpResponseBadRequest(json.dumps({'error': '手动选择日期不能为空'}, ensure_ascii=False), content_type='application/json')

    try:
        selection_mode = str(payload.get('selectionMode') or 'auto').strip().lower()
        if selection_mode not in {'auto', 'manual'}:
            raise ValueError('参数格式无效：selectionMode')
        schedule_options['selectionMode'] = selection_mode
        schedule_options['selectedLibrarySeqs'] = _selected_library_seq_options(payload)
        if selection_mode == 'manual' and not schedule_options['selectedLibrarySeqs']:
            raise ValueError('手动选择模式下请至少选择一条材料已到货焊口')
    except ValueError as error:
        return HttpResponseBadRequest(json.dumps({'error': str(error)}, ensure_ascii=False), content_type='application/json')

    stage_only = _truthy_payload_value(payload.get('stageOnly'))
    try:
        result = generate_future_schedule_from_database(project, persist=not stage_only, **schedule_options)
    except Exception as error:
        return HttpResponseBadRequest(
            json.dumps({'error': f'生成总排产计划失败：{error}'}, ensure_ascii=False),
            content_type='application/json',
        )
    staged_files = []
    stage_token = ''
    if stage_only:
        output_files = result.pop('_output_files', [])
        stage_token, staged_files = _stage_plan_outputs(project, result, output_files)
    return JsonResponse({
        'key': 'future-schedule',
        'name': action['name'],
        'projectId': project.id,
        'dataRoot': _relative_path(data_root),
        'options': schedule_options,
        'stageOnly': stage_only,
        'stageToken': stage_token,
        'stagedFiles': staged_files,
        'ok': True,
        'returnCode': 0,
        'stdout': (
            f'已生成总排产计划预览：{result["planned_day_count"]} 天，{result["planned_weld_count"]} 道焊口'
            if stage_only
            else f'已从数据库生成总排产计划：{result["planned_day_count"]} 天，{result["planned_weld_count"]} 道焊口'
        ),
        'stderr': '',
        'result': result,
        'summary': [_module_payload(module, data_root, project) for module in _modules_for_project(project)],
    }, json_dumps_params={'ensure_ascii': False})


@csrf_exempt
@require_POST
def run_action(request, action_key):
    project, data_root, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)

    action = ACTIONS.get(action_key)
    if action is None:
        return HttpResponseBadRequest(json.dumps({'error': '未知操作'}, ensure_ascii=False), content_type='application/json')

    try:
        payload = json.loads(request.body.decode('utf-8')) if request.body else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        return HttpResponseBadRequest(json.dumps({'error': '请求内容不是有效 JSON'}, ensure_ascii=False), content_type='application/json')
    if not isinstance(payload, dict):
        return HttpResponseBadRequest(json.dumps({'error': '请求内容格式无效'}, ensure_ascii=False), content_type='application/json')

    action_options = {}
    initialization_task_id = ''
    initialization_cancel_event = None

    if action_key == 'prefab-weld-library':
        fill_material_units = payload.get('fillMaterialUnits', True)
        if not isinstance(fill_material_units, bool):
            return HttpResponseBadRequest(
                json.dumps({'error': '参数格式无效：fillMaterialUnits'}, ensure_ascii=False),
                content_type='application/json',
            )
        action_options['fillMaterialUnits'] = fill_material_units
        initialization_filters = payload.get('initializationFilters', {})
        if not isinstance(initialization_filters, dict) or any(
            not isinstance(value, bool) for value in initialization_filters.values()
        ):
            return HttpResponseBadRequest(
                json.dumps({'error': '参数格式无效：initializationFilters'}, ensure_ascii=False),
                content_type='application/json',
            )
        action_options['initializationFilters'] = initialization_filters
        initialization_task_id = str(payload.get('taskId') or '').strip()
        initialization_cancel_event = _register_initialization_task(initialization_task_id)

    if action_key == 'anti-corrosion-pre-schedule':
        try:
            action_options.update(_pre_schedule_action_options(
                payload,
            ))
        except ValueError as error:
            return HttpResponseBadRequest(
                json.dumps({'error': str(error)}, ensure_ascii=False),
                content_type='application/json',
            )

    if action_key == 'material-locking':
        try:
            action_options.update(_pre_schedule_action_options(payload))
            selection_mode = str(payload.get('selectionMode') or 'auto').strip().lower()
            if selection_mode not in {'auto', 'manual'}:
                raise ValueError('参数格式无效：selectionMode')
            action_options['selectionMode'] = selection_mode
            action_options['selectedLibrarySeqs'] = _selected_library_seq_options(payload)
            if selection_mode == 'manual' and not action_options['selectedLibrarySeqs']:
                raise ValueError('手动选择模式下请至少选择一条预制焊口记录')
        except ValueError as error:
            return HttpResponseBadRequest(
                json.dumps({'error': str(error)}, ensure_ascii=False),
                content_type='application/json',
            )

    if action_key == 'anti-corrosion-schedule':
        stage_only = _truthy_payload_value(payload.get('stageOnly'))
        action_options['stageOnly'] = stage_only
        raw_commission_area = payload.get('commissionArea', 1500)
        if raw_commission_area in (None, ''):
            raw_commission_area = 1500
        try:
            commission_area = float(raw_commission_area)
        except (TypeError, ValueError):
            return HttpResponseBadRequest(json.dumps({'error': '参数格式无效：commissionArea'}, ensure_ascii=False), content_type='application/json')
        if commission_area <= 0:
            return HttpResponseBadRequest(json.dumps({'error': '参数必须大于 0：commissionArea'}, ensure_ascii=False), content_type='application/json')
        action_options['commissionArea'] = commission_area
        commission_date_option_specs = {
            'weldStartDate': str,
            'maxDays': int,
            'dateMode': str,
            'manualWeldDates': str,
            'holidayDates': str,
            'canceledWeekendDates': str,
        }
        for key, caster in commission_date_option_specs.items():
            raw_value = payload.get(key)
            if raw_value is None or raw_value == '':
                continue
            try:
                value = caster(raw_value)
            except (TypeError, ValueError):
                return HttpResponseBadRequest(json.dumps({'error': f'参数格式无效：{key}'}, ensure_ascii=False), content_type='application/json')
            if key == 'dateMode':
                value = value.strip().lower()
                if value not in {'auto', 'manual'}:
                    return HttpResponseBadRequest(json.dumps({'error': f'参数格式无效：{key}'}, ensure_ascii=False), content_type='application/json')
            if key == 'maxDays' and value <= 0:
                return HttpResponseBadRequest(json.dumps({'error': f'参数必须大于 0：{key}'}, ensure_ascii=False), content_type='application/json')
            action_options[key] = value
        if payload.get('skipHolidays') is not None:
            if not isinstance(payload.get('skipHolidays'), bool):
                return HttpResponseBadRequest(json.dumps({'error': '参数格式无效：skipHolidays'}, ensure_ascii=False), content_type='application/json')
            action_options['skipHolidays'] = payload.get('skipHolidays')
        if action_options.get('dateMode') == 'manual' and not str(action_options.get('manualWeldDates', '')).strip():
            return HttpResponseBadRequest(json.dumps({'error': '手动选择日期不能为空'}, ensure_ascii=False), content_type='application/json')
        try:
            selection_mode = str(payload.get('selectionMode') or 'auto').strip().lower()
            if selection_mode not in {'auto', 'manual'}:
                raise ValueError('参数格式无效：selectionMode')
            action_options['selectionMode'] = selection_mode
            action_options['selectedLibrarySeqs'] = _selected_library_seq_options(payload)
            if selection_mode == 'manual' and not action_options['selectedLibrarySeqs']:
                raise ValueError('手动选择模式下请至少选择一条防腐预排产记录')
        except ValueError as error:
            return HttpResponseBadRequest(json.dumps({'error': str(error)}, ensure_ascii=False), content_type='application/json')

    if action_key in {'auto-weld-schedule', 'cutting-schedule'}:
        action_options['stageOnly'] = _truthy_payload_value(payload.get('stageOnly'))
        schedule_date_option_specs = {
            'weldStartDate': str,
            'maxDays': int,
            'dateMode': str,
            'manualWeldDates': str,
            'holidayDates': str,
            'canceledWeekendDates': str,
        }
        for key, caster in schedule_date_option_specs.items():
            raw_value = payload.get(key)
            if raw_value is None or raw_value == '':
                continue
            try:
                value = caster(raw_value)
            except (TypeError, ValueError):
                return HttpResponseBadRequest(json.dumps({'error': f'参数格式无效：{key}'}, ensure_ascii=False), content_type='application/json')
            if key == 'dateMode':
                value = value.strip().lower()
                if value not in {'auto', 'manual'}:
                    return HttpResponseBadRequest(json.dumps({'error': f'参数格式无效：{key}'}, ensure_ascii=False), content_type='application/json')
            if key == 'maxDays' and value <= 0:
                return HttpResponseBadRequest(json.dumps({'error': f'参数必须大于 0：{key}'}, ensure_ascii=False), content_type='application/json')
            action_options[key] = value
        if payload.get('skipHolidays') is not None:
            if not isinstance(payload.get('skipHolidays'), bool):
                return HttpResponseBadRequest(json.dumps({'error': '参数格式无效：skipHolidays'}, ensure_ascii=False), content_type='application/json')
            action_options['skipHolidays'] = payload.get('skipHolidays')
        if action_options.get('dateMode') == 'manual' and not str(action_options.get('manualWeldDates', '')).strip():
            return HttpResponseBadRequest(json.dumps({'error': '手动选择日期不能为空'}, ensure_ascii=False), content_type='application/json')
        if action_key == 'cutting-schedule':
            try:
                selection_mode = str(payload.get('selectionMode') or 'auto').strip().lower()
                if selection_mode not in {'auto', 'manual'}:
                    raise ValueError('参数格式无效：selectionMode')
                action_options['selectionMode'] = selection_mode
                action_options['selectedLibrarySeqs'] = _selected_library_seq_options(payload)
                if selection_mode == 'manual' and not action_options['selectedLibrarySeqs']:
                    raise ValueError('手动选择模式下请至少选择一条下料预排产记录')
            except ValueError as error:
                return HttpResponseBadRequest(
                    json.dumps({'error': str(error)}, ensure_ascii=False),
                    content_type='application/json',
                )

    if action_key in {'auto-weld-schedule', 'cutting-schedule'}:
        welding_option_specs = {
            'weldDate': str,
            'cutDate': str,
            'targetDiameter': float,
            'ordersPerDay': int,
        }
        for key, caster in welding_option_specs.items():
            raw_value = payload.get(key)
            if raw_value is None or raw_value == '':
                continue
            try:
                value = caster(raw_value)
            except (TypeError, ValueError):
                return HttpResponseBadRequest(json.dumps({'error': f'参数格式无效：{key}'}, ensure_ascii=False), content_type='application/json')
            if key in {'weldDate', 'cutDate'}:
                value = str(value).strip()
                if not re.fullmatch(r'\d{4}-\d{2}-\d{2}|\d{8}', value):
                    return HttpResponseBadRequest(json.dumps({'error': f'参数格式无效：{key}'}, ensure_ascii=False), content_type='application/json')
            elif value <= 0:
                return HttpResponseBadRequest(json.dumps({'error': f'参数必须大于 0：{key}'}, ensure_ascii=False), content_type='application/json')
            action_options[key] = value

    try:
        if action_key == 'prefab-weld-library':
            result = maintain_weld_library_from_database(
                project,
                fill_material_units=action_options.get('fillMaterialUnits', True),
                initialization_filters=action_options.get('initializationFilters'),
                cancellation_check=initialization_cancel_event.is_set if initialization_cancel_event else None,
            )
            _update_project_weld_metrics(project, data_root)
            stdout = f'已从数据库生成预制焊口库：{result["weld_count"]} 条'
        elif action_key == 'arrival-library':
            result = maintain_material_libraries_from_database(project)
            stdout = (
                f'已从数据库生成统一材料库：管子 {result["pipe_count"]} 条，'
                f'管件法兰 {result["fitting_count"]} 条'
            )
        elif action_key == 'material-locking':
            result = match_and_lock_materials_from_database(
                project,
                only_auto_weld=action_options.get('onlyAutoWeld', False),
                concentration_dimension=action_options.get('concentrationDimension'),
                concentration_threshold_percent=action_options.get('concentrationThresholdPercent'),
                selection_mode=action_options.get('selectionMode', 'auto'),
                selected_library_seqs=action_options.get('selectedLibrarySeqs'),
            )
            stdout = (
                f'已完成材料匹配与锁定：已锁定 {result["locked_count"]} 条，'
                f'不可锁定 {result["rejected_count"]} 条'
            )
        elif action_key == 'update-weld-arrival-status':
            result = update_weld_material_arrival_status_from_database(project)
            stdout = (
                f'已更新预制焊口库材料到货状态：已到货 {result["arrived_count"]} 条，'
                f'未到货 {result["pending_count"]} 条'
            )
        elif action_key == 'anti-corrosion-pre-schedule':
            result = match_anti_corrosion_pre_schedule_from_database(
                project,
                only_auto_weld=action_options.get('onlyAutoWeld', False),
                concentration_dimension=action_options.get('concentrationDimension'),
                concentration_threshold_percent=action_options.get('concentrationThresholdPercent'),
            )
            stdout = (
                f'已从数据库生成防腐预排产：可排管段 {result["pre_schedule_segment_count"]} 个，'
                f'不可排管段 {result["rejected_segment_count"]} 个'
            )
        elif action_key == 'anti-corrosion-schedule':
            result = generate_anti_corrosion_schedule_from_database(
                project,
                commission_area=action_options.get('commissionArea'),
                selected_library_seqs=action_options.get('selectedLibrarySeqs'),
                selection_mode=action_options.get('selectionMode', 'auto'),
                persist=not action_options.get('stageOnly'),
                dateMode=action_options.get('dateMode'),
                weldStartDate=action_options.get('weldStartDate'),
                manualWeldDates=action_options.get('manualWeldDates'),
                maxDays=action_options.get('maxDays'),
                skipHolidays=action_options.get('skipHolidays'),
                holidayDates=action_options.get('holidayDates'),
                canceledWeekendDates=action_options.get('canceledWeekendDates'),
            )
            stdout = (
                f'已生成防腐委托预览：{result["summary_count"]} 条'
                if action_options.get('stageOnly')
                else f'已从数据库生成防腐委托：{result["summary_count"]} 条'
            )
        elif action_key == 'weld-pre-schedule':
            result = match_weld_pre_schedule_from_database(
                project,
            )
            stdout = f'已从数据库生成下料预排产：可排 {result["pre_schedule_count"]} 条'
        elif action_key == 'cutting-schedule':
            result = generate_cutting_schedule_from_database(
                project,
                cut_date=action_options.get('cutDate') or action_options.get('weldDate'),
                target_diameter=action_options.get('targetDiameter'),
                orders_per_day=action_options.get('ordersPerDay'),
                persist=not action_options.get('stageOnly'),
                dateMode=action_options.get('dateMode'),
                weldStartDate=action_options.get('weldStartDate'),
                manualWeldDates=action_options.get('manualWeldDates'),
                maxDays=action_options.get('maxDays'),
                skipHolidays=action_options.get('skipHolidays'),
                holidayDates=action_options.get('holidayDates'),
                canceledWeekendDates=action_options.get('canceledWeekendDates'),
                selection_mode=action_options.get('selectionMode', 'auto'),
                selected_library_seqs=action_options.get('selectedLibrarySeqs'),
            )
            stdout = (
                f'已生成下料排产单预览：{result["order_count"]} 张排产单，{result["weld_count"]} 道焊口'
                if action_options.get('stageOnly')
                else f'已从数据库生成下料排产单：{result["order_count"]} 张排产单，{result["weld_count"]} 道焊口'
            )
        elif action_key == 'welding-pre-schedule':
            result = match_welding_pre_schedule_from_database(project)
            stdout = f'已从数据库生成焊接预排产：可排 {result["pre_schedule_count"]} 条'
        elif action_key == 'auto-weld-schedule':
            result = generate_welding_schedule_from_database(
                project,
                weld_date=action_options.get('weldDate'),
                target_diameter=action_options.get('targetDiameter'),
                orders_per_day=action_options.get('ordersPerDay'),
                persist=not action_options.get('stageOnly'),
                dateMode=action_options.get('dateMode'),
                weldStartDate=action_options.get('weldStartDate'),
                manualWeldDates=action_options.get('manualWeldDates'),
                maxDays=action_options.get('maxDays'),
                skipHolidays=action_options.get('skipHolidays'),
                holidayDates=action_options.get('holidayDates'),
                canceledWeekendDates=action_options.get('canceledWeekendDates'),
            )
            stdout = (
                f'已生成焊接排产预览：{result["order_count"]} 张排产单，{result["weld_count"]} 道焊口'
                if action_options.get('stageOnly')
                else f'已从数据库生成焊接排产：{result["order_count"]} 张排产单，{result["weld_count"]} 道焊口'
            )
        else:
            return HttpResponseBadRequest(json.dumps({'error': f'动作尚未支持数据库执行：{action_key}'}, ensure_ascii=False), content_type='application/json')
    except Exception as error:
        _finish_initialization_task(initialization_task_id)
        error_text = f'{action["name"]}失败：{error}'
        return HttpResponseBadRequest(
            json.dumps({
                'key': action_key,
                'name': action['name'],
                'projectId': project.id,
                'dataRoot': _relative_path(data_root),
                'options': action_options,
                'stageOnly': False,
                'stageToken': '',
                'stagedFiles': [],
                'ok': False,
                'returnCode': 1,
                'stdout': '',
                'stderr': error_text,
                'error': error_text,
                'summary': [_module_payload(module, data_root, project) for module in _modules_for_project(project)],
            }, ensure_ascii=False),
            content_type='application/json',
        )

    _finish_initialization_task(initialization_task_id)
    staged_files = []
    stage_token = ''
    if action_options.get('stageOnly'):
        output_files = result.pop('_output_files', [])
        stage_token, staged_files = _stage_plan_outputs(project, result, output_files)

    return JsonResponse({
        'key': action_key,
        'name': action['name'],
        'projectId': project.id,
        'dataRoot': _relative_path(data_root),
        'options': action_options,
        'stageOnly': bool(action_options.get('stageOnly')),
        'stageToken': stage_token,
        'stagedFiles': staged_files,
        'ok': True,
        'returnCode': 0,
        'stdout': stdout,
        'stderr': '',
        'result': result,
        'summary': [_module_payload(module, data_root, project) for module in _modules_for_project(project)],
    }, json_dumps_params={'ensure_ascii': False})


@csrf_exempt
@require_POST
def commit_staged_plan(request):
    project, data_root, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
        token = payload.get('stageToken') or payload.get('token')
        copied_files = commit_staged_plan_outputs(project, token)
        backup_paths, sync_warnings = [], []
    except Exception as error:
        return HttpResponseBadRequest(json.dumps({'error': f'保存暂存计划失败：{error}'}, ensure_ascii=False), content_type='application/json')

    return JsonResponse({
        'ok': True,
        'savedFiles': copied_files,
        'backupPaths': backup_paths,
        'syncWarnings': sync_warnings,
        'savedCount': len(copied_files),
        'summary': [_module_payload(module, data_root, project) for module in _modules_for_project(project)],
    }, json_dumps_params={'ensure_ascii': False})


@csrf_exempt
@require_POST
def discard_staged_plans(request):
    project, _, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
        tokens = payload.get('stageTokens') or []
        if not isinstance(tokens, list):
            tokens = [tokens]
        discarded_count = sum(discard_staged_plan_outputs(project, token) for token in set(tokens) if token)
    except Exception as error:
        return HttpResponseBadRequest(
            json.dumps({'error': f'删除暂存计划失败：{error}'}, ensure_ascii=False),
            content_type='application/json',
        )
    return JsonResponse({'ok': True, 'discardedCount': discarded_count})


@require_GET
def staged_plan_file_rows(request):
    project, _, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)

    token = request.GET.get('stageToken') or request.GET.get('token')
    source_key = request.GET.get('sourceKey') or ''
    relative_path = request.GET.get('path') or request.GET.get('file')
    sheet_name = request.GET.get('sheet')
    if not token:
        return _project_bad_request('暂存令牌不能为空')
    if not source_key and not relative_path:
        return _project_bad_request('暂存计划文件不能为空')

    try:
        ensure_project_tables(project)
        with using_project_tables(project):
            queryset = DataSourceFile.objects.filter(
                project=project,
                source_type='plan-stage',
                source_key__startswith=f'{str(token).strip()}:',
            )
            if source_key:
                source = queryset.filter(source_key=source_key).first()
            else:
                target_suffix = str(relative_path).strip()
                source = None
                for item in queryset.order_by('-file_updated_at', '-id'):
                    suffix = ':'.join(str(item.source_key or '').split(':', 1)[1:])
                    if suffix == target_suffix:
                        source = item
                        break
            if source is None:
                raise FileNotFoundError('暂存计划不存在或已失效')
        file_name = str(source.display_name or '')
        sheet_models = _plan_file_models(file_name)
        if sheet_models is None:
            workbook_payload = staged_plan_workbook_payload(source.source_key)
            if not workbook_payload:
                raise ValueError(f'暂存计划文件未配置结构化数据表：{file_name}')
            sheets = list(workbook_payload.keys())
            selected_sheet = sheet_name if sheet_name in sheets else (sheets[0] if sheets else '')
            dataframe = workbook_payload.get(selected_sheet) if selected_sheet else pd.DataFrame()
            payload = dataframe_payload(dataframe)
            total = len(payload['rows'])
            columns = payload['columns']
            rows = payload['rows']
        else:
            selected_sheet, sheets, total, columns, rows = table_payload(source, sheet_models, sheet_name)
        parsed_source = str(source.source_key or '').split(':', 3)
        if len(parsed_source) >= 2 and parsed_source[1] == 'cutting':
            columns, rows = strip_cutting_plan_columns(columns, rows, project)
        if len(parsed_source) >= 2 and parsed_source[1] == 'welding' and file_name == '管段焊口表.xlsx':
            columns, rows = strip_welding_plan_columns(project, columns, rows)
    except Exception as error:
        return HttpResponseBadRequest(
            json.dumps({'error': str(error)}, ensure_ascii=False),
            content_type='application/json',
        )

    return JsonResponse({
        'path': relative_path or ':'.join(str(source.source_key).split(':', 1)[1:]),
        'sourceKey': source.source_key,
        'name': source.display_name or file_name,
        'sheet': selected_sheet,
        'sheets': sheets,
        'total': total,
        'columns': columns,
        'rows': rows,
    }, json_dumps_params={'ensure_ascii': False})
