from .common import *
import hashlib
import signal
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.core.exceptions import ObjectDoesNotExist
from django.db import close_old_connections
from django.utils import timezone

from ..models import IdfModelPart, ParserArtifact, ParserJob, ParserSubtask
from pipecloud.services.idf_model_storage import (
    fail_idf_model,
    finalize_idf_model,
    idf_model_part_payload,
    initialize_idf_model,
)
from pipecloud.services.db_storage import (
    INITIALIZATION_MATERIAL_MODELS,
    INITIALIZATION_MATERIAL_SHEET,
    INITIALIZATION_MODELS,
    initialization_preview_payload,
    latest_source,
    normalize_initialization_payload,
    read_workbook_rows,
    replace_source_rows,
    replace_source_with_workbook,
    standardize_workbook_payload,
    table_payload,
    table_preview_payload,
    workbook_preview_payload,
)


PARSER_JOB_EXECUTOR = ThreadPoolExecutor(max_workers=int(os.environ.get('PIPECLOUD_PARSER_JOB_WORKERS', '2')))
PARSER_CHUNK_SIZE = int(os.environ.get('PIPECLOUD_IDF_PARSER_CHUNK_SIZE', '50'))
PARSER_MAX_SUBTASK_WORKERS = int(os.environ.get('PIPECLOUD_IDF_PARSER_SUBTASK_WORKERS', '4'))
PARSER_CACHE_VERSION = {
    'idf': 'idf-viewer-parser-db-v2',
    'pcf': 'pcf-parser-v1',
}
INITIALIZATION_UPLOAD_MARKER = '.initialization-upload'
PARSER_JOB_PROCESSES = {}
PARSER_JOB_PROCESSES_LOCK = threading.Lock()


class ParserJobCanceled(RuntimeError):
    pass


def _parser_job_is_canceled(job_id):
    return ParserJob.objects.filter(job_id=job_id, status='canceled').exists()


def _register_parser_process(job_id, process):
    with PARSER_JOB_PROCESSES_LOCK:
        PARSER_JOB_PROCESSES.setdefault(job_id, set()).add(process)


def _unregister_parser_process(job_id, process):
    with PARSER_JOB_PROCESSES_LOCK:
        processes = PARSER_JOB_PROCESSES.get(job_id)
        if not processes:
            return
        processes.discard(process)
        if not processes:
            PARSER_JOB_PROCESSES.pop(job_id, None)


def _terminate_parser_processes(job_id):
    with PARSER_JOB_PROCESSES_LOCK:
        processes = list(PARSER_JOB_PROCESSES.get(job_id, ()))
    for process in processes:
        try:
            process.terminate()
        except (OSError, ProcessLookupError):
            pass


def _parser_job_model_available(job):
    try:
        model = job.idf_model
    except ObjectDoesNotExist:
        return False
    expected_parts = int(job.completed or 0)
    return (
        model.status in {'importing', 'ready'}
        and expected_parts > 0
        and model.parts.count() >= expected_parts
    )


def _parser_job_snapshot(job):
    try:
        model_saved = job.idf_model.status == 'ready'
    except ObjectDoesNotExist:
        model_saved = False
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
        'canceled': job.subtasks.filter(status='canceled').count(),
        'percent': job.percent,
        'current': job.current,
        'results': list(job.results or []),
        'errors': list(job.errors or []),
        'message': job.message,
        'batchPath': job.batch_path,
        'createdAt': job.created_at.isoformat(timespec='seconds') if job.created_at else '',
        'updatedAt': job.updated_at.isoformat(timespec='seconds') if job.updated_at else '',
        'modelSaved': model_saved,
        'modelAvailable': _parser_job_model_available(job) if job.file_type == 'idf' else False,
    }


