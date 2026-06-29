from .common import *
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.db import close_old_connections
from django.utils import timezone

from ..models import ParserJob, ParserSubtask
from pipecloud.services.db_storage import (
    INITIALIZATION_MODELS,
    initialization_preview_payload,
    latest_source,
    read_workbook_rows,
    replace_source_rows,
    replace_source_with_workbook,
    standardize_workbook_payload,
    table_payload,
    workbook_preview_payload,
)


PARSER_JOB_EXECUTOR = ThreadPoolExecutor(max_workers=int(os.environ.get('PIPECLOUD_PARSER_JOB_WORKERS', '2')))
PARSER_CHUNK_SIZE = int(os.environ.get('PIPECLOUD_IDF_PARSER_CHUNK_SIZE', '50'))
PARSER_MAX_SUBTASK_WORKERS = int(os.environ.get('PIPECLOUD_IDF_PARSER_SUBTASK_WORKERS', '4'))
PARSER_CACHE_VERSION = {
    'idf': 'idf-viewer-parser-v1',
    'pcf': 'pcf-parser-v1',
}


def _parser_job_snapshot(job):
    return {
        'jobId': job.job_id,
        'projectId': job.project_id,
        'projectName': job.project.project_name if hasattr(job, 'project') else '',
        'source': 'parse',
        'fileType': job.file_type,
        'status': job.status,
        'total': job.total,
        'completed': job.completed,
        'failed': job.failed,
        'percent': job.percent,
        'current': job.current,
        'results': list(job.results or []),
        'errors': list(job.errors or []),
        'message': job.message,
        'batchPath': job.batch_path,
        'createdAt': job.created_at.isoformat(timespec='seconds') if job.created_at else '',
        'updatedAt': job.updated_at.isoformat(timespec='seconds') if job.updated_at else '',
    }


def _update_parser_job(job_id, **updates):
    try:
        job = ParserJob.objects.select_related('project').get(job_id=job_id)
    except ParserJob.DoesNotExist:
        return None
    for field, value in updates.items():
        if hasattr(job, field):
            setattr(job, field, value)
    total = int(job.total or 0)
    done = int(job.completed or 0) + int(job.failed or 0)
    job.percent = int(done / total * 100) if total else 0
    if updates.get('percent') is not None:
        job.percent = int(updates['percent'])
    job.save()
    return _parser_job_snapshot(job)


def _refresh_parser_job_counts(job):
    subtasks = list(job.subtasks.all())
    completed = sum(1 for item in subtasks if item.status == 'completed')
    failed = sum(1 for item in subtasks if item.status == 'failed')
    total = len(subtasks) or job.total
    results = [
        item.result_payload
        for item in subtasks
        if item.status == 'completed' and item.result_payload
    ]
    errors = [
        {
            'subtask': item.index,
            'files': (item.input_files or [])[:10],
            'fileCount': item.file_count,
            'error': item.error,
        }
        for item in subtasks
        if item.status == 'failed'
    ]
    job.total = total
    job.completed = completed
    job.failed = failed
    job.results = results
    job.errors = errors
    done = completed + failed
    job.percent = int(done / total * 100) if total else 0
    job.save()
    return job


def _refresh_result_previews(job):
    changed = False
    refreshed_results = []
    for result in job.results or []:
        next_result = dict(result)
        staged_path = next_result.get('stagedPath')
        try:
            target_path = _resolve_parser_file(staged_path)
            preview = workbook_preview_payload(target_path)
            next_result['preview'] = preview
            next_result['normalization'] = preview.get('normalization', {})
            next_result['totalRows'] = preview.get('total', 0)
            changed = True
        except Exception:
            pass
        refreshed_results.append(next_result)
    if changed:
        job.results = refreshed_results
        job.save(update_fields=['results', 'updated_at'])
    return job


def _create_parser_job(project, file_type, total, batch_dir, input_hash, input_files):
    return ParserJob.objects.create(
        job_id=uuid.uuid4().hex,
        project=project,
        file_type=file_type,
        status='queued',
        total=total,
        completed=0,
        failed=0,
        percent=0,
        message='解析任务已提交，后端正在处理。',
        batch_path=_parser_relative_path(batch_dir),
        input_hash=input_hash,
        input_files=input_files,
        results=[],
        errors=[],
    )


