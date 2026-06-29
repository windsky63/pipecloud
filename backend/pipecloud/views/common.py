import json
import locale
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

import pandas as pd
from django.db.models import Count
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from openpyxl import load_workbook
from spool_analysis.project_spool_info import (
    read_project_spool_info_from_database,
)

from ..models import (
    ArrivalOrderRow,
    DataSourceFile,
    FittingMaterialRow,
    InitializationWeldRow,
    PipeMaterialRow,
    PlanRecord,
    Project,
    WeldingPlanRow,
    WeldLibraryRow,
    WeldPreScheduleRow,
)
from pipecloud.services.project_tables import ensure_project_tables, using_project_tables
from pipecloud.services.db_storage import replace_source_rows, table_payload


BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
PREFAB_ROOT = BACKEND_DIR / 'prefab_schedule'
SPOOL_ANALYSIS_ROOT = BACKEND_DIR / 'spool_analysis'
FILE_ROOT = BACKEND_DIR / 'file'
PROJECTS_ROOT = FILE_ROOT / 'projects'
FILE_PARSER_ROOT = FILE_ROOT / 'parser'
FILE_BACKUP_ROOT = FILE_ROOT / 'backups'
DATA_ROOT = PROJECTS_ROOT
STAGED_PLAN_ROOT = FILE_ROOT / 'staged_plans'
LIBRARY_ROOT = DATA_ROOT / '库管理'
ARRIVAL_ROOT = DATA_ROOT / '入库单'
CUTTING_PIPE_LIBRARY = LIBRARY_ROOT / '防腐管子材料库.xlsx'
CUTTING_PENDING_PIPE_LIBRARY = DATA_ROOT / '中间结果' / '待确认防腐管子材料库.xlsx'
CUTTING_PRE_SCHEDULE_OUTPUT = DATA_ROOT / '中间结果' / '焊口预排产匹配结果.xlsx'
ANTI_CORROSION_PLAN_ROOT = DATA_ROOT / '防腐委托单'
CUTTING_PLAN_ROOT = DATA_ROOT / '下料排产单'
WELDING_PLAN_ROOT = DATA_ROOT / '焊接排产单'

PROJECT_COLUMNS = [
    {'field': 'project_name', 'title': '项目名称'},
    {'field': 'pipe_segment', 'title': '可预制管段'},
    {'field': 'prefab_weld_count', 'title': '可预制焊口数'},
    {'field': 'completion_rate', 'title': '完成率'},
    {'field': 'start_date', 'title': '开始日期'},
]
PROJECT_FIELD_NAMES = {column['field'] for column in PROJECT_COLUMNS}
PROJECT_TITLE_TO_FIELD = {column['title']: column['field'] for column in PROJECT_COLUMNS}
PROJECT_TITLE_TO_FIELD['管段'] = 'pipe_segment'
PROJECT_DATA_ROOT = PROJECTS_ROOT
INIT_WELD_FILE_PATTERN = '焊口初始化数据*.xlsx'
PARSER_OUTPUT_FILES = {
    'idf': 'IDF拓扑材料表.xlsx',
    'pcf': 'PCF材料段输出信息.xlsx',
}
PARSER_SCRIPTS = {
    'idf': SPOOL_ANALYSIS_ROOT / 'parse_idf_viewer_to_excel.py',
    'pcf': SPOOL_ANALYSIS_ROOT / 'rename_pcf_files_v5.py',
}

CUTTING_COLUMNS = {
    'material_code': '材料代码',
    'description': '名称及规格',
    'pipe_no': '管子序号',
    'stock_qty': '库存数量（米）',
    'original_length': '原始米数',
    'remaining_length': '剩余米数',
    'cut_lengths': '已切割长度列表',
    'loss_lengths': '切割损耗列表',
    'consumed_lengths': '实际占用长度列表',
    'heat_no': '炉批号',
}

WELD_LIBRARY_FILE_NAME = '预制焊口库.xlsx'
WELDING_PRIMARY_PLAN_FILE_NAME = '管段焊口表.xlsx'
WELD_COLUMNS = {
    'unit': '单元号',
    'pipeline': '管线号',
    'segment_no': '管段号',
    'diameter': '寸径',
    'weld_no_start': '初始焊口号',
    'weld_no_final': '最终焊口号',
    'library_seq': '库序号',
    'completed_flag': '是否完成',
}
WELD_COLUMN_ALIASES = {
    WELD_COLUMNS['segment_no']: ['预制组件', '管段号', '预制管段', '预制段'],
    WELD_COLUMNS['completed_flag']: ['是否完成', '完成状态', '状态', '完工状态'],
    WELD_COLUMNS['weld_no_start']: ['初始焊口号', '起始焊口号', '焊口起始号', '开始焊口号'],
    WELD_COLUMNS['weld_no_final']: ['最终焊口号', '结束焊口号', '焊口结束号', '完成焊口号'],
    WELD_COLUMNS['pipeline']: ['管线号(必填)', '管线号'],
    WELD_COLUMNS['unit']: ['单元号(必填)', '单元号'],
    WELD_COLUMNS['diameter']: ['英制', '英制尺寸', '寸径'],
    WELD_COLUMNS['library_seq']: ['库序号', '序号', '行号'],
}

PLAN_SOURCES = {
    'anti-corrosion': {
        'key': 'anti-corrosion',
        'name': '防腐',
        'root': ANTI_CORROSION_PLAN_ROOT,
    },
    'cutting': {
        'key': 'cutting',
        'name': '下料',
        'root': CUTTING_PLAN_ROOT,
    },
    'welding': {
        'key': 'welding',
        'name': '焊接',
        'root': WELDING_PLAN_ROOT,
    },
}


