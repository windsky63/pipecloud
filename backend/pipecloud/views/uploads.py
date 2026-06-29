import json

from django.http import HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .file_parser import parse_uploaded_files, stage_initialization_upload
from .workflow import upload_arrival_file


UPLOAD_HANDLERS = {
    'file-parser-parse': parse_uploaded_files,
    'initialization-upload': stage_initialization_upload,
    'arrival-order': upload_arrival_file,
}


@csrf_exempt
@require_POST
def upload_files(request, upload_key):
    handler = UPLOAD_HANDLERS.get(upload_key)
    if handler is None:
        return HttpResponseBadRequest(json.dumps({'error': '未知上传类型'}, ensure_ascii=False), content_type='application/json')
    return handler(request)