def _input_manifest_hash(source_files, file_type):
    manifest = {
        'parser': PARSER_CACHE_VERSION.get(file_type, file_type),
        'files': [
            {
                'name': item['name'],
                'size': item['size'],
                'sha256': item['sha256'],
            }
            for item in sorted(source_files, key=lambda value: (value['name'], value['sha256']))
        ],
    }
    encoded = json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _completed_parser_job(project, file_type, input_hash):
    return (
        ParserJob.objects
        .filter(project=project, file_type=file_type, input_hash=input_hash, status='completed')
        .order_by('-updated_at')
        .first()
    )


def _safe_upload_session(value):
    text = str(value or '').strip()
    if not re.fullmatch(r'[0-9A-Za-z_-]{8,80}', text):
        return ''
    return text


def _chunked(items, chunk_size):
    size = max(int(chunk_size or 1), 1)
    return [items[index:index + size] for index in range(0, len(items), size)]


def _unique_upload_path(folder, file_name):
    target_path = folder / file_name
    if not target_path.exists():
        return target_path
    stem = Path(file_name).stem or 'file'
    suffix = Path(file_name).suffix
    counter = 2
    while True:
        candidate = folder / f'{stem}-{counter}{suffix}'
        if not candidate.exists():
            return candidate
        counter += 1


def _run_parser_subtask(project, file_type, script, run_dir, output_name, source_names):
    env = os.environ.copy()
    env['PIPECLOUD_PARSER_INPUT_DIR'] = str(run_dir)
    env['PIPECLOUD_PARSER_OUTPUT_DIR'] = str(run_dir)
    completed = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(SPOOL_ANALYSIS_ROOT),
        env=env,
        capture_output=True,
        text=False,
        timeout=900,
    )

    output_path = run_dir / PARSER_OUTPUT_FILES[file_type]
    stdout = _decode_process_output(completed.stdout)
    stderr = _decode_process_output(completed.stderr)
    if completed.returncode != 0 or not output_path.exists():
        raise RuntimeError(json.dumps({
            'error': f'子任务解析失败：{output_name}',
            'returnCode': completed.returncode,
            'stdout': stdout,
            'stderr': stderr,
        }, ensure_ascii=False))

    result_path = run_dir / output_name
    if result_path != output_path:
        output_path.replace(result_path)

    return _parser_result_payload(
        project,
        'parse',
        result_path,
        '解析完成，请核对预览内容后确认导入。',
        fileType=file_type,
        sourceName=output_name,
        uploaded=source_names,
        stdout=stdout,
        stderr=stderr,
    )


def _run_parser_job(job_id, project_id, file_type, source_files):
    close_old_connections()
    try:
        project = Project.objects.get(pk=project_id)
    except Project.DoesNotExist:
        _update_parser_job(job_id, status='failed', message='项目不存在')
        return

    script = PARSER_SCRIPTS[file_type]
    _update_parser_job(job_id, status='running', message='后端正在解析文件。')

    chunks = _chunked(source_files, PARSER_CHUNK_SIZE if file_type == 'idf' else 1)
    _update_parser_job(job_id, total=len(chunks))
    try:
        job = ParserJob.objects.get(job_id=job_id)
    except ParserJob.DoesNotExist:
        return
    for index, chunk in enumerate(chunks, start=1):
        ParserSubtask.objects.update_or_create(
            job=job,
            index=index,
            defaults={
                'status': 'queued',
                'input_files': [item['name'] for item in chunk],
                'file_count': len(chunk),
            },
        )
    max_workers = min(max(PARSER_MAX_SUBTASK_WORKERS, 1), len(chunks) or 1)

    def submit_chunk(chunk_index, chunk):
        close_old_connections()
        subtask = ParserSubtask.objects.get(job__job_id=job_id, index=chunk_index)
        subtask.status = 'running'
        subtask.started_at = timezone.now()
        run_dir = Path(chunk[0]['path']).parent.parent / f'subtask-{chunk_index:03d}'
        run_dir.mkdir(parents=True, exist_ok=True)
        subtask.work_path = _parser_relative_path(run_dir)
        subtask.save()
        source_names = []
        for item in chunk:
            source_path = Path(item['path'])
            target_path = _unique_upload_path(run_dir, source_path.name)
            shutil.copy2(source_path, target_path)
            source_names.append(item['name'])
        if file_type == 'idf':
            output_name = f'IDF解析结果-{chunk_index:03d}.xlsx'
        else:
            output_name = f'{Path(source_names[0]).stem}-{PARSER_OUTPUT_FILES[file_type]}'
        try:
            result = _run_parser_subtask(project, file_type, script, run_dir, output_name, source_names)
            subtask.status = 'completed'
            subtask.result_path = result.get('stagedPath', '')
            subtask.result_payload = result
            subtask.error = ''
            return result
        except Exception as error:
            subtask.status = 'failed'
            error_text = str(error)
            try:
                parsed = json.loads(error_text)
                error_text = parsed.get('error') or error_text
            except (TypeError, json.JSONDecodeError):
                pass
            subtask.error = error_text
            raise
        finally:
            subtask.finished_at = timezone.now()
            subtask.save()
            close_old_connections()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(submit_chunk, index, chunk): {
                'index': index,
                'names': [item['name'] for item in chunk],
            }
            for index, chunk in enumerate(chunks, start=1)
        }
        for future in as_completed(futures):
            meta = futures[future]
            names = meta['names']
            current = f'子任务 {meta["index"]}/{len(chunks)}：{len(names)} 个文件'
            _update_parser_job(job_id, current=current)
            try:
                future.result()
            except Exception as error:
                pass
            job = _refresh_parser_job_counts(ParserJob.objects.get(job_id=job_id))

    job = _refresh_parser_job_counts(ParserJob.objects.get(job_id=job_id))
    if job.results:
        status = 'completed'
        message = '解析完成，请逐个核对预览内容后确认导入。'
        if job.failed:
            message = f'解析完成，其中 {job.failed} 个子任务失败，请查看失败明细。'
    else:
        status = 'failed'
        message = '解析任务失败，未生成可导入结果。'
    _update_parser_job(job_id, status=status, percent=100, current='', message=message)
    close_old_connections()