def _update_parser_job(job_id, **updates):
    try:
        job = ParserJob.objects.select_related('project').get(job_id=job_id)
    except ParserJob.DoesNotExist:
        return None
    if job.status == 'canceled' and updates.get('status') != 'canceled':
        return _parser_job_snapshot(job)
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
    canceled = sum(1 for item in subtasks if item.status == 'canceled')
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
    done = completed + failed + canceled
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
            artifact = _result_artifact(next_result)
            if artifact is None:
                target_path = _resolve_parser_file(staged_path)
                artifact = _store_parser_artifact(
                    job.project,
                    next_result.get('source') or 'parse',
                    target_path,
                    job,
                )
                next_result['artifactId'] = artifact.id
            preview = workbook_preview_payload(BytesIO(bytes(artifact.content)))
            next_result['preview'] = preview
            next_result['normalization'] = preview.get('normalization', {})
            next_result['totalRows'] = preview.get('total', 0)
            next_result['downloadUrl'] = _artifact_download_url(artifact)
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
    queryset = (
        ParserJob.objects
        .filter(project=project, file_type=file_type, input_hash=input_hash, status='completed')
        .order_by('-updated_at')
    )
    return queryset.first()


def _parser_job_result_files_available(job):
    results = list(job.results or [])
    if not results:
        return False
    try:
        for result in results:
            if _result_artifact(result) is None:
                _resolve_parser_file(result.get('stagedPath') or result.get('path') or '')
    except (TypeError, ValueError, RuntimeError, FileNotFoundError):
        return False
    return True


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


def _run_parser_subtask(
    job_id,
    project,
    file_type,
    script,
    run_dir,
    output_name,
    source_names,
    subtask_index=None,
    idf_model_id=None,
):
    env = os.environ.copy()
    env['PIPECLOUD_PARSER_INPUT_DIR'] = str(run_dir)
    env['PIPECLOUD_PARSER_OUTPUT_DIR'] = str(run_dir)
    if file_type == 'idf':
        if not idf_model_id or not subtask_index:
            raise RuntimeError('IDF 模型数据库写入参数不完整')
        env['PIPECLOUD_IDF_MODEL_ID'] = str(idf_model_id)
        env['PIPECLOUD_IDF_MODEL_PART_INDEX'] = str(subtask_index)
    if _parser_job_is_canceled(job_id):
        raise ParserJobCanceled('解析任务已被用户中断')
    process = subprocess.Popen(
        [sys.executable, str(script)],
        cwd=str(SPOOL_ANALYSIS_ROOT),
        env=env,
        capture_output=True,
        text=False,
    )
    if subtask_index:
        ParserSubtask.objects.filter(
            job__job_id=job_id,
            index=subtask_index,
        ).update(process_id=process.pid)
    _register_parser_process(job_id, process)
    if _parser_job_is_canceled(job_id):
        process.terminate()
    try:
        completed_stdout, completed_stderr = process.communicate(timeout=900)
    except subprocess.TimeoutExpired:
        process.kill()
        completed_stdout, completed_stderr = process.communicate()
        raise RuntimeError(f'子任务解析超时：{output_name}')
    finally:
        _unregister_parser_process(job_id, process)

    output_path = run_dir / PARSER_OUTPUT_FILES[file_type]
    stdout = _decode_process_output(completed_stdout)
    stderr = _decode_process_output(completed_stderr)
    if _parser_job_is_canceled(job_id):
        raise ParserJobCanceled('解析任务已被用户中断')
    if process.returncode != 0 or not output_path.exists():
        raise RuntimeError(json.dumps({
            'error': f'子任务解析失败：{output_name}',
            'returnCode': process.returncode,
            'stdout': stdout,
            'stderr': stderr,
        }, ensure_ascii=False))

    if file_type == 'idf':
        try:
            model_part = IdfModelPart.objects.get(
                model_id=idf_model_id,
                subtask_index=subtask_index,
            )
        except IdfModelPart.DoesNotExist as error:
            raise RuntimeError('IDF 解析完成但空间模型未写入数据库') from error
        model_extra = {
            'modelPartIndex': subtask_index,
            'modelSummary': {
                'componentCount': model_part.component_count,
                'weldCount': model_part.components.filter(component_type='weld').count(),
            },
        }
    else:
        model_extra = {}

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
        parser_job=ParserJob.objects.get(job_id=job_id),
        **model_extra,
    )


