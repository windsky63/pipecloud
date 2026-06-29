import json
import time
from pathlib import Path

from django.db import models
from django.db import transaction
from openpyxl import load_workbook

from pipecloud.models import (
    ArrivalMaterialRow,
    ArrivalOrderRow,
    DataSourceFile,
    FittingMaterialRow,
    InitializationWeldRow,
    MaterialMatchDetailRow,
    PipeMaterialRow,
    WeldingPlanRow,
    WeldLibraryRow,
    WeldPreScheduleRow,
)
from pipecloud.services.project_tables import ensure_project_tables, using_project_tables


SYSTEM_FIELDS = {
    'id',
    'project',
    'source_file',
    'sheet_name',
    'row_index',
    'created_at',
    'updated_at',
}

COLUMN_ALIASES = {
    '单元号(必填)': 'unit',
    '管线号(必填)': 'pipeline',
    '预制组件': 'segment_no',
    '英制': 'diameter',
    '英制尺寸': 'diameter',
    '焊接方法': 'weld_method',
    '焊接方式': 'welding_mode',
    '材料代码（NCC文本）': 'material_code_ncc',
    '材料代码': 'material_code',
    '库存数量（米）': 'stock_qty',
    '发货数量（米/根）': 'shipment_qty',
}

TRUE_VALUES = {'1', 'true', 't', 'yes', 'y', '是', '已完成', '完成'}
FALSE_VALUES = {'0', 'false', 'f', 'no', 'n', '否', '未完成', '未', ''}


def model_column_map(model):
    mapping = {}
    model_field_names = {
        field.name
        for field in model._meta.fields
        if field.name not in SYSTEM_FIELDS
    }
    for field in model._meta.fields:
        if field.name in SYSTEM_FIELDS:
            continue
        label = str(field.verbose_name)
        mapping[label] = field.name
    mapping.update({key: value for key, value in COLUMN_ALIASES.items() if value in model_field_names})
    return mapping


def model_columns(model):
    return [
        str(field.verbose_name)
        for field in model._meta.fields
        if field.name not in SYSTEM_FIELDS
    ]


def model_field_labels(model):
    return {
        field.name: str(field.verbose_name)
        for field in model._meta.fields
        if field.name not in SYSTEM_FIELDS
    }


def clean_cell(value):
    if value is None:
        return ''
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return str(value)