def _parser_result_payload(project, source, target_path, message, preview_mode='raw', **extra):
    preview = workbook_preview_payload(target_path) if preview_mode == 'raw' else initialization_preview_payload(target_path)
    return {
        'projectId': project.id,
        'projectName': project.project_name,
        'source': source,
        'filename': target_path.name,
        'stagedPath': _parser_relative_path(target_path),
        'downloadUrl': _parser_download_url(target_path),
        'totalRows': preview.get('total', 0),
        'preview': preview,
        'normalization': preview.get('normalization', {}),
        'message': message,
        'confirmed': False,
        **extra,
    }


def _parser_list_response(project, source, results, message, **extra):
    payload = {
        'projectId': project.id,
        'projectName': project.project_name,
        'source': source,
        'results': results,
        'message': message,
        **extra,
    }
    if len(results) == 1:
        payload.update(results[0])
        payload['results'] = results
    return JsonResponse(payload, json_dumps_params={'ensure_ascii': False})


def _merge_parser_excel_files(source_paths, output_path):
    merged_dataframe = None
    for source_path in source_paths:
        dataframe = pd.read_excel(source_path)
        if merged_dataframe is None:
            merged_dataframe = dataframe
            continue

        target_columns = list(merged_dataframe.columns)
        aligned = pd.DataFrame(columns=target_columns)
        for column in target_columns:
            aligned[column] = dataframe[column] if column in dataframe.columns else ''
        merged_dataframe = pd.concat([merged_dataframe, aligned], ignore_index=True)

    if merged_dataframe is None:
        raise ValueError('没有可合并的文件')
    merged_dataframe.to_excel(output_path, index=False)
    return output_path


@csrf_exempt
@require_POST
def merge_parser_results(request):
    project, data_root, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
        staged_paths = payload.get('stagedPaths') or []
        if not isinstance(staged_paths, list) or len(staged_paths) < 2:
            raise ValueError
        source_paths = [_resolve_parser_file(path) for path in staged_paths]
    except FileNotFoundError as error:
        return HttpResponseBadRequest(json.dumps({'error': str(error)}, ensure_ascii=False), content_type='application/json')
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return HttpResponseBadRequest(json.dumps({'error': '合并参数无效，请至少选择两个待确认结果'}, ensure_ascii=False), content_type='application/json')

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    run_dir = FILE_PARSER_ROOT / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)
    output_path = run_dir / '合并解析结果.xlsx'

    try:
        _merge_parser_excel_files(source_paths, output_path)
    except Exception as error:
        return HttpResponseBadRequest(json.dumps({'error': f'合并结果失败：{error}'}, ensure_ascii=False), content_type='application/json')

    result = _parser_result_payload(
        project,
        'merge',
        output_path,
        '结果已合并，请核对预览内容后确认导入。',
        sourceName='合并结果',
        mergedFrom=[path.name for path in source_paths],
        mergedFromPaths=[_parser_relative_path(path) for path in source_paths],
    )
    return JsonResponse(result, json_dumps_params={'ensure_ascii': False})


