from pathlib import Path
import sys

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
CUTTING_DIR = Path(__file__).resolve().parent
for path in [ROOT_DIR, CUTTING_DIR]:
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from common_utils import normalize_columns, prepare_output_file
from cutting.cutting_config import (
    COLUMNS,
    CUTTING_FILES,
    DEFAULT_PRIORITY,
    EXTRA_MATERIAL_QTY_FOR_P,
    MATCH_REASON_COL,
    MATCH_RESULT_COL,
    MATCH_SEQ_COL,
    MATCH_TYPE_COL,
    MATCHED_RESOURCE_COL,
    MATCHED_STATUS,
    CONSUMED_LENGTHS_COL,
    CUT_LENGTHS_COL,
    CUT_LOSSES_COL,
    FITTING_STOCK_QTY_COL,
    MATERIAL_CODE_COL,
    MATERIAL_UNIQUE_COL,
    PIPE_UNIQUE_CODE_COL,
    PRE_SCHEDULE_DETAIL_COLUMNS,
    PRE_SCHEDULE_ONLY_AUTO_WELD,
    REASON_COL,
    REMAINING_LENGTH_COL,
    SHORTAGE_STATUS,
    STATUS_COL,
)
import main as cutting_main


DEFAULT_PIPELINE_CONCENTRATION_DIMENSION = 'segment'
DEFAULT_PIPELINE_CONCENTRATION_THRESHOLD_PERCENT = 50
PIPELINE_CONCENTRATION_DIMENSIONS = {'segment', 'weld'}
PIPELINE_CONCENTRATION_REASON = '同管线预排产集中度低于设定阈值'
GROUP_SHORTAGE_RATIO_THRESHOLD = 0.5
GROUP_SHORTAGE_REASON = '同单元同管线分组中多数焊口无法匹配，整组不进行预排产'
ORDINARY_POOL = '普通'
ANTI_CORROSION_POOL = '防腐'
INVENTORY_POOL_KEY = '库存类型'


def _read_excel_or_empty(file_path):
    file_path = Path(file_path)
    if not file_path.exists() or file_path.stat().st_size == 0:
        return pd.DataFrame()
    return normalize_columns(pd.read_excel(file_path))


def _normalize_pipe_library_or_empty(dataframe):
    if dataframe is None or dataframe.empty:
        dataframe = pd.DataFrame(columns=[MATERIAL_CODE_COL, PIPE_UNIQUE_CODE_COL, '库存数量（米）'])
    return cutting_main._normalize_pipe_library(dataframe)


def _normalize_fitting_library_or_empty(dataframe):
    if dataframe is None or dataframe.empty:
        dataframe = pd.DataFrame(columns=[MATERIAL_CODE_COL, FITTING_STOCK_QTY_COL])
    return cutting_main._normalize_fitting_library(dataframe)


def _to_bool_series(series):
    true_values = {
        'true', '1', 'yes', 'y', '是', '真', '完成', '已完成', 'done', 'finished',
        '到货', '已到货', '防腐完成', '已防腐', '下料完成', '已下料',
    }
    false_values = {
        'false', '0', 'no', 'n', '否', '假', '未完成', '进行中', 'pending', '',
        '未到货', '到货未完成', '未防腐', '防腐未完成', '未下料', '下料未完成',
    }
    normalized = series.fillna('').astype(str).str.strip().str.lower()
    out = pd.Series(False, index=series.index)
    out.loc[normalized.isin(true_values)] = True
    out.loc[normalized.isin(false_values)] = False
    return out


def _format_joined(values):
    cleaned = [str(value).strip() for value in values if pd.notna(value) and str(value).strip() != '']
    return '、'.join(cleaned)


def _copy_pipe_state(state):
    copied = state.copy()
    copied['cut_list'] = list(state.get('cut_list', []))
    copied['loss_list'] = list(state.get('loss_list', []))
    copied['consumed_list'] = list(state.get('consumed_list', []))
    return copied


def _copy_all_pipe_states(pipe_states):
    return {
        material_code: [_copy_pipe_state(state) for state in states]
        for material_code, states in pipe_states.items()
    }


