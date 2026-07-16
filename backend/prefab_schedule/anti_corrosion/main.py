from pathlib import Path
import sys

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from common_utils import calculate_unit_area, prepare_area_input_columns
import schedule as future_schedule


MATERIAL_CODE_COL = '材料代码'
SPEC_COL = '规格'
THICKNESS_COL = '壁厚'
PIPE_STOCK_QTY_COL = '库存数量（米）'
FITTING_STOCK_QTY_COL = '库存数量'
SOURCE_TYPE_COL = '材料库类型'
QTY_COL = '委托数量'
UNIT_AREA_COL = '单位面积'
COMMISSION_AREA_COL = '委托面积'
COMPLETED_AREA_COL = '已完成面积'
PRE_SCHEDULE_STATUS_COL = '预排产状态'
PRE_SCHEDULE_SEQ_COL = '预排产序号'
ANTI_CORROSION_AREA_COL = '防腐面积'
COMMISSION_NO_COL = '防腐委托单号'
COMMISSION_DATE_COL = '委托日期'
MATCHED_STATUS = '可预排产'
COMMISSION_FILE_PREFIX = '防腐委托单'
COMMISSION_SHEET_NAME = '防腐委托单'

AREA_INPUT_COLUMNS = ['外径1', '壁厚1', '外径2', '壁厚2']
OUTPUT_AREA_COLUMNS = [UNIT_AREA_COL, COMMISSION_AREA_COL, COMPLETED_AREA_COL]


def _commission_date_sequence(
    commission_date=None,
    date_mode='auto',
    commission_start_date=None,
    manual_commission_dates=None,
    max_days=None,
    skip_holidays=False,
    holiday_dates=None,
    canceled_weekend_dates=None,
):
    if commission_date:
        date_value = future_schedule._parse_schedule_date(commission_date)
        while True:
            yield date_value

    date_mode = str(date_mode or 'auto').strip().lower()
    skip_holidays = future_schedule._to_bool(skip_holidays)
    holidays = set(future_schedule._split_date_list(holiday_dates))
    canceled_weekends = set(future_schedule._split_date_list(canceled_weekend_dates))
    if date_mode not in {'auto', 'manual'}:
        raise ValueError(f'日期生成方式无效：{date_mode}')
    if date_mode == 'manual':
        dates = future_schedule._manual_weld_dates(
            manual_commission_dates,
            skip_holidays,
            holidays,
            canceled_weekends,
        )
        if not dates:
            raise ValueError('手动选择日期为空，或已全部被节假日规则过滤')
        for date_value in dates:
            yield date_value
        return

    start_date = (
        future_schedule._parse_schedule_date(commission_start_date)
        if commission_start_date
        else pd.Timestamp.now().date()
    )
    yield from future_schedule._auto_weld_dates(start_date, max_days, skip_holidays, holidays, canceled_weekends)


def _next_commission_date_text(date_iter):
    try:
        return future_schedule._date_text(next(date_iter))
    except StopIteration:
        return None


def split_commission_files(summary_df):
    if summary_df is None or summary_df.empty:
        return []
    if COMMISSION_NO_COL not in summary_df.columns or COMMISSION_DATE_COL not in summary_df.columns:
        return [{
            'commission_no': '',
            'commission_date': '',
            'file_name': f'{COMMISSION_FILE_PREFIX}.xlsx',
            'dataframe': summary_df.copy(),
        }]

    files = []
    for commission_date, group_df in summary_df.groupby(COMMISSION_DATE_COL, sort=False, dropna=False):
        current_df = group_df.copy()
        commission_values = current_df[COMMISSION_NO_COL].dropna().astype(str).str.strip()
        commission_no = '、'.join(list(dict.fromkeys(value for value in commission_values if value)))
        files.append({
            'commission_no': commission_no,
            'commission_date': str(commission_date or '').strip(),
            'file_name': f'{COMMISSION_FILE_PREFIX}.xlsx',
            'dataframe': current_df,
        })
    return files