def _run_parser_job(job_id, project_id, file_type, source_files):
    close_old_connections()
    try:
        project = Project.objects.get(pk=project_id)
    except Project.DoesNotExist:
        _update_parser_job(job_id, status='failed', message='项目不存在')
        return
    if _parser_job_is_canceled(job_id):
        return

    script = PARSER_SCRIPTS[file_type]
    _update_parser_job(job_id, status='running', message='后端正在解析文件。')
    if _parser_job_is_canceled(job_id):
        return

    chunks = _chunked(source_files, PARSER_CHUNK_SIZE if file_type == 'idf' else 1)
    _update_parser_job(job_id, total=len(chunks))
    try:
        job = ParserJob.objects.get(job_id=job_id)
    except ParserJob.DoesNotExist:
        return
    idf_model_id = initialize_idf_model(job).id if file_type == 'idf' else None
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
        if _parser_job_is_canceled(job_id):
            subtask.status = 'canceled'
            subtask.finished_at = timezone.now()
            subtask.save(update_fields=['status', 'finished_at', 'updated_at'])
            return None
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
            result = _run_parser_subtask(
                job_id,
                project,
                file_type,
                script,
                run_dir,
                output_name,
                source_names,
                subtask_index=chunk_index,
                idf_model_id=idf_model_id,
            )
            subtask.status = 'completed'
            subtask.result_path = result.get('stagedPath', '')
            subtask.result_payload = result
            subtask.error = ''
            return result
        except ParserJobCanceled:
            subtask.status = 'canceled'
            subtask.error = ''
            return None
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
            subtask.process_id = None
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
    if job.status == 'canceled':
        if idf_model_id:
            fail_idf_model(idf_model_id)
        close_old_connections()
        return
    if job.results:
        status = 'completed'
        message = (
            'IDF 解析完成，请预览模型后决定是否保存；表格结果仅供下载。'
            if file_type == 'idf'
            else '解析完成，表格结果仅供下载。'
        )
        if job.failed:
            message = f'解析完成，其中 {job.failed} 个子任务失败，请查看失败明细。'
    else:
        status = 'failed'
        message = '解析任务失败，未生成可下载结果。'
        if idf_model_id:
            fail_idf_model(idf_model_id)
    _update_parser_job(job_id, status=status, percent=100, current='', message=message)
    close_old_connections()


def _artifact_download_url(artifact):
    return f'/api/pipecloud/file-parser/download/?artifactId={artifact.id}'


def _result_artifact(result):
    artifact_id = result.get('artifactId') if isinstance(result, dict) else None
    if not artifact_id:
        return None
    return ParserArtifact.objects.filter(pk=artifact_id).first()


def _store_parser_artifact(project, source, target_path, job=None):
    content = Path(target_path).read_bytes()
    return ParserArtifact.objects.create(
        project=project,
        job=job,
        source=source,
        filename=Path(target_path).name,
        content=content,
        file_size=len(content),
        content_hash=hashlib.sha256(content).hexdigest(),
    )


