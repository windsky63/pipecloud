from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Lock
import uuid

from django.db import close_old_connections

from pipecloud.models import Project
from pipecloud.services.file_exports import build_project_file_tree, export_project_files


_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix='pipecloud-export')
_JOBS = {}
_LOCK = Lock()
_JOB_TTL = timedelta(hours=1)


def _now():
    return datetime.now(timezone.utc)


def _cleanup_jobs():
    expires_before = _now() - _JOB_TTL
    with _LOCK:
        expired = [
            job_id
            for job_id, job in _JOBS.items()
            if job['updated_at'] < expires_before
        ]
        for job_id in expired:
            _JOBS.pop(job_id, None)


def _update_job(job_id, **changes):
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return
        job.update(changes)
        job['updated_at'] = _now()


def _run_export(job_id, project_id, selected_ids):
    close_old_connections()
    try:
        _update_job(job_id, status='running', progress=1, message='正在准备导出数据')
        project = Project.objects.get(pk=project_id)

        def report(progress, message=''):
            _update_job(
                job_id,
                progress=max(1, min(int(progress), 99)),
                message=str(message or ''),
            )

        content = export_project_files(project, selected_ids, progress_callback=report)
        _update_job(
            job_id,
            status='completed',
            progress=100,
            message='导出完成',
            content=content,
        )
    except Exception as error:
        _update_job(
            job_id,
            status='failed',
            message=str(error),
            error=str(error),
        )
    finally:
        close_old_connections()


def start_export_job(project, selected_ids):
    selected = list(dict.fromkeys(str(value) for value in selected_ids or []))
    if not selected:
        raise ValueError('请至少选择一个文件')

    # 这里只校验元数据，不生成 Excel。
    _, leaf_map = build_project_file_tree(project)
    missing = [value for value in selected if value not in leaf_map]
    if missing:
        raise ValueError('所选文件不存在或已失效，请刷新文件树')

    _cleanup_jobs()
    job_id = uuid.uuid4().hex
    now = _now()
    with _LOCK:
        _JOBS[job_id] = {
            'id': job_id,
            'project_id': project.id,
            'status': 'queued',
            'progress': 0,
            'message': '等待开始导出',
            'error': '',
            'content': None,
            'created_at': now,
            'updated_at': now,
        }
    _EXECUTOR.submit(_run_export, job_id, project.id, selected)
    return job_id


def export_job_status(project, job_id):
    _cleanup_jobs()
    with _LOCK:
        job = _JOBS.get(str(job_id or ''))
        if job is None or job['project_id'] != project.id:
            raise FileNotFoundError('导出任务不存在或已失效')
        return {
            'jobId': job['id'],
            'status': job['status'],
            'progress': job['progress'],
            'message': job['message'],
            'error': job['error'],
        }


def take_export_job_content(project, job_id):
    with _LOCK:
        job = _JOBS.get(str(job_id or ''))
        if job is None or job['project_id'] != project.id:
            raise FileNotFoundError('导出任务不存在或已失效')
        if job['status'] == 'failed':
            raise ValueError(job['error'] or '导出失败')
        if job['status'] != 'completed' or job['content'] is None:
            raise ValueError('导出任务尚未完成')
        content = job['content']
        _JOBS.pop(job['id'], None)
        return content