def build_anti_corrosion_commission_file_sheets(commission_df, match_detail_df=None):
    return {
        COMMISSION_SHEET_NAME: commission_df.copy() if commission_df is not None else pd.DataFrame(),
    }


def _build_pipe_commission_rows(pipe_df):
    if pipe_df is None or pipe_df.empty:
        return pd.DataFrame()

    out = pipe_df.copy()
    out[SOURCE_TYPE_COL] = '管子材料库'
    if PIPE_STOCK_QTY_COL in out.columns:
        out[QTY_COL] = pd.to_numeric(out[PIPE_STOCK_QTY_COL], errors='coerce').fillna(0)
    else:
        out[QTY_COL] = 0.0
    return out


def _build_fitting_commission_rows(fitting_df):
    if fitting_df is None or fitting_df.empty:
        return pd.DataFrame()

    out = fitting_df.copy()
    out[SOURCE_TYPE_COL] = '管件法兰材料库'
    if FITTING_STOCK_QTY_COL in out.columns:
        out[QTY_COL] = pd.to_numeric(out[FITTING_STOCK_QTY_COL], errors='coerce').fillna(0)
    else:
        out[QTY_COL] = 0.0
    return out


def build_anti_corrosion_commission_summary(pipe_df, fitting_df, precision=6):
    frames = [
        _build_pipe_commission_rows(pipe_df),
        _build_fitting_commission_rows(fitting_df),
    ]
    frames = [frame for frame in frames if frame is not None and not frame.empty]
    if not frames:
        return pd.DataFrame(columns=[SOURCE_TYPE_COL, QTY_COL] + OUTPUT_AREA_COLUMNS)

    summary_df = pd.concat(frames, ignore_index=True, sort=False)
    if MATERIAL_CODE_COL not in summary_df.columns:
        summary_df[MATERIAL_CODE_COL] = ''
    summary_df[MATERIAL_CODE_COL] = summary_df[MATERIAL_CODE_COL].astype(str).str.strip()
    summary_df = prepare_area_input_columns(summary_df, SPEC_COL, THICKNESS_COL)
    summary_df[UNIT_AREA_COL] = summary_df.apply(calculate_unit_area, axis=1).round(precision)
    summary_df[COMMISSION_AREA_COL] = (summary_df[UNIT_AREA_COL] * summary_df[QTY_COL]).round(precision)
    summary_df[COMPLETED_AREA_COL] = 0.0

    leading_cols = [SOURCE_TYPE_COL, MATERIAL_CODE_COL, QTY_COL] + OUTPUT_AREA_COLUMNS
    dimension_cols = [col for col in AREA_INPUT_COLUMNS if col in summary_df.columns]
    remaining_cols = [col for col in summary_df.columns if col not in leading_cols + dimension_cols]
    return summary_df[leading_cols + dimension_cols + remaining_cols]


