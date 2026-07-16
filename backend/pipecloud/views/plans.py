from .common import *
from django.db import transaction
from pipecloud.services.db_storage import replace_source_sheet_rows, table_payload
from pipecloud.services.plan_completion import sync_project_plan_completion
from pipecloud.services.prefab_database import (
    delete_plan_stage,
    derived_plan_file_payload,
    cutting_primary_plan_payload_from_master,
    reconcile_anti_corrosion_material_order_plan,
    strip_cutting_plan_columns,
    strip_welding_plan_columns,
    _plan_file_models,
)
from pipecloud.services.project_tables import ensure_project_tables, using_project_tables


@require_GET
def plan_rows(request, plan_key):
    project, data_root, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)
    payload = _plan_payload(project, plan_key, request.GET.get('date') or None, _plan_sources(data_root))
    if payload is None:
        return HttpResponseBadRequest(json.dumps({'error': '未知计划类型'}, ensure_ascii=False), content_type='application/json')
    return JsonResponse(payload, json_dumps_params={'ensure_ascii': False})


@csrf_exempt
@require_POST
def move_plan_date(request, plan_key):
    project, data_root, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)

    plan_sources = _plan_sources(data_root)
    source = plan_sources.get(plan_key)
    if source is None:
        return HttpResponseBadRequest(json.dumps({'error': '未知计划类型'}, ensure_ascii=False), content_type='application/json')

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        return HttpResponseBadRequest(json.dumps({'error': '请求数据无效'}, ensure_ascii=False), content_type='application/json')

    record_id = payload.get('recordId') or payload.get('id')
    target_date = str(payload.get('targetDate') or payload.get('planDate') or '').replace('-', '')
    if not record_id:
        return HttpResponseBadRequest(json.dumps({'error': '缺少计划记录'}, ensure_ascii=False), content_type='application/json')
    if not _is_date_value(target_date):
        return HttpResponseBadRequest(json.dumps({'error': '目标日期无效'}, ensure_ascii=False), content_type='application/json')

    try:
        ensure_project_tables(project)
        with using_project_tables(project):
            record = PlanRecord.objects.get(pk=record_id, project=project, plan_key=plan_key)
    except PlanRecord.DoesNotExist:
        return HttpResponseBadRequest(json.dumps({'error': '计划记录不存在'}, ensure_ascii=False), content_type='application/json')

    if record.plan_date == target_date and record.plan_folder == target_date:
        return JsonResponse({'ok': True, 'record': _plan_record_payload(record)}, json_dumps_params={'ensure_ascii': False})

    try:
        with using_project_tables(project):
            if PlanRecord.objects.filter(project=project, plan_key=plan_key, plan_folder=target_date).exclude(pk=record.pk).exists():
                return HttpResponseBadRequest(json.dumps({'error': f'目标日期已有{source["name"]}计划'}, ensure_ascii=False), content_type='application/json')
            old_prefix = f'{plan_key}:{record.plan_folder}:'
            new_prefix = f'{plan_key}:{target_date}:'
            for data_source in DataSourceFile.objects.filter(project=project, source_type='plan', source_key__startswith=old_prefix):
                file_name = data_source.source_key[len(old_prefix):]
                data_source.source_key = f'{new_prefix}{file_name}'
                data_source.relative_path = f'database://plan/{plan_key}/{target_date}/{file_name}'
                data_source.save(update_fields=['source_key', 'relative_path', 'imported_at'])
            files = []
            for item in record.files or []:
                next_item = dict(item)
                name = next_item.get('name') or ''
                next_item['path'] = f'database://plan/{plan_key}/{target_date}/{name}'
                next_item['updatedAt'] = datetime.now().timestamp()
                files.append(next_item)
            record.plan_date = target_date
            record.plan_folder = target_date
            record.relative_path = f'database://plan/{plan_key}/{target_date}'
            record.folder_updated_at = datetime.now().timestamp()
            record.files = files
            record.save(update_fields=['plan_date', 'plan_folder', 'relative_path', 'folder_updated_at', 'files', 'updated_at'])
    except Exception as error:
        return HttpResponseBadRequest(
            json.dumps({'error': f'修改计划日期失败：{error}'}, ensure_ascii=False),
            content_type='application/json',
        )

    with using_project_tables(project):
        moved_record = PlanRecord.objects.filter(project=project, plan_key=plan_key, plan_folder=target_date).first()
    return JsonResponse({
        'ok': True,
        'record': _plan_record_payload(moved_record) if moved_record else None,
    }, json_dumps_params={'ensure_ascii': False})


