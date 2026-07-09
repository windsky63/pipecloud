from django.http import JsonResponse
from django.views.decorators.http import require_GET

from pipecloud.models import WeldingPlanRow
from pipecloud.services.db_storage import clean_cell, model_field_labels
from pipecloud.services.project_tables import ensure_project_tables, using_project_tables

from .common import _project_bad_request, _request_project_context, _today_plan_date


def _clean_text(value):
    text = str(value or '').strip()
    return '' if text.lower() in {'nan', 'none', 'null'} else text


def _today_pipe_materials(rows):
    materials_by_unique = {}
    for row in rows:
        for side in (1, 2):
            unique_code = _clean_text(getattr(row, f'material_unique_{side}', ''))
            mark = _clean_text(getattr(row, f'material_mark_{side}', ''))
            unit_name = _clean_text(getattr(row, f'unit_name_{side}', ''))
            description = _clean_text(getattr(row, f'description_{side}', ''))
            if not unique_code:
                continue

            material = materials_by_unique.setdefault(unique_code, {
                'uniqueCode': unique_code,
                'materialCode': '',
                'materialMark': '',
                'quantity': '',
                'unitName': '',
                'paint': '',
                'description': '',
                'diameter': '',
                'wallThickness': '',
                'material': '',
            })
            values = {
                'materialCode': getattr(row, f'material_code_{side}', ''),
                'materialMark': mark,
                'quantity': getattr(row, f'quantity_{side}', ''),
                'unitName': unit_name,
                'paint': getattr(row, f'material_paint_{side}', ''),
                'description': description,
                'diameter': getattr(row, 'diameter', ''),
                'wallThickness': getattr(row, 'wall_thickness', ''),
                'material': getattr(row, 'material', ''),
            }
            for key, value in values.items():
                if not material[key]:
                    material[key] = _clean_text(value)
    return list(materials_by_unique.values())


def _number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _today_welding_plan(rows, today):
    order_numbers = []
    segment_numbers = set()
    pipeline_numbers = set()
    completed_count = 0
    diameter_total = 0.0
    for row in rows:
        order_no = _clean_text(getattr(row, 'weld_order_no', ''))
        if order_no:
            order_numbers.append(order_no)
        segment_no = _clean_text(getattr(row, 'segment_no', ''))
        if segment_no:
            segment_numbers.add(segment_no)
        pipeline = _clean_text(getattr(row, 'pipeline', ''))
        if pipeline:
            pipeline_numbers.add(pipeline)
        diameter_total += _number(getattr(row, 'diameter', 0))
        completed = _clean_text(getattr(row, 'completed_flag', '')).lower()
        if completed in {'true', '1', 'yes', 'y', '完成', '已完成', 'done', 'finished'}:
            completed_count += 1
    unique_orders = list(dict.fromkeys(order_numbers))
    labels = model_field_labels(WeldingPlanRow)
    sheets_by_name = {}
    for row in rows:
        sheet_name = _clean_text(getattr(row, 'sheet_name', '')) or 'Sheet1'
        sheet_rows = sheets_by_name.setdefault(sheet_name, [])
        sheet_rows.append({
            label: clean_cell(getattr(row, field_name, ''))
            for field_name, label in labels.items()
        })
    sheets = [
        {
            'name': sheet_name,
            'total': len(sheet_rows),
            'columns': list(labels.values()),
            'rows': sheet_rows,
        }
        for sheet_name, sheet_rows in sheets_by_name.items()
    ]
    return {
        'date': today,
        'available': bool(rows),
        'orderNumbers': unique_orders,
        'orderCount': len(unique_orders),
        'weldCount': len(rows),
        'completedCount': completed_count,
        'diameterTotal': round(diameter_total, 3),
        'segmentCount': len(segment_numbers),
        'pipelineCount': len(pipeline_numbers),
        'selectedSheet': sheets[0]['name'] if sheets else '',
        'sheets': sheets,
    }


@require_GET
def today_pipe_materials(request):
    project, _, error = _request_project_context(request, required=True)
    if error:
        return _project_bad_request(error)

    today = _today_plan_date()
    ensure_project_tables(project)
    with using_project_tables(project):
        rows = list(
            WeldingPlanRow.objects
            .filter(project=project, weld_date=today)
            .order_by('source_file_id', 'sheet_name', 'row_index')
        )
    materials = _today_pipe_materials(rows)
    return JsonResponse({
        'projectId': project.id,
        'projectName': project.project_name,
        'date': today,
        'total': len(materials),
        'materials': materials,
        'weldingPlan': _today_welding_plan(rows, today),
    }, json_dumps_params={'ensure_ascii': False})