def build_anti_corrosion_commission_from_pre_schedule(
    pre_schedule_df,
    commission_area=1500,
    commission_date=None,
    date_mode='auto',
    commission_start_date=None,
    manual_commission_dates=None,
    max_days=None,
    skip_holidays=False,
    holiday_dates=None,
    canceled_weekend_dates=None,
    precision=6,
    apply_area_limit=True,
    split_by_area=False,
    max_commission_count=None,
):
    if pre_schedule_df is None or pre_schedule_df.empty:
        return pd.DataFrame(columns=[
            COMMISSION_NO_COL,
            COMMISSION_DATE_COL,
            ANTI_CORROSION_AREA_COL,
        ])

    work_df = pre_schedule_df.copy()
    if PRE_SCHEDULE_STATUS_COL in work_df.columns:
        work_df = work_df.loc[
            work_df[PRE_SCHEDULE_STATUS_COL].fillna('').astype(str).str.strip().eq(MATCHED_STATUS)
        ].copy()
    if work_df.empty:
        return pd.DataFrame(columns=[
            COMMISSION_NO_COL,
            COMMISSION_DATE_COL,
            ANTI_CORROSION_AREA_COL,
        ])

    if ANTI_CORROSION_AREA_COL not in work_df.columns:
        work_df[ANTI_CORROSION_AREA_COL] = 0.0
    area_series = pd.to_numeric(work_df[ANTI_CORROSION_AREA_COL], errors='coerce').fillna(0.0)
    work_df[ANTI_CORROSION_AREA_COL] = area_series.round(precision)

    area_limit = None
    if commission_area not in (None, ''):
        area_limit = float(commission_area)
        if area_limit <= 0:
            raise ValueError('委托单防腐面积必须大于 0')

    date_iter = iter(_commission_date_sequence(
        commission_date=commission_date,
        date_mode=date_mode,
        commission_start_date=commission_start_date,
        manual_commission_dates=manual_commission_dates,
        max_days=max_days,
        skip_holidays=skip_holidays,
        holiday_dates=holiday_dates,
        canceled_weekend_dates=canceled_weekend_dates,
    ))
    fallback_date_text = str(commission_date or pd.Timestamp.now().strftime('%Y%m%d')).strip()
    if split_by_area:
        max_count = None
        if max_commission_count not in (None, ''):
            max_count = int(max_commission_count)
            if max_count <= 0:
                raise ValueError('委托单数量必须大于 0')

        picked_frames = []
        current_indexes = []
        running_area = 0.0
        commission_index = 1

        def append_current_group():
            nonlocal commission_index
            if not current_indexes:
                return True
            date_text = _next_commission_date_text(date_iter)
            if not date_text:
                return False
            group_df = work_df.loc[current_indexes].copy()
            group_df.insert(0, COMMISSION_NO_COL, f'FFWT-{date_text}-{commission_index:03d}')
            group_df.insert(1, COMMISSION_DATE_COL, date_text)
            picked_frames.append(group_df)
            commission_index += 1
            return True

        for index, area in work_df[ANTI_CORROSION_AREA_COL].items():
            next_area = float(area)
            if area_limit and current_indexes and running_area + next_area > area_limit:
                if not append_current_group():
                    current_indexes = []
                    break
                if max_count is not None and len(picked_frames) >= max_count:
                    current_indexes = []
                    break
                current_indexes = []
                running_area = 0.0
            current_indexes.append(index)
            running_area += next_area
            if area_limit and running_area >= area_limit:
                if not append_current_group():
                    current_indexes = []
                    break
                if max_count is not None and len(picked_frames) >= max_count:
                    current_indexes = []
                    break
                current_indexes = []
                running_area = 0.0
        append_current_group()
        work_df = pd.concat(picked_frames, ignore_index=True, sort=False) if picked_frames else work_df.iloc[0:0].copy()
    elif apply_area_limit and area_limit:
        picked_indexes = []
        running_area = 0.0
        for index, area in work_df[ANTI_CORROSION_AREA_COL].items():
            next_area = float(area)
            if picked_indexes and running_area + next_area > area_limit:
                break
            picked_indexes.append(index)
            running_area += next_area
            if running_area >= area_limit:
                break
        work_df = work_df.loc[picked_indexes].copy()

    date_text = fallback_date_text
    if COMMISSION_NO_COL not in work_df.columns or COMMISSION_DATE_COL not in work_df.columns:
        date_text = _next_commission_date_text(date_iter) or fallback_date_text
    if COMMISSION_NO_COL not in work_df.columns:
        work_df.insert(0, COMMISSION_NO_COL, f'FFWT-{date_text}-001')
    if COMMISSION_DATE_COL not in work_df.columns:
        work_df.insert(1, COMMISSION_DATE_COL, date_text)
    leading_cols = [
        COMMISSION_NO_COL,
        COMMISSION_DATE_COL,
        PRE_SCHEDULE_SEQ_COL,
        ANTI_CORROSION_AREA_COL,
    ]
    leading_cols = [col for col in leading_cols if col in work_df.columns]
    remaining_cols = [col for col in work_df.columns if col not in leading_cols]
    return work_df[leading_cols + remaining_cols]