@csrf_exempt
@require_POST
def delete_plan(request, plan_key):
    project, data_root, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)

    plan_sources = _plan_sources(data_root)
    if plan_key not in plan_sources:
        return HttpResponseBadRequest(json.dumps({'error': '未知计划类型'}, ensure_ascii=False), content_type='application/json')

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        return HttpResponseBadRequest(json.dumps({'error': '请求数据无效'}, ensure_ascii=False), content_type='application/json')

    record_id = payload.get('recordId') or payload.get('id')
    if not record_id:
        return HttpResponseBadRequest(json.dumps({'error': '缺少计划记录'}, ensure_ascii=False), content_type='application/json')

    try:
        ensure_project_tables(project)
        with using_project_tables(project):
            record = PlanRecord.objects.get(pk=record_id, project=project, plan_key=plan_key)
    except PlanRecord.DoesNotExist:
        return HttpResponseBadRequest(json.dumps({'error': '计划记录不存在'}, ensure_ascii=False), content_type='application/json')

    plan_date = record.plan_date
    plan_folder = record.plan_folder
    deleted_rows = 0
    deleted_sources = 0
    deleted_records = 0
    cleared_master_rows = 0
    deleted_master_rows = 0
    linked_plan_folders = {}
    try:
        with using_project_tables(project), transaction.atomic():
            delete_result = delete_plan_stage(project, plan_key, plan_folder)
            deleted_sources = delete_result['deletedSources']
            deleted_records = delete_result['deletedRecords']
            cleared_master_rows = delete_result['clearedMasterRows']
            deleted_master_rows = delete_result['deletedMasterRows']
            linked_plan_folders = delete_result['planFolders']
    except Exception as error:
        return HttpResponseBadRequest(
            json.dumps({'error': f'删除计划失败：{error}'}, ensure_ascii=False),
            content_type='application/json',
        )

    return JsonResponse({
        'ok': True,
        'planKey': plan_key,
        'planDate': plan_date,
        'deletedRows': deleted_rows,
        'deletedSources': deleted_sources,
        'deletedRecords': deleted_records,
        'clearedMasterRows': cleared_master_rows,
        'deletedMasterRows': deleted_master_rows,
        'linkedPlanFolders': linked_plan_folders,
    }, json_dumps_params={'ensure_ascii': False})