MODULES = [
    {
        'key': 'initialization',
        'name': '初始化预制',
        'description': '读取焊口初始化数据，完成自动焊划分，并生成预制焊口库。',
        'actions': ['prefab-weld-library'],
        'files': [
            '焊口初始化数据*.xlsx',
            '中间结果/可预制焊口初步过滤结果.xlsx',
            '中间结果/自动焊口初步过滤结果.xlsx',
            '中间结果/链路划分结果.xlsx',
            '中间结果/自动焊口数据.xlsx',
            '库管理/预制焊口库.xlsx',
        ],
    },
    {
        'key': 'arrival',
        'name': '到货管理',
        'description': '汇总入库单，维护管子材料库和管件法兰材料库。',
        'actions': ['arrival-library'],
        'files': [
            '入库单',
            '库管理/管子材料库.xlsx',
            '库管理/管件法兰材料库.xlsx',
        ],
    },
    {
        'key': 'antiCorrosion',
        'name': '防腐管理及排产',
        'description': '暂不生成专用防腐材料库，直接复制管子材料库和管件法兰材料库作为防腐库，再生成防腐委托总表。',
        'actions': ['prepare-anti-corrosion-libraries', 'anti-corrosion-schedule'],
        'files': [
            '库管理/防腐管子材料库.xlsx',
            '库管理/防腐管件法兰材料库.xlsx',
            '防腐委托单/防腐委托总表.xlsx',
        ],
    },
    {
        'key': 'cutting',
        'name': '下料管理及排产',
        'description': '进行焊口预排产材料匹配，按最小管材消耗生成待确认防腐材料库。',
        'actions': ['weld-pre-schedule', 'confirm-cutting-pre-schedule'],
        'files': [
            '中间结果/焊口预排产匹配结果.xlsx',
            '中间结果/待确认防腐管子材料库.xlsx',
            '中间结果/待确认防腐管件法兰材料库.xlsx',
        ],
    },
    {
        'key': 'welding',
        'name': '焊接管理及排产',
        'description': '在初始化预制和下料预排产确认完成后，生成焊接排产单和领料单。',
        'actions': ['auto-weld-schedule'],
        'files': [
            '焊接排产单',
        ],
    },
    {
        'key': 'schedule',
        'name': '总排产计划',
        'description': '按预排产结果滚动生成未来下料计划、焊接计划和总排产计划。',
        'actions': ['future-schedule'],
        'files': [
            '中间结果/焊口预排产匹配结果.xlsx',
            '下料排产单',
            '焊接排产单',
            '焊接排产单/总排产计划.xlsx',
        ],
    },
]


ACTIONS = {
    'prefab-weld-library': {
        'name': '生成预制焊口库',
        'script': PREFAB_ROOT / '初始化文件处理' / '生成预制焊口库.py',
        'module': '初始化预制',
    },
    'arrival-library': {
        'name': '生成材料库',
        'script': PREFAB_ROOT / '到货管理' / 'material_library_maintenance.py',
        'module': '到货管理',
    },
    'prepare-anti-corrosion-libraries': {
        'name': '复制防腐材料库',
        'script': PREFAB_ROOT / '防腐管理及排产' / 'prepare_libraries.py',
        'module': '防腐管理及排产',
    },
    'anti-corrosion-schedule': {
        'name': '生成防腐委托总表',
        'script': PREFAB_ROOT / '防腐管理及排产' / 'main.py',
        'module': '防腐管理及排产',
    },
    'auto-weld-schedule': {
        'name': '生成焊接排产单',
        'script': PREFAB_ROOT / '焊接管理及排产' / '自动焊排产' / 'main.py',
        'module': '焊接管理及排产',
    },
    'weld-pre-schedule': {
        'name': '生成下料预排产',
        'script': PREFAB_ROOT / '下料管理及排产' / 'weld_pre_schedule_matcher.py',
        'module': '下料管理及排产',
    },
    'confirm-cutting-pre-schedule': {
        'name': '确认同步防腐库',
        'script': PREFAB_ROOT / '下料管理及排产' / 'confirm_pre_schedule.py',
        'module': '下料管理及排产',
    },
    'future-schedule': {
        'name': '生成所有计划',
        'script': PREFAB_ROOT / 'schedule.py',
        'module': '总排产计划',
    },
}


LIBRARY_FILES = {
    'weld-library': {
        'name': '预制焊口库',
        'path': LIBRARY_ROOT / '预制焊口库.xlsx',
    },
    'pipe-library': {
        'name': '管子材料库',
        'path': LIBRARY_ROOT / '管子材料库.xlsx',
    },
    'fitting-library': {
        'name': '管件法兰材料库',
        'path': LIBRARY_ROOT / '管件法兰材料库.xlsx',
    },
    'anti-pipe-library': {
        'name': '防腐管子材料库',
        'path': LIBRARY_ROOT / '防腐管子材料库.xlsx',
    },
    'anti-fitting-library': {
        'name': '防腐管件法兰材料库',
        'path': LIBRARY_ROOT / '防腐管件法兰材料库.xlsx',
    },
}


def _relative_path(path):
    try:
        return str(path.relative_to(BACKEND_DIR)).replace('\\', '/')
    except ValueError:
        pass
    try:
        return str(path.relative_to(PREFAB_ROOT)).replace('\\', '/')
    except ValueError:
        return str(path).replace('\\', '/')


def _request_project_context(request, required=False):
    project_id = request.GET.get('project_id') or request.POST.get('project_id')
    if not project_id:
        return None, DATA_ROOT, '请先选择项目' if required else ''
    try:
        project = Project.objects.get(pk=int(project_id))
    except (TypeError, ValueError, Project.DoesNotExist):
        return None, DATA_ROOT, '项目不存在'
    return project, _project_root(project), ''


def _project_bad_request(error):
    return HttpResponseBadRequest(
        json.dumps({'error': error}, ensure_ascii=False),
        content_type='application/json',
    )


def _library_files(data_root):
    library_root = data_root / '库管理'
    return {
        'weld-library': {
            'name': '预制焊口库',
            'path': library_root / '预制焊口库.xlsx',
        },
        'pipe-library': {
            'name': '管子材料库',
            'path': library_root / '管子材料库.xlsx',
        },
        'fitting-library': {
            'name': '管件法兰材料库',
            'path': library_root / '管件法兰材料库.xlsx',
        },
        'anti-pipe-library': {
            'name': '防腐管子材料库',
            'path': library_root / '防腐管子材料库.xlsx',
        },
        'anti-fitting-library': {
            'name': '防腐管件法兰材料库',
            'path': library_root / '防腐管件法兰材料库.xlsx',
        },
    }


def _plan_sources(data_root):
    return {
        'anti-corrosion': {
            'key': 'anti-corrosion',
            'name': '防腐',
            'root': data_root / '防腐委托单',
        },
        'cutting': {
            'key': 'cutting',
            'name': '下料',
            'root': data_root / '下料排产单',
        },
        'welding': {
            'key': 'welding',
            'name': '焊接',
            'root': data_root / '焊接排产单',
        },
    }


def _database_status_payload(relative_name, exists=False, count=0, updated_at=None, path=None, status_type='数据库'):
    return {
        'name': relative_name,
        'path': path or relative_name,
        'exists': bool(exists),
        'type': status_type,
        'count': int(count or 0),
        'size': None,
        'updatedAt': updated_at or None,
    }


def _latest_source_from_queryset(queryset):
    return queryset.order_by('-file_updated_at', '-id').first()