def _parser_result_payload(
    project,
    source,
    target_path,
    message,
    preview_mode='raw',
    parser_job=None,
    **extra,
):
    preview = (
        workbook_preview_payload(target_path)
        if preview_mode == 'raw'
        else initialization_preview_payload(target_path, project=project)
    )
    artifact = _store_parser_artifact(project, source, target_path, parser_job)
    return {
        'projectId': project.id,
        'projectName': project.project_name,
        'source': source,
        'filename': target_path.name,
        'stagedPath': _parser_relative_path(target_path),
        'artifactId': artifact.id,
        'downloadUrl': _artifact_download_url(artifact),
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
    merged_sheets = {}
    for source_path in source_paths:
        for sheet_name, dataframe in pd.read_excel(source_path, sheet_name=None).items():
            if sheet_name == '解析概况':
                continue
            existing = merged_sheets.get(sheet_name)
            if existing is None:
                merged_sheets[sheet_name] = dataframe
                continue
            columns = list(dict.fromkeys([*existing.columns, *dataframe.columns]))
            merged_sheets[sheet_name] = pd.concat(
                [existing.reindex(columns=columns), dataframe.reindex(columns=columns)],
                ignore_index=True,
            )

    if not merged_sheets:
        raise ValueError('没有可合并的文件')
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        for sheet_name, dataframe in merged_sheets.items():
            dataframe.to_excel(writer, sheet_name=str(sheet_name)[:31], index=False)
    return output_path


@csrf_exempt
@require_POST
def merge_parser_results(request):
    project, data_root, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)

    temporary_sources = None
    source_names = []
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
        sources = payload.get('sources') or []
        staged_paths = payload.get('stagedPaths') or []
        if sources:
            if not isinstance(sources, list) or len(sources) < 2:
                raise ValueError
            temporary_sources = tempfile.TemporaryDirectory()
            source_paths = []
            for index, item in enumerate(sources, start=1):
                artifact = _result_artifact(item)
                if artifact is not None:
                    source_path = Path(temporary_sources.name) / f'{index:04d}-{_safe_upload_name(artifact.filename)}'
                    source_path.write_bytes(bytes(artifact.content))
                    source_names.append(artifact.filename)
                else:
                    source_path = _resolve_parser_file(item.get('stagedPath') or '')
                    source_names.append(source_path.name)
                source_paths.append(source_path)
        elif isinstance(staged_paths, list) and len(staged_paths) >= 2:
            source_paths = [_resolve_parser_file(path) for path in staged_paths]
            source_names = [path.name for path in source_paths]
        else:
            raise ValueError
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
    finally:
        if temporary_sources is not None:
            temporary_sources.cleanup()

    result = _parser_result_payload(
        project,
        'merge',
        output_path,
        '结果已合并，请核对预览内容后确认导入。',
        sourceName='合并结果',
        mergedFrom=source_names,
        mergedFromPaths=staged_paths,
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
    if existing_job and existing_job.status == 'completed' and file_type == 'idf':
        has_preview_models = _parser_job_model_available(existing_job)
        if not has_preview_models:
            existing_job.status = 'failed'
            existing_job.message = '历史解析结果缺少数据库模型，正在重新解析。'
            existing_job.save(update_fields=['status', 'message', 'updated_at'])
    if existing_job and existing_job.status == 'completed' and not _parser_job_result_files_available(existing_job):
        existing_job.status = 'failed'
        existing_job.message = '历史解析结果文件已失效，正在重新解析。'
        existing_job.save(update_fields=['status', 'message', 'updated_at'])
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
    if existing_job and existing_job.status in {'failed', 'canceled'}:
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
def latest_parser_result(request):
    project, data_root, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)

    candidates = (
        ParserJob.objects
        .select_related('project')
        .filter(project=project, status='completed')
        .exclude(results=[])
        .order_by('-updated_at', '-id')
    )
    job = next((
        item
        for item in candidates
        if (
            _parser_job_result_files_available(item)
            and (item.file_type != 'idf' or _parser_job_model_available(item))
        )
    ), None)
    if not job:
        return JsonResponse(
            {'error': '当前项目暂无可恢复的解析结果'},
            status=404,
            json_dumps_params={'ensure_ascii': False},
        )

    job = _refresh_result_previews(job)
    payload = _parser_job_snapshot(job)
    payload['results'] = sorted(
        payload.get('results') or [],
        key=lambda item: item.get('sourceName') or item.get('filename') or '',
    )
    return JsonResponse(payload, json_dumps_params={'ensure_ascii': False})


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
def cancel_parser_job(request, job_id):
    try:
        job = ParserJob.objects.select_related('project').get(job_id=job_id)
    except ParserJob.DoesNotExist:
        return JsonResponse(
            {'error': '解析任务不存在'},
            status=404,
            json_dumps_params={'ensure_ascii': False},
        )
    if job.status not in {'queued', 'running'}:
        return JsonResponse(_parser_job_snapshot(job), json_dumps_params={'ensure_ascii': False})

    job.status = 'canceled'
    job.current = ''
    job.message = '解析任务已由用户中断。'
    job.save(update_fields=['status', 'current', 'message', 'updated_at'])
    job.subtasks.filter(status='queued').update(
        status='canceled',
        finished_at=timezone.now(),
    )
    _terminate_parser_processes(job_id)

    # 在多进程部署中，请求可能不在执行任务的进程内；按已记录的 PID 再终止一次。
    for process_id in job.subtasks.filter(status='running').values_list('process_id', flat=True):
        if not process_id:
            continue
        try:
            os.kill(process_id, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            pass

    job = _refresh_parser_job_counts(ParserJob.objects.get(pk=job.pk))
    return JsonResponse(_parser_job_snapshot(job), json_dumps_params={'ensure_ascii': False})


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
    (run_dir / INITIALIZATION_UPLOAD_MARKER).touch()

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
            initialization_preview_payload(target_path, project=project)
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

    temporary_path = None
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
        artifact = _result_artifact(payload)
        if artifact is not None:
            if artifact.source != 'upload':
                raise ValueError('解析生成的表格仅供下载，不允许导入数据库')
            temporary_path = Path(tempfile.gettempdir()) / f'pipecloud-{uuid.uuid4().hex}-{_safe_upload_name(artifact.filename)}'
            temporary_path.write_bytes(bytes(artifact.content))
            staged_path = temporary_path
        else:
            staged_path = _resolve_parser_file(payload.get('stagedPath') or payload.get('path'))
            if not (staged_path.parent / INITIALIZATION_UPLOAD_MARKER).is_file():
                raise ValueError('解析生成的表格仅供下载，不允许导入数据库')
    except (FileNotFoundError, ParserArtifact.DoesNotExist) as error:
        return HttpResponseBadRequest(json.dumps({'error': str(error)}, ensure_ascii=False), content_type='application/json')
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        return HttpResponseBadRequest(
            json.dumps({'error': str(error) or '确认导入参数无效'}, ensure_ascii=False),
            content_type='application/json',
        )

    import_mode = payload.get('importMode') or payload.get('mode') or 'replace'
    if import_mode not in {'replace', 'append'}:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
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
        selected_sheet, sheets, total, columns, rows = table_preview_payload(
            source,
            INITIALIZATION_MODELS,
            None,
            limit=20,
        )
        preview = {
            'sheet': selected_sheet,
            'sheets': sheets,
            'total': total,
            'columns': columns,
            'rows': rows,
            'previewLimit': 20,
        }
    except Exception as error:
        return HttpResponseBadRequest(json.dumps({'error': str(error)}, ensure_ascii=False), content_type='application/json')
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

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
    artifact = None
    try:
        artifact_id = request.GET.get('artifactId') or ''
        if artifact_id:
            artifact = ParserArtifact.objects.get(pk=artifact_id)
            preview_source = BytesIO(bytes(artifact.content))
        else:
            preview_source = _resolve_parser_file(request.GET.get('path') or request.GET.get('stagedPath') or '')
    except (ParserArtifact.DoesNotExist, ValueError, RuntimeError, FileNotFoundError):
        return HttpResponseBadRequest(json.dumps({'error': '预览路径无效'}, ensure_ascii=False), content_type='application/json')

    sheet_name = request.GET.get('sheet') or None
    preview_mode = request.GET.get('previewMode') or request.GET.get('source') or 'raw'
    try:
        preview = (
            initialization_preview_payload(preview_source, sheet_name)
            if preview_mode in {'upload', 'initialization'}
            else workbook_preview_payload(preview_source, sheet_name)
        )
    except Exception as error:
        return HttpResponseBadRequest(json.dumps({'error': f'读取工作表预览失败：{error}'}, ensure_ascii=False), content_type='application/json')

    return JsonResponse({
        'stagedPath': request.GET.get('stagedPath') or '',
        'artifactId': artifact.id if artifact else None,
        'filename': artifact.filename if artifact else preview_source.name,
        'preview': preview,
        'normalization': preview.get('normalization', {}),
        'totalRows': preview.get('total', 0),
    }, json_dumps_params={'ensure_ascii': False})


@require_GET
def parser_model_preview(request):
    project, data_root, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)

    try:
        job_id = request.GET.get('jobId') or ''
        part_index = int(request.GET.get('partIndex') or 0)
        job = ParserJob.objects.select_related('idf_model').get(
            job_id=job_id,
            project=project,
            file_type='idf',
            status='completed',
        )
        if part_index <= 0 or not _parser_job_model_available(job):
            raise ValueError
        payload = idf_model_part_payload(job.idf_model, part_index)
    except (ParserJob.DoesNotExist, ObjectDoesNotExist, ValueError, TypeError):
        return HttpResponseBadRequest(
            json.dumps({'error': 'IDF 空间模型数据不存在，请重新解析'}, ensure_ascii=False),
            content_type='application/json',
        )
    return JsonResponse(payload, json_dumps_params={'ensure_ascii': False})