def _append_reason(current_reason, reason):
    return _format_joined([current_reason, reason])


def normalize_pipeline_concentration_options(dimension=None, threshold_percent=None):
    dimension = str(dimension or DEFAULT_PIPELINE_CONCENTRATION_DIMENSION).strip().lower()
    if dimension not in PIPELINE_CONCENTRATION_DIMENSIONS:
        raise ValueError(f'管线集中度维度无效：{dimension}')
    if threshold_percent is None or threshold_percent == '':
        threshold_percent = DEFAULT_PIPELINE_CONCENTRATION_THRESHOLD_PERCENT
    try:
        threshold = float(threshold_percent)
    except (TypeError, ValueError) as error:
        raise ValueError('管线集中度百分比必须是数字') from error
    if threshold < 0 or threshold > 100:
        raise ValueError('管线集中度百分比必须在 0 到 100 之间')
    return dimension, threshold


def _pipeline_concentration_ratio(rows, dimension):
    rows = list(rows or [])
    if not rows:
        return 1.0
    if dimension == 'weld':
        matched_count = sum(
            1
            for row in rows
            if str(row.get(STATUS_COL, '')).strip() == MATCHED_STATUS
        )
        return matched_count / len(rows)

    segment_col = COLUMNS['segment_no']
    all_segments = {
        str(row.get(segment_col, '')).strip()
        for row in rows
        if str(row.get(segment_col, '')).strip()
    }
    if not all_segments:
        return _pipeline_concentration_ratio(rows, 'weld')
    matched_segments = {
        str(row.get(segment_col, '')).strip()
        for row in rows
        if str(row.get(segment_col, '')).strip()
        and str(row.get(STATUS_COL, '')).strip() == MATCHED_STATUS
    }
    return len(matched_segments) / len(all_segments)


def _meets_pipeline_concentration(rows, dimension=None, threshold_percent=None):
    dimension, threshold = normalize_pipeline_concentration_options(dimension, threshold_percent)
    ratio = _pipeline_concentration_ratio(rows, dimension)
    return ratio * 100 >= threshold


def _reject_pipeline_rows(rows, reason=PIPELINE_CONCENTRATION_REASON):
    rejected_rows = []
    all_rows = []
    for row in rows:
        row_out = row.copy()
        row_out[MATCH_SEQ_COL] = ''
        row_out[STATUS_COL] = SHORTAGE_STATUS
        row_out[REASON_COL] = _append_reason(row_out.get(REASON_COL, ''), reason)
        rejected_rows.append(row_out)
        all_rows.append(row_out.copy())
    return rejected_rows, all_rows


def _base_detail(row, seq, material_type, demand, result, reason=''):
    pool_name = demand.get(INVENTORY_POOL_KEY, '')
    display_type = f'{pool_name}{material_type}' if pool_name else material_type
    return {
        MATCH_SEQ_COL: seq,
        COLUMNS['library_seq']: row.get(COLUMNS['library_seq'], ''),
        COLUMNS['weld_priority']: row.get(COLUMNS['weld_priority'], DEFAULT_PRIORITY),
        COLUMNS['unit']: row.get(COLUMNS['unit'], ''),
        COLUMNS['pipeline']: row.get(COLUMNS['pipeline'], ''),
        COLUMNS['segment_no']: row.get(COLUMNS['segment_no'], ''),
        COLUMNS['weld_no_start']: row.get(COLUMNS['weld_no_start'], ''),
        COLUMNS['weld_no_final']: row.get(COLUMNS['weld_no_final'], ''),
        MATCH_TYPE_COL: display_type,
        MATERIAL_CODE_COL: demand.get(MATERIAL_CODE_COL, ''),
        MATERIAL_UNIQUE_COL: demand.get(MATERIAL_UNIQUE_COL, ''),
        MATCH_RESULT_COL: result,
        MATCH_REASON_COL: reason,
    }


