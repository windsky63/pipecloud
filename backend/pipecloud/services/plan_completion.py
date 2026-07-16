from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re

from django.db import transaction
from django.utils import timezone

from pipecloud.models import (
    AntiCorrosionMaterialOrderRow,
    DataSourceFile,
    FittingMaterialRow,
    MasterScheduleRow,
    MaterialMatchDetailRow,
    PipeMaterialRow,
    Project,
    ScheduledTaskRun,
    WeldLibraryRow,
    WeldStatusRow,
)
from pipecloud.services import prefab_database
from pipecloud.services.db_storage import PLAN_FILE_MODELS, _sync_weld_status_values
from pipecloud.services.project_tables import ensure_project_tables, using_project_tables


TASK_NAMES = {
    'anti-corrosion': 'sync_anti_corrosion_plan_completion',
    'cutting': 'sync_cutting_plan_completion',
    'welding': 'sync_welding_plan_completion',
}

STATUS_FIELDS = {
    'anti-corrosion': 'material_anti_corrosion_status',
    'cutting': 'material_cutting_status',
    'welding': 'completed_flag',
}

PLAN_LABELS = {
    'anti-corrosion': '防腐',
    'cutting': '下料',
    'welding': '焊接',
}

def _date_value(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return prefab_database.future_schedule._parse_schedule_date(value)


def _date_text(value):
    return prefab_database.future_schedule._date_text(_date_value(value))


def _number(value):
    if value in (None, ''):
        return Decimal('0')
    try:
        return Decimal(str(value).strip().replace(',', ''))
    except (InvalidOperation, ValueError):
        return Decimal('0')


def _truthy(value):
    return str(value if value is not None else '').strip().lower() in {
        'true',
        '1',
        'yes',
        'y',
        '完成',
        '已完成',
        'done',
        'finished',
        '是',
    }


def _normalized_key_part(value):
    text = str(value if value is not None else '').strip()
    if not text:
        return ''
    try:
        return format(float(text), 'g')
    except (TypeError, ValueError):
        return text


def _row_weld_key(row):
    return '|'.join(
        _normalized_key_part(getattr(row, field_name, ''))
        for field_name in ['weld_no_final', 'weld_no_start', 'pipeline', 'unit', 'diameter']
    )


def _plan_sources(project, plan_key, business_date=None):
    queryset = DataSourceFile.objects.filter(
        project=project,
        source_type='plan',
        source_key__startswith=f'{plan_key}:',
    ).order_by('source_key', 'id')
    if business_date is not None:
        queryset = queryset.filter(source_key__startswith=f'{plan_key}:{_date_text(business_date)}:')
    return queryset


def _source_rows(source):
    sheet_models = PLAN_FILE_MODELS.get(source.display_name)
    if not sheet_models:
        return []
    rows = []
    for sheet_name in source.sheet_names or []:
        model = sheet_models.get(sheet_name) or sheet_models.get('*')
        if model is None:
            continue
        field_columns = [
            (field.name, str(field.verbose_name))
            for field in model._meta.fields
            if field.name not in {
                'id',
                'project',
                'source_file',
                'sheet_name',
                'row_index',
                'created_at',
                'updated_at',
            }
        ]
        for item in model.objects.filter(source_file=source, sheet_name=sheet_name).order_by('row_index'):
            rows.append({
                label: getattr(item, field_name, '')
                for field_name, label in field_columns
            })
    return rows


def _sync_status_by_library_seq(project, status_field, status_by_seq):
    cleaned = {
        str(seq or '').strip(): _truthy(value)
        for seq, value in status_by_seq.items()
        if str(seq or '').strip()
    }
    if not cleaned:
        return 0, 0

    changed = 0
    master_updates = []
    for row in MasterScheduleRow.objects.filter(project=project, library_seq__in=cleaned.keys()):
        next_value = cleaned.get(row.library_seq, False)
        if getattr(row, status_field) != next_value:
            setattr(row, status_field, next_value)
            master_updates.append(row)
    if master_updates:
        MasterScheduleRow.objects.bulk_update(master_updates, [status_field, 'updated_at'], batch_size=500)
        changed += len(master_updates)

    changed_status = _sync_weld_status_values(project, [
        {
            'library_seq': library_seq,
            status_field: value,
        }
        for library_seq, value in cleaned.items()
    ])
    return changed, changed_status


def _sync_welding_library(project, status_by_seq):
    if not status_by_seq:
        return 0
    changed = []
    for row in WeldLibraryRow.objects.filter(project=project, library_seq__in=status_by_seq.keys()):
        next_value = bool(_truthy(status_by_seq.get(row.library_seq)))
        if row.completed_flag != next_value:
            row.completed_flag = next_value
            changed.append(row)
    if changed:
        WeldLibraryRow.objects.bulk_update(changed, ['completed_flag'], batch_size=500)
    total = WeldLibraryRow.objects.filter(project=project).count()
    completed = WeldLibraryRow.objects.filter(project=project, completed_flag=True).count()
    next_rate = Decimal('0.00')
    if total:
        next_rate = Decimal(str(round(completed / total * 100, 2))).quantize(Decimal('0.01'))
    if project.completion_rate != next_rate:
        project.completion_rate = next_rate
        project.save(update_fields=['completion_rate', 'updated_at'])
    return len(changed)


def _plan_status_by_seq(rows, status_field):
    seq_column = prefab_database.COLUMNS['library_seq']
    status_column = prefab_database.COLUMNS['completed_flag']
    if status_field == 'material_anti_corrosion_status':
        status_column = prefab_database.COLUMNS['material_anti_corrosion_status']
    elif status_field == 'material_cutting_status':
        status_column = prefab_database.COLUMNS['material_cutting_status']
    result = {}
    for row in rows:
        library_seq = str(row.get(seq_column) or '').strip()
        if not library_seq:
            continue
        value = row.get(status_column)
        if value in (None, '') and status_column != prefab_database.COLUMNS['completed_flag']:
            value = row.get(prefab_database.COLUMNS['completed_flag'])
        result[library_seq] = value
    return result


def _anti_corrosion_material_status_by_seq(project, business_date=None):
    queryset = AntiCorrosionMaterialOrderRow.objects.filter(project=project)
    if business_date is not None:
        queryset = queryset.filter(source_file__source_key__startswith=f'anti-corrosion:{_date_text(business_date)}:')
    completed = {}
    for row in queryset:
        if _number(row.commission_area) <= 0 or _number(row.commission_area) != _number(row.completed_area):
            continue
        for library_seq in re.split(r'[,，、]', str(row.related_library_seqs or '')):
            library_seq = library_seq.strip()
            if library_seq:
                completed[library_seq] = True
    return completed


def _qty_text(value):
    value = max(Decimal(str(value)), Decimal('0'))
    return format(value.quantize(Decimal('0.001')).normalize(), 'f')


def _sync_anti_corrosion_material_inventory(project, business_date=None):
    queryset = AntiCorrosionMaterialOrderRow.objects.filter(project=project)
    if business_date is not None:
        queryset = queryset.filter(
            source_file__source_key__startswith=f'anti-corrosion:{_date_text(business_date)}:'
        )
    completed_rows = [
        row for row in queryset
        if _number(row.commission_area) > 0 and _number(row.commission_area) == _number(row.completed_area)
    ]
    pipe_resources = {
        str(row.matched_resource or '').strip()
        for row in completed_rows
        if '管子' in str(row.material_type or '') and str(row.matched_resource or '').strip()
    }
    fitting_completed = {}
    for row in completed_rows:
        if '管件法兰' not in str(row.material_type or ''):
            continue
        code = str(row.material_code or '').strip()
        if code:
            fitting_completed[code] = fitting_completed.get(code, Decimal('0')) + _number(row.commission_qty)

    changed = 0
    pipe_updates = []
    for row in PipeMaterialRow.objects.filter(
        project=project,
        source_file__source_key='anti-pipe-library',
        pipe_no__in=pipe_resources,
    ):
        uncoated_locked = _number(row.uncoated_locked_qty)
        if uncoated_locked <= 0 and _number(row.coated_locked_qty) <= 0:
            uncoated_locked = _number(row.locked_qty)
        coated_locked = _number(row.coated_locked_qty) + uncoated_locked
        available = max(_number(row.stock_qty) - _number(row.locked_qty) - _number(row.used_qty), Decimal('0'))
        next_stock = _qty_text(available)
        if (
            row.anti_corrosion_status != '已完成'
            or row.anti_corrosion_stock_qty != next_stock
            or row.coated_locked_qty != _qty_text(coated_locked)
            or row.uncoated_locked_qty != '0'
        ):
            row.anti_corrosion_status = '已完成'
            row.anti_corrosion_stock_qty = next_stock
            row.coated_locked_qty = _qty_text(coated_locked)
            row.uncoated_locked_qty = '0'
            pipe_updates.append(row)
    if pipe_updates:
        PipeMaterialRow.objects.bulk_update(
            pipe_updates,
            [
                'anti_corrosion_status', 'anti_corrosion_stock_qty',
                'coated_locked_qty', 'uncoated_locked_qty', 'updated_at',
            ],
            batch_size=500,
        )
        changed += len(pipe_updates)

    fitting_updates = []
    for row in FittingMaterialRow.objects.filter(
        project=project,
        source_file__source_key='anti-fitting-library',
        material_code__in=fitting_completed.keys(),
    ):
        completed_qty = fitting_completed[row.material_code]
        uncoated_locked = _number(row.uncoated_locked_qty)
        if uncoated_locked <= 0 and _number(row.coated_locked_qty) <= 0:
            uncoated_locked = _number(row.locked_qty)
        converted = min(uncoated_locked, completed_qty)
        next_coated_locked = _number(row.coated_locked_qty) + converted
        next_uncoated_locked = uncoated_locked - converted
        next_stock = _number(row.anti_corrosion_stock_qty)
        if _number(row.locked_qty) <= 0:
            next_stock = min(_number(row.stock_qty), completed_qty)
        if (
            row.anti_corrosion_stock_qty != _qty_text(next_stock)
            or row.coated_locked_qty != _qty_text(next_coated_locked)
            or row.uncoated_locked_qty != _qty_text(next_uncoated_locked)
        ):
            row.anti_corrosion_stock_qty = _qty_text(next_stock)
            row.coated_locked_qty = _qty_text(next_coated_locked)
            row.uncoated_locked_qty = _qty_text(next_uncoated_locked)
            fitting_updates.append(row)
    if fitting_updates:
        FittingMaterialRow.objects.bulk_update(
            fitting_updates,
            ['anti_corrosion_stock_qty', 'coated_locked_qty', 'uncoated_locked_qty', 'updated_at'],
            batch_size=500,
        )
        changed += len(fitting_updates)
    return changed


def _sync_welded_material_usage(project, status_by_seq):
    requested = {
        str(seq or '').strip(): _truthy(value)
        for seq, value in status_by_seq.items()
        if str(seq or '').strip()
    }
    if not requested:
        return 0
    current = {
        row.library_seq: row
        for row in WeldStatusRow.objects.filter(project=project, library_seq__in=requested.keys())
    }
    completed_seqs = {
        seq for seq, completed in requested.items()
        if completed and not bool(current.get(seq) and current[seq].completed_flag)
    }
    if not completed_seqs:
        return 0
    anti_ready_seqs = {
        seq for seq in completed_seqs
        if bool(current.get(seq) and current[seq].material_anti_corrosion_status)
    }
    details = MaterialMatchDetailRow.objects.filter(
        project=project,
        source_file__source_key='material-locking',
        library_seq__in=completed_seqs,
        match_result='可预排产',
    )
    changed = 0
    for detail in details:
        material_type = str(detail.material_type or '')
        is_anti = material_type.startswith('防腐')
        if is_anti and detail.library_seq not in anti_ready_seqs:
            continue
        quantity = _number(detail.matched_qty)
        if '管子' in material_type:
            match = {
                'project': project,
                'source_file__source_key': 'anti-pipe-library' if is_anti else 'pipe-library',
                'pipe_no': str(detail.matched_inventory_key or '').strip(),
            }
            row = PipeMaterialRow.objects.filter(**match).first()
            if row is None:
                continue
            consumed_match = re.search(r'占用\s*([0-9]+(?:\.[0-9]+)?)\s*米', str(detail.match_note or ''))
            if consumed_match:
                quantity = _number(consumed_match.group(1))
        elif '管件法兰' in material_type:
            match = {
                'project': project,
                'source_file__source_key': 'anti-fitting-library' if is_anti else 'fitting-library',
                'material_code': str(detail.material_code or '').strip(),
            }
            row = FittingMaterialRow.objects.filter(**match).first()
            if row is None:
                continue
        else:
            continue
        movable = min(
            _number(row.coated_locked_qty) if is_anti else _number(row.locked_qty),
            quantity,
        )
        if movable <= 0:
            continue
        row.locked_qty = _qty_text(_number(row.locked_qty) - movable)
        update_fields = ['locked_qty', 'used_qty', 'updated_at']
        if is_anti:
            row.coated_locked_qty = _qty_text(_number(row.coated_locked_qty) - movable)
            update_fields.append('coated_locked_qty')
        row.used_qty = _qty_text(_number(row.used_qty) + movable)
        row.save(update_fields=update_fields)
        changed += 1
    return changed


def sync_project_plan_completion(project, plan_key, business_date=None):
    if plan_key not in TASK_NAMES:
        raise ValueError(f'未知同步任务：{plan_key}')
    ensure_project_tables(project)
    with using_project_tables(project), transaction.atomic():
        status_field = STATUS_FIELDS[plan_key]
        status_by_seq = {}
        sources = list(_plan_sources(project, plan_key, business_date=business_date))
        for source in sources:
            status_by_seq.update(_plan_status_by_seq(_source_rows(source), status_field))
        if plan_key == 'anti-corrosion':
            status_by_seq.update(_anti_corrosion_material_status_by_seq(project, business_date=business_date))

        changed_material = 0
        if plan_key == 'anti-corrosion':
            changed_material = _sync_anti_corrosion_material_inventory(project, business_date=business_date)
        elif plan_key == 'welding':
            changed_material = _sync_welded_material_usage(project, status_by_seq)
        changed_master, changed_status = _sync_status_by_library_seq(project, status_field, status_by_seq)
        changed_library = _sync_welding_library(project, status_by_seq) if plan_key == 'welding' else 0
        completed_count = sum(1 for value in status_by_seq.values() if _truthy(value))
        return {
            'planKey': plan_key,
            'planName': PLAN_LABELS[plan_key],
            'sourceCount': len(sources),
            'matchedCount': len(status_by_seq),
            'completedCount': completed_count,
            'changedMasterRows': changed_master,
            'changedLibraryRows': changed_library,
            'changedStatusRows': changed_status,
            'changedMaterialRows': changed_material,
            'updatedCount': changed_status,
        }


def execute_project_completion_sync(project, plan_key, business_date=None, force=False):
    business_value = _date_value(business_date or timezone.localdate())
    ensure_project_tables(project)
    with using_project_tables(project), transaction.atomic():
        Project.objects.select_for_update().get(pk=project.pk)
        task_run, _ = ScheduledTaskRun.objects.select_for_update().get_or_create(
            project=project,
            task_name=TASK_NAMES[plan_key],
            business_date=business_value,
            defaults={'status': 'running'},
        )
        if task_run.status == 'succeeded' and not force:
            return {
                **(task_run.stats or {}),
                'alreadyExecuted': True,
            }
        task_run.status = 'running'
        task_run.stats = {}
        task_run.error_message = ''
        task_run.finished_at = None
        task_run.save(update_fields=['status', 'stats', 'error_message', 'finished_at'])

    try:
        stats = sync_project_plan_completion(project, plan_key, business_date=business_value)
        with using_project_tables(project):
            task_run.status = 'succeeded'
            task_run.stats = stats
            task_run.error_message = ''
            task_run.finished_at = timezone.now()
            task_run.save(update_fields=['status', 'stats', 'error_message', 'finished_at'])
        return stats
    except Exception as error:
        with using_project_tables(project):
            ScheduledTaskRun.objects.filter(pk=task_run.pk).update(
                status='failed',
                error_message=str(error),
                finished_at=timezone.now(),
            )
        raise


def execute_all_completion_syncs(plan_key, business_date=None, project_id=None, force=False):
    projects = Project.objects.order_by('id')
    if project_id:
        projects = projects.filter(pk=project_id)
    results = []
    for project in projects:
        try:
            stats = execute_project_completion_sync(
                project,
                plan_key,
                business_date=business_date,
                force=force,
            )
            results.append({
                'projectId': project.id,
                'projectName': project.project_name,
                **stats,
            })
        except Exception as error:
            results.append({
                'projectId': project.id,
                'projectName': project.project_name,
                'planKey': plan_key,
                'planName': PLAN_LABELS.get(plan_key, plan_key),
                'error': str(error),
            })
    return results
