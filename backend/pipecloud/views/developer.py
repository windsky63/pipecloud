import json

from django.apps import apps
from django.db import transaction
from django.http import HttpResponseBadRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from pipecloud.services.plan_rollover import execute_all_project_rollovers


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