def _build_weld_material_demands(row):
    pipe_demands = []
    fitting_demands = []

    for side in (1, 2):
        material_no = str(row.get(COLUMNS[f'material_no_{side}'], '')).strip().upper()
        material_code = str(row.get(COLUMNS[f'material_code_{side}'], '')).strip()
        material_unique = str(row.get(COLUMNS[f'material_unique_{side}'], '')).strip()
        material_paint = str(row.get(COLUMNS[f'paint_{side}'], '')).strip().upper()
        qty = pd.to_numeric(row.get(COLUMNS[f'qty_{side}']), errors='coerce')

        if material_code == '' or pd.isna(qty) or float(qty) <= 0:
            continue

        demand = {
            MATERIAL_CODE_COL: material_code,
            MATERIAL_UNIQUE_COL: material_unique,
            '需求数量': float(qty),
            INVENTORY_POOL_KEY: ANTI_CORROSION_POOL if material_paint.startswith('PA') else ORDINARY_POOL,
        }
        if material_no == 'P':
            pipe_demands.append(demand)
        else:
            fitting_demands.append(demand)

    return pipe_demands, fitting_demands


def _demands_for_pool(demands, pool_name):
    return [demand for demand in demands if demand.get(INVENTORY_POOL_KEY) == pool_name]


def _aggregate_fitting_demands(fitting_demands):
    if not fitting_demands:
        return []

    demand_df = pd.DataFrame(fitting_demands)
    group_cols = [MATERIAL_CODE_COL]
    if INVENTORY_POOL_KEY in demand_df.columns:
        group_cols.append(INVENTORY_POOL_KEY)
    grouped = (
        demand_df.groupby(group_cols, as_index=False)
        .agg({
            MATERIAL_UNIQUE_COL: _format_joined,
            '需求数量': 'sum',
        })
    )
    return grouped.to_dict('records')


def _build_pipe_states(pipe_df):
    states = {}
    for idx, pipe_row in pipe_df.iterrows():
        material_code = str(pipe_row.get(MATERIAL_CODE_COL, '')).strip()
        if material_code == '':
            continue
        remaining = pd.to_numeric(pipe_row.get(REMAINING_LENGTH_COL), errors='coerce')
        cut_list = cutting_main._parse_cut_lengths(pipe_row.get(CUT_LENGTHS_COL, '[]'))
        loss_list = cutting_main._parse_cut_lengths(pipe_row.get(CUT_LOSSES_COL, '[]'))
        consumed_list = cutting_main._parse_cut_lengths(pipe_row.get(CONSUMED_LENGTHS_COL, '[]'))
        state = {
            'index': idx,
            'pipe_no': pipe_row.get(PIPE_UNIQUE_CODE_COL, ''),
            'remaining': float(remaining) if pd.notna(remaining) else 0.0,
            'has_prior_cuts': bool(consumed_list),
            'cut_list': cut_list,
            'loss_list': loss_list,
            'consumed_list': consumed_list,
        }
        states.setdefault(material_code, []).append(state)
    return states


def _build_fitting_stock(fitting_df):
    if fitting_df.empty:
        return {}
    stock_series = (
        fitting_df.assign(_material_code=fitting_df[MATERIAL_CODE_COL].astype(str).str.strip())
        .groupby('_material_code')[FITTING_STOCK_QTY_COL]
        .sum()
    )
    return {str(code): float(qty) for code, qty in stock_series.items()}


def _copy_pipe_states_for_demands(pipe_states, pipe_demands):
    material_codes = {str(demand[MATERIAL_CODE_COL]).strip() for demand in pipe_demands}
    return {
        material_code: [_copy_pipe_state(state) for state in pipe_states.get(material_code, [])]
        for material_code in material_codes
    }


