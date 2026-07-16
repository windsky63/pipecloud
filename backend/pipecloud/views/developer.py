import json

from django.apps import apps
from django.conf import settings
from django.db import transaction
from django.http import HttpResponseBadRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from pipecloud.services.plan_rollover import execute_all_project_rollovers
from pipecloud.services.plan_completion import execute_all_completion_syncs
from pipecloud.models import OperationLog, ScheduledTaskRun


@ensure_csrf_cookie
@require_http_methods(['GET'])
def operation_logs(request):
    try:
        limit = min(max(int(request.GET.get('limit', 500)), 1), 2000)
    except (TypeError, ValueError):
        limit = 500
    rows = OperationLog.objects.all()[:limit]
    return JsonResponse({
        'ok': True,
        'total': OperationLog.objects.count(),
        'logs': [
            {
                'id': row.pk,
                'createdAt': row.created_at.isoformat(timespec='seconds'),
                'userName': row.user_name,
                'action': row.action,
                'method': row.method,
                'path': row.path,
                'projectId': row.project_id_value,
                'projectName': row.project_name,
                'statusCode': row.status_code,
                'succeeded': row.succeeded,
                'detail': row.detail,
                'ipAddress': row.ip_address or '',
            }
            for row in rows
        ],
    }, json_dumps_params={'ensure_ascii': False})


def _pipecloud_models():
    return [
        model
        for model in apps.get_app_config('pipecloud').get_models()
        if not model._meta.auto_created
    ]


def _database_table_payload(model):
    return {
        'model': model.__name__,
        'verboseName': str(model._meta.verbose_name),
        'tableName': model._meta.db_table,
        'count': model.objects.count(),
    }


def _scheduled_task_log_payload(task_run, job_names):
    stats = task_run.stats or {}
    return {
        'id': task_run.pk,
        'taskName': task_run.task_name,
        'taskDisplayName': job_names.get(task_run.task_name, task_run.task_name),
        'projectId': task_run.project_id,
        'projectName': task_run.project.project_name,
        'businessDate': task_run.business_date.isoformat(),
        'status': task_run.status,
        'planKey': stats.get('planKey', ''),
        'planName': stats.get('planName', ''),
        'stats': stats,
        'error': task_run.error_message,
        'startedAt': task_run.started_at.isoformat() if task_run.started_at else '',
        'finishedAt': task_run.finished_at.isoformat() if task_run.finished_at else '',
    }


@ensure_csrf_cookie
@require_http_methods(['GET', 'POST'])
def run_plan_rollover(request):
    if request.method == 'GET':
        return JsonResponse({'ready': True})

    results = execute_all_project_rollovers()
    failed = sum(1 for result in results if result.get('error'))
    skipped = sum(1 for result in results if result.get('skipped') or result.get('alreadyExecuted'))
    succeeded = len(results) - failed - skipped
    return JsonResponse({
        'ok': failed == 0,
        'results': results,
        'summary': {
            'succeeded': succeeded,
            'skipped': skipped,
            'failed': failed,
        },
    }, json_dumps_params={'ensure_ascii': False})


