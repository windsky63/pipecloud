from pathlib import Path
import json
import sys

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from common_utils import prepare_output_file
from 下料管理及排产.cutting_config import (
    CONSUMED_LENGTHS_COL,
    CUT_LENGTHS_COL,
    CUT_LOSSES_COL,
    CUTTING_FILES,
    EXTRA_MATERIAL_QTY_FOR_P,
    FITTING_STOCK_QTY_COL,
    MATERIAL_CODE_COL,
    ORIGINAL_LENGTH_COL,
    PIPE_STOCK_QTY_COL,
    PIPE_UNIQUE_CODE_COL,
    REMAINING_LENGTH_COL,
)


def _read_excel_or_empty(file_path):
    file_path = Path(file_path)
    if not file_path.exists() or file_path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_excel(file_path)
    except ValueError:
        return pd.DataFrame()


def _is_empty_library(df):
    return df is None or df.empty or len(df.columns) == 0


def _parse_cut_lengths(value):
    if pd.isna(value) or str(value).strip() == '':
        return []

    if isinstance(value, list):
        return [float(item) for item in value if pd.notna(item)]

    text = str(value).strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [float(item) for item in parsed if pd.notna(item)]
    except json.JSONDecodeError:
        pass

    lengths = []
    for part in text.replace('，', ',').replace(';', ',').replace('；', ',').split(','):
        part = part.strip()
        if not part:
            continue
        try:
            lengths.append(float(part))
        except ValueError:
            continue
    return lengths


def _format_cut_lengths(lengths):
    return json.dumps([round(float(length), 3) for length in lengths], ensure_ascii=False)


def _build_cut_state(row, cutting_allowance=EXTRA_MATERIAL_QTY_FOR_P, precision=3):
    design_lengths = _parse_cut_lengths(row.get(CUT_LENGTHS_COL))
    original_length = pd.to_numeric(row.get(ORIGINAL_LENGTH_COL), errors='coerce')
    if pd.isna(original_length):
        original_length = pd.to_numeric(row.get(PIPE_STOCK_QTY_COL), errors='coerce')
    original_length = float(original_length) if pd.notna(original_length) else 0.0

    loss_lengths = _parse_cut_lengths(row.get(CUT_LOSSES_COL)) if CUT_LOSSES_COL in row.index else []
    consumed_lengths = _parse_cut_lengths(row.get(CONSUMED_LENGTHS_COL)) if CONSUMED_LENGTHS_COL in row.index else []

    if len(consumed_lengths) == len(design_lengths) and consumed_lengths:
        if len(loss_lengths) != len(design_lengths):
            loss_lengths = [
                round(float(consumed) - float(design), precision)
                for design, consumed in zip(design_lengths, consumed_lengths)
            ]
        remaining = round(original_length - sum(consumed_lengths), precision)
        return design_lengths, loss_lengths, consumed_lengths, remaining

    loss_lengths = []
    consumed_lengths = []
    remaining = round(original_length, precision)
    for design_length in design_lengths:
        design_length = round(float(design_length), precision)
        consumed_length, loss_length = _calculate_consumed_length(
            remaining,
            design_length,
            cutting_allowance,
            precision,
            has_prior_cuts=bool(consumed_lengths),
        )
        loss_lengths.append(loss_length)
        consumed_lengths.append(consumed_length)
        remaining = round(remaining - consumed_length, precision)

    return design_lengths, loss_lengths, consumed_lengths, remaining


def _is_exact_length_match(remaining_length, design_length, precision):
    return round(float(remaining_length), precision) == round(float(design_length), precision)


def _calculate_consumed_length(remaining_length, design_length, cutting_allowance, precision, has_prior_cuts=False):
    if not has_prior_cuts and _is_exact_length_match(remaining_length, design_length, precision):
        return round(float(design_length), precision), 0.0
    allowance = round(float(cutting_allowance), precision)
    consumed_length = round(float(design_length) + allowance, precision)
    return consumed_length, allowance


