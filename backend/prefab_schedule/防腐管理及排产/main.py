from pathlib import Path
import re
import sys

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from common_utils import calculate_unit_area, prepare_output_file
from 防腐管理及排产.anti_corrosion_config import ANTI_CORROSION_FILES


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

AREA_INPUT_COLUMNS = ['外径1', '壁厚1', '外径2', '壁厚2']
OUTPUT_AREA_COLUMNS = [UNIT_AREA_COL, COMMISSION_AREA_COL, COMPLETED_AREA_COL]


def _read_excel_or_empty(file_path):
    file_path = Path(file_path)
    if not file_path.exists() or file_path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_excel(file_path)
    except ValueError:
        return pd.DataFrame()


def _parse_numeric_parts(value):
    if pd.isna(value):
        return []
    return [float(item) for item in re.findall(r'\d+(?:\.\d+)?', str(value))]


def _prepare_area_input_columns(df):
    out = df.copy()
    spec_parts = out[SPEC_COL].apply(_parse_numeric_parts) if SPEC_COL in out.columns else pd.Series([[]] * len(out), index=out.index)
    thickness_parts = out[THICKNESS_COL].apply(_parse_numeric_parts) if THICKNESS_COL in out.columns else pd.Series([[]] * len(out), index=out.index)

    out['外径1'] = spec_parts.apply(lambda values: values[0] if values else 0.0)
    out['外径2'] = spec_parts.apply(lambda values: values[1] if len(values) > 1 else 0.0)
    out['壁厚1'] = thickness_parts.apply(lambda values: values[0] if values else 0.0)
    out['壁厚2'] = thickness_parts.apply(lambda values: values[1] if len(values) > 1 else 0.0)
    return out


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
    summary_df = _prepare_area_input_columns(summary_df)
    summary_df[UNIT_AREA_COL] = summary_df.apply(calculate_unit_area, axis=1).round(precision)
    summary_df[COMMISSION_AREA_COL] = (summary_df[UNIT_AREA_COL] * summary_df[QTY_COL]).round(precision)
    summary_df[COMPLETED_AREA_COL] = 0.0

    leading_cols = [SOURCE_TYPE_COL, MATERIAL_CODE_COL, QTY_COL] + OUTPUT_AREA_COLUMNS
    dimension_cols = [col for col in AREA_INPUT_COLUMNS if col in summary_df.columns]
    remaining_cols = [col for col in summary_df.columns if col not in leading_cols + dimension_cols]
    return summary_df[leading_cols + dimension_cols + remaining_cols]


def run_anti_corrosion_commission(
    pipe_library_file=ANTI_CORROSION_FILES['pipe_library'],
    fitting_library_file=ANTI_CORROSION_FILES['fitting_library'],
    commission_summary_output=ANTI_CORROSION_FILES['commission_summary_output'],
):
    pipe_df = _read_excel_or_empty(pipe_library_file)
    fitting_df = _read_excel_or_empty(fitting_library_file)
    summary_df = build_anti_corrosion_commission_summary(pipe_df, fitting_df)

    prepare_output_file(commission_summary_output)
    summary_df.to_excel(commission_summary_output, index=False)

    return {
        'pipe_count': len(pipe_df),
        'fitting_count': len(fitting_df),
        'summary_count': len(summary_df),
        'commission_summary_output': Path(commission_summary_output),
    }


if __name__ == '__main__':
    result = run_anti_corrosion_commission()
    print(f"管子材料库记录数：{result['pipe_count']}")
    print(f"管件法兰材料库记录数：{result['fitting_count']}")
    print(f"防腐委托总表记录数：{result['summary_count']}")
    print(f"防腐委托总表：{result['commission_summary_output']}")