@csrf_exempt
@require_POST
def parse_uploaded_files(request):
    project, data_root, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)

    upload_files = request.FILES.getlist('files')
    if not upload_files:
        return HttpResponseBadRequest(json.dumps({'error': '请先选择要解析的文件'}, ensure_ascii=False), content_type='application/json')

    upload_names = [_safe_upload_name(upload_file.name) for upload_file in upload_files]
    file_types = {_parser_file_type(file_name) for file_name in upload_names}
    if '' in file_types:
        return HttpResponseBadRequest(json.dumps({'error': '仅支持上传 .idf 或 .pcf 文件'}, ensure_ascii=False), content_type='application/json')
    if len(file_types) != 1:
        return HttpResponseBadRequest(json.dumps({'error': '请一次上传同一种格式的文件'}, ensure_ascii=False), content_type='application/json')

    file_type = next(iter(file_types))
    script = PARSER_SCRIPTS[file_type]
    if not script.exists():
        return HttpResponseBadRequest(json.dumps({'error': f'解析脚本不存在：{_relative_path(script)}'}, ensure_ascii=False), content_type='application/json')

    upload_session = _safe_upload_session(request.GET.get('upload_session') or request.POST.get('upload_session'))
    try:
        chunk_index = int(request.GET.get('chunk_index') or request.POST.get('chunk_index') or 1)
        chunk_total = int(request.GET.get('chunk_total') or request.POST.get('chunk_total') or 1)
    except (TypeError, ValueError):
        return HttpResponseBadRequest(json.dumps({'error': '上传分片参数无效'}, ensure_ascii=False), content_type='application/json')
    chunk_index = max(chunk_index, 1)
    chunk_total = max(chunk_total, 1)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    batch_dir = FILE_PARSER_ROOT / 'upload_sessions' / upload_session if upload_session else FILE_PARSER_ROOT / timestamp
    batch_dir.mkdir(parents=True, exist_ok=True)
    upload_dir = batch_dir / 'uploads'
    upload_dir.mkdir(parents=True, exist_ok=True)

    for index, upload_file in enumerate(upload_files, start=1):
        safe_name = upload_names[index - 1]
        target_path = _unique_upload_path(upload_dir, safe_name)

        try:
            with target_path.open('wb') as target_file:
                for chunk in upload_file.chunks():
                    target_file.write(chunk)
        except Exception as error:
            return HttpResponseBadRequest(json.dumps({'error': f'保存解析文件失败：{safe_name}：{error}'}, ensure_ascii=False), content_type='application/json')

    if upload_session and chunk_index < chunk_total:
        return JsonResponse({
            'uploadSession': upload_session,
            'status': 'uploading',
            'uploadedChunks': chunk_index,
            'totalChunks': chunk_total,
            'message': f'正在上传解析文件：{chunk_index}/{chunk_total}',
        }, json_dumps_params={'ensure_ascii': False})

    source_files = []
    for path in sorted(upload_dir.iterdir()):
        if not path.is_file():
            continue
        file_hash = hashlib.sha256()
        file_size = 0
        with path.open('rb') as source_file:
            for chunk in iter(lambda: source_file.read(1024 * 1024), b''):
                file_hash.update(chunk)
                file_size += len(chunk)
        source_files.append({
            'name': path.name,
            'path': str(path),
            'size': file_size,
            'sha256': file_hash.hexdigest(),
        })

    input_hash = _input_manifest_hash(source_files, file_type)
    existing_job = ParserJob.objects.filter(project=project, file_type=file_type, input_hash=input_hash).order_by('-updated_at').first()
    if existing_job:
        if existing_job.status == 'completed':
            existing_job = _refresh_result_previews(existing_job)
            payload = _parser_job_snapshot(existing_job)
            payload['reused'] = True
            payload['message'] = '已命中相同文件的历史解析结果，无需重复解析。'
            return JsonResponse(payload, json_dumps_params={'ensure_ascii': False})
        if existing_job.status in {'queued', 'running'}:
            return JsonResponse(_parser_job_snapshot(existing_job), json_dumps_params={'ensure_ascii': False})

    initial_total = len(_chunked(source_files, PARSER_CHUNK_SIZE if file_type == 'idf' else 1))
    if existing_job and existing_job.status == 'failed':
        existing_job.subtasks.all().delete()
        existing_job.status = 'queued'
        existing_job.total = initial_total
        existing_job.completed = 0
        existing_job.failed = 0
        existing_job.percent = 0
        existing_job.current = ''
        existing_job.message = '解析任务已重新提交，后端正在处理。'
        existing_job.batch_path = _parser_relative_path(batch_dir)
        existing_job.input_files = source_files
        existing_job.results = []
        existing_job.errors = []
        existing_job.save()
        job = existing_job
    else:
        job = _create_parser_job(project, file_type, initial_total, batch_dir, input_hash, source_files)

    PARSER_JOB_EXECUTOR.submit(_run_parser_job, job.job_id, project.id, file_type, source_files)
    return JsonResponse({
        'jobId': job.job_id,
        'status': job.status,
        'fileType': file_type,
        'total': initial_total,
        'completed': 0,
        'failed': 0,
        'percent': 0,
        'message': job.message,
    }, json_dumps_params={'ensure_ascii': False})


