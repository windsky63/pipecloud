from .common import *
from pipecloud.services.db_storage import (
    ARRIVAL_MODELS,
    INITIALIZATION_MODELS,
    PRE_SCHEDULE_MODELS,
    LIBRARY_MODELS,
    PLAN_FILE_MODELS,
    latest_source,
    replace_source_with_workbook,
    table_payload,
)
from pipecloud.services.prefab_database import (
    commit_staged_plan_outputs,
    confirm_pre_schedule_from_database,
    generate_anti_corrosion_schedule_from_database,
    generate_future_schedule_from_database,
    generate_welding_schedule_from_database,
    maintain_weld_library_from_database,
    maintain_material_libraries_from_database,
    match_weld_pre_schedule_from_database,
    prepare_anti_corrosion_libraries_from_database,
    stage_plan_output_files,
)


def _truthy_payload_value(value):
    if isinstance(value, bool):
        return value
    return str(value or '').strip().lower() in {'1', 'true', 'yes', 'y', 'on'}


def _stage_plan_outputs(project, result, output_files):
    return stage_plan_output_files(project, output_files)


@require_GET
def summary(request):
    project, data_root, error = _request_project_context(request)
    if error:
        return _project_bad_request(error)
    return JsonResponse({
        'root': _relative_path(PREFAB_ROOT),
        'dataRoot': _relative_path(data_root),
        'projectId': project.id if project else None,
        'modules': [_module_payload(module, data_root, project) for module in MODULES],
        'actions': [_action_payload(key) for key in ACTIONS],
    }, json_dumps_params={'ensure_ascii': False})


