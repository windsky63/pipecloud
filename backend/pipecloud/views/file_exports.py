import json
from urllib.parse import quote

from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from pipecloud.services.file_exports import build_project_file_tree, export_project_files
from pipecloud.services.file_export_jobs import (
    export_job_status,
    start_export_job,
    take_export_job_content,
)

from .common import _project_bad_request, _request_project_context


@require_GET
def project_file_tree(request):
    project, _, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)
    tree, leaf_map = build_project_file_tree(project)
    return JsonResponse({
        'projectId': project.id,
        'projectName': project.project_name,
        'fileCount': len(leaf_map),
        'tree': tree,
    }, json_dumps_params={'ensure_ascii': False})


@csrf_exempt
@require_POST
def batch_export_project_files(request):
    project, _, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
        selected_ids = payload.get('fileIds') or []
        if not isinstance(selected_ids, list):
            raise ValueError('导出文件参数无效')
        content = export_project_files(project, selected_ids)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        return HttpResponseBadRequest(
            json.dumps({'error': str(error)}, ensure_ascii=False),
            content_type='application/json',
        )
    filename = quote(f'{project.project_name}-项目文件.zip')
    response = HttpResponse(content, content_type='application/zip')
    response['Content-Disposition'] = f"attachment; filename*=UTF-8''{filename}"
    return response


@csrf_exempt
@require_POST
def start_batch_export(request):
    project, _, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
        selected_ids = payload.get('fileIds') or []
        if not isinstance(selected_ids, list):
            raise ValueError('导出文件参数无效')
        job_id = start_export_job(project, selected_ids)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        return HttpResponseBadRequest(
            json.dumps({'error': str(error)}, ensure_ascii=False),
            content_type='application/json',
        )
    return JsonResponse({
        'jobId': job_id,
        'status': 'queued',
        'progress': 0,
    })


@require_GET
def batch_export_status(request):
    project, _, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)
    try:
        payload = export_job_status(project, request.GET.get('jobId'))
    except FileNotFoundError as error:
        return HttpResponseBadRequest(
            json.dumps({'error': str(error)}, ensure_ascii=False),
            content_type='application/json',
        )
    return JsonResponse(payload, json_dumps_params={'ensure_ascii': False})


@require_GET
def download_batch_export(request):
    project, _, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)
    try:
        content = take_export_job_content(project, request.GET.get('jobId'))
    except (FileNotFoundError, ValueError) as error:
        return HttpResponseBadRequest(
            json.dumps({'error': str(error)}, ensure_ascii=False),
            content_type='application/json',
        )
    filename = quote(f'{project.project_name}-项目文件.zip')
    response = HttpResponse(content, content_type='application/zip')
    response['Content-Disposition'] = f"attachment; filename*=UTF-8''{filename}"
    return response
