import json

WRITE_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}
SENSITIVE_KEYS = {'password', 'token', 'stageToken', 'secret', 'authorization'}
ACTION_NAMES = {
    'run': '执行排产操作',
    'save': '保存数据',
    'upload': '上传文件',
    'import': '导入数据',
    'export': '导出数据',
    'delete': '删除数据',
    'clear': '清空数据',
    'cancel': '取消任务',
    'commit': '确认保存计划',
    'move': '调整计划日期',
    'release': '释放材料锁定',
}


def _clean_detail(value):
    if isinstance(value, dict):
        return {
            key: ('***' if key.lower() in {item.lower() for item in SENSITIVE_KEYS} else _clean_detail(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_clean_detail(item) for item in value[:100]]
    return value


def _action_name(path):
    parts = [part for part in path.strip('/').split('/') if part]
    marker = next((part for part in reversed(parts) if part in ACTION_NAMES), '')
    if '/run/' in path and parts:
        return f'{ACTION_NAMES["run"]}：{parts[-1]}'
    return ACTION_NAMES.get(marker, f'{"/".join(parts[-2:]) or path}')


class OperationLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.method not in WRITE_METHODS or not request.path.startswith('/api/pipecloud/'):
            return response
        try:
            from pipecloud.models import OperationLog, Project

            detail = {}
            content_type = request.headers.get('Content-Type', '')
            if 'application/json' in content_type and request.body:
                detail = _clean_detail(json.loads(request.body.decode('utf-8')))
            elif request.FILES:
                detail = {'files': [file.name for file in request.FILES.values()]}
            project_id = request.GET.get('projectId')
            project = Project.objects.filter(pk=project_id).only('project_name').first() if project_id else None
            user = getattr(request, 'user', None)
            user_name = user.get_username() if user and user.is_authenticated else request.headers.get('X-User-Name', '匿名用户')
            forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
            ip_address = (forwarded.split(',')[0].strip() if forwarded else request.META.get('REMOTE_ADDR')) or None
            OperationLog.objects.create(
                user_name=user_name or '匿名用户',
                action=_action_name(request.path),
                method=request.method,
                path=request.path,
                project_id_value=project.pk if project else (int(project_id) if str(project_id or '').isdigit() else None),
                project_name=project.project_name if project else '',
                status_code=response.status_code,
                succeeded=response.status_code < 400,
                detail=detail,
                ip_address=ip_address,
                user_agent=request.headers.get('User-Agent', '')[:2000],
            )
        except Exception:
            # Logging must never break the business operation, including before migrations run.
            pass
        return response