@require_GET
def plan_file_rows(request, plan_key):
    project, data_root, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)
    plan_sources = _plan_sources(data_root)
    if plan_key not in plan_sources:
        return HttpResponseBadRequest(json.dumps({'error': '未知计划类型'}, ensure_ascii=False), content_type='application/json')
    plan_folder = request.GET.get('planFolder') or request.GET.get('folder') or request.GET.get('date') or ''
    file_name = request.GET.get('file') or ''
    if not plan_folder or Path(plan_folder).name != plan_folder:
        return HttpResponseBadRequest(json.dumps({'error': '计划文件夹无效'}, ensure_ascii=False), content_type='application/json')
    if not file_name or Path(file_name).name != file_name:
        return HttpResponseBadRequest(json.dumps({'error': '文件名无效'}, ensure_ascii=False), content_type='application/json')
    sheet_name = request.GET.get('sheet') or None
    try:
        if plan_key == 'anti-corrosion' and file_name == '防腐焊口单.xlsx':
            derived_payload = derived_plan_file_payload(project, plan_key, plan_folder, file_name, sheet_name)
            if derived_payload is not None:
                return JsonResponse(derived_payload, json_dumps_params={'ensure_ascii': False})
        sheet_models = _plan_file_models(file_name)
        if sheet_models is None:
            derived_payload = derived_plan_file_payload(project, plan_key, plan_folder, file_name, sheet_name)
            if derived_payload is None:
                raise ValueError(f'计划文件未配置结构化数据表：{file_name}')
            return JsonResponse(derived_payload, json_dumps_params={'ensure_ascii': False})
        ensure_project_tables(project)
        with using_project_tables(project):
            source = DataSourceFile.objects.filter(
                project=project,
                source_type='plan',
                source_key=f'{plan_key}:{plan_folder}:{file_name}',
            ).first()
        if source is None:
            if plan_key == 'anti-corrosion' and file_name == '防腐材料单.xlsx':
                derived_payload = derived_plan_file_payload(project, plan_key, plan_folder, file_name, sheet_name)
                if derived_payload is not None:
                    return JsonResponse(derived_payload, json_dumps_params={'ensure_ascii': False})
            raise ValueError(f'计划文件尚未同步到数据库：{plan_folder}/{file_name}')
        selected_sheet, sheets, total, columns, rows = table_payload(source, sheet_models, sheet_name)
        if plan_key == 'cutting':
            if file_name == '下料排产单.xlsx':
                recovered = cutting_primary_plan_payload_from_master(project, plan_folder, sheet_name)
                if recovered is not None:
                    stored_sheets = set(sheets)
                    sheets = list(dict.fromkeys([*recovered['sheets'], *sheets]))
                    target_sheet = sheet_name if sheet_name in sheets else sheets[0]
                    if target_sheet not in stored_sheets:
                        selected_sheet = recovered['sheet']
                        total = recovered['total']
                        columns = recovered['columns']
                        rows = recovered['rows']
            columns, rows = strip_cutting_plan_columns(columns, rows, project)
        if plan_key == 'welding' and file_name == '管段焊口表.xlsx':
            columns, rows = strip_welding_plan_columns(project, columns, rows)
        if plan_key == 'anti-corrosion' and file_name == '防腐焊口单.xlsx' and total == 0:
            derived_payload = derived_plan_file_payload(project, plan_key, plan_folder, file_name, sheet_name)
            if derived_payload is not None and derived_payload.get('total', 0) > 0:
                return JsonResponse(derived_payload, json_dumps_params={'ensure_ascii': False})
    except Exception as error:
        return HttpResponseBadRequest(
            json.dumps({'error': f'读取计划数据库失败：{error}'}, ensure_ascii=False),
            content_type='application/json',
        )

    return JsonResponse({
        'path': source.relative_path,
        'name': source.display_name or file_name,
        'sheet': selected_sheet,
        'sheets': sheets,
        'total': total,
        'columns': columns,
        'rows': rows,
    }, json_dumps_params={'ensure_ascii': False})