def _try_allocate_pipe_demands(row, seq, pipe_demands, pipe_states, precision=3):
    if not pipe_demands:
        return True, {}, []

    working_states = _copy_pipe_states_for_demands(pipe_states, pipe_demands)
    detail_rows = []
    demands = sorted(
        pipe_demands,
        key=lambda demand: (str(demand[MATERIAL_CODE_COL]), -float(demand['需求数量'])),
    )

    for demand in demands:
        material_code = str(demand[MATERIAL_CODE_COL]).strip()
        length = round(float(demand['需求数量']), precision)
        candidates = working_states.get(material_code, [])
        if not candidates:
            detail = _base_detail(row, seq, '管子', demand, SHORTAGE_STATUS, '无匹配材料代码')
            detail.update({'需求数量': length, '匹配数量': 0, '缺料数量': length, MATCHED_RESOURCE_COL: ''})
            detail_rows.append(detail)
            return False, {}, detail_rows

        feasible = []
        for pos, state in enumerate(candidates):
            before_remaining = round(float(state['remaining']), precision)
            consumed_length, allowance = cutting_main._calculate_consumed_length(
                before_remaining,
                length,
                EXTRA_MATERIAL_QTY_FOR_P,
                precision,
                has_prior_cuts=state['has_prior_cuts'],
            )
            if before_remaining >= consumed_length:
                feasible.append((round(consumed_length, precision), round(before_remaining - consumed_length, precision), pos, allowance))

        if not feasible:
            detail = _base_detail(row, seq, '管子', demand, SHORTAGE_STATUS, '加切割余量后剩余长度不足')
            detail.update({'需求数量': length, '匹配数量': 0, '缺料数量': length, MATCHED_RESOURCE_COL: ''})
            detail_rows.append(detail)
            return False, {}, detail_rows

        consumed_length, after_remaining, best_pos, allowance = sorted(feasible, key=lambda item: (item[0], item[1]))[0]
        candidates[best_pos]['remaining'] = after_remaining
        candidates[best_pos]['has_prior_cuts'] = True
        candidates[best_pos]['cut_list'].append(length)
        candidates[best_pos]['loss_list'].append(allowance)
        candidates[best_pos]['consumed_list'].append(consumed_length)

        detail = _base_detail(row, seq, '管子', demand, MATCHED_STATUS, f'占用{consumed_length:g}米，余量{allowance:g}米')
        detail.update({
            '需求数量': length,
            '匹配数量': length,
            '缺料数量': 0,
            MATCHED_RESOURCE_COL: candidates[best_pos]['pipe_no'],
        })
        detail_rows.append(detail)

    return True, working_states, detail_rows


def _copy_fitting_stock_for_demands(fitting_stock, fitting_demands):
    material_codes = {str(demand[MATERIAL_CODE_COL]).strip() for demand in fitting_demands}
    return {material_code: float(fitting_stock.get(material_code, 0)) for material_code in material_codes}


def _try_allocate_fitting_demands(row, seq, fitting_demands, fitting_stock):
    aggregated_demands = _aggregate_fitting_demands(fitting_demands)
    if not aggregated_demands:
        return True, {}, []

    working_stock = _copy_fitting_stock_for_demands(fitting_stock, aggregated_demands)
    detail_rows = []

    for demand in aggregated_demands:
        material_code = str(demand[MATERIAL_CODE_COL]).strip()
        demand_qty = float(demand['需求数量'])
        stock_qty = float(working_stock.get(material_code, 0))

        if stock_qty < demand_qty:
            detail = _base_detail(row, seq, '管件法兰', demand, SHORTAGE_STATUS, '防腐管件法兰库存不足')
            detail.update({'需求数量': demand_qty, '匹配数量': max(stock_qty, 0), '缺料数量': demand_qty - max(stock_qty, 0), MATCHED_RESOURCE_COL: ''})
            detail_rows.append(detail)
            return False, {}, detail_rows

        working_stock[material_code] = stock_qty - demand_qty

        detail = _base_detail(row, seq, '管件法兰', demand, MATCHED_STATUS, '库存数量满足')
        detail.update({
            '需求数量': demand_qty,
            '匹配数量': demand_qty,
            '缺料数量': 0,
            MATCHED_RESOURCE_COL: material_code,
        })
        detail_rows.append(detail)

    return True, working_stock, detail_rows