def _normalize_pipe_library(pipe_df):
    pipe_df = pipe_df.copy()
    if PIPE_STOCK_QTY_COL not in pipe_df.columns:
        raise ValueError(f'管子材料库缺少列：{PIPE_STOCK_QTY_COL}')
    if MATERIAL_CODE_COL not in pipe_df.columns:
        raise ValueError(f'管子材料库缺少列：{MATERIAL_CODE_COL}')
    if PIPE_UNIQUE_CODE_COL not in pipe_df.columns:
        pipe_df[PIPE_UNIQUE_CODE_COL] = range(1, len(pipe_df) + 1)

    pipe_df[MATERIAL_CODE_COL] = pipe_df[MATERIAL_CODE_COL].astype(str).str.strip()
    pipe_df[PIPE_STOCK_QTY_COL] = pd.to_numeric(pipe_df[PIPE_STOCK_QTY_COL], errors='coerce').fillna(0)

    if ORIGINAL_LENGTH_COL not in pipe_df.columns:
        pipe_df[ORIGINAL_LENGTH_COL] = pipe_df[PIPE_STOCK_QTY_COL]
    else:
        pipe_df[ORIGINAL_LENGTH_COL] = pd.to_numeric(pipe_df[ORIGINAL_LENGTH_COL], errors='coerce')
        pipe_df[ORIGINAL_LENGTH_COL] = pipe_df[ORIGINAL_LENGTH_COL].fillna(pipe_df[PIPE_STOCK_QTY_COL])

    for col in [CUT_LENGTHS_COL, CUT_LOSSES_COL, CONSUMED_LENGTHS_COL]:
        if col not in pipe_df.columns:
            pipe_df[col] = '[]'

    cut_states = pipe_df.apply(_build_cut_state, axis=1)
    pipe_df[CUT_LENGTHS_COL] = cut_states.apply(lambda item: _format_cut_lengths(item[0]))
    pipe_df[CUT_LOSSES_COL] = cut_states.apply(lambda item: _format_cut_lengths(item[1]))
    pipe_df[CONSUMED_LENGTHS_COL] = cut_states.apply(lambda item: _format_cut_lengths(item[2]))
    pipe_df[REMAINING_LENGTH_COL] = cut_states.apply(lambda item: item[3]).clip(lower=0)
    return pipe_df


def ensure_anti_corrosion_pipe_library(
    pipe_library_file=CUTTING_FILES['pipe_library'],
    anti_corrosion_pipe_library_file=CUTTING_FILES['anti_corrosion_pipe_library'],
    reset=False,
    persist_initialized=True,
):
    """防腐管子库为空时，用管子材料库逐根复制初始化。"""
    anti_file = Path(anti_corrosion_pipe_library_file)
    anti_df = _read_excel_or_empty(anti_file)
    if not reset and not _is_empty_library(anti_df):
        return _normalize_pipe_library(anti_df), False

    pipe_df = _read_excel_or_empty(pipe_library_file)
    if _is_empty_library(pipe_df):
        raise ValueError(f'管子材料库为空，无法初始化防腐管子材料库：{pipe_library_file}')

    anti_df = _normalize_pipe_library(pipe_df)
    if persist_initialized:
        prepare_output_file(anti_file)
        anti_df.to_excel(anti_file, index=False)
    return anti_df, True


def ensure_anti_corrosion_fitting_library(
    fitting_library_file=CUTTING_FILES['fitting_library'],
    anti_corrosion_fitting_library_file=CUTTING_FILES['anti_corrosion_fitting_library'],
    reset=False,
    persist_initialized=True,
):
    """防腐管件法兰库为空时，用管件法兰材料库初始化。"""
    anti_file = Path(anti_corrosion_fitting_library_file)
    anti_df = _read_excel_or_empty(anti_file)
    if not reset and not _is_empty_library(anti_df):
        return _normalize_fitting_library(anti_df), False

    fitting_df = _read_excel_or_empty(fitting_library_file)
    if _is_empty_library(fitting_df):
        raise ValueError(f'管件法兰材料库为空，无法初始化防腐管件法兰材料库：{fitting_library_file}')

    anti_df = _normalize_fitting_library(fitting_df)
    if persist_initialized:
        prepare_output_file(anti_file)
        anti_df.to_excel(anti_file, index=False)
    return anti_df, True


def _normalize_fitting_library(fitting_df):
    fitting_df = fitting_df.copy()
    if MATERIAL_CODE_COL not in fitting_df.columns:
        raise ValueError(f'管件法兰材料库缺少列：{MATERIAL_CODE_COL}')
    if FITTING_STOCK_QTY_COL not in fitting_df.columns:
        raise ValueError(f'管件法兰材料库缺少列：{FITTING_STOCK_QTY_COL}')

    fitting_df[MATERIAL_CODE_COL] = fitting_df[MATERIAL_CODE_COL].astype(str).str.strip()
    fitting_df[FITTING_STOCK_QTY_COL] = pd.to_numeric(fitting_df[FITTING_STOCK_QTY_COL], errors='coerce').fillna(0)
    return fitting_df


if __name__ == '__main__':
    print('正式下料排产已停用。请运行 weld_pre_schedule_matcher.py 生成下料预排产匹配结果。')
