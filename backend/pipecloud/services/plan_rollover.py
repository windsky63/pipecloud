from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
import hashlib

import pandas as pd
from django.db import transaction
from django.utils import timezone

from pipecloud.models import (
    DataSourceFile,
    PlanRecord,
    Project,
    ProjectSchedulePolicy,
    ScheduledTaskRun,
    WeldLibraryRow,
    WeldingPlanRow,
    WeldRolloverLog,
)
from pipecloud.services.db_storage import PLAN_FILE_MODELS, _sync_weld_status_values, sync_dataframes, table_payload
from pipecloud.services.project_tables import ensure_project_tables, using_project_tables
from pipecloud.services import prefab_database


TASK_NAMES = {
    'cutting': 'rollover_incomplete_cutting_plan',
    'welding': 'rollover_incomplete_welding_plan',
}
PLAN_CONFIGS = {
    'cutting': {
        'primary_file_name': prefab_database.CUTTING_PRIMARY_PLAN_FILE_NAME,
        'plan_name': '下料',
        'plan_file_names': prefab_database.CUTTING_PLAN_FILE_NAMES,
        'order_column': prefab_database.future_schedule.CUT_ORDER_NO_COL,
        'date_column': prefab_database.future_schedule.CUT_DATE_COL,
        'completed_column': prefab_database.COLUMNS['material_cutting_status'],
        'count_label': 'Cutting',
    },
    'welding': {
        'primary_file_name': prefab_database.WELDING_PRIMARY_PLAN_FILE_NAME,
        'plan_name': '焊接',
        'plan_file_names': prefab_database.WELDING_PLAN_FILE_NAMES,
        'order_column': prefab_database.future_schedule.WELD_ORDER_NO_COL,
        'date_column': prefab_database.future_schedule.WELD_DATE_COL,
        'completed_column': prefab_database.COLUMNS['completed_flag'],
        'count_label': 'Weld',
    },
}
ROLLOVER_KEY_COLUMNS = [
    prefab_database.COLUMNS['weld_no_final'],
    prefab_database.COLUMNS['weld_no_start'],
    prefab_database.COLUMNS['pipeline'],
    prefab_database.COLUMNS['unit'],
    prefab_database.COLUMNS['diameter'],
]
INTERNAL_COLUMNS = {'_rollover_key', '_rollover_from_date'}


def _date_text(value):
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.strftime('%Y%m%d')
    return prefab_database.future_schedule._date_text(
        prefab_database.future_schedule._parse_schedule_date(value)
    )