def _prepare_uncompleted_welds(weld_df, only_auto_weld=None):
    weld_df = weld_df.copy()
    completed_col = COLUMNS['completed_flag']
    priority_col = COLUMNS['weld_priority']
    seq_col = COLUMNS['library_seq']

    if completed_col not in weld_df.columns:
        weld_df[completed_col] = False
    if priority_col not in weld_df.columns:
        weld_df[priority_col] = DEFAULT_PRIORITY
    if seq_col not in weld_df.columns:
        weld_df.insert(0, seq_col, range(1, len(weld_df) + 1))

    weld_df[completed_col] = _to_bool_series(weld_df[completed_col])
    weld_df[priority_col] = pd.to_numeric(weld_df[priority_col], errors='coerce').fillna(DEFAULT_PRIORITY).astype(int)
    weld_df[seq_col] = weld_df[seq_col].fillna('').astype(str).str.strip()
    weld_df['_library_seq_sort'] = weld_df[seq_col].map(_library_seq_sort_key)

    uncompleted_df = weld_df.loc[~weld_df[completed_col]].copy()
    if only_auto_weld is None:
        only_auto_weld = PRE_SCHEDULE_ONLY_AUTO_WELD
    if only_auto_weld:
        weld_method_col = COLUMNS['weld_method']
        if weld_method_col not in uncompleted_df.columns:
            return uncompleted_df.iloc[0:0].copy()
        uncompleted_df = uncompleted_df.loc[
            uncompleted_df[weld_method_col].fillna('').astype(str).str.strip() == '自动焊'
        ].copy()
    return (
        uncompleted_df
        .sort_values([priority_col, '_library_seq_sort'], ascending=[False, True], kind='mergesort')
        .drop(columns=['_library_seq_sort'])
        .reset_index(drop=True)
    )


def _filter_truthy_statuses(dataframe, status_columns):
    filtered = dataframe.copy()
    for column in status_columns:
        if column not in filtered.columns:
            return filtered.iloc[0:0].copy()
        filtered = filtered.loc[_to_bool_series(filtered[column])].copy()
        if filtered.empty:
            break
    return filtered


def _prepare_cutting_candidate_welds(weld_df, only_auto_weld=None, ignore_anti_corrosion_status=False):
    candidate_df = _prepare_uncompleted_welds(weld_df, only_auto_weld=only_auto_weld)
    status_columns = [COLUMNS['material_arrival_status']]
    if not ignore_anti_corrosion_status:
        status_columns.append(COLUMNS['material_anti_corrosion_status'])
    return _filter_truthy_statuses(candidate_df, status_columns)


def _library_seq_sort_key(value):
    text = str(value or '').strip()
    number = pd.to_numeric(text, errors='coerce')
    if pd.notna(number):
        return (0, int(number), text)
    return (1, text)


def _simulate_group_matches(group_df, pipe_states, fitting_stock, start_seq):
    group_pipe_states = _copy_all_pipe_states(pipe_states)
    group_fitting_stock = fitting_stock.copy()
    accepted_rows = []
    rejected_rows = []
    all_rows = []
    detail_rows = []
    match_seq = start_seq

    for _, row in group_df.iterrows():
        pipe_demands, fitting_demands = _build_weld_material_demands(row)
        pipe_ok, next_pipe_states, pipe_details = _try_allocate_pipe_demands(row, match_seq, pipe_demands, group_pipe_states)
        fitting_ok = False
        next_fitting_stock = {}
        fitting_details = []

        if pipe_ok:
            fitting_ok, next_fitting_stock, fitting_details = _try_allocate_fitting_demands(row, match_seq, fitting_demands, group_fitting_stock)

        row_out = row.to_dict()
        row_detail = pipe_details + fitting_details
        detail_rows.extend(row_detail)

        if pipe_ok and fitting_ok:
            row_out[MATCH_SEQ_COL] = match_seq
            row_out[STATUS_COL] = MATCHED_STATUS
            row_out[REASON_COL] = ''
            accepted_rows.append(row_out)
            all_rows.append(row_out.copy())
            group_pipe_states.update(next_pipe_states)
            group_fitting_stock.update(next_fitting_stock)
            match_seq += 1
        else:
            reasons = [detail.get(MATCH_REASON_COL, '') for detail in row_detail if detail.get(MATCH_RESULT_COL) == SHORTAGE_STATUS]
            row_out[MATCH_SEQ_COL] = ''
            row_out[STATUS_COL] = SHORTAGE_STATUS
            row_out[REASON_COL] = _format_joined(reasons)
            rejected_rows.append(row_out)
            all_rows.append(row_out.copy())

    return {
        'accepted_rows': accepted_rows,
        'rejected_rows': rejected_rows,
        'all_rows': all_rows,
        'detail_rows': detail_rows,
        'pipe_states': group_pipe_states,
        'fitting_stock': group_fitting_stock,
        'next_seq': match_seq,
    }