def coerce_boolean(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in TRUE_VALUES:
        return True
    if text in FALSE_VALUES:
        return False
    return bool(text)


def coerce_model_value(field, value):
    if isinstance(field, models.BooleanField):
        return coerce_boolean(value)
    return clean_cell(value)


def normalize_json_value(value, fallback):
    if value is None or value == '':
        return fallback
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return fallback
        return parsed
    return value


def row_values(columns, values):
    padded = list(values or [])[:len(columns)]
    if len(padded) < len(columns):
        padded.extend([''] * (len(columns) - len(padded)))
    return {column: clean_cell(value) for column, value in zip(columns, padded)}


def relative_path(path, backend_dir):
    try:
        return str(Path(path).resolve().relative_to(Path(backend_dir).resolve())).replace('\\', '/')
    except ValueError:
        return str(path).replace('\\', '/')


def read_workbook_rows(file_path):
    workbook = load_workbook(file_path, read_only=True, data_only=True)
    try:
        payload = {}
        for sheet_name in workbook.sheetnames:
            worksheet = workbook[sheet_name]
            rows_iter = worksheet.iter_rows(values_only=True)
            header = next(rows_iter, [])
            columns = [str(column or '') for column in header]
            rows = [row_values(columns, values) for values in rows_iter]
            payload[sheet_name] = {'columns': columns, 'rows': rows}
        return payload
    finally:
        workbook.close()


INITIALIZATION_REQUIRED_FIELDS = {
    'unit',
    'pipeline',
    'segment_no',
    'weld_no_start',
    'weld_no_final',
    'diameter',
    'wall_thickness',
    'material',
    'joint_type',
}


def _source_column_mapping(model, columns):
    column_map = model_column_map(model)
    mapping = {}
    aliases = []
    for column in columns:
        source_label = str(column or '').strip()
        field_name = column_map.get(source_label)
        if not field_name or field_name in mapping:
            continue
        target_label = model_field_labels(model).get(field_name, source_label)
        mapping[field_name] = source_label
        if source_label != target_label:
            aliases.append({
                'source': source_label,
                'target': target_label,
                'field': field_name,
            })
    return mapping, aliases


def normalize_rows_for_model(model, columns, rows):
    field_labels = model_field_labels(model)
    source_mapping, aliases = _source_column_mapping(model, columns)
    normalized_columns = list(field_labels.values())
    normalized_rows = []
    for row in rows:
        normalized_row = {}
        for field_name, label in field_labels.items():
            source_column = source_mapping.get(field_name)
            normalized_row[label] = row.get(source_column, '') if source_column else ''
        normalized_rows.append(normalized_row)
    missing_fields = [
        {'field': field_name, 'column': label}
        for field_name, label in field_labels.items()
        if field_name not in source_mapping
    ]
    return normalized_columns, normalized_rows, aliases, missing_fields, source_mapping


def validate_normalized_rows(model, rows, source_mapping, required_fields):
    field_labels = model_field_labels(model)
    required = [field_name for field_name in required_fields if field_name in field_labels]
    missing_required = [
        {'field': field_name, 'column': field_labels[field_name]}
        for field_name in required
        if field_name not in source_mapping
    ]
    invalid_rows = []
    for index, row in enumerate(rows, start=1):
        empty_columns = [
            field_labels[field_name]
            for field_name in required
            if not str(row.get(field_labels[field_name], '') or '').strip()
        ]
        if empty_columns:
            invalid_rows.append({
                'rowIndex': index,
                'missingColumns': empty_columns,
            })
        if len(invalid_rows) >= 20:
            break
    return missing_required, invalid_rows


def standardize_workbook_payload(workbook_payload, sheet_models, required_fields=None):
    required_fields = set(required_fields or [])
    normalized_payload = {}
    sheet_summaries = []
    can_import = True
    for sheet_name, payload in workbook_payload.items():
        model = sheet_models.get(sheet_name) or sheet_models.get('*')
        if model is None:
            normalized_payload[sheet_name] = payload
            continue

        columns, rows, aliases, missing_fields, source_mapping = normalize_rows_for_model(
            model,
            payload.get('columns') or [],
            payload.get('rows') or [],
        )
        missing_required, invalid_rows = validate_normalized_rows(model, rows, source_mapping, required_fields)
        if missing_required:
            can_import = False
        normalized_payload[sheet_name] = {'columns': columns, 'rows': rows}
        sheet_summaries.append({
            'sheet': sheet_name,
            'rowCount': len(rows),
            'sourceColumnCount': len(payload.get('columns') or []),
            'standardColumnCount': len(columns),
            'aliasMappings': aliases,
            'missingFields': missing_fields,
            'missingRequiredFields': missing_required,
            'invalidRows': invalid_rows,
            'canImport': not missing_required and not invalid_rows,
        })
    return normalized_payload, {
        'standardized': True,
        'canImport': can_import,
        'sheets': sheet_summaries,
    }


def initialization_preview_payload(file_path, sheet_name=None, limit=20):
    workbook_payload = read_workbook_rows(file_path)
    normalized_payload, validation = standardize_workbook_payload(
        workbook_payload,
        INITIALIZATION_MODELS,
        INITIALIZATION_REQUIRED_FIELDS,
    )
    sheets = list(normalized_payload.keys())
    selected_sheet = sheet_name if sheet_name in sheets else (sheets[0] if sheets else '')
    selected_payload = normalized_payload.get(selected_sheet) or {'columns': [], 'rows': []}
    rows = selected_payload.get('rows') or []
    return {
        'sheet': selected_sheet,
        'sheets': sheets,
        'total': len(rows),
        'columns': selected_payload.get('columns') or [],
        'rows': rows[:limit],
        'previewLimit': limit,
        'normalization': validation,
    }


def workbook_preview_payload(file_path, sheet_name=None, limit=20):
    workbook_payload = read_workbook_rows(file_path)
    sheets = list(workbook_payload.keys())
    selected_sheet = sheet_name if sheet_name in sheets else (sheets[0] if sheets else '')
    selected_payload = workbook_payload.get(selected_sheet) or {'columns': [], 'rows': []}
    rows = selected_payload.get('rows') or []
    return {
        'sheet': selected_sheet,
        'sheets': sheets,
        'total': len(rows),
        'columns': selected_payload.get('columns') or [],
        'rows': rows[:limit],
        'previewLimit': limit,
        'normalization': {
            'standardized': False,
            'canImport': True,
            'sheets': [],
        },
    }


def source_signature(file_path):
    stat = Path(file_path).stat()
    return int(stat.st_size), float(stat.st_mtime)


def upsert_source_file(project, source_type, source_key, file_path, backend_dir, workbook_payload):
    size, updated_at = source_signature(file_path)
    source, _ = DataSourceFile.objects.update_or_create(
        project=project,
        source_type=source_type,
        source_key=source_key,
        relative_path=relative_path(file_path, backend_dir),
        defaults={
            'display_name': Path(file_path).name,
            'file_size': size,
            'file_updated_at': updated_at,
            'sheet_names': list(workbook_payload.keys()),
            'sheet_columns': {
                sheet_name: sheet_payload['columns']
                for sheet_name, sheet_payload in workbook_payload.items()
            },
        },
    )
    return source


def upsert_virtual_source_file(project, source_type, source_key, display_name, relative_path_value, workbook_payload):
    source, _ = DataSourceFile.objects.update_or_create(
        project=project,
        source_type=source_type,
        source_key=source_key,
        relative_path=str(relative_path_value).replace('\\', '/'),
        defaults={
            'display_name': display_name,
            'file_size': 0,
            'file_updated_at': time.time(),
            'sheet_names': list(workbook_payload.keys()),
            'sheet_columns': {
                sheet_name: sheet_payload['columns']
                for sheet_name, sheet_payload in workbook_payload.items()
            },
        },
    )
    return source


def dataframe_payload(dataframe):
    if dataframe is None:
        columns = []
        rows = []
    else:
        normalized = dataframe.fillna('').copy()
        columns = [str(column) for column in normalized.columns]
        rows = [
            {column: clean_cell(row.get(column, '')) for column in columns}
            for row in normalized.to_dict(orient='records')
        ]
    return {'columns': columns, 'rows': rows}


def normalize_workbook_payload_for_models(workbook_payload, sheet_models):
    normalized_payload = {}
    for sheet_name, payload in workbook_payload.items():
        model = sheet_models.get(sheet_name) or sheet_models.get('*')
        if model is None:
            normalized_payload[sheet_name] = payload
            continue
        columns = payload.get('columns') or []
        rows = payload.get('rows') or []
        normalized_columns, normalized_rows, _, _, _ = normalize_rows_for_model(model, columns, rows)
        normalized_payload[sheet_name] = {
            'columns': normalized_columns,
            'rows': normalized_rows,
        }
    return normalized_payload


def sync_table_payload(project, source_type, source_key, display_name, relative_path_value, workbook_payload, sheet_models):
    ensure_project_tables(project)
    with using_project_tables(project), transaction.atomic():
        workbook_payload = normalize_workbook_payload_for_models(workbook_payload, sheet_models)
        source = upsert_virtual_source_file(
            project,
            source_type,
            source_key,
            display_name,
            relative_path_value,
            workbook_payload,
        )
        for model in set(sheet_models.values()):
            if model is not None:
                model.objects.filter(project=project, source_file=source).delete()
        for sheet_name, payload in workbook_payload.items():
            model = sheet_models.get(sheet_name) or sheet_models.get('*')
            if model is None:
                continue
            sync_rows_for_model(project, source, model, sheet_name, payload['rows'])
        return source


def sync_dataframes(project, source_type, source_key, display_name, relative_path_value, sheet_dataframes, sheet_models):
    workbook_payload = {
        str(sheet_name): dataframe_payload(dataframe)
        for sheet_name, dataframe in sheet_dataframes.items()
    }
    return sync_table_payload(project, source_type, source_key, display_name, relative_path_value, workbook_payload, sheet_models)


def source_is_current(source, file_path):
    if source is None or not Path(file_path).exists():
        return False
    size, updated_at = source_signature(file_path)
    return source.file_size == size and source.file_updated_at == updated_at


def source_for_file(project, source_type, source_key, file_path, backend_dir):
    return DataSourceFile.objects.filter(
        project=project,
        source_type=source_type,
        source_key=source_key,
        relative_path=relative_path(file_path, backend_dir),
    ).first()


def sync_rows_for_model(project, source, model, sheet_name, rows):
    mapping = model_column_map(model)
    model_fields = {
        field.name: field
        for field in model._meta.fields
        if field.name not in SYSTEM_FIELDS
    }
    model.objects.filter(project=project, source_file=source, sheet_name=sheet_name).delete()
    instances = []
    for index, row in enumerate(rows, start=1):
        values = {
            field_name: False if isinstance(field, models.BooleanField) else ''
            for field_name, field in model_fields.items()
        }
        for column, field_name in mapping.items():
            if field_name in SYSTEM_FIELDS or column not in row:
                continue
            field = model_fields.get(field_name)
            if field is None:
                continue
            value = coerce_model_value(field, row.get(column, ''))
            if isinstance(field, models.BooleanField):
                values[field_name] = value
            elif value or not values.get(field_name):
                values[field_name] = value
        instances.append(model(
            project=project,
            source_file=source,
            sheet_name=sheet_name,
            row_index=index,
            **values,
        ))
    if instances:
        model.objects.bulk_create(instances, batch_size=500)


def sync_excel_table(project, file_path, backend_dir, source_type, source_key, sheet_models, force=False):
    ensure_project_tables(project)
    file_path = Path(file_path)
    with using_project_tables(project):
        source = source_for_file(project, source_type, source_key, file_path, backend_dir)
        if not force and source_is_current(source, file_path):
            return source

        workbook_payload = read_workbook_rows(file_path)
        if source_type == 'initialization':
            workbook_payload, validation = standardize_workbook_payload(
                workbook_payload,
                sheet_models,
                INITIALIZATION_REQUIRED_FIELDS,
            )
            if not validation.get('canImport'):
                raise ValueError('初始化数据标准化校验未通过，存在缺失的关键字段或必填值')
        with transaction.atomic():
            source = upsert_source_file(project, source_type, source_key, file_path, backend_dir, workbook_payload)
            for sheet_name, payload in workbook_payload.items():
                model = sheet_models.get(sheet_name) or sheet_models.get('*')
                if model is None:
                    continue
                sync_rows_for_model(project, source, model, sheet_name, payload['rows'])
        return source


def queryset_rows(source, model, sheet_name):
    field_columns = [
        (field.name, str(field.verbose_name))
        for field in model._meta.fields
        if field.name not in SYSTEM_FIELDS
    ]
    sheet_columns = normalize_json_value(source.sheet_columns, {})
    if not isinstance(sheet_columns, dict):
        sheet_columns = {}
    columns = sheet_columns.get(sheet_name) or [column for _, column in field_columns]
    label_to_field = {label: name for name, label in field_columns}
    rows = []
    for item in model.objects.filter(source_file=source, sheet_name=sheet_name).order_by('row_index'):
        rows.append({
            column: getattr(item, label_to_field.get(column, ''), '')
            for column in columns
        })
    return columns, rows


def table_payload(source, sheet_models, sheet_name=None):
    with using_project_tables(source.project_id):
        sheets = normalize_json_value(source.sheet_names, [])
        if not isinstance(sheets, list):
            sheets = []
        selected_sheet = sheet_name if sheet_name in sheets else (sheets[0] if sheets else '')
        model = sheet_models.get(selected_sheet) or sheet_models.get('*')
        if not selected_sheet or model is None:
            return selected_sheet, sheets, 0, [], []
        columns, rows = queryset_rows(source, model, selected_sheet)
        return selected_sheet, sheets, len(rows), columns, rows


def latest_source(project, source_type, source_key=None, source_key_prefix=None, display_name=None):
    ensure_project_tables(project)
    with using_project_tables(project):
        queryset = DataSourceFile.objects.filter(project=project, source_type=source_type)
        if source_key:
            queryset = queryset.filter(source_key=source_key)
        if source_key_prefix:
            queryset = queryset.filter(source_key__startswith=source_key_prefix)
        if display_name:
            queryset = queryset.filter(display_name=display_name)
        return queryset.order_by('-file_updated_at', '-id').first()


def replace_source_rows(project, source_type, source_key, display_name, relative_path_value, workbook_payload, sheet_models):
    ensure_project_tables(project)
    with using_project_tables(project), transaction.atomic():
        DataSourceFile.objects.filter(
            project=project,
            source_type=source_type,
            source_key=source_key,
        ).delete()
    return sync_table_payload(
        project,
        source_type,
        source_key,
        display_name,
        relative_path_value,
        workbook_payload,
        sheet_models,
    )


def replace_source_with_workbook(project, source_type, source_key, display_name, relative_path_value, file_path, sheet_models):
    workbook_payload = read_workbook_rows(file_path)
    if source_type == 'initialization':
        workbook_payload, validation = standardize_workbook_payload(
            workbook_payload,
            sheet_models,
            INITIALIZATION_REQUIRED_FIELDS,
        )
        if not validation.get('canImport'):
            raise ValueError('初始化数据标准化校验未通过，存在缺失的关键字段或必填值')
    return replace_source_rows(
        project,
        source_type,
        source_key,
        display_name,
        relative_path_value,
        workbook_payload,
        sheet_models,
    )


def source_payload(source, sheet_models, sheet_name=None):
    if source is None:
        return '', [], 0, [], []
    return table_payload(source, sheet_models, sheet_name)


LIBRARY_MODELS = {
    'weld-library': {'*': WeldLibraryRow},
    'pipe-library': {'*': PipeMaterialRow},
    'anti-pipe-library': {'*': PipeMaterialRow},
    'pending-anti-pipe-library': {'*': PipeMaterialRow},
    'fitting-library': {'*': FittingMaterialRow},
    'anti-fitting-library': {'*': FittingMaterialRow},
    'pending-anti-fitting-library': {'*': FittingMaterialRow},
}

PRE_SCHEDULE_MODELS = {
    '预排产匹配结果': WeldPreScheduleRow,
    '材料匹配明细': MaterialMatchDetailRow,
}

ARRIVAL_MODELS = {
    'Sheet1': ArrivalOrderRow,
    'Sheet2': ArrivalMaterialRow,
}

INITIALIZATION_MODELS = {'*': InitializationWeldRow}

PLAN_FILE_MODELS = {
    '管段焊口表.xlsx': {'*': WeldingPlanRow},
}
