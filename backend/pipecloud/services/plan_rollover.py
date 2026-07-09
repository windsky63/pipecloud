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
from pipecloud.services.db_storage import PLAN_FILE_MODELS, sync_dataframes, table_payload
from pipecloud.services.project_tables import ensure_project_tables, using_project_tables
from pipecloud.services import prefab_database


TASK_NAME = 'rollover_incomplete_welding_plan'
PRIMARY_FILE_NAME = prefab_database.WELDING_PRIMARY_PLAN_FILE_NAME
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


def _plan_source(project, plan_date):
    return DataSourceFile.objects.filter(
        project=project,
        source_type='plan',
        source_key=f'welding:{_date_text(plan_date)}:{PRIMARY_FILE_NAME}',
    ).first()


def _load_plan_dataframe(project, plan_date):
    source = _plan_source(project, plan_date)
    if source is None:
        return source, pd.DataFrame()
    frames = []
    for sheet_name in source.sheet_names or []:
        selected_sheet, _, _, columns, rows = table_payload(
            source,
            PLAN_FILE_MODELS[PRIMARY_FILE_NAME],
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


def _prepare_plan_sheets(packed_rows, plan_date):
    sheets = {}
    weld_date = _date_value(plan_date)
    for index, dataframe in enumerate(packed_rows, start=1):
        sheet_name = str(index)
        output = dataframe.copy()
        order_no = prefab_database.generate_schedule_order_no(
            output,
            extraction_index=index,
            unit_column=prefab_database.COLUMNS['unit'],
            material_type_column=prefab_database.COLUMNS['material_type'],
            order_date=_date_text(weld_date),
        )
        output[prefab_database.future_schedule.WELD_ORDER_NO_COL] = order_no
        output[prefab_database.future_schedule.WELD_DATE_COL] = _date_text(weld_date)
        output[prefab_database.future_schedule.SOURCE_SHEET_COL] = sheet_name
        output = output.drop(columns=list(INTERNAL_COLUMNS), errors='ignore')
        sheets[sheet_name] = output
    return sheets


def _write_plan_day(project, plan_date, packed_rows):
    plan_text = _date_text(plan_date)
    if not packed_rows:
        source = _plan_source(project, plan_text)
        if source:
            source.delete()
        PlanRecord.objects.filter(
            project=project,
            plan_key='welding',
            plan_folder=plan_text,
        ).delete()
        return

    sync_dataframes(
        project,
        'plan',
        f'welding:{plan_text}:{PRIMARY_FILE_NAME}',
        PRIMARY_FILE_NAME,
        prefab_database._plan_source_path('welding', plan_text, PRIMARY_FILE_NAME),
        _prepare_plan_sheets(packed_rows, plan_text),
        PLAN_FILE_MODELS[PRIMARY_FILE_NAME],
    )
    prefab_database._sync_plan_record(
        project,
        'welding',
        '焊接',
        plan_text,
        prefab_database.WELDING_PLAN_FILE_NAMES,
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

    total = WeldLibraryRow.objects.filter(project=project).count()
    completed = WeldLibraryRow.objects.filter(project=project, completed_flag=True).count()
    next_rate = Decimal('0.00')
    if total:
        next_rate = Decimal(str(round(completed / total * 100, 2))).quantize(Decimal('0.01'))
    if project.completion_rate != next_rate:
        project.completion_rate = next_rate
        project.save(update_fields=['completion_rate', 'updated_at'])
    return len(changed)


def _rollover_project(project, business_date, policy, write=True):
    business_value = _date_value(business_date)
    business_text = _date_text(business_value)
    _, today_frame = _load_plan_dataframe(project, business_text)
    if today_frame.empty:
        return {
            'businessDate': business_text,
            'hasTodayPlan': False,
            'todayWeldCount': 0,
            'completedWeldCount': 0,
            'rolledWeldCount': 0,
            'affectedPlanDates': [],
            'moves': [],
        }

    completed_column = prefab_database.COLUMNS['completed_flag']
    completed_series = (
        prefab_database.future_schedule._to_bool_series(today_frame[completed_column])
        if completed_column in today_frame.columns
        else pd.Series(False, index=today_frame.index)
    )
    completed_count = int(completed_series.sum())
    carry = today_frame.loc[~completed_series].copy()
    carry = carry.drop_duplicates('_rollover_key', keep='last').reset_index(drop=True)

    if carry.empty:
        if write:
            _sync_today_completion(project, today_frame)
        return {
            'businessDate': business_text,
            'hasTodayPlan': True,
            'todayWeldCount': int(len(today_frame)),
            'completedWeldCount': completed_count,
            'rolledWeldCount': 0,
            'affectedPlanDates': [],
            'moves': [],
        }

    future_dates = list(
        PlanRecord.objects.filter(
            project=project,
            plan_key='welding',
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
        _, existing_frame = _load_plan_dataframe(project, plan_text)
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
            _write_plan_day(project, plan_text, packed)
        affected_dates.append(plan_text)
        carry = overflow.copy()
        date_index += 1

    if write:
        _sync_today_completion(project, today_frame)

    return {
        'businessDate': business_text,
        'hasTodayPlan': True,
        'todayWeldCount': int(len(today_frame)),
        'completedWeldCount': completed_count,
        'rolledWeldCount': int(len(today_frame) - completed_count),
        'affectedPlanDates': affected_dates,
        'moves': moves,
    }


def execute_project_rollover(project, business_date=None, dry_run=False, force=False):
    business_value = _date_value(business_date or timezone.localdate())
    ensure_project_tables(project)
    with using_project_tables(project):
        policy = ProjectSchedulePolicy.objects.filter(project=project).first()
        if policy is None:
            policy = ProjectSchedulePolicy(project=project)

    if dry_run:
        with using_project_tables(project):
            return _rollover_project(project, business_value, policy, write=False)

    if policy.pk is None:
        with using_project_tables(project):
            policy.save()

    with using_project_tables(project), transaction.atomic():
        Project.objects.select_for_update().get(pk=project.pk)
        task_run, _ = ScheduledTaskRun.objects.select_for_update().get_or_create(
            project=project,
            task_name=TASK_NAME,
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
            stats = _rollover_project(project, business_value, policy, write=True)
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


def execute_all_project_rollovers(business_date=None, project_id=None, dry_run=False, force=False):
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
            results.append({
                'projectId': project.id,
                'projectName': project.project_name,
                'skipped': True,
                'reason': 'auto rollover disabled',
            })
            continue
        try:
            stats = execute_project_rollover(
                project,
                business_date=business_date,
                dry_run=dry_run,
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
                'error': str(error),
            })
    return results