@ensure_csrf_cookie
@require_http_methods(['GET', 'POST'])
def scheduled_tasks(request):
    if request.method == 'GET':
        jobs = []
        job_names = {}
        for config in settings.SCHEDULED_MAINTENANCE_JOBS:
            job_names[config.get('command') or ''] = config.get('name') or config.get('key', '')
            jobs.append({
                'key': config.get('key'),
                'kind': config.get('kind', ''),
                'name': config.get('name') or config.get('key', ''),
                'command': config.get('command') or '',
                'enabled': bool(config.get('enabled', True)),
                'hour': int(config.get('hour', 0)),
                'minute': int(config.get('minute', 0)),
                'timezone': settings.TIME_ZONE,
            })
        logs = [
            _scheduled_task_log_payload(task_run, job_names)
            for task_run in ScheduledTaskRun.objects.select_related('project').order_by(
                '-business_date', '-started_at', '-id',
            )[:500]
        ]
        return JsonResponse({
            'ok': True,
            'jobs': jobs,
            'logs': logs,
            'misfireGraceSeconds': settings.PLAN_COMPLETION_SYNC_MISFIRE_GRACE_SECONDS,
        }, json_dumps_params={'ensure_ascii': False})

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except (UnicodeDecodeError, json.JSONDecodeError):
        return HttpResponseBadRequest(json.dumps({'error': '请求数据无效'}, ensure_ascii=False), content_type='application/json')
    job_key = str(payload.get('key') or payload.get('jobKey') or '').strip()
    job_config = next(
        (config for config in settings.SCHEDULED_MAINTENANCE_JOBS if config.get('key') == job_key),
        None,
    )
    if job_config is None:
        return HttpResponseBadRequest(json.dumps({'error': '未知定时任务'}, ensure_ascii=False), content_type='application/json')

    if job_config.get('kind') == 'completion-sync':
        plan_key = {
            'sync-anti-corrosion-completion': 'anti-corrosion',
            'sync-cutting-completion': 'cutting',
            'sync-welding-completion': 'welding',
        }.get(job_key, '')
        results = execute_all_completion_syncs(plan_key, force=bool(payload.get('force')))
    elif job_config.get('kind') == 'plan-rollover':
        plan_key = {
            'rollover-cutting-plan': 'cutting',
            'rollover-welding-plan': 'welding',
        }.get(job_key, '')
        results = execute_all_project_rollovers(plan_key=plan_key, force=bool(payload.get('force')))
    else:
        return HttpResponseBadRequest(json.dumps({'error': '未知定时任务类型'}, ensure_ascii=False), content_type='application/json')
    failed = sum(1 for result in results if result.get('error'))
    skipped = sum(1 for result in results if result.get('alreadyExecuted'))
    succeeded = len(results) - failed - skipped
    return JsonResponse({
        'ok': failed == 0,
        'results': results,
        'summary': {
            'succeeded': succeeded,
            'skipped': skipped,
            'failed': failed,
        },
    }, json_dumps_params={'ensure_ascii': False})


@ensure_csrf_cookie
@require_http_methods(['GET'])
def database_overview(request):
    rows = [_database_table_payload(model) for model in _pipecloud_models()]
    return JsonResponse({
        'ok': True,
        'totalTables': len(rows),
        'totalRows': sum(row['count'] for row in rows),
        'tables': sorted(rows, key=lambda row: row['tableName']),
    }, json_dumps_params={'ensure_ascii': False})


@ensure_csrf_cookie
@csrf_exempt
@require_http_methods(['POST'])
def clear_database(request):
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except (UnicodeDecodeError, json.JSONDecodeError):
        return HttpResponseBadRequest(json.dumps({'error': '请求数据无效'}, ensure_ascii=False), content_type='application/json')

    selected_tables = payload.get('tables') or payload.get('tableNames') or []
    if not isinstance(selected_tables, list):
        return HttpResponseBadRequest(json.dumps({'error': '数据库表参数无效'}, ensure_ascii=False), content_type='application/json')
    selected_tables = {
        str(table or '').strip()
        for table in selected_tables
        if str(table or '').strip()
    }
    if not selected_tables:
        return HttpResponseBadRequest(json.dumps({'error': '请先选择要清空的数据库表'}, ensure_ascii=False), content_type='application/json')

    models = _pipecloud_models()
    models_by_table = {model._meta.db_table: model for model in models}
    unknown_tables = sorted(selected_tables.difference(models_by_table))
    if unknown_tables:
        return HttpResponseBadRequest(
            json.dumps({'error': f'数据库表不存在或不允许清空：{", ".join(unknown_tables)}'}, ensure_ascii=False),
            content_type='application/json',
        )

    selected_models = [model for model in models if model._meta.db_table in selected_tables]
    deleted = []
    with transaction.atomic():
        for model in reversed(selected_models):
            count, _ = model.objects.all().delete()
            deleted.append({
                'model': model.__name__,
                'verboseName': str(model._meta.verbose_name),
                'tableName': model._meta.db_table,
                'deletedCount': count,
            })
    return JsonResponse({
        'ok': True,
        'deleted': list(reversed(deleted)),
        'deletedRows': sum(row['deletedCount'] for row in deleted),
    }, json_dumps_params={'ensure_ascii': False})