def _simulate_group_matches_by_inventory(
    group_df,
    pipe_states_by_pool,
    fitting_stock_by_pool,
    start_seq,
):
    group_pipe_states = {
        pool: _copy_all_pipe_states(states)
        for pool, states in pipe_states_by_pool.items()
    }
    group_fitting_stock = {
        pool: stock.copy()
        for pool, stock in fitting_stock_by_pool.items()
    }
    accepted_rows = []
    rejected_rows = []
    all_rows = []
    detail_rows = []
    match_seq = start_seq

    for _, row in group_df.iterrows():
        pipe_demands, fitting_demands = _build_weld_material_demands(row)
        next_pipe_states = {
            pool: _copy_all_pipe_states(states)
            for pool, states in group_pipe_states.items()
        }
        next_fitting_stock = {
            pool: stock.copy()
            for pool, stock in group_fitting_stock.items()
        }
        row_details = []
        row_ok = True

        for pool in (ORDINARY_POOL, ANTI_CORROSION_POOL):
            pool_pipe_demands = _demands_for_pool(pipe_demands, pool)
            pipe_ok, updated_pipe_states, pipe_details = _try_allocate_pipe_demands(
                row,
                match_seq,
                pool_pipe_demands,
                next_pipe_states[pool],
            )
            row_details.extend(pipe_details)
            if pipe_ok:
                next_pipe_states[pool].update(updated_pipe_states)

            pool_fitting_demands = _demands_for_pool(fitting_demands, pool)
            fitting_ok = False
            updated_fitting_stock = {}
            fitting_details = []
            if pipe_ok:
                fitting_ok, updated_fitting_stock, fitting_details = _try_allocate_fitting_demands(
                    row,
                    match_seq,
                    pool_fitting_demands,
                    next_fitting_stock[pool],
                )
            row_details.extend(fitting_details)
            if fitting_ok:
                next_fitting_stock[pool].update(updated_fitting_stock)
            if not pipe_ok or not fitting_ok:
                row_ok = False

        row_out = row.to_dict()
        detail_rows.extend(row_details)
        if row_ok:
            row_out[MATCH_SEQ_COL] = match_seq
            row_out[STATUS_COL] = MATCHED_STATUS
            row_out[REASON_COL] = ''
            accepted_rows.append(row_out)
            all_rows.append(row_out.copy())
            group_pipe_states = next_pipe_states
            group_fitting_stock = next_fitting_stock
            match_seq += 1
        else:
            reasons = [
                detail.get(MATCH_REASON_COL, '')
                for detail in row_details
                if detail.get(MATCH_RESULT_COL) == SHORTAGE_STATUS
            ]
            row_out[MATCH_SEQ_COL] = ''
            row_out[STATUS_COL] = SHORTAGE_STATUS
            row_out[REASON_COL] = _format_joined(reasons)
            rejected_rows.append(row_out)
            all_rows.append(row_out.copy())

    return {
        'accepted_rows': accepted_rows,
        'rejected_rows': rejected_rows,
        'all_rows': all_rows,
        'detail_rows': detail_rows,
        'pipe_states_by_pool': group_pipe_states,
        'fitting_stock_by_pool': group_fitting_stock,
        'next_seq': match_seq,
    }


def _group_should_be_rejected(group_result):
    total_count = len(group_result['all_rows'])
    if total_count == 0:
        return False
    shortage_count = len(group_result['rejected_rows'])
    return shortage_count / total_count > GROUP_SHORTAGE_RATIO_THRESHOLD


def _reject_group_rows(group_result):
    rejected_rows = []
    all_rows = []

    for row in group_result['all_rows']:
        row_out = row.copy()
        row_out[MATCH_SEQ_COL] = ''
        row_out[STATUS_COL] = SHORTAGE_STATUS
        row_out[REASON_COL] = _append_reason(row_out.get(REASON_COL, ''), GROUP_SHORTAGE_REASON)
        rejected_rows.append(row_out)
        all_rows.append(row_out.copy())

    return rejected_rows, all_rows