def _database_source_file_info(
    project,
    relative_name,
    source_type=None,
    source_key=None,
    source_key_prefix=None,
    display_name=None,
    row_model=None,
    row_filters=None,
    source_count_only=False,
):
    if project is None:
        return _database_status_payload(relative_name)

    source_queryset = DataSourceFile.objects.filter(project=project)
    if source_type:
        source_queryset = source_queryset.filter(source_type=source_type)
    if source_key:
        source_queryset = source_queryset.filter(source_key=source_key)
    if source_key_prefix:
        source_queryset = source_queryset.filter(source_key__startswith=source_key_prefix)
    if display_name:
        source_queryset = source_queryset.filter(display_name=display_name)

    source_count = source_queryset.count()
    latest_source = _latest_source_from_queryset(source_queryset)
    row_count = None
    if row_model is not None and not source_count_only:
        row_queryset = row_model.objects.filter(project=project)
        if source_type:
            row_queryset = row_queryset.filter(source_file__source_type=source_type)
        if source_key:
            row_queryset = row_queryset.filter(source_file__source_key=source_key)
        if source_key_prefix:
            row_queryset = row_queryset.filter(source_file__source_key__startswith=source_key_prefix)
        if display_name:
            row_queryset = row_queryset.filter(source_file__display_name=display_name)
        if row_filters:
            row_queryset = row_queryset.filter(**row_filters)
        row_count = row_queryset.count()

    count = source_count if source_count_only or row_count is None else row_count
    return _database_status_payload(
        relative_name,
        exists=source_count > 0 or (row_count or 0) > 0,
        count=count,
        updated_at=latest_source.file_updated_at if latest_source else None,
        path=latest_source.relative_path if latest_source else relative_name,
    )


def _database_plan_record_info(project, relative_name, plan_key, row_model=None):
    if project is None:
        return _database_status_payload(relative_name)
    records = PlanRecord.objects.filter(project=project, plan_key=plan_key)
    latest = records.order_by('-folder_updated_at', '-id').first()
    row_count = 0
    if row_model is not None:
        row_count = row_model.objects.filter(
            project=project,
            source_file__source_type='plan',
            source_file__source_key__startswith=f'{plan_key}:',
        ).count()
    count = row_count or records.count()
    return _database_status_payload(
        relative_name,
        exists=records.exists() or row_count > 0,
        count=count,
        updated_at=latest.folder_updated_at if latest else None,
        path=latest.relative_path if latest else relative_name,
        status_type='计划记录',
    )


def _database_module_file_info(project, relative_name, data_root=DATA_ROOT):
    if project is None:
        return _database_status_payload(relative_name)

    with using_project_tables(project):
        if relative_name == '焊口初始化数据*.xlsx':
            return _database_source_file_info(project, relative_name, 'initialization', 'welds', row_model=InitializationWeldRow)
        if relative_name in {'库管理/焊口库.xlsx', '库管理/预制焊口库.xlsx'}:
            return _database_source_file_info(project, relative_name, 'library', 'weld-library', row_model=WeldLibraryRow)
        if relative_name in {'中间结果/可预制焊口初步过滤结果.xlsx', '中间结果/链路划分结果.xlsx'}:
            return _database_source_file_info(project, relative_name, 'library', 'weld-library', row_model=WeldLibraryRow)
        if relative_name in {'中间结果/自动焊口初步过滤结果.xlsx', '中间结果/自动焊口数据.xlsx'}:
            return _database_source_file_info(
                project,
                relative_name,
                'library',
                'weld-library',
                row_model=WeldLibraryRow,
                row_filters={'welding_mode__contains': '自动焊'},
            )
        if relative_name == '入库单':
            return _database_source_file_info(project, relative_name, 'arrival', row_model=ArrivalOrderRow, source_count_only=True)
        if relative_name == '库管理/管子材料库.xlsx':
            return _database_source_file_info(project, relative_name, 'library', 'pipe-library', row_model=PipeMaterialRow)
        if relative_name == '库管理/管件法兰材料库.xlsx':
            return _database_source_file_info(project, relative_name, 'library', 'fitting-library', row_model=FittingMaterialRow)
        if relative_name == '库管理/防腐管子材料库.xlsx':
            return _database_source_file_info(project, relative_name, 'library', 'anti-pipe-library', row_model=PipeMaterialRow)
        if relative_name == '库管理/防腐管件法兰材料库.xlsx':
            return _database_source_file_info(project, relative_name, 'library', 'anti-fitting-library', row_model=FittingMaterialRow)
        if relative_name == '防腐委托单/防腐委托总表.xlsx':
            return _database_plan_record_info(project, relative_name, 'anti-corrosion')
        if relative_name == '中间结果/焊口预排产匹配结果.xlsx':
            return _database_source_file_info(project, relative_name, 'pre-schedule', 'weld-pre-schedule', row_model=WeldPreScheduleRow)
        if relative_name == '中间结果/待确认防腐管子材料库.xlsx':
            return _database_source_file_info(project, relative_name, 'library', 'pending-anti-pipe-library', row_model=PipeMaterialRow)
        if relative_name == '中间结果/待确认防腐管件法兰材料库.xlsx':
            return _database_source_file_info(project, relative_name, 'library', 'pending-anti-fitting-library', row_model=FittingMaterialRow)
        if relative_name == '下料排产单':
            return _database_plan_record_info(project, relative_name, 'cutting')
        if relative_name == '焊接排产单':
            return _database_plan_record_info(project, relative_name, 'welding', WeldingPlanRow)
        if relative_name == '焊接排产单/总排产计划.xlsx':
            return _database_plan_record_info(project, relative_name, 'welding', WeldingPlanRow)
    return _database_status_payload(relative_name)


def _clean_cell(value):
    if pd.isna(value):
        return ''
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return value


def _project_payload(project):
    weld_source = _latest_source(project, 'initialization', 'welds')
    prefab_source = _latest_source(project, 'library', 'weld-library')
    return {
        'id': project.id,
        'project_name': project.project_name,
        'pipe_segment': project.pipe_segment,
        'prefab_weld_count': project.prefab_weld_count,
        'completion_rate': '' if project.completion_rate is None else str(project.completion_rate),
        'start_date': project.start_date.isoformat() if project.start_date else '',
        'dataPath': f'database://project/{project.id}',
        'weldFile': _data_source_payload(weld_source, '焊口初始化数据.xlsx') if weld_source else None,
        'prefabWeldFile': _data_source_payload(prefab_source, '预制焊口库.xlsx') if prefab_source else None,
        'parserModels': _project_parser_models(project),
        **_project_data_status(project),
        'createdAt': project.created_at.isoformat() if project.created_at else '',
        'updatedAt': project.updated_at.isoformat() if project.updated_at else '',
    }


