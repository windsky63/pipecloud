# -*- coding: utf-8 -*-
"""预制总排产：按预排产库滚动生成未来下料和焊接计划。"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path
import sys

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent
AUTO_WELD_DIR = ROOT_DIR / '焊接管理及排产' / '自动焊排产'
for path in (ROOT_DIR, AUTO_WELD_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from common_utils import normalize_columns, prepare_output_file
from project_config import COLUMNS, SCHEDULE_DIR, VERBOSE
from 下料管理及排产.cutting_config import CUTTING_DIR, MATCHED_STATUS, STATUS_COL
from 焊接管理及排产.weld_config import FILES, get_weld_schedule_output_files
from 焊接管理及排产.自动焊排产.auto_weld_schedule_config import EXTRACT
from extract_welds import (
    extract_welds_multiple_times,
    save_extractions_to_excel,
    save_segment_list_to_excel,
    save_statistics_to_excel,
    sort_and_clean_data,
)
from generate_material_detail import generate_material_details_for_sheet, save_material_detail_files


DATE_FORMAT = '%Y%m%d'
PRE_SCHEDULE_SHEET = '预排产匹配结果'
WELD_OUTPUT_NAME = '管段焊口表.xlsx'
CUT_DETAIL_NAME = '切管明细表.xlsx'
CUT_SUMMARY_NAME = '切管汇总表.xlsx'
MASTER_PLAN_NAME = '总排产计划.xlsx'
PLAN_DATE_COL = '计划日期'
CUT_DATE_COL = '下料日期'
WELD_DATE_COL = '焊接日期'
CUT_ORDER_NO_COL = '下料排产单号'
WELD_ORDER_NO_COL = '焊接排产单号'
SOURCE_SHEET_COL = '来源工作表'
DEFAULT_CUTTING_LEAD_DAYS = 1


def _log(*args, **kwargs):
    if VERBOSE:
        print(*args, **kwargs)


def _parse_schedule_date(value=None):
    if value is None:
        return datetime.now().date()
    if hasattr(value, 'date') and not isinstance(value, str):
        return value.date()
    text = str(value).strip()
    for fmt in (DATE_FORMAT, '%Y-%m-%d'):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ValueError(f'日期格式无效：{value}，请使用 YYYYMMDD 或 YYYY-MM-DD')


def _date_text(date_value):
    return _parse_schedule_date(date_value).strftime(DATE_FORMAT)


def _split_date_list(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        values = value
    else:
        values = str(value).replace('，', ',').replace(';', ',').replace('；', ',').split(',')
    dates = []
    seen = set()
    for item in values:
        text = str(item).strip()
        if not text:
            continue
        date_value = _parse_schedule_date(text)
        if date_value in seen:
            continue
        seen.add(date_value)
        dates.append(date_value)
    return dates


def _to_bool(value=False):
    if isinstance(value, bool):
        return value
    return str(value if value is not None else '').strip().lower() in {
        'true',
        '1',
        'yes',
        'y',
        'on',
        '跳过',
        '是',
    }


def _is_holiday(date_value, holiday_dates=None, canceled_weekend_dates=None):
    holidays = holiday_dates or set()
    canceled_weekends = canceled_weekend_dates or set()
    if date_value.weekday() >= 5 and date_value not in canceled_weekends:
        return True
    return date_value in holidays


def _next_schedule_date(start_date, skip_holidays=False, holiday_dates=None, canceled_weekend_dates=None):
    date_value = start_date
    while skip_holidays and _is_holiday(date_value, holiday_dates, canceled_weekend_dates):
        date_value += timedelta(days=1)
    return date_value


def _previous_schedule_date(start_date, days=1, skip_holidays=False, holiday_dates=None, canceled_weekend_dates=None):
    steps = max(int(days or 0), 0)
    date_value = start_date
    if steps <= 0:
        return _next_schedule_date(date_value, skip_holidays, holiday_dates, canceled_weekend_dates)

    if not skip_holidays:
        return date_value - timedelta(days=steps)

    moved = 0
    while moved < steps:
        date_value -= timedelta(days=1)
        if not _is_holiday(date_value, holiday_dates, canceled_weekend_dates):
            moved += 1
    return date_value


def _manual_weld_dates(manual_dates, skip_holidays=False, holiday_dates=None, canceled_weekend_dates=None):
    dates = _split_date_list(manual_dates)
    if not skip_holidays:
        return dates
    return [date_value for date_value in dates if not _is_holiday(date_value, holiday_dates, canceled_weekend_dates)]


def _auto_weld_dates(weld_start, max_days=None, skip_holidays=False, holiday_dates=None, canceled_weekend_dates=None):
    date_value = _next_schedule_date(weld_start, skip_holidays, holiday_dates, canceled_weekend_dates)
    generated = 0
    while max_days is None or generated < int(max_days):
        if not skip_holidays or not _is_holiday(date_value, holiday_dates, canceled_weekend_dates):
            yield date_value
            generated += 1
        date_value += timedelta(days=1)


def _to_bool_series(series):
    true_values = {'true', '1', 'yes', 'y', '完成', '已完成', 'done', 'finished'}
    normalized = series.fillna('').astype(str).str.strip().str.lower()
    return normalized.isin(true_values)


def _read_excel_sheets(file_path):
    path = Path(file_path)
    if not path.exists():
        return {}
    try:
        sheets = pd.read_excel(path, sheet_name=None)
    except ValueError:
        return {}
    return {name: normalize_columns(df) for name, df in sheets.items()}


def _build_weld_key(df):
    key_cols = [
        COLUMNS['library_seq'],
        COLUMNS['weld_no_final'],
        COLUMNS['weld_no_start'],
        COLUMNS['pipeline'],
        COLUMNS['unit'],
        COLUMNS['diameter'],
    ]
    existing = [col for col in key_cols if col in df.columns]
    if not existing:
        return pd.Series(range(len(df)), index=df.index).astype(str)

    key_df = df[existing].copy()
    for col in existing:
        raw = key_df[col]
        numeric = pd.to_numeric(raw, errors='coerce')
        normalized = raw.astype('string').fillna('').str.strip()
        numeric_mask = numeric.notna()
        if numeric_mask.any():
            normalized.loc[numeric_mask] = numeric.loc[numeric_mask].map(lambda value: format(float(value), 'g'))
        key_df[col] = normalized
    return key_df.agg('|'.join, axis=1)


def _load_completed_weld_keys(schedule_dir=SCHEDULE_DIR):
    completed_col = COLUMNS['completed_flag']
    completed_keys = set()
    schedule_root = Path(schedule_dir)
    if not schedule_root.exists():
        return completed_keys

    for work_order in schedule_root.glob(f'*/{WELD_OUTPUT_NAME}'):
        for df in _read_excel_sheets(work_order).values():
            if df is None or df.empty or completed_col not in df.columns:
                continue
            completed_df = df.loc[_to_bool_series(df[completed_col])].copy()
            if not completed_df.empty:
                completed_keys.update(_build_weld_key(completed_df))
    return completed_keys


def load_pre_schedule(pre_schedule_file=FILES['extract_input'], sheet_name=PRE_SCHEDULE_SHEET):
    pre_schedule_path = Path(pre_schedule_file)
    if not pre_schedule_path.exists():
        raise FileNotFoundError(f'预排产结果不存在：{pre_schedule_path}')

    df = normalize_columns(pd.read_excel(pre_schedule_path, sheet_name=sheet_name))
    if STATUS_COL not in df.columns:
        raise ValueError(f'预排产结果缺少列：{STATUS_COL}')

    completed_col = COLUMNS['completed_flag']
    if completed_col not in df.columns:
        df[completed_col] = False
    else:
        df[completed_col] = _to_bool_series(df[completed_col])

    return df.loc[df[STATUS_COL].fillna('').astype(str).str.strip().eq(MATCHED_STATUS)].copy()


def _remove_completed_welds(pre_schedule_df, completed_keys):
    if not completed_keys:
        return pre_schedule_df.copy(), 0
    work_df = pre_schedule_df.copy()
    key_series = _build_weld_key(work_df)
    remain_df = work_df.loc[~key_series.isin(completed_keys)].copy()
    return remain_df, len(work_df) - len(remain_df)


def _ensure_completed_column(df):
    completed_col = COLUMNS['completed_flag']
    out = df.copy()
    if completed_col not in out.columns:
        out[completed_col] = False
    else:
        out[completed_col] = _to_bool_series(out[completed_col])
    return out


def _sheet_order_no(df, fallback=''):
    if WELD_ORDER_NO_COL in df.columns:
        values = df[WELD_ORDER_NO_COL].dropna().astype(str).str.strip()
    elif '排产单号' in df.columns:
        values = df['排产单号'].dropna().astype(str).str.strip()
    else:
        values = pd.Series(dtype=str)
    values = values[values != '']
    return values.iloc[0] if not values.empty else fallback


def _clean_joined_values(values):
    cleaned = []
    seen = set()
    for value in values:
        text = str(value or '').strip()
        if not text or text.lower() == 'nan' or text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
    return '、'.join(cleaned)


def _material_units_for_side(material_mark):
    mark_text = str(material_mark or '').strip().upper()
    if not mark_text:
        return ''
    return '米' if mark_text == 'P' else '个'


def _build_welding_plan_for_sheet(sheet_name, weld_df, cut_date, weld_date):
    out = weld_df.copy()
    if out.empty:
        return out

    weld_order_no = _sheet_order_no(out, fallback=str(sheet_name))
    cut_order_no = f"QG-{_date_text(cut_date)}-{sheet_name}"

    out[CUT_ORDER_NO_COL] = cut_order_no
    out[WELD_ORDER_NO_COL] = weld_order_no
    out[CUT_DATE_COL] = _date_text(cut_date)
    out[WELD_DATE_COL] = _date_text(weld_date)
    out[SOURCE_SHEET_COL] = str(sheet_name)

    for side in (1, 2):
        mark_col = COLUMNS[f'material_no_{side}']
        out[f'单位{side}'] = out[mark_col].map(_material_units_for_side) if mark_col in out.columns else ''
    return out


def _build_cut_detail_for_sheet(sheet_name, weld_df, cut_date, weld_date):
    rows = []
    base_cols = [
        COLUMNS['unit'],
        COLUMNS['pipeline'],
        COLUMNS['segment_no'],
        COLUMNS['weld_no_start'],
        COLUMNS['weld_no_final'],
        COLUMNS['diameter'],
        COLUMNS['thickness'],
        COLUMNS['material'],
    ]
    weld_order_no = _sheet_order_no(weld_df, fallback=str(sheet_name))
    cut_order_no = f"QG-{_date_text(cut_date)}-{sheet_name}"

    for side in (1, 2):
        material_no_col = COLUMNS[f'material_no_{side}']
        material_unique_col = COLUMNS[f'material_unique_{side}']
        material_code_col = COLUMNS[f'material_code_{side}']
        qty_col = COLUMNS[f'qty_{side}']
        desc_col = COLUMNS[f'desc_{side}']
        paint_col = COLUMNS[f'paint_{side}']
        if material_no_col not in weld_df.columns or qty_col not in weld_df.columns:
            continue

        pipe_mask = weld_df[material_no_col].fillna('').astype(str).str.upper().str.strip().eq('P')
        if not pipe_mask.any():
            continue

        for _, source_row in weld_df.loc[pipe_mask].iterrows():
            row = {
                CUT_ORDER_NO_COL: cut_order_no,
                WELD_ORDER_NO_COL: weld_order_no,
                CUT_DATE_COL: _date_text(cut_date),
                WELD_DATE_COL: _date_text(weld_date),
                SOURCE_SHEET_COL: sheet_name,
                '材料侧': side,
                '材料唯一码': source_row.get(material_unique_col, ''),
                '材料代码': source_row.get(material_code_col, ''),
                '材料代号': source_row.get(material_no_col, ''),
                '设计切割长度': source_row.get(qty_col, 0),
                '单位': '米',
                '材料油漆': source_row.get(paint_col, ''),
                '描述': source_row.get(desc_col, ''),
                COLUMNS['completed_flag']: False,
            }
            for col in base_cols:
                row[col] = source_row.get(col, '')
            rows.append(row)

    return pd.DataFrame(rows)


def _build_cut_summary(detail_df):
    if detail_df is None or detail_df.empty:
        return pd.DataFrame()
    group_cols = [
        CUT_ORDER_NO_COL,
        WELD_ORDER_NO_COL,
        CUT_DATE_COL,
        WELD_DATE_COL,
        '材料代码',
        '材料代号',
        '单位',
        '材料油漆',
        '描述',
    ]
    group_cols = [col for col in group_cols if col in detail_df.columns]
    summary = detail_df.copy()
    summary['设计切割长度'] = pd.to_numeric(summary['设计切割长度'], errors='coerce').fillna(0)
    agg_map = {
        '设计切割长度': 'sum',
        '材料唯一码': lambda x: '、'.join(pd.unique(x.fillna('').astype(str).str.strip())),
        COLUMNS['pipeline']: lambda x: '、'.join(pd.unique(x.fillna('').astype(str).str.strip())),
        COLUMNS['segment_no']: lambda x: '、'.join(pd.unique(x.fillna('').astype(str).str.strip())),
    }
    agg_map = {k: v for k, v in agg_map.items() if k in summary.columns}
    out = summary.groupby(group_cols, as_index=False).agg(agg_map)
    return out.sort_values(group_cols).reset_index(drop=True)


def save_cutting_plan(all_extractions, cut_date, weld_date, cutting_dir=CUTTING_DIR):
    cut_output_dir = Path(cutting_dir) / _date_text(cut_date)
    detail_file = cut_output_dir / CUT_DETAIL_NAME
    summary_file = cut_output_dir / CUT_SUMMARY_NAME

    detail_sheets = {}
    summary_sheets = {}
    for extraction in all_extractions:
        sheet_name = str(extraction['info']['抽取次数'])
        detail_df = _build_cut_detail_for_sheet(sheet_name, extraction['data'], cut_date, weld_date)
        detail_sheets[sheet_name] = detail_df
        summary_sheets[sheet_name] = _build_cut_summary(detail_df)

    prepare_output_file(detail_file)
    with pd.ExcelWriter(detail_file, engine='openpyxl') as writer:
        wrote = False
        for sheet_name, detail_df in detail_sheets.items():
            if detail_df is None or detail_df.empty:
                continue
            detail_df.to_excel(writer, sheet_name=str(sheet_name)[:31], index=False)
            wrote = True
        if not wrote:
            pd.DataFrame(columns=[CUT_ORDER_NO_COL, WELD_ORDER_NO_COL, CUT_DATE_COL, WELD_DATE_COL]).to_excel(
                writer, sheet_name='无切管明细', index=False
            )

    prepare_output_file(summary_file)
    with pd.ExcelWriter(summary_file, engine='openpyxl') as writer:
        wrote = False
        for sheet_name, summary_df in summary_sheets.items():
            if summary_df is None or summary_df.empty:
                continue
            summary_df.to_excel(writer, sheet_name=str(sheet_name)[:31], index=False)
            wrote = True
        if not wrote:
            pd.DataFrame(columns=[CUT_ORDER_NO_COL, WELD_ORDER_NO_COL, CUT_DATE_COL, WELD_DATE_COL]).to_excel(
                writer, sheet_name='无切管汇总', index=False
            )

    return {'cut_detail': detail_file, 'cut_summary': summary_file}


def save_welding_plan(all_extractions, weld_date, cut_date=None, save_extract_stats=None):
    output_files = get_weld_schedule_output_files(_date_text(weld_date))
    extract_data_file = output_files['extract_output_data']
    segment_list_file = output_files['segment_list_output']
    extract_stats_file = output_files['extract_output_stats']
    material_output_file = output_files['material_output']
    pipe_pick_output_file = output_files['pipe_pick_list_output']
    fitting_pick_output_file = output_files['fitting_pick_list_output']

    cut_date = _parse_schedule_date(cut_date) if cut_date else _previous_schedule_date(
        weld_date,
        days=DEFAULT_CUTTING_LEAD_DAYS,
    )
    welding_extractions = []
    for extraction in all_extractions:
        sheet_name = str(extraction['info']['抽取次数'])
        welding_extractions.append({
            **extraction,
            'data': _build_welding_plan_for_sheet(sheet_name, extraction['data'], cut_date, weld_date),
        })

    save_extractions_to_excel(welding_extractions, extract_data_file)
    save_segment_list_to_excel(all_extractions, segment_list_file)
    if save_extract_stats is None:
        save_extract_stats = EXTRACT.get('save_extract_stats', True)
    if save_extract_stats:
        save_statistics_to_excel(all_extractions, extract_stats_file, COLUMNS['diameter'])

    material_details = {}
    for extraction in all_extractions:
        sheet_name = str(extraction['info']['抽取次数'])
        material_df = generate_material_details_for_sheet(sheet_name, extraction['data'])
        if material_df is not None and not material_df.empty:
            material_details[sheet_name] = material_df

    if material_details:
        save_material_detail_files(
            material_details,
            material_output_file,
            pipe_pick_output_file,
            fitting_pick_output_file,
        )

    return output_files


def _append_master_rows(master_rows, all_extractions, cut_date, weld_date, cutting_lead_days=DEFAULT_CUTTING_LEAD_DAYS):
    lead_days = max(int(cutting_lead_days or 0), 0)
    completion_requirement = '焊接当天完成' if lead_days == 0 else f'焊接前{lead_days}天完成'
    for extraction in all_extractions:
        info = extraction['info']
        master_rows.append({
            CUT_DATE_COL: _date_text(cut_date),
            WELD_DATE_COL: _date_text(weld_date),
            WELD_ORDER_NO_COL: info.get('排产单号', ''),
            '抽取次数': info.get('抽取次数', ''),
            '焊口数量': info.get('焊口数量', 0),
            '直径总和': info.get('直径总和', 0),
            '目标值': info.get('目标值', 0),
            '下料完成要求': completion_requirement,
        })


def save_master_plan(master_rows, output_file=None):
    output_path = Path(output_file or (SCHEDULE_DIR / MASTER_PLAN_NAME))
    prepare_output_file(output_path)
    pd.DataFrame(master_rows).to_excel(output_path, index=False)
    return output_path


def generate_future_schedule(
    pre_schedule_file=FILES['extract_input'],
    weld_start_date=None,
    max_days=None,
    target_diameter=None,
    orders_per_day=None,
    date_mode='auto',
    manual_weld_dates=None,
    skip_holidays=False,
    holiday_dates=None,
    canceled_weekend_dates=None,
    cutting_lead_days=DEFAULT_CUTTING_LEAD_DAYS,
):
    weld_start = _parse_schedule_date(weld_start_date) if weld_start_date else datetime.now().date() + timedelta(days=1)
    target_diameter = target_diameter or EXTRACT['target_diameter']
    orders_per_day = orders_per_day or EXTRACT['num_extractions']
    date_mode = str(date_mode or 'auto').strip().lower()
    skip_holidays = _to_bool(skip_holidays)
    holiday_date_set = set(_split_date_list(holiday_dates))
    canceled_weekend_date_set = set(_split_date_list(canceled_weekend_dates))
    cutting_lead_days = DEFAULT_CUTTING_LEAD_DAYS if cutting_lead_days is None else max(int(cutting_lead_days), 0)
    if date_mode not in {'auto', 'manual'}:
        raise ValueError(f'日期生成方式无效：{date_mode}')

    pre_schedule_df = load_pre_schedule(pre_schedule_file)
    completed_keys = _load_completed_weld_keys()
    available_df, completed_count = _remove_completed_welds(pre_schedule_df, completed_keys)
    available_df = _ensure_completed_column(available_df)

    work_df = sort_and_clean_data(available_df, COLUMNS['diameter'], COLUMNS['completed_flag'])
    master_rows = []
    output_days = []
    if date_mode == 'manual':
        weld_dates = _manual_weld_dates(manual_weld_dates, skip_holidays, holiday_date_set, canceled_weekend_date_set)
        if not weld_dates:
            raise ValueError('手动选择日期为空，或已全部被节假日规则过滤')
    else:
        weld_dates = _auto_weld_dates(weld_start, max_days, skip_holidays, holiday_date_set, canceled_weekend_date_set)

    for weld_date in weld_dates:
        cut_date = _previous_schedule_date(
            weld_date,
            days=cutting_lead_days,
            skip_holidays=skip_holidays,
            holiday_dates=holiday_date_set,
            canceled_weekend_dates=canceled_weekend_date_set,
        )
        all_extractions = extract_welds_multiple_times(
            work_df,
            num_extractions=orders_per_day,
            target_diameter=target_diameter,
            diameter_column=COLUMNS['diameter'],
            completed_flag_column=COLUMNS['completed_flag'],
            order_date=_date_text(weld_date),
        )
        if not all_extractions:
            break

        cut_files = save_cutting_plan(all_extractions, cut_date, weld_date)
        weld_files = save_welding_plan(all_extractions, weld_date, cut_date=cut_date)
        _append_master_rows(master_rows, all_extractions, cut_date, weld_date, cutting_lead_days)
        output_days.append({
            CUT_DATE_COL: _date_text(cut_date),
            WELD_DATE_COL: _date_text(weld_date),
            '下料文件': cut_files,
            '焊接文件': weld_files,
        })

        remaining_count = int(((work_df['_run_picked'] == False) & (work_df[COLUMNS['completed_flag']] == False)).sum())
        if remaining_count == 0:
            break

    master_plan_file = save_master_plan(master_rows)
    return {
        'pre_schedule_count': len(pre_schedule_df),
        'completed_weld_count': completed_count,
        'planned_weld_count': int(sum(row['焊口数量'] for row in master_rows)),
        'planned_day_count': len(output_days),
        'master_plan_file': master_plan_file,
        'output_days': output_days,
    }


def main():
    parser = argparse.ArgumentParser(description='根据预排产库滚动生成未来下料和焊接排产计划')
    parser.add_argument('--pre-schedule-file', default=str(FILES['extract_input']), help='焊口预排产匹配结果文件')
    parser.add_argument('--weld-start-date', default=None, help='第一天焊接日期，默认明天，格式 YYYYMMDD 或 YYYY-MM-DD')
    parser.add_argument('--max-days', type=int, default=None, help='最多生成未来天数，默认直到可排焊口全部排完')
    parser.add_argument('--target-diameter', type=float, default=None, help='单张焊接排产单目标寸径')
    parser.add_argument('--orders-per-day', type=int, default=None, help='每天焊接排产单数量')
    parser.add_argument('--date-mode', choices=['auto', 'manual'], default='auto', help='日期生成方式：auto 自动生成，manual 使用手动焊接日期')
    parser.add_argument('--manual-weld-dates', default=None, help='手动焊接日期，多个日期用逗号分隔')
    parser.add_argument('--skip-holidays', action='store_true', help='跳过周六周日和指定节假日')
    parser.add_argument('--holiday-dates', default=None, help='节假日日期，多个日期用逗号分隔')
    parser.add_argument('--canceled-weekend-dates', default=None, help='取消跳过的周末日期，多个日期用逗号分隔')
    parser.add_argument('--cutting-lead-days', type=int, default=DEFAULT_CUTTING_LEAD_DAYS, help='下料日期相对焊接日期提前天数')
    args = parser.parse_args()

    result = generate_future_schedule(
        pre_schedule_file=args.pre_schedule_file,
        weld_start_date=args.weld_start_date,
        max_days=args.max_days,
        target_diameter=args.target_diameter,
        orders_per_day=args.orders_per_day,
        date_mode=args.date_mode,
        manual_weld_dates=args.manual_weld_dates,
        skip_holidays=args.skip_holidays,
        holiday_dates=args.holiday_dates,
        canceled_weekend_dates=args.canceled_weekend_dates,
        cutting_lead_days=args.cutting_lead_days,
    )
    _log(f"预排产焊口数：{result['pre_schedule_count']}")
    _log(f"已完成焊口数：{result['completed_weld_count']}")
    _log(f"本次生成焊口数：{result['planned_weld_count']}")
    _log(f"本次生成焊接天数：{result['planned_day_count']}")
    _log(f"总排产计划：{result['master_plan_file']}")


if __name__ == '__main__':
    main()