def _apply_pipe_states_to_df(pipe_df, pipe_states, precision=3):
    updated_df = pipe_df.copy()
    for states in pipe_states.values():
        for state in states:
            idx = state['index']
            if idx not in updated_df.index:
                continue
            updated_df.at[idx, CUT_LENGTHS_COL] = cutting_main._format_cut_lengths(state.get('cut_list', []))
            updated_df.at[idx, CUT_LOSSES_COL] = cutting_main._format_cut_lengths(state.get('loss_list', []))
            updated_df.at[idx, CONSUMED_LENGTHS_COL] = cutting_main._format_cut_lengths(state.get('consumed_list', []))
            updated_df.at[idx, REMAINING_LENGTH_COL] = round(float(state.get('remaining', 0)), precision)
    return updated_df


def _apply_fitting_stock_to_df(fitting_df, fitting_stock):
    updated_df = fitting_df.copy()
    for material_code, group in updated_df.groupby(updated_df[MATERIAL_CODE_COL].astype(str).str.strip(), sort=False):
        row_stocks = pd.to_numeric(group[FITTING_STOCK_QTY_COL], errors='coerce').fillna(0).astype(float)
        consumed_qty = max(float(row_stocks.sum()) - float(fitting_stock.get(material_code, 0)), 0)
        for idx in group.index:
            row_stock = float(row_stocks.at[idx])
            consume_qty = min(row_stock, consumed_qty)
            updated_df.at[idx, FITTING_STOCK_QTY_COL] = row_stock - consume_qty
            consumed_qty -= consume_qty
    return updated_df