def _project_values(payload):
    return {
        'project_name': str(payload.get('project_name', '') or '').strip(),
        'pipe_segment': str(payload.get('pipe_segment', '') or '').strip(),
        'prefab_weld_count': _clean_project_int(payload.get('prefab_weld_count')),
        'completion_rate': _clean_project_decimal(payload.get('completion_rate')),
        'start_date': _clean_project_date(payload.get('start_date')),
    }


def _clean_project_decimal(value):
    if value is None or value == '':
        return None
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return value


def _clean_project_int(value):
    if value is None or value == '':
        return 0
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return value


def _clean_project_date(value):
    if value is None or value == '':
        return None
    text = str(value).strip()
    try:
        return datetime.strptime(text[:10], '%Y-%m-%d').date()
    except ValueError:
        return value


def _validate_project_values(values):
    if not values.get('project_name'):
        return '项目名称不能为空'
    if values.get('completion_rate') is not None and not isinstance(values.get('completion_rate'), Decimal):
        return '完成率必须是数字'
    if not isinstance(values.get('prefab_weld_count'), int):
        return '可预制焊口数必须是整数'
    if values.get('start_date') is not None and not hasattr(values.get('start_date'), 'isoformat'):
        return '开始日期格式应为 YYYY-MM-DD'
    return ''


def _safe_project_dir_name(project):
    raw_name = project.project_name
    cleaned = re.sub(r'[<>:"/\\|?*]+', '_', str(raw_name)).strip().strip('.')
    return cleaned


def _project_root(project):
    return PROJECT_DATA_ROOT / _safe_project_dir_name(project)


def _data_source_payload(source, default_name=''):
    if source is None:
        return None
    return {
        'name': source.display_name or default_name,
        'path': source.relative_path,
        'size': source.file_size,
        'updatedAt': source.file_updated_at,
    }


def _project_data_status(project):
    weld_source = _latest_source(project, 'initialization', 'welds') if project else None
    return {
        'hasInitializationData': weld_source is not None,
        'needsInitializationData': weld_source is None,
        'initializationHint': '' if weld_source else '当前项目暂无初始化数据，请先进行文件解析或上传焊口初始化数据。',
    }


def _project_parser_models(project):
    return {
        'idf': _project_parser_model_payload(project, 'idf', 'IDF模型数据.json'),
        'pcf': _project_parser_model_payload(project, 'pcf', ''),
    }


def _project_parser_model_payload(project, file_type, model_name):
    from pipecloud.models import ParserJob

    job = (
        ParserJob.objects
        .filter(project=project, file_type=file_type)
        .order_by('-updated_at', '-id')
        .first()
    )
    if not job:
        return {
            'fileType': file_type,
            'exists': False,
            'status': 'missing',
            'jobId': '',
            'message': '',
            'modelFile': None,
            'inputFileCount': 0,
            'resultCount': 0,
            'updatedAt': '',
        }

    result_count = len(job.results or [])
    input_file_count = len(job.input_files or [])
    model_file = _parser_job_model_file(job, model_name) if model_name else None
    return {
        'fileType': file_type,
        'exists': bool(model_file) if model_name else job.status == 'completed' and result_count > 0,
        'status': job.status,
        'jobId': job.job_id,
        'message': job.message,
        'current': job.current,
        'percent': job.percent,
        'total': job.total,
        'completed': job.completed,
        'failed': job.failed,
        'modelFile': model_file,
        'inputFileCount': input_file_count,
        'resultCount': result_count,
        'updatedAt': job.updated_at.isoformat(timespec='seconds') if job.updated_at else '',
    }


def _parser_job_model_file(job, model_name):
    candidate_paths = []
    for result in job.results or []:
        staged_path = result.get('stagedPath')
        if staged_path:
            candidate_paths.append((FILE_PARSER_ROOT / staged_path).resolve().parent / model_name)
    if job.batch_path:
        candidate_paths.append((FILE_PARSER_ROOT / job.batch_path / model_name).resolve())

    for path in candidate_paths:
        if path.exists() and path.is_file():
            stat = path.stat()
            return {
                'name': path.name,
                'path': _parser_relative_path(path),
                'size': stat.st_size,
                'updatedAt': datetime.fromtimestamp(stat.st_mtime).isoformat(timespec='seconds'),
            }
    return None


def _safe_upload_name(name):
    file_name = Path(str(name or '').replace('\\', '/').split('/')[-1]).name
    return file_name or f'upload-{datetime.now().strftime("%H%M%S")}'


def _parser_file_type(file_name):
    suffix = Path(file_name).suffix.lower()
    if suffix == '.idf':
        return 'idf'
    if suffix == '.pcf':
        return 'pcf'
    return ''


def _parser_download_url(file_path):
    relative_path = Path(file_path).resolve().relative_to(FILE_PARSER_ROOT.resolve())
    relative_text = str(relative_path).replace('\\', '/')
    return f'/api/pipecloud/file-parser/download/?path={quote(relative_text)}'


def _parser_relative_path(file_path):
    return str(Path(file_path).resolve().relative_to(FILE_PARSER_ROOT.resolve())).replace('\\', '/')


def _resolve_parser_file(relative_path):
    target_path = (FILE_PARSER_ROOT / (relative_path or '')).resolve()
    target_path.relative_to(FILE_PARSER_ROOT.resolve())
    if not target_path.exists() or not target_path.is_file():
        raise FileNotFoundError('待确认文件不存在')
    return target_path


def _parse_project_payload(request):
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, '请求内容不是有效 JSON'
    if not isinstance(payload, dict):
        return None, '项目数据无效'
    values = _project_values(payload)
    error = _validate_project_values(values)
    if error:
        return None, error
    return values, None


def _project_file_response():
    rows = []
    for project in Project.objects.all():
        rows.append({
            column['title']: getattr(project, column['field'])
            for column in PROJECT_COLUMNS
        })

    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        pd.DataFrame(rows, columns=[column['title'] for column in PROJECT_COLUMNS]).to_excel(
            writer,
            index=False,
            sheet_name='项目',
        )

    output.seek(0)
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = 'attachment; filename="projects.xlsx"'
    return response


def _project_or_error(project_id):
    try:
        return Project.objects.get(pk=project_id), ''
    except Project.DoesNotExist:
        return None, '项目不存在'


def _is_date_dir(path):
    return path.is_dir() and len(path.name) == 8 and path.name.isdigit()


def _is_date_value(value):
    return len(str(value)) == 8 and str(value).isdigit()