@require_GET
def parser_job_status(request, job_id):
    try:
        job = ParserJob.objects.select_related('project').get(job_id=job_id)
    except ParserJob.DoesNotExist:
        return HttpResponseBadRequest(json.dumps({'error': '解析任务不存在'}, ensure_ascii=False), content_type='application/json')
    if job.status in {'completed', 'failed'}:
        job = _refresh_result_previews(job)
    payload = _parser_job_snapshot(job)
    if payload.get('status') in {'completed', 'failed'}:
        payload['results'] = sorted(payload.get('results') or [], key=lambda item: item.get('sourceName') or item.get('filename') or '')
    return JsonResponse(payload, json_dumps_params={'ensure_ascii': False})


@csrf_exempt
@require_POST
def stage_initialization_upload(request):
    project, data_root, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)

    upload_files = request.FILES.getlist('files') or request.FILES.getlist('file')
    if not upload_files:
        return HttpResponseBadRequest(json.dumps({'error': '未选择焊口初始化数据文件'}, ensure_ascii=False), content_type='application/json')

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    run_dir = FILE_PARSER_ROOT / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for upload_file in upload_files:
        file_name = _safe_upload_name(upload_file.name)
        suffix = Path(file_name).suffix.lower()
        if file_name.startswith('~$') or suffix not in {'.xlsx', '.xlsm'}:
            return HttpResponseBadRequest(json.dumps({'error': f'仅支持上传 .xlsx 或 .xlsm 焊口初始化数据：{file_name}'}, ensure_ascii=False), content_type='application/json')

        target_path = run_dir / file_name
        try:
            with target_path.open('wb') as target_file:
                for chunk in upload_file.chunks():
                    target_file.write(chunk)
            initialization_preview_payload(target_path)
        except Exception as error:
            return HttpResponseBadRequest(json.dumps({'error': f'读取焊口初始化数据失败：{file_name}：{error}'}, ensure_ascii=False), content_type='application/json')

        results.append(_parser_result_payload(
            project,
            'upload',
            target_path,
            '文件已上传，请核对预览内容后确认导入。',
            preview_mode='initialization',
            sourceName=file_name,
        ))

    return _parser_list_response(
        project,
        'upload',
        results,
        '文件已上传，请逐个核对预览内容后确认导入。',
    )