@csrf_exempt
@require_POST
def save_plan_file_rows(request, plan_key):
    project, data_root, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)
    plan_file, error = _resolve_plan_file(
        plan_key,
        request.GET.get('planFolder') or request.GET.get('folder') or request.GET.get('date') or '',
        request.GET.get('file') or '',
        _plan_sources(data_root),
    )
    if error:
        return HttpResponseBadRequest(json.dumps({'error': error}, ensure_ascii=False), content_type='application/json')

    payload, error = _parse_library_save_payload(request)
    if error:
        return HttpResponseBadRequest(json.dumps({'error': error}, ensure_ascii=False), content_type='application/json')

    try:
        file_name = plan_file['file_name']
        sheet_models = _plan_file_models(file_name)
        if sheet_models is None:
            raise ValueError(f'{file_name} 由管段焊口表自动生成，请修改管段焊口表')
        sheet_name = payload.get('sheet') or 'Sheet1'
        source = replace_source_sheet_rows(
            project,
            'plan',
            plan_file['source_key'],
            file_name,
            f'database://plan/{plan_key}/{plan_file["plan_folder"]}/{file_name}',
            sheet_name,
            {'columns': payload['columns'], 'rows': payload['rows']},
            sheet_models,
        )
        selected_sheet, _, total, _, _ = table_payload(source, sheet_models, sheet_name)
        synced_count = 0
        if plan_key == 'anti-corrosion' and file_name == '防腐材料单.xlsx':
            reconcile_anti_corrosion_material_order_plan(
                project,
                plan_file['plan_folder'],
                payload['rows'],
            )
        if plan_key == 'welding' and file_name.startswith(WELDING_PRIMARY_PLAN_FILE_NAME.removesuffix('.xlsx')):
            synced_count = _sync_completed_plan_rows_to_weld_library(project, payload['rows'])
            _update_project_weld_metrics(
                project,
                None,
                update_segment_count=False,
                update_prefab_weld_count=False,
                update_completion_rate=True,
            )
        if plan_key == 'anti-corrosion' and file_name == '防腐焊口单.xlsx':
            synced_count = _sync_anti_corrosion_completed_rows_to_weld_library(project, payload['rows'])
        if plan_key in {'anti-corrosion', 'cutting', 'welding'}:
            sync_project_plan_completion(project, plan_key, business_date=plan_file['plan_folder'])
        with using_project_tables(project):
            record = PlanRecord.objects.filter(project=project, plan_key=plan_key, plan_folder=plan_file['plan_folder']).first()
            if record:
                record.folder_updated_at = datetime.now().timestamp()
                record.save(update_fields=['folder_updated_at', 'updated_at'])
    except Exception as error:
        return HttpResponseBadRequest(
            json.dumps({'error': f'写入计划数据库失败：{error}'}, ensure_ascii=False),
            content_type='application/json',
        )

    return JsonResponse({
        'path': source.relative_path,
        'name': source.display_name or file_name,
        'sheet': selected_sheet,
        'total': total,
        'backupPath': '',
        'syncedWeldCount': synced_count,
    }, json_dumps_params={'ensure_ascii': False})


@csrf_exempt
@require_POST
def import_plan_patch_rows(request, plan_key):
    upload_file = request.FILES.get('file')
    if not upload_file:
        return HttpResponseBadRequest(json.dumps({'error': '未上传文件'}, ensure_ascii=False), content_type='application/json')
    if not upload_file.name.lower().endswith(('.xlsx', '.xlsm')):
        return HttpResponseBadRequest(json.dumps({'error': '仅支持 xlsx/xlsm 文件'}, ensure_ascii=False), content_type='application/json')

    sheet_name = request.POST.get('sheet') or None
    try:
        excel_file = pd.ExcelFile(upload_file)
        selected_sheet = sheet_name if sheet_name in excel_file.sheet_names else excel_file.sheet_names[0]
        dataframe = pd.read_excel(excel_file, sheet_name=selected_sheet)
        dataframe = dataframe.where(pd.notnull(dataframe), '')
    except Exception as error:
        return HttpResponseBadRequest(
            json.dumps({'error': f'读取导入文件失败：{error}'}, ensure_ascii=False),
            content_type='application/json',
        )

    return JsonResponse({
        'sheet': selected_sheet,
        'sheets': excel_file.sheet_names,
        'columns': [str(column) for column in dataframe.columns],
        'rows': dataframe.to_dict(orient='records'),
    }, json_dumps_params={'ensure_ascii': False})


@csrf_exempt
@require_POST
def export_plan_patch_rows(request, plan_key):
    payload, error = _parse_library_save_payload(request)
    if error:
        return HttpResponseBadRequest(json.dumps({'error': error}, ensure_ascii=False), content_type='application/json')

    output = BytesIO()
    sheet_name = payload.get('sheet') or 'Sheet1'
    safe_sheet_name = str(sheet_name)[:31] or 'Sheet1'
    dataframe = pd.DataFrame(payload['rows'], columns=payload['columns'])
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        dataframe.to_excel(writer, sheet_name=safe_sheet_name, index=False)
    output.seek(0)
    filename = quote(f'{safe_sheet_name}.xlsx')
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f"attachment; filename*=UTF-8''{filename}"
    return response