def _date_value(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return prefab_database.future_schedule._parse_schedule_date(value)


def _number(value):
    if value in (None, ''):
        return Decimal('0')
    try:
        return Decimal(str(value).strip().replace(',', ''))
    except (InvalidOperation, ValueError):
        return Decimal('0')


def _normalized_key_part(value):
    text = str(value if value is not None else '').strip()
    if not text:
        return ''
    try:
        return format(float(text), 'g')
    except (TypeError, ValueError):
        return text


def _weld_key_series(dataframe):
    if dataframe is None or dataframe.empty:
        return pd.Series(dtype='string')
    existing = [column for column in ROLLOVER_KEY_COLUMNS if column in dataframe.columns]
    if not existing:
        return pd.Series(
            [f'row:{index}' for index in dataframe.index],
            index=dataframe.index,
            dtype='string',
        )
    return dataframe[existing].apply(
        lambda row: '|'.join(_normalized_key_part(row.get(column)) for column in existing),
        axis=1,
    )


def _row_weld_key(row):
    field_names = [
        'weld_no_final',
        'weld_no_start',
        'pipeline',
        'unit',
        'diameter',
    ]
    return '|'.join(_normalized_key_part(getattr(row, field_name, '')) for field_name in field_names)


def _plan_config(plan_key):
    if plan_key not in PLAN_CONFIGS:
        raise ValueError(f'不支持滚动的计划类型：{plan_key}')
    return PLAN_CONFIGS[plan_key]


def _plan_source(project, plan_key, plan_date):
    config = _plan_config(plan_key)
    return DataSourceFile.objects.filter(
        project=project,
        source_type='plan',
        source_key=f'{plan_key}:{_date_text(plan_date)}:{config["primary_file_name"]}',
    ).first()


def _load_plan_dataframe(project, plan_key, plan_date):
    config = _plan_config(plan_key)
    source = _plan_source(project, plan_key, plan_date)
    if source is None:
        return source, pd.DataFrame()
    frames = []
    for sheet_name in source.sheet_names or []:
        selected_sheet, _, _, columns, rows = table_payload(
            source,
            PLAN_FILE_MODELS[config['primary_file_name']],
            sheet_name,
        )
        frame = pd.DataFrame(rows, columns=columns)
        if frame.empty:
            continue
        frame['_rollover_from_date'] = _date_text(plan_date)
        frame['_rollover_key'] = _weld_key_series(frame)
        frames.append(frame)
    if not frames:
        return source, pd.DataFrame()
    return source, pd.concat(frames, ignore_index=True)


def pack_rollover_rows(dataframe, target_diameter=260, max_diameter=300, orders_per_day=3):
    """Pack rows in priority order, aiming for target and never crossing max."""
    if dataframe is None or dataframe.empty:
        return [], pd.DataFrame(columns=list(dataframe.columns) if dataframe is not None else [])

    target = _number(target_diameter)
    maximum = _number(max_diameter)
    order_limit = max(int(orders_per_day), 1)
    diameter_column = prefab_database.COLUMNS['diameter']
    queue = dataframe.reset_index(drop=True).copy()
    packed = []

    for _ in range(order_limit):
        if queue.empty:
            break
        selected_indexes = []
        total = Decimal('0')
        for index, row in queue.iterrows():
            diameter = _number(row.get(diameter_column))
            if diameter <= 0:
                raise ValueError(f'焊口寸径无效：{row.get("_rollover_key", index)}')
            if diameter > maximum:
                raise ValueError(
                    f'单道焊口寸径 {diameter} 超过滚动上限 {maximum}：'
                    f'{row.get("_rollover_key", index)}'
                )
            if selected_indexes and total >= target:
                break
            if total + diameter > maximum:
                continue
            selected_indexes.append(index)
            total += diameter

        if not selected_indexes:
            first = queue.iloc[0]
            raise ValueError(
                f'无法在滚动上限 {maximum} 内安排焊口：'
                f'{first.get("_rollover_key", queue.index[0])}'
            )

        packed.append(queue.loc[selected_indexes].copy().reset_index(drop=True))
        queue = queue.drop(index=selected_indexes).reset_index(drop=True)

    return packed, queue


def _next_eligible_date(start_date, policy):
    holidays = set(prefab_database.future_schedule._split_date_list(policy.holiday_dates))
    canceled_weekends = set(
        prefab_database.future_schedule._split_date_list(policy.canceled_weekend_dates)
    )
    return prefab_database.future_schedule._next_schedule_date(
        start_date,
        skip_holidays=policy.skip_holidays,
        holiday_dates=holidays,
        canceled_weekend_dates=canceled_weekends,
    )


def _prepare_plan_sheets(packed_rows, plan_key, plan_date):
    config = _plan_config(plan_key)
    sheets = {}
    target_date = _date_value(plan_date)
    for index, dataframe in enumerate(packed_rows, start=1):
        sheet_name = str(index)
        output = dataframe.copy()
        order_no = prefab_database.generate_schedule_order_no(
            output,
            extraction_index=index,
            unit_column=prefab_database.COLUMNS['unit'],
            material_type_column=prefab_database.COLUMNS['material_type'],
            order_date=_date_text(target_date),
        )
        output[config['order_column']] = order_no
        output[config['date_column']] = _date_text(target_date)
        output[prefab_database.future_schedule.SOURCE_SHEET_COL] = sheet_name
        output = output.drop(columns=list(INTERNAL_COLUMNS), errors='ignore')
        sheets[sheet_name] = output
    return sheets


def _write_plan_day(project, plan_key, plan_date, packed_rows):
    config = _plan_config(plan_key)
    plan_text = _date_text(plan_date)
    if not packed_rows:
        source = _plan_source(project, plan_key, plan_text)
        if source:
            source.delete()
        PlanRecord.objects.filter(
            project=project,
            plan_key=plan_key,
            plan_folder=plan_text,
        ).delete()
        return

    sync_dataframes(
        project,
        'plan',
        f'{plan_key}:{plan_text}:{config["primary_file_name"]}',
        config['primary_file_name'],
        prefab_database._plan_source_path(plan_key, plan_text, config['primary_file_name']),
        _prepare_plan_sheets(packed_rows, plan_key, plan_text),
        PLAN_FILE_MODELS[config['primary_file_name']],
    )
    merged_frame = pd.concat(packed_rows, ignore_index=True, sort=False)
    prefab_database._sync_master_schedule_rows(project, plan_key, plan_text, merged_frame)
    prefab_database._sync_plan_record(
        project,
        plan_key,
        config['plan_name'],
        plan_text,
        config['plan_file_names'],
    )


def _sync_today_completion(project, today_frame):
    if today_frame.empty:
        return 0
    completed_column = prefab_database.COLUMNS['completed_flag']
    if completed_column not in today_frame.columns:
        return 0

    completion_map = dict(zip(
        today_frame['_rollover_key'],
        prefab_database.future_schedule._to_bool_series(today_frame[completed_column]),
    ))
    changed = []
    for row in WeldLibraryRow.objects.filter(project=project):
        key = _row_weld_key(row)
        if key not in completion_map:
            continue
        next_value = bool(completion_map[key])
        if row.completed_flag != next_value:
            row.completed_flag = next_value
            changed.append(row)
    if changed:
        WeldLibraryRow.objects.bulk_update(changed, ['completed_flag'], batch_size=500)
        _sync_weld_status_values(project, [
            {
                'library_seq': row.library_seq,
                'completed_flag': row.completed_flag,
            }
            for row in changed
        ])

    total = WeldLibraryRow.objects.filter(project=project).count()
    completed = WeldLibraryRow.objects.filter(project=project, completed_flag=True).count()
    next_rate = Decimal('0.00')
    if total:
        next_rate = Decimal(str(round(completed / total * 100, 2))).quantize(Decimal('0.01'))
    if project.completion_rate != next_rate:
        project.completion_rate = next_rate
        project.save(update_fields=['completion_rate', 'updated_at'])
    return len(changed)


def _rollover_project(project, business_date, policy, write=True, plan_key='welding'):
    config = _plan_config(plan_key)
    business_value = _date_value(business_date)
    business_text = _date_text(business_value)
    _, today_frame = _load_plan_dataframe(project, plan_key, business_text)
    count_label = config['count_label']
    if today_frame.empty:
        return {
            'businessDate': business_text,
            'hasTodayPlan': False,
            f'today{count_label}Count': 0,
            f'completed{count_label}Count': 0,
            f'rolled{count_label}Count': 0,
            'affectedPlanDates': [],
            'moves': [],
        }

    completed_column = config['completed_column']
    completed_series = (
        prefab_database.future_schedule._to_bool_series(today_frame[completed_column])
        if completed_column in today_frame.columns
        else pd.Series(False, index=today_frame.index)
    )
    completed_count = int(completed_series.sum())
    carry = today_frame.loc[~completed_series].copy()
    carry = carry.drop_duplicates('_rollover_key', keep='last').reset_index(drop=True)

    if carry.empty:
        if write and plan_key == 'welding':
            _sync_today_completion(project, today_frame)
        return {
            'businessDate': business_text,
            'hasTodayPlan': True,
            f'today{count_label}Count': int(len(today_frame)),
            f'completed{count_label}Count': completed_count,
            f'rolled{count_label}Count': 0,
            'affectedPlanDates': [],
            'moves': [],
        }

    future_dates = list(
        PlanRecord.objects.filter(
            project=project,
            plan_key=plan_key,
            plan_date__gt=business_text,
        )
        .order_by('plan_date')
        .values_list('plan_date', flat=True)
        .distinct()
    )
    pending_dates = [_date_value(value) for value in future_dates]
    if not pending_dates:
        pending_dates.append(_next_eligible_date(business_value + timedelta(days=1), policy))

    affected_dates = []
    moves = []
    assigned_keys = set()
    date_index = 0
    safety_limit = 366

    while not carry.empty:
        if date_index >= safety_limit:
            raise ValueError('滚动计划超过 366 个计划日，已停止处理')
        if date_index >= len(pending_dates):
            pending_dates.append(
                _next_eligible_date(pending_dates[-1] + timedelta(days=1), policy)
            )

        plan_date = pending_dates[date_index]
        plan_text = _date_text(plan_date)
        _, existing_frame = _load_plan_dataframe(project, plan_key, plan_text)
        if not existing_frame.empty:
            existing_frame = existing_frame.loc[
                ~existing_frame['_rollover_key'].isin(set(carry['_rollover_key']))
                & ~existing_frame['_rollover_key'].isin(assigned_keys)
            ].copy()
        candidates = pd.concat([carry, existing_frame], ignore_index=True, sort=False)
        candidates = candidates.drop_duplicates('_rollover_key', keep='first').reset_index(drop=True)

        packed, overflow = pack_rollover_rows(
            candidates,
            target_diameter=policy.target_diameter,
            max_diameter=policy.rollover_max_diameter,
            orders_per_day=policy.orders_per_day,
        )
        packed_keys = set()
        for sheet in packed:
            packed_keys.update(sheet['_rollover_key'].astype(str))
            for _, row in sheet.iterrows():
                from_text = str(row.get('_rollover_from_date') or '')
                if from_text and from_text != plan_text:
                    moves.append({
                        'weldKey': str(row.get('_rollover_key') or ''),
                        'fromDate': from_text,
                        'toDate': plan_text,
                        'diameter': float(_number(row.get(prefab_database.COLUMNS['diameter']))),
                    })
        assigned_keys.update(packed_keys)
        if write:
            _write_plan_day(project, plan_key, plan_text, packed)
        affected_dates.append(plan_text)
        carry = overflow.copy()
        date_index += 1

    if write and plan_key == 'welding':
        _sync_today_completion(project, today_frame)

    return {
        'businessDate': business_text,
        'hasTodayPlan': True,
        f'today{count_label}Count': int(len(today_frame)),
        f'completed{count_label}Count': completed_count,
        f'rolled{count_label}Count': int(len(today_frame) - completed_count),
        'affectedPlanDates': affected_dates,
        'moves': moves,
    }


def execute_project_rollover(project, business_date=None, dry_run=False, force=False, plan_key='welding'):
    _plan_config(plan_key)
    business_value = _date_value(business_date or timezone.localdate())
    ensure_project_tables(project)
    with using_project_tables(project):
        policy = ProjectSchedulePolicy.objects.filter(project=project).first()
        if policy is None:
            policy = ProjectSchedulePolicy(project=project)

    if dry_run:
        with using_project_tables(project):
            return _rollover_project(project, business_value, policy, write=False, plan_key=plan_key)

    if policy.pk is None:
        with using_project_tables(project):
            policy.save()

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
        with using_project_tables(project), transaction.atomic():
            Project.objects.select_for_update().get(pk=project.pk)
            stats = _rollover_project(project, business_value, policy, write=True, plan_key=plan_key)
            moves = stats.pop('moves', [])
            logs = [
                WeldRolloverLog(
                    project=project,
                    task_run=task_run,
                    weld_key=move['weldKey'],
                    weld_key_hash=hashlib.sha256(move['weldKey'].encode('utf-8')).hexdigest(),
                    from_date=_date_value(move['fromDate']),
                    to_date=_date_value(move['toDate']),
                    diameter=Decimal(str(move['diameter'])),
                )
                for move in moves
                if move['weldKey']
            ]
            if logs:
                WeldRolloverLog.objects.bulk_create(logs, ignore_conflicts=True, batch_size=500)
            stats['moveCount'] = len(logs)
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


def execute_all_project_rollovers(business_date=None, project_id=None, dry_run=False, force=False, plan_key='welding'):
    _plan_config(plan_key)
    business_value = _date_value(business_date or timezone.localdate())
    projects = Project.objects.order_by('id')
    if project_id:
        projects = projects.filter(pk=project_id)
    results = []
    for project in projects:
        policy = ProjectSchedulePolicy.objects.filter(project=project).first()
        if policy is None and not dry_run:
            policy = ProjectSchedulePolicy.objects.create(project=project)
        elif policy is None:
            policy = ProjectSchedulePolicy(project=project)
        if not policy.auto_rollover_enabled:
            skipped_stats = {
                'projectId': project.id,
                'projectName': project.project_name,
                'planKey': plan_key,
                'planName': _plan_config(plan_key)['plan_name'],
                'skipped': True,
                'reason': 'auto rollover disabled',
            }
            if not dry_run:
                task_run, _ = ScheduledTaskRun.objects.get_or_create(
                    project=project,
                    task_name=TASK_NAMES[plan_key],
                    business_date=business_value,
                    defaults={
                        'status': 'skipped',
                        'stats': skipped_stats,
                        'finished_at': timezone.now(),
                    },
                )
                if task_run.status != 'succeeded':
                    task_run.status = 'skipped'
                    task_run.stats = skipped_stats
                    task_run.error_message = ''
                    task_run.finished_at = timezone.now()
                    task_run.save(update_fields=['status', 'stats', 'error_message', 'finished_at'])
            results.append(skipped_stats)
            continue
        try:
            stats = execute_project_rollover(
                project,
                business_date=business_value,
                dry_run=dry_run,
                force=force,
                plan_key=plan_key,
            )
            results.append({
                'projectId': project.id,
                'projectName': project.project_name,
                'planKey': plan_key,
                'planName': _plan_config(plan_key)['plan_name'],
                **stats,
            })
        except Exception as error:
            results.append({
                'projectId': project.id,
                'projectName': project.project_name,
                'planKey': plan_key,
                'planName': _plan_config(plan_key)['plan_name'],
                'error': str(error),
            })
    return results