def _today_plan_date():
    return datetime.now().strftime('%Y%m%d')


def _plan_folder_date(folder_path):
    if _is_date_value(folder_path.name):
        return folder_path.name
    return datetime.fromtimestamp(folder_path.stat().st_mtime).strftime('%Y%m%d')


def _plan_record_payload(record):
    return {
        'id': record.id,
        'planKey': record.plan_key,
        'planName': record.plan_name,
        'planDate': record.plan_date,
        'planFolder': record.plan_folder,
        'name': record.plan_folder,
        'path': record.relative_path,
        'fileCount': record.file_count,
        'updatedAt': record.folder_updated_at,
        'files': record.files or [],
    }


def _sync_plan_records(project, plan_sources):
    ensure_project_tables(project)
    return None


def _plan_records_for_source(project, source):
    ensure_project_tables(project)
    with using_project_tables(project):
        return list(PlanRecord.objects.filter(project=project, plan_key=source['key']))


def _plan_records_by_date(records, selected_date):
    return [_plan_record_payload(record) for record in records if record.plan_date == selected_date]


def _plan_group_payload(records, today_date):
    today_records = sorted(
        [record for record in records if record.plan_date == today_date],
        key=lambda record: (-record.folder_updated_at, record.plan_folder),
    )
    future_records = sorted(
        [record for record in records if record.plan_date > today_date],
        key=lambda record: (record.plan_date, record.plan_folder),
    )
    history_records = sorted(
        [record for record in records if record.plan_date < today_date],
        key=lambda record: (record.plan_date, record.folder_updated_at),
        reverse=True,
    )
    return {
        'todayPlans': [_plan_record_payload(record) for record in today_records],
        'futurePlans': [_plan_record_payload(record) for record in future_records],
        'historyPlans': [_plan_record_payload(record) for record in history_records],
        'todayCount': len(today_records),
        'futureCount': len(future_records),
        'historyCount': len(history_records),
    }


def _plan_source_payload(project, source, selected_date=None):
    records = _plan_records_for_source(project, source)
    dates = sorted({record.plan_date for record in records}, reverse=True)
    selected_date = selected_date if selected_date in dates else (dates[0] if dates else '')
    plans = _plan_records_by_date(records, selected_date)

    return {
        'key': source['key'],
        'name': source['name'],
        'root': f'database://plan/{source["key"]}',
        'exists': bool(records),
        'dates': dates,
        'selectedDate': selected_date,
        'selectedPath': f'database://plan/{source["key"]}/{selected_date}' if selected_date else '',
        'plans': plans,
        'files': plans,
        'fileCount': len(plans),
        **_plan_group_payload(records, _today_plan_date()),
    }


def _plan_date_file_count(project, source, date):
    ensure_project_tables(project)
    with using_project_tables(project):
        return PlanRecord.objects.filter(project=project, plan_key=source['key'], plan_date=date).count()


def _resolve_plan_file(plan_key, plan_folder, file_name, plan_sources):
    source = plan_sources.get(plan_key)
    if source is None:
        return None, '未知计划类型'
    if not plan_folder or Path(plan_folder).name != plan_folder:
        return None, '计划文件夹无效'
    if not file_name or Path(file_name).name != file_name:
        return None, '文件名无效'

    return {
        'plan_key': plan_key,
        'plan_folder': plan_folder,
        'file_name': file_name,
        'source_key': f'{plan_key}:{plan_folder}:{file_name}',
    }, ''


def _plan_payload(project, plan_key, selected_date=None, plan_sources=None):
    plan_sources = plan_sources or PLAN_SOURCES
    if plan_key == 'all':
        sources = list(plan_sources.values())
    else:
        source = plan_sources.get(plan_key)
        if source is None:
            return None
        sources = [source]

    _sync_plan_records(project, plan_sources)
    source_payloads = [_plan_source_payload(project, source, selected_date) for source in sources]
    all_dates = sorted({date for source in source_payloads for date in source['dates']}, reverse=True)
    records_by_source_date = {
        source_payload['key']: {
            date: _plan_records_by_date(_plan_records_for_source(project, plan_sources[source_payload['key']]), date)
            for date in source_payload['dates']
        }
        for source_payload in source_payloads
    }
    timeline = [
        {
            'date': date,
            'plans': [
                {
                    'planKey': source['key'],
                    'planName': source['name'],
                    'fileCount': _plan_date_file_count(project, plan_sources[source['key']], date),
                    'available': date in source['dates'],
                    'records': records_by_source_date.get(source['key'], {}).get(date, []),
                }
                for source in source_payloads
            ],
        }
        for date in all_dates
    ]

    return {
        'key': plan_key,
        'name': '排产计划' if plan_key == 'all' else source_payloads[0]['name'],
        'selectedDate': selected_date or (all_dates[0] if all_dates else ''),
        'dates': all_dates,
        'sources': source_payloads,
        'timeline': timeline,
    }


def _source_payload_from_database(source, total=0, unit_column='单元号'):
    return {
        'path': source.relative_path if source else '',
        'exists': bool(source) or total > 0,
        'total': int(total),
        'unitColumn': unit_column if total else '',
        'units': {},
    }


def _unit_counts_from_queryset(queryset, source=None):
    units = {}
    total = 0
    for row in queryset.values('unit').annotate(count=Count('id')):
        unit = str(row.get('unit') or '').strip() or '未分单元'
        count = int(row.get('count') or 0)
        units[unit] = units.get(unit, 0) + count
        total += count
    payload = _source_payload_from_database(source, total)
    payload['units'] = units
    return payload


def _latest_source(project, source_type, source_key=None, display_name=None):
    ensure_project_tables(project)
    with using_project_tables(project):
        queryset = DataSourceFile.objects.filter(project=project, source_type=source_type)
        if source_key is not None:
            queryset = queryset.filter(source_key=source_key)
        if display_name is not None:
            queryset = queryset.filter(display_name=display_name)
        return queryset.order_by('-file_updated_at', '-id').first()


def _plan_primary_file_name(record):
    files = record.files or []
    primary_name = WELDING_PRIMARY_PLAN_FILE_NAME
    primary_stem = Path(primary_name).stem
    file_info = next((item for item in files if item.get('name') == primary_name), None)
    if file_info is None:
        file_info = next((item for item in files if str(item.get('name', '')).startswith(primary_stem)), None)
    if file_info is None:
        return ''
    return Path(file_info.get('name', '')).name