@require_GET
def files(request):
    project, data_root, error = _request_project_context(request)
    if error:
        return _project_bad_request(error)
    all_files = []
    for module in MODULES:
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
        'summary': [_module_payload(module, data_root, project) for module in MODULES],
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
        'summary': [_module_payload(module, data_root, project) for module in MODULES],
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
        with using_project_tables(project):
            source = DataSourceFile.objects.filter(
                project=project,
                source_type='library',
                source_key='pending-anti-pipe-library',
            ).order_by('-file_updated_at', '-id').first()
            if source is None:
                raise ValueError('数据库中没有待确认防腐管子材料库，请先生成下料预排产')
        _, _, _, _, pipe_rows = table_payload(source, LIBRARY_MODELS['anti-pipe-library'], None)
        pipe_df = pd.DataFrame(pipe_rows)
    except Exception as error:
        return HttpResponseBadRequest(
            json.dumps({'error': f'读取数据库待确认防腐管子材料库失败：{error}'}, ensure_ascii=False),
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
            json.dumps({'error': f'待确认防腐管子材料库缺少列：{", ".join(missing_columns)}'}, ensure_ascii=False),
            content_type='application/json',
        )

    rows = [_cutting_pipe_payload(row) for _, row in pipe_df.iterrows()]
    rows = [row for row in rows if row['originalLength'] > 0 and (row['cutCount'] > 0 or row['remainingLength'] > 0)]
    rows.sort(key=lambda item: (item['materialCode'], item['pipeNo']))

    total_original = round(sum(row['originalLength'] for row in rows), 3)
    total_used = round(sum(row['usedLength'] for row in rows), 3)
    total_remaining = round(sum(row['remainingLength'] for row in rows), 3)

    return JsonResponse({
        'path': source.relative_path,
        'source': 'pending',
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
                raise ValueError('数据库中没有焊口预排产匹配结果')
        selected_sheet, sheets, total, columns, rows = table_payload(source, PRE_SCHEDULE_MODELS, sheet_name)
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
            'stdout': f'已从数据库生成材料库：管子 {result["pipe_count"]} 条，管件法兰 {result["fitting_count"]} 条',
            'stderr': '',
        },
        'summary': [_module_payload(module, data_root, project) for module in MODULES],
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
        if key == 'cuttingLeadDays' and value < 0:
            return HttpResponseBadRequest(json.dumps({'error': f'参数不能小于 0：{key}'}, ensure_ascii=False), content_type='application/json')
        schedule_options[key] = value

    if payload.get('skipHolidays') is not None:
        if not isinstance(payload.get('skipHolidays'), bool):
            return HttpResponseBadRequest(json.dumps({'error': '参数格式无效：skipHolidays'}, ensure_ascii=False), content_type='application/json')
        schedule_options['skipHolidays'] = payload.get('skipHolidays')

    if schedule_options.get('dateMode') == 'manual' and not str(schedule_options.get('manualWeldDates', '')).strip():
        return HttpResponseBadRequest(json.dumps({'error': '手动选择日期不能为空'}, ensure_ascii=False), content_type='application/json')

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
        'summary': [_module_payload(module, data_root, project) for module in MODULES],
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

    if action_key == 'weld-pre-schedule' and 'onlyAutoWeld' in payload:
        only_auto_weld = payload.get('onlyAutoWeld')
        if not isinstance(only_auto_weld, bool):
            return HttpResponseBadRequest(
                json.dumps({'error': '参数格式无效：onlyAutoWeld'}, ensure_ascii=False),
                content_type='application/json',
            )
        action_options['onlyAutoWeld'] = only_auto_weld

    if action_key == 'auto-weld-schedule':
        welding_option_specs = {
            'weldDate': str,
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
            if key == 'weldDate':
                value = str(value).strip()
                if not re.fullmatch(r'\d{4}-\d{2}-\d{2}|\d{8}', value):
                    return HttpResponseBadRequest(json.dumps({'error': f'参数格式无效：{key}'}, ensure_ascii=False), content_type='application/json')
            elif value <= 0:
                return HttpResponseBadRequest(json.dumps({'error': f'参数必须大于 0：{key}'}, ensure_ascii=False), content_type='application/json')
            action_options[key] = value

    try:
        if action_key == 'prefab-weld-library':
            result = maintain_weld_library_from_database(project)
            _update_project_weld_metrics(project, data_root)
            stdout = f'已从数据库生成预制焊口库：{result["weld_count"]} 条'
        elif action_key == 'arrival-library':
            result = maintain_material_libraries_from_database(project)
            stdout = f'已从数据库生成材料库：管子 {result["pipe_count"]} 条，管件法兰 {result["fitting_count"]} 条'
        elif action_key == 'prepare-anti-corrosion-libraries':
            result = prepare_anti_corrosion_libraries_from_database(project)
            stdout = f'已从数据库生成防腐材料库：管子 {result["pipe_count"]} 条，管件法兰 {result["fitting_count"]} 条'
        elif action_key == 'anti-corrosion-schedule':
            result = generate_anti_corrosion_schedule_from_database(project)
            stdout = f'已从数据库生成防腐委托汇总：{result["summary_count"]} 条'
        elif action_key == 'weld-pre-schedule':
            result = match_weld_pre_schedule_from_database(project, action_options.get('onlyAutoWeld'))
            stdout = f'已从数据库生成焊口预排产：可排 {result["pre_schedule_count"]} 条，不可排 {result["rejected_count"]} 条'
        elif action_key == 'confirm-cutting-pre-schedule':
            result = confirm_pre_schedule_from_database(project)
            stdout = f'已确认数据库防腐材料库：管子 {result["pipe_count"]} 条，管件法兰 {result["fitting_count"]} 条'
        elif action_key == 'auto-weld-schedule':
            result = generate_welding_schedule_from_database(
                project,
                weld_date=action_options.get('weldDate'),
                target_diameter=action_options.get('targetDiameter'),
                orders_per_day=action_options.get('ordersPerDay'),
            )
            stdout = f'已从数据库生成焊接排产：{result["order_count"]} 张排产单，{result["weld_count"]} 道焊口'
        else:
            return HttpResponseBadRequest(json.dumps({'error': f'动作尚未支持数据库执行：{action_key}'}, ensure_ascii=False), content_type='application/json')
    except Exception as error:
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
                'summary': [_module_payload(module, data_root, project) for module in MODULES],
            }, ensure_ascii=False),
            content_type='application/json',
        )

    return JsonResponse({
        'key': action_key,
        'name': action['name'],
        'projectId': project.id,
        'dataRoot': _relative_path(data_root),
        'options': action_options,
        'stageOnly': False,
        'stageToken': '',
        'stagedFiles': [],
        'ok': True,
        'returnCode': 0,
        'stdout': stdout,
        'stderr': '',
        'result': result,
        'summary': [_module_payload(module, data_root, project) for module in MODULES],
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
        'summary': [_module_payload(module, data_root, project) for module in MODULES],
    }, json_dumps_params={'ensure_ascii': False})


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
        sheet_models = PLAN_FILE_MODELS.get(file_name)
        if sheet_models is None:
            raise ValueError(f'暂存计划文件未配置结构化数据表：{file_name}')
        selected_sheet, sheets, total, columns, rows = table_payload(source, sheet_models, sheet_name)
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