def match_weld_pre_schedule(
    weld_library_file=CUTTING_FILES['weld_library'],
    pipe_library_file=CUTTING_FILES['pipe_library'],
    fitting_library_file=CUTTING_FILES['fitting_library'],
    anti_corrosion_pipe_library_file=CUTTING_FILES['anti_corrosion_pipe_library'],
    anti_corrosion_fitting_library_file=CUTTING_FILES['anti_corrosion_fitting_library'],
    output_file=CUTTING_FILES['weld_pre_schedule_output'],
    pending_pipe_library_file=CUTTING_FILES['pending_pipe_library'],
    pending_fitting_library_file=CUTTING_FILES['pending_fitting_library'],
    pending_anti_corrosion_pipe_library_file=CUTTING_FILES['pending_anti_corrosion_pipe_library'],
    pending_anti_corrosion_fitting_library_file=CUTTING_FILES['pending_anti_corrosion_fitting_library'],
    only_auto_weld=None,
    ignore_anti_corrosion_status=False,
    concentration_dimension=None,
    concentration_threshold_percent=None,
):
    concentration_dimension, concentration_threshold_percent = normalize_pipeline_concentration_options(
        concentration_dimension,
        concentration_threshold_percent,
    )
    weld_df = _read_excel_or_empty(weld_library_file)
    if weld_df.empty:
        raise ValueError(f'焊口库为空，无法匹配预排产焊口：{weld_library_file}')

    pipe_dfs = {
        ORDINARY_POOL: _normalize_pipe_library_or_empty(_read_excel_or_empty(pipe_library_file)),
        ANTI_CORROSION_POOL: _normalize_pipe_library_or_empty(_read_excel_or_empty(anti_corrosion_pipe_library_file)),
    }
    fitting_dfs = {
        ORDINARY_POOL: _normalize_fitting_library_or_empty(_read_excel_or_empty(fitting_library_file)),
        ANTI_CORROSION_POOL: _normalize_fitting_library_or_empty(_read_excel_or_empty(anti_corrosion_fitting_library_file)),
    }
    pipe_states_by_pool = {
        pool: _build_pipe_states(dataframe)
        for pool, dataframe in pipe_dfs.items()
    }
    fitting_stock_by_pool = {
        pool: _build_fitting_stock(dataframe)
        for pool, dataframe in fitting_dfs.items()
    }
    candidate_df = _prepare_cutting_candidate_welds(
        weld_df,
        only_auto_weld=only_auto_weld,
        ignore_anti_corrosion_status=ignore_anti_corrosion_status,
    )

    accepted_rows = []
    rejected_rows = []
    all_rows = []
    detail_rows = []
    match_seq = 1

    group_cols = [COLUMNS['unit'], COLUMNS['pipeline']]
    for _, group_df in candidate_df.groupby(group_cols, sort=False, dropna=False):
        group_result = _simulate_group_matches_by_inventory(
            group_df,
            pipe_states_by_pool,
            fitting_stock_by_pool,
            match_seq,
        )
        detail_rows.extend(group_result['detail_rows'])

        if not _meets_pipeline_concentration(
            group_result['all_rows'],
            concentration_dimension,
            concentration_threshold_percent,
        ):
            group_rejected_rows, group_all_rows = _reject_pipeline_rows(group_result['all_rows'])
            rejected_rows.extend(group_rejected_rows)
            all_rows.extend(group_all_rows)
            continue

        accepted_rows.extend(group_result['accepted_rows'])
        rejected_rows.extend(group_result['rejected_rows'])
        all_rows.extend(group_result['all_rows'])
        pipe_states_by_pool = group_result['pipe_states_by_pool']
        fitting_stock_by_pool = group_result['fitting_stock_by_pool']
        match_seq = group_result['next_seq']

    all_df = pd.DataFrame(all_rows)
    accepted_df = pd.DataFrame(accepted_rows)
    rejected_df = pd.DataFrame(rejected_rows)
    detail_df = pd.DataFrame(detail_rows, columns=PRE_SCHEDULE_DETAIL_COLUMNS)

    prepare_output_file(output_file)
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        all_df.to_excel(writer, sheet_name='预排产匹配结果', index=False)
        detail_df.to_excel(writer, sheet_name='材料匹配明细', index=False)

    pending_files = {
        ORDINARY_POOL: (pending_pipe_library_file, pending_fitting_library_file),
        ANTI_CORROSION_POOL: (
            pending_anti_corrosion_pipe_library_file,
            pending_anti_corrosion_fitting_library_file,
        ),
    }
    for pool, (pending_pipe_file, pending_fitting_file) in pending_files.items():
        updated_pipe_df = _apply_pipe_states_to_df(pipe_dfs[pool], pipe_states_by_pool[pool])
        prepare_output_file(pending_pipe_file)
        updated_pipe_df.to_excel(pending_pipe_file, index=False)

        updated_fitting_df = _apply_fitting_stock_to_df(fitting_dfs[pool], fitting_stock_by_pool[pool])
        prepare_output_file(pending_fitting_file)
        updated_fitting_df.to_excel(pending_fitting_file, index=False)

    return {
        'candidate_count': len(candidate_df),
        'pre_schedule_count': len(accepted_df),
        'rejected_count': len(rejected_df),
        'detail_count': len(detail_df),
        'output_file': Path(output_file),
        'pending_pipe_library': Path(pending_pipe_library_file),
        'pending_fitting_library': Path(pending_fitting_library_file),
        'pending_anti_corrosion_pipe_library': Path(pending_anti_corrosion_pipe_library_file),
        'pending_anti_corrosion_fitting_library': Path(pending_anti_corrosion_fitting_library_file),
    }


if __name__ == '__main__':
    result = match_weld_pre_schedule()
    print(f"未完成焊口数：{result['candidate_count']}")
    print(f"可进入预排产焊口数：{result['pre_schedule_count']}")
    print(f"不可预排产焊口数：{result['rejected_count']}")
    print(f"材料匹配明细数：{result['detail_count']}")
    print(f"焊口预排产匹配结果：{result['output_file']}")
    print(f"待确认普通管子材料库：{result['pending_pipe_library']}")
    print(f"待确认普通管件法兰材料库：{result['pending_fitting_library']}")
    print(f"待确认防腐管子材料库：{result['pending_anti_corrosion_pipe_library']}")
    print(f"待确认防腐管件法兰材料库：{result['pending_anti_corrosion_fitting_library']}")