def _welding_dashboard_payload(project, data_root, force_refresh=False):
    source = _plan_sources(data_root)['welding']
    records = _plan_records_for_source(project, source)
    today_date = _today_plan_date()
    today_records = [record for record in records if record.plan_date == today_date]
    history_records = [record for record in records if record.plan_date != today_date]

    with using_project_tables(project):
        source_by_key = {
            source_file.source_key: source_file
            for source_file in DataSourceFile.objects.filter(
                project=project,
                source_type='plan',
                source_key__startswith='welding:',
            )
        }
        rows = []
        for record in records:
            file_name = _plan_primary_file_name(record)
            source_file = source_by_key.get(f'welding:{record.plan_folder}:{file_name}') if file_name else None
            queryset = WeldingPlanRow.objects.filter(project=project, source_file=source_file) if source_file else WeldingPlanRow.objects.none()
            total_rows = queryset.count()
            completed_rows = sum(1 for value in queryset.values_list('completed_flag', flat=True) if _truthy_text(value))
            rows.append({
                'planDate': record.plan_date,
                'planFolder': record.plan_folder,
                'fileName': file_name,
                'path': source_file.relative_path if source_file else record.relative_path,
                'totalRows': total_rows,
                'completedRows': completed_rows,
                'completionRate': _percentage(completed_rows, total_rows),
                'updatedAt': source_file.file_updated_at if source_file else record.folder_updated_at,
            })

    history_rows = [row for row in rows if row['planDate'] != today_date]
    today_rows = [row for row in rows if row['planDate'] == today_date]

    total_rows = sum(row['totalRows'] for row in rows)
    completed_rows = sum(row['completedRows'] for row in rows)
    history_total_rows = sum(row['totalRows'] for row in history_rows)
    history_completed_rows = sum(row['completedRows'] for row in history_rows)
    today_total_rows = sum(row['totalRows'] for row in today_rows)
    today_completed_rows = sum(row['completedRows'] for row in today_rows)

    payload = {
        'projectId': project.id,
        'projectName': project.project_name,
        'updatedAt': datetime.now().isoformat(timespec='seconds'),
        'todayDate': today_date,
        'planCount': len(records),
        'historyPlanCount': len(history_records),
        'todayPlanCount': len(today_records),
        'totalRows': total_rows,
        'completedRows': completed_rows,
        'completionRate': _percentage(completed_rows, total_rows),
        'historyTotalRows': history_total_rows,
        'historyCompletedRows': history_completed_rows,
        'historyCompletionRate': _percentage(history_completed_rows, history_total_rows),
        'todayTotalRows': today_total_rows,
        'todayCompletedRows': today_completed_rows,
        'todayCompletionRate': _percentage(today_completed_rows, today_total_rows),
        'recentPlans': rows[:8],
    }
    return payload


def _number_value(value, default=0.0):
    number = pd.to_numeric(value, errors='coerce')
    return float(number) if pd.notna(number) else default


def _parse_number_list(value):
    if isinstance(value, list):
        return [_number_value(item) for item in value if pd.notna(item)]

    if pd.isna(value) or str(value).strip() == '':
        return []

    text = str(value).strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [_number_value(item) for item in parsed if pd.notna(item)]
    except json.JSONDecodeError:
        pass

    numbers = []
    for part in text.replace('，', ',').replace(';', ',').replace('；', ',').split(','):
        part = part.strip()
        if part:
            numbers.append(_number_value(part))
    return numbers


def _text_value(row, column_name):
    if column_name not in row.index:
        return ''
    value = row.get(column_name)
    return '' if pd.isna(value) else str(value).strip()


def _cutting_pipe_payload(row):
    original_length = _number_value(row.get(CUTTING_COLUMNS['original_length']))
    if original_length <= 0:
        original_length = _number_value(row.get(CUTTING_COLUMNS['stock_qty']))
    remaining_length = _number_value(row.get(CUTTING_COLUMNS['remaining_length']))
    cut_lengths = _parse_number_list(row.get(CUTTING_COLUMNS['cut_lengths']))
    loss_lengths = _parse_number_list(row.get(CUTTING_COLUMNS['loss_lengths']))
    consumed_lengths = _parse_number_list(row.get(CUTTING_COLUMNS['consumed_lengths']))

    if len(consumed_lengths) != len(cut_lengths):
        consumed_lengths = [
            round(cut + (loss_lengths[index] if index < len(loss_lengths) else 0), 3)
            for index, cut in enumerate(cut_lengths)
        ]

    used_length = round(sum(consumed_lengths), 3)
    if remaining_length <= 0 and original_length > used_length:
        remaining_length = round(original_length - used_length, 3)

    segments = []
    cursor = 0.0
    for index, cut_length in enumerate(cut_lengths):
        consumed_length = consumed_lengths[index] if index < len(consumed_lengths) else cut_length
        loss_length = loss_lengths[index] if index < len(loss_lengths) else max(consumed_length - cut_length, 0)
        segment_length = max(float(consumed_length), 0)
        if segment_length <= 0:
            continue
        segments.append({
            'type': 'cut',
            'index': index + 1,
            'label': round(float(cut_length), 3),
            'length': round(float(cut_length), 3),
            'consumedLength': round(segment_length, 3),
            'lossLength': round(float(loss_length), 3),
            'start': round(cursor, 3),
            'percent': round(segment_length / original_length * 100, 4) if original_length > 0 else 0,
        })
        cursor = round(cursor + segment_length, 3)

    if remaining_length > 0:
        segments.append({
            'type': 'remaining',
            'index': None,
            'label': round(remaining_length, 3),
            'length': round(remaining_length, 3),
            'consumedLength': round(remaining_length, 3),
            'lossLength': 0,
            'start': round(cursor, 3),
            'percent': round(remaining_length / original_length * 100, 4) if original_length > 0 else 0,
        })

    return {
        'pipeNo': _text_value(row, CUTTING_COLUMNS['pipe_no']),
        'materialCode': _text_value(row, CUTTING_COLUMNS['material_code']),
        'description': _text_value(row, CUTTING_COLUMNS['description']),
        'heatNo': _text_value(row, CUTTING_COLUMNS['heat_no']),
        'originalLength': round(original_length, 3),
        'usedLength': used_length,
        'remainingLength': round(max(remaining_length, 0), 3),
        'utilization': round(used_length / original_length * 100, 1) if original_length > 0 else 0,
        'cutCount': len(cut_lengths),
        'segments': segments,
    }


def _row_payload(columns, values):
    padded_values = list(values or [])[:len(columns)]
    if len(padded_values) < len(columns):
        padded_values.extend([''] * (len(columns) - len(padded_values)))
    return {
        column: _clean_cell(value)
        for column, value in zip(columns, padded_values)
    }