@csrf_exempt
@require_POST
def confirm_initialization_file(request):
    project, data_root, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
        staged_path = _resolve_parser_file(payload.get('stagedPath') or payload.get('path'))
    except FileNotFoundError as error:
        return HttpResponseBadRequest(json.dumps({'error': str(error)}, ensure_ascii=False), content_type='application/json')
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return HttpResponseBadRequest(json.dumps({'error': '确认导入参数无效'}, ensure_ascii=False), content_type='application/json')

    import_mode = payload.get('importMode') or payload.get('mode') or 'replace'
    if import_mode not in {'replace', 'append'}:
        return HttpResponseBadRequest(json.dumps({'error': '导入模式无效'}, ensure_ascii=False), content_type='application/json')

    try:
        display_name = _safe_upload_name(payload.get('filename') or staged_path.name)
        if not display_name.startswith('焊口初始化数据'):
            display_name = f'焊口初始化数据-{display_name}'
        if import_mode == 'append':
            source = _append_initialization_source(project, staged_path, display_name)
        else:
            source = replace_source_with_workbook(
                project,
                'initialization',
                'welds',
                display_name,
                f'database://initialization/{project.id}/{display_name}',
                staged_path,
                INITIALIZATION_MODELS,
            )
        selected_sheet, sheets, total, columns, rows = table_payload(source, INITIALIZATION_MODELS, None)
        preview = {
            'sheet': selected_sheet,
            'sheets': sheets,
            'total': total,
            'columns': columns,
            'rows': rows[:20],
            'previewLimit': 20,
        }
    except Exception as error:
        return HttpResponseBadRequest(json.dumps({'error': str(error)}, ensure_ascii=False), content_type='application/json')

    message = '已新增导入，数据行已追加到当前项目初始化数据库。' if import_mode == 'append' else '已覆盖导入，当前项目初始化数据库已更新。'
    return JsonResponse({
        'projectId': project.id,
        'projectName': project.project_name,
        'importMode': import_mode,
        'file': _data_source_payload(source, display_name),
        'backupPaths': [],
        'preview': preview,
        'normalization': preview.get('normalization', {}),
        'message': message,
    }, json_dumps_params={'ensure_ascii': False})


@require_GET
def parser_file_preview(request):
    try:
        target_path = _resolve_parser_file(request.GET.get('path') or request.GET.get('stagedPath') or '')
    except (ValueError, RuntimeError, FileNotFoundError):
        return HttpResponseBadRequest(json.dumps({'error': '预览路径无效'}, ensure_ascii=False), content_type='application/json')

    sheet_name = request.GET.get('sheet') or None
    preview_mode = request.GET.get('previewMode') or request.GET.get('source') or 'raw'
    try:
        preview = (
            initialization_preview_payload(target_path, sheet_name)
            if preview_mode in {'upload', 'initialization'}
            else workbook_preview_payload(target_path, sheet_name)
        )
    except Exception as error:
        return HttpResponseBadRequest(json.dumps({'error': f'读取工作表预览失败：{error}'}, ensure_ascii=False), content_type='application/json')

    return JsonResponse({
        'stagedPath': _parser_relative_path(target_path),
        'filename': target_path.name,
        'preview': preview,
        'normalization': preview.get('normalization', {}),
        'totalRows': preview.get('total', 0),
    }, json_dumps_params={'ensure_ascii': False})


def _append_initialization_source(project, staged_path, display_name):
    workbook_payload = read_workbook_rows(staged_path)
    normalized_payload, validation = standardize_workbook_payload(
        workbook_payload,
        INITIALIZATION_MODELS,
        {'unit', 'pipeline', 'segment_no', 'weld_no_start', 'weld_no_final', 'diameter', 'wall_thickness', 'material', 'joint_type'},
    )
    if not validation.get('canImport'):
        raise ValueError('初始化数据标准化校验未通过，存在缺失的关键字段或必填值')

    source = latest_source(project, 'initialization', 'welds')
    if source is None:
        return replace_source_rows(
            project,
            'initialization',
            'welds',
            display_name,
            f'database://initialization/{project.id}/{display_name}',
            normalized_payload,
            INITIALIZATION_MODELS,
        )

    selected_sheet, _, _, columns, existing_rows = table_payload(source, INITIALIZATION_MODELS, None)
    incoming_sheet = next(iter(normalized_payload.keys()), 'Sheet1')
    incoming_rows = normalized_payload.get(incoming_sheet, {}).get('rows') or []
    next_columns = columns or normalized_payload.get(incoming_sheet, {}).get('columns') or []
    next_rows = [*existing_rows, *incoming_rows]
    return replace_source_rows(
        project,
        'initialization',
        'welds',
        source.display_name or display_name,
        source.relative_path or f'database://initialization/{project.id}/{display_name}',
        {selected_sheet or incoming_sheet or 'Sheet1': {'columns': next_columns, 'rows': next_rows}},
        INITIALIZATION_MODELS,
    )


@require_GET
def download_parsed_file(request):
    relative_path = request.GET.get('path') or ''
    try:
        target_path = _resolve_parser_file(relative_path)
    except (ValueError, RuntimeError, FileNotFoundError):
        return HttpResponseBadRequest(json.dumps({'error': '下载路径无效'}, ensure_ascii=False), content_type='application/json')

    with target_path.open('rb') as file_obj:
        content = file_obj.read()
    response = HttpResponse(content, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="{quote(target_path.name)}"'
    return response