@csrf_exempt
@require_POST
def confirm_idf_model(request):
    project, data_root, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
        job = ParserJob.objects.select_related('idf_model').prefetch_related('subtasks').get(
            job_id=payload.get('jobId'),
            project=project,
            file_type='idf',
            status='completed',
        )
        model = job.idf_model
        expected_indexes = list(
            job.subtasks.filter(status='completed').order_by('index').values_list('index', flat=True)
        )
        stored_indexes = list(
            model.parts.order_by('subtask_index').values_list('subtask_index', flat=True)
        )
        if not expected_indexes or expected_indexes != stored_indexes:
            raise ValueError('IDF 空间模型数据库记录不完整，请重新解析')
    except (ParserJob.DoesNotExist, ObjectDoesNotExist):
        return HttpResponseBadRequest(
            json.dumps({'error': '可保存的 IDF 解析任务不存在'}, ensure_ascii=False),
            content_type='application/json',
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        return HttpResponseBadRequest(
            json.dumps({'error': str(error) or '保存 IDF 模型参数无效'}, ensure_ascii=False),
            content_type='application/json',
        )

    try:
        model = finalize_idf_model(model.id)
    except Exception as error:
        fail_idf_model(model.id)
        return HttpResponseBadRequest(
            json.dumps({'error': f'保存 IDF 模型失败：{error}'}, ensure_ascii=False),
            content_type='application/json',
        )

    return JsonResponse({
        'jobId': job.job_id,
        'modelSaved': True,
        'componentCount': model.component_count,
        'weldCount': model.weld_count,
        'message': 'IDF 模型已保存到当前项目。',
    }, json_dumps_params={'ensure_ascii': False})


def _append_initialization_source(project, staged_path, display_name):
    workbook_payload = read_workbook_rows(staged_path)
    normalized = normalize_initialization_payload(project, workbook_payload)
    validation = normalized['validation']
    if not validation.get('canImport'):
        raise ValueError('初始化数据标准化校验未通过，存在缺失的关键字段或必填值')
    normalized_payload = {
        normalized['sheet']: {
            'columns': normalized['columns'],
            'rows': normalized['visibleRows'],
        },
    }
    incoming_material = workbook_payload.get(INITIALIZATION_MATERIAL_SHEET)

    source = latest_source(project, 'initialization', 'welds')
    if source is None:
        if incoming_material is not None:
            normalized_payload[INITIALIZATION_MATERIAL_SHEET] = incoming_material
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
    combined_payload = {
        selected_sheet or incoming_sheet or 'Sheet1': {
            'columns': next_columns,
            'rows': next_rows,
        },
    }

    material_source = latest_source(project, 'idf-material', 'materials')
    existing_material_columns = []
    existing_material_rows = []
    if material_source is not None:
        _, _, _, existing_material_columns, existing_material_rows = table_payload(
            material_source,
            INITIALIZATION_MATERIAL_MODELS,
            INITIALIZATION_MATERIAL_SHEET,
        )
    if incoming_material is not None or existing_material_rows:
        incoming_material_columns = (incoming_material or {}).get('columns') or []
        material_columns = list(dict.fromkeys([
            *existing_material_columns,
            *incoming_material_columns,
        ]))
        combined_payload[INITIALIZATION_MATERIAL_SHEET] = {
            'columns': material_columns,
            'rows': [
                *existing_material_rows,
                *((incoming_material or {}).get('rows') or []),
            ],
        }
    return replace_source_rows(
        project,
        'initialization',
        'welds',
        source.display_name or display_name,
        source.relative_path or f'database://initialization/{project.id}/{display_name}',
        combined_payload,
        INITIALIZATION_MODELS,
    )


@require_GET
def download_parsed_file(request):
    artifact = None
    try:
        artifact_id = request.GET.get('artifactId') or ''
        if artifact_id:
            artifact = ParserArtifact.objects.get(pk=artifact_id)
            content = bytes(artifact.content)
            filename = artifact.filename
        else:
            target_path = _resolve_parser_file(request.GET.get('path') or '')
            content = target_path.read_bytes()
            filename = target_path.name
    except (ParserArtifact.DoesNotExist, ValueError, RuntimeError, FileNotFoundError):
        return HttpResponseBadRequest(json.dumps({'error': '下载路径无效'}, ensure_ascii=False), content_type='application/json')

    response = HttpResponse(content, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = (
        'attachment; filename="parser-result.xlsx"; '
        f"filename*=UTF-8''{quote(filename)}"
    )
    return response


@csrf_exempt
@require_POST
def download_parsed_files(request):
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
        artifact_ids = payload.get('artifactIds') or []
        relative_paths = payload.get('stagedPaths') or payload.get('paths') or []
        if not isinstance(artifact_ids, list) or not isinstance(relative_paths, list):
            raise ValueError
        files = []
        for artifact_id in artifact_ids:
            artifact = ParserArtifact.objects.get(pk=artifact_id)
            files.append((artifact.filename, bytes(artifact.content)))
        for path in relative_paths:
            target_path = _resolve_parser_file(path)
            files.append((target_path.name, target_path.read_bytes()))
        if not files:
            raise ValueError
    except (ParserArtifact.DoesNotExist, FileNotFoundError):
        return HttpResponseBadRequest(
            json.dumps({'error': '部分预览文件已失效，请重新解析后下载'}, ensure_ascii=False),
            content_type='application/json',
        )
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, RuntimeError):
        return HttpResponseBadRequest(
            json.dumps({'error': '下载参数无效'}, ensure_ascii=False),
            content_type='application/json',
        )

    archive_buffer = BytesIO()
    used_names = set()
    with zipfile.ZipFile(archive_buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for filename, content in files:
            archive_name = filename
            if archive_name in used_names:
                stem = Path(filename).stem
                suffix = Path(filename).suffix
                counter = 2
                while f'{stem}-{counter}{suffix}' in used_names:
                    counter += 1
                archive_name = f'{stem}-{counter}{suffix}'
            used_names.add(archive_name)
            archive.writestr(archive_name, content)

    response = HttpResponse(archive_buffer.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = (
        'attachment; filename="parser-preview-files.zip"; '
        f"filename*=UTF-8''{quote('全部预览文件.zip')}"
    )
    return response