def _read_excel_rows(file_path, sheet_name):
    workbook = load_workbook(file_path, read_only=True, data_only=True)
    try:
        sheets = workbook.sheetnames
        selected_sheet = sheet_name if sheet_name in sheets else sheets[0]
        worksheet = workbook[selected_sheet]

        rows_iter = worksheet.iter_rows(values_only=True)
        header = next(rows_iter, [])
        columns = [str(column or '') for column in header]
        rows = [_row_payload(columns, values) for values in rows_iter]
        return selected_sheet, sheets, len(rows), columns, rows
    finally:
        workbook.close()


def _percentage(numerator, denominator):
    denominator = int(denominator or 0)
    if denominator <= 0:
        return 0
    return round(int(numerator or 0) / denominator * 100, 2)


def _initialization_stats_payload(project, data_root, force_refresh=False):
    with using_project_tables(project):
        total_source = _latest_source(project, 'initialization', 'welds')
        library_source = _latest_source(project, 'library', 'weld-library')
        total_counts = _unit_counts_from_queryset(
            InitializationWeldRow.objects.filter(project=project),
            total_source,
        )
        prefab_counts = _unit_counts_from_queryset(
            WeldLibraryRow.objects.filter(project=project),
            library_source,
        )
        auto_counts = _unit_counts_from_queryset(
            WeldLibraryRow.objects.filter(project=project, welding_mode__contains='自动焊'),
            library_source,
        )

    units = sorted(set(total_counts['units']) | set(prefab_counts['units']) | set(auto_counts['units']))

    unit_rows = [
        {
            'unit': unit,
            'totalWeldCount': int(total_counts['units'].get(unit, 0)),
            'prefabWeldCount': int(prefab_counts['units'].get(unit, 0)),
            'autoWeldCount': int(auto_counts['units'].get(unit, 0)),
            'prefabRate': _percentage(prefab_counts['units'].get(unit, 0), total_counts['units'].get(unit, 0)),
            'autoRate': _percentage(auto_counts['units'].get(unit, 0), prefab_counts['units'].get(unit, 0)),
        }
        for unit in units
    ]

    payload = {
        'projectId': project.id,
        'projectName': project.project_name,
        'updatedAt': datetime.now().isoformat(timespec='seconds'),
        'sources': {
            'total': total_counts,
            'prefab': prefab_counts,
            'auto': auto_counts,
        },
        'totalWeldCount': total_counts['total'],
        'prefabWeldCount': prefab_counts['total'],
        'autoWeldCount': auto_counts['total'],
        'prefabRate': _percentage(prefab_counts['total'], total_counts['total']),
        'autoRate': _percentage(auto_counts['total'], prefab_counts['total']),
        'unitCount': len(unit_rows),
        'units': unit_rows,
    }
    return payload


def _truthy_text(value):
    return str(value if value is not None else '').strip().lower() in {
        'true',
        '1',
        'yes',
        'y',
        '完成',
        '已完成',
        'done',
        'finished',
    }


def _resolve_column(columns, canonical_name):
    aliases = [canonical_name, *WELD_COLUMN_ALIASES.get(canonical_name, [])]
    normalized = {str(column).strip(): column for column in columns}
    for alias in aliases:
        if alias in normalized:
            return normalized[alias]
    return ''


def _weld_key_series(dataframe):
    key_columns = [
        WELD_COLUMNS['weld_no_final'],
        WELD_COLUMNS['weld_no_start'],
        WELD_COLUMNS['pipeline'],
        WELD_COLUMNS['unit'],
        WELD_COLUMNS['diameter'],
    ]
    existing = [_resolve_column(dataframe.columns, column) for column in key_columns]
    existing = [column for column in existing if column]
    if not existing:
        seq_col = _resolve_column(dataframe.columns, WELD_COLUMNS['library_seq'])
        if seq_col:
            return dataframe[seq_col].astype('string').fillna('').str.strip()
        return pd.Series(range(len(dataframe)), index=dataframe.index).astype(str)

    key_df = dataframe[existing].copy()
    for column in existing:
        raw_series = key_df[column]
        numeric_series = pd.to_numeric(raw_series, errors='coerce')
        normalized = raw_series.astype('string')
        numeric_mask = numeric_series.notna()
        if numeric_mask.any():
            normalized.loc[numeric_mask] = numeric_series.loc[numeric_mask].map(lambda value: format(float(value), 'g'))
        key_df[column] = normalized.fillna('').str.strip()
    return key_df.agg('|'.join, axis=1)


def _source_dataframe(source, sheet_models, sheet_name=None):
    if source is None:
        return pd.DataFrame(), '', []
    selected_sheet, sheets, _, columns, rows = table_payload(source, sheet_models, sheet_name)
    return pd.DataFrame(rows, columns=columns), selected_sheet, sheets


def _update_project_weld_metrics(
    project,
    data_root,
    update_segment_count=True,
    update_prefab_weld_count=True,
    update_completion_rate=True,
):
    source = _latest_source(project, 'library', 'weld-library')
    dataframe, _, _ = _source_dataframe(source, {'*': WeldLibraryRow})
    if dataframe.empty:
        return False
    changed = False
    if update_segment_count:
        segment_col = _resolve_column(dataframe.columns, WELD_COLUMNS['segment_no'])
        segment_count = 0
        if segment_col:
            segment_count = int(dataframe[segment_col].fillna('').astype(str).str.strip().replace('', pd.NA).dropna().nunique())
        next_value = str(segment_count)
        if project.pipe_segment != next_value:
            project.pipe_segment = next_value
            changed = True

    if update_prefab_weld_count:
        next_count = int(len(dataframe))
        if project.prefab_weld_count != next_count:
            project.prefab_weld_count = next_count
            changed = True

    if update_completion_rate:
        completed_col = _resolve_column(dataframe.columns, WELD_COLUMNS['completed_flag'])
        total = len(dataframe)
        completed_count = int(dataframe[completed_col].map(_truthy_text).sum()) if completed_col and total else 0
        next_rate = Decimal('0.00') if total == 0 else Decimal(str(round(completed_count / total * 100, 2))).quantize(Decimal('0.01'))
        if project.completion_rate != next_rate:
            project.completion_rate = next_rate
            changed = True

    if changed:
        project.save(update_fields=['pipe_segment', 'prefab_weld_count', 'completion_rate', 'updated_at'])
    return changed


def _sync_completed_plan_rows_to_weld_library(project, rows):
    if not rows:
        return 0

    source = _latest_source(project, 'library', 'weld-library')
    library_df, selected_sheet, _ = _source_dataframe(source, {'*': WeldLibraryRow})
    if library_df.empty:
        return 0

    plan_df = pd.DataFrame(rows)
    plan_completed_col = _resolve_column(plan_df.columns, WELD_COLUMNS['completed_flag'])
    if not plan_completed_col:
        return 0

    library_completed_col = _resolve_column(library_df.columns, WELD_COLUMNS['completed_flag'])
    if not library_completed_col:
        library_completed_col = WELD_COLUMNS['completed_flag']
        library_df[library_completed_col] = False

    plan_df = plan_df.copy()
    plan_df['_key'] = _weld_key_series(plan_df)
    completion_map = (
        plan_df.loc[plan_df['_key'].astype(str).str.len() > 0]
        .drop_duplicates('_key', keep='last')
        .set_index('_key')[plan_completed_col]
        .map(_truthy_text)
        .to_dict()
    )
    if not completion_map:
        return 0

    library_df = library_df.copy()
    library_df['_key'] = _weld_key_series(library_df)
    matched_mask = library_df['_key'].isin(completion_map)
    changed_count = int(matched_mask.sum())
    if changed_count <= 0:
        return 0

    library_df.loc[matched_mask, library_completed_col] = library_df.loc[matched_mask, '_key'].map(completion_map)
    library_df = library_df.drop(columns=['_key'])
    replace_source_rows(
        project,
        'library',
        'weld-library',
        source.display_name if source else WELD_LIBRARY_FILE_NAME,
        source.relative_path if source else 'database://library/weld-library/预制焊口库.xlsx',
        {selected_sheet or 'Sheet1': {'columns': list(library_df.columns), 'rows': library_df.to_dict(orient='records')}},
        {'*': WeldLibraryRow},
    )
    return changed_count


def _stage_root(project, token):
    safe_token = str(token or '').strip()
    if not re.fullmatch(r'[0-9a-fA-F-]{32,36}', safe_token):
        raise ValueError('暂存令牌无效')
    return STAGED_PLAN_ROOT / _safe_project_dir_name(project) / safe_token


def _arrival_file_payload(file_path):
    stat = file_path.stat()
    return {
        'name': file_path.name,
        'path': _relative_path(file_path),
        'size': stat.st_size,
        'updatedAt': stat.st_mtime,
    }


def _arrival_rows_summary(rows):
    actual_qty_col = '实际到货数量'
    send_qty_col = '发货数量（米/根）'
    pipe_count_col = '实际到货支数'
    category_col = '材料分类'
    unit_col = '单位'

    total_qty = 0
    pipe_rows = 0
    fitting_rows = 0
    pipe_count = 0
    categories = {}

    for row in rows or []:
        qty = pd.to_numeric(row.get(actual_qty_col), errors='coerce')
        if pd.isna(qty) or float(qty) <= 0:
            qty = pd.to_numeric(row.get(send_qty_col), errors='coerce')
        if pd.notna(qty):
            total_qty += float(qty)

        category = str(row.get(category_col, '') or '').strip() or '未分类'
        unit = str(row.get(unit_col, '') or '').strip()
        name = str(row.get('名称', '') or '').strip()
        is_pipe = unit == '米' or name == '管子' or category == '直管'
        if is_pipe:
            pipe_rows += 1
            count = pd.to_numeric(row.get(pipe_count_col), errors='coerce')
            if pd.notna(count):
                pipe_count += int(count)
        else:
            fitting_rows += 1

        categories[category] = categories.get(category, 0) + 1

    return {
        'materialRows': len(rows or []),
        'pipeRows': pipe_rows,
        'fittingRows': fitting_rows,
        'pipeCount': pipe_count,
        'totalQuantity': round(total_qty, 3),
        'categories': [
            {'category': category, 'count': count}
            for category, count in sorted(categories.items(), key=lambda item: item[0])
        ],
    }


def _parse_library_save_payload(request):
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, '请求内容不是有效 JSON'

    columns = payload.get('columns')
    rows = payload.get('rows')
    if not isinstance(columns, list) or not columns or not all(isinstance(column, str) for column in columns):
        return None, '列定义无效'
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        return None, '表格数据无效'

    return {
        'sheet': payload.get('sheet') or None,
        'columns': columns,
        'rows': rows,
    }, None


def _welding_schedule_defaults():
    defaults = {
        'weldDate': datetime.now().strftime('%Y-%m-%d'),
        'targetDiameter': 260,
        'ordersPerDay': 3,
    }
    try:
        auto_weld_dir = PREFAB_ROOT / '焊接管理及排产' / '自动焊排产'
        for path in (PREFAB_ROOT, auto_weld_dir):
            if str(path) not in sys.path:
                sys.path.insert(0, str(path))
        from 焊接管理及排产.自动焊排产.auto_weld_schedule_config import EXTRACT
        defaults['targetDiameter'] = EXTRACT.get('target_diameter', defaults['targetDiameter'])
        defaults['ordersPerDay'] = EXTRACT.get('num_extractions', defaults['ordersPerDay'])
    except Exception:
        pass
    return defaults


def _future_schedule_defaults():
    return {
        **_welding_schedule_defaults(),
        'weldStartDate': (datetime.now().date() + timedelta(days=1)).strftime('%Y-%m-%d'),
        'maxDays': '',
        'dateMode': 'auto',
        'manualWeldDates': '',
        'skipHolidays': True,
        'holidayDates': '',
        'canceledWeekendDates': '',
        'cuttingLeadDays': 1,
    }


def _action_payload(action_key):
    action = ACTIONS[action_key]
    payload = {**action, 'key': action_key, 'script': _relative_path(action['script'])}
    if action_key == 'auto-weld-schedule':
        payload['defaults'] = _welding_schedule_defaults()
    if action_key == 'future-schedule':
        payload['defaults'] = _future_schedule_defaults()
    return payload


def _module_payload(module, data_root=DATA_ROOT, project=None):
    file_infos = [_database_module_file_info(project, file_name, data_root) for file_name in module['files']]
    return {
        **module,
        'actions': [_action_payload(action_key) for action_key in module['actions']],
        'files': file_infos,
        'readyCount': sum(1 for item in file_infos if item['exists']),
        'totalCount': len(file_infos),
    }


def _decode_process_output(output):
    if not output:
        return ''

    encodings = [
        'utf-8',
        'utf-8-sig',
        locale.getpreferredencoding(False),
        'gb18030',
        'gbk',
    ]
    for encoding in dict.fromkeys(item for item in encodings if item):
        try:
            return output.decode(encoding)
        except UnicodeDecodeError:
            continue
    return output.decode('utf-8', errors='replace')




__all__ = [name for name in globals() if not name.startswith('__')]
