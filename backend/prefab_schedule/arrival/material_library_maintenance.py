from pathlib import Path
import sys

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from arrival.arrival_config import ARRIVAL_COLUMNS, ARRIVAL_LIBRARY_COLUMNS, ARRIVAL_PIPE_RULES
from common_utils import calculate_unit_area, prepare_area_input_columns


CODE_COL = ARRIVAL_COLUMNS['code']
SEND_QTY_COL = ARRIVAL_COLUMNS['send_qty']
ACTUAL_QTY_COL = ARRIVAL_COLUMNS['actual_qty']
MATERIAL_CATEGORY_COL = ARRIVAL_COLUMNS['material_category']
NAME_COL = ARRIVAL_COLUMNS['name']
MATERIAL_COL = ARRIVAL_COLUMNS['material']
SPEC_COL = ARRIVAL_COLUMNS['spec']
THICKNESS_COL = ARRIVAL_COLUMNS['thickness']
UNIT_COL = ARRIVAL_COLUMNS['unit']
DESCRIPTION_COL = ARRIVAL_COLUMNS['description']
MATERIAL_FULL_NAME_COL = ARRIVAL_COLUMNS['material_full_name']
PIPE_COUNT_COL = ARRIVAL_COLUMNS['pipe_count']
NEED_ANTI_CORROSION_COL = ARRIVAL_COLUMNS['anti_corrosion']

SOURCE_FILE_COL = ARRIVAL_LIBRARY_COLUMNS['source_file']
ARRIVAL_DATE_COL = ARRIVAL_LIBRARY_COLUMNS['arrival_date']
STOCK_QTY_COL = ARRIVAL_LIBRARY_COLUMNS['stock_qty']
PIPE_STOCK_QTY_COL = ARRIVAL_LIBRARY_COLUMNS['pipe_stock_qty']
PIPE_UNIQUE_CODE_COL = ARRIVAL_LIBRARY_COLUMNS['pipe_unique_code']
MATERIAL_CODE_OUTPUT_COL = ARRIVAL_LIBRARY_COLUMNS['material_code_output']
ANTI_CORROSION_STATUS_COL = ARRIVAL_LIBRARY_COLUMNS['anti_corrosion_status']
ANTI_CORROSION_STOCK_QTY_COL = ARRIVAL_LIBRARY_COLUMNS['anti_corrosion_stock_qty']
LOCKED_QTY_COL = ARRIVAL_LIBRARY_COLUMNS['locked_qty']
COATED_LOCKED_QTY_COL = ARRIVAL_LIBRARY_COLUMNS['coated_locked_qty']
UNCOATED_LOCKED_QTY_COL = ARRIVAL_LIBRARY_COLUMNS['uncoated_locked_qty']
USED_QTY_COL = ARRIVAL_LIBRARY_COLUMNS['used_qty']
UNIT_AREA_COL = ARRIVAL_LIBRARY_COLUMNS['unit_area']
ANTI_CORROSION_AREA_COL = ARRIVAL_LIBRARY_COLUMNS['anti_corrosion_area']

PIPE_UNIT = ARRIVAL_PIPE_RULES['unit']
PIPE_NAME = ARRIVAL_PIPE_RULES['name']
PIPE_CATEGORY = ARRIVAL_PIPE_RULES['category']
PIPE_OUTPUT_KEEP_COLS = ARRIVAL_PIPE_RULES['pipe_output_keep_cols']

ANTI_CORROSION_UNFINISHED = '防腐未完成'
ANTI_CORROSION_COMPLETED_VALUES = {'true', '1', 'yes', 'y', '是', '完成', '已完成', '已防腐', '防腐完成'}
ANTI_CORROSION_PREFIX = 'pa'


def _is_anti_corrosion_completed_series(series, index):
    if series is None:
        return pd.Series(False, index=index)
    normalized = series.fillna('').astype(str).str.strip().str.lower()
    return normalized.isin(ANTI_CORROSION_COMPLETED_VALUES)


def _normalize_qty(df):
    actual_qty = pd.to_numeric(df[ACTUAL_QTY_COL], errors="coerce")
    send_qty = pd.to_numeric(df[SEND_QTY_COL], errors="coerce")
    return actual_qty.where(actual_qty.notna() & (actual_qty > 0), send_qty).fillna(0)


def _normalize_row_qty(row):
    actual_qty = pd.to_numeric(row.get(ACTUAL_QTY_COL), errors="coerce")
    send_qty = pd.to_numeric(row.get(SEND_QTY_COL), errors="coerce")
    if pd.notna(actual_qty) and actual_qty > 0:
        return float(actual_qty)
    if pd.notna(send_qty) and send_qty > 0:
        return float(send_qty)
    return 0.0


def _is_pipe(df):
    unit = df[UNIT_COL].astype(str).str.strip()
    name = df[NAME_COL].astype(str).str.strip()
    category = df[MATERIAL_CATEGORY_COL].astype(str).str.strip()
    return unit.eq(PIPE_UNIT) | name.eq(PIPE_NAME) | category.eq(PIPE_CATEGORY)


def split_arrival_materials_by_anti_corrosion(arrival_df):
    """按“是否需防腐”列分流；PA 开头的材料只进入防腐材料库。"""
    if arrival_df is None or arrival_df.empty:
        empty = pd.DataFrame() if arrival_df is None else arrival_df.copy()
        return empty.copy(), empty.copy()

    out = arrival_df.copy()
    requirement = out.get(NEED_ANTI_CORROSION_COL, pd.Series('', index=out.index))
    anti_mask = requirement.fillna('').astype(str).str.strip().str.lower().str.startswith(ANTI_CORROSION_PREFIX)
    ordinary_df = out.loc[~anti_mask].copy()
    anti_corrosion_df = out.loc[anti_mask].copy()
    ordinary_df = ordinary_df.drop(columns=[UNIT_AREA_COL, ANTI_CORROSION_AREA_COL], errors='ignore')
    if NEED_ANTI_CORROSION_COL not in ordinary_df.columns:
        ordinary_df[NEED_ANTI_CORROSION_COL] = '否'
    return ordinary_df, anti_corrosion_df


def build_pipe_material_library(arrival_df):
    """构造管子材料库，入库时按管子支数展开为逐根记录。"""
    if arrival_df is None or arrival_df.empty:
        return pd.DataFrame()

    pipe_df = arrival_df[_is_pipe(arrival_df)].copy()
    if pipe_df.empty:
        return pd.DataFrame()

    expanded_rows = []
    for _, row in pipe_df.iterrows():
        pipe_count = pd.to_numeric(row.get(PIPE_COUNT_COL), errors="coerce")
        pipe_count = int(pipe_count) if pd.notna(pipe_count) and pipe_count > 0 else 1
        total_qty = _normalize_row_qty(row)
        single_qty = total_qty / pipe_count if pipe_count > 0 else total_qty

        for _ in range(pipe_count):
            piece_row = row.copy()
            piece_row[STOCK_QTY_COL] = single_qty
            expanded_rows.append(piece_row)

    pipe_df = pd.DataFrame(expanded_rows)

    pipe_df = pipe_df.rename(columns={CODE_COL: MATERIAL_CODE_OUTPUT_COL})
    sort_cols = [col for col in [ARRIVAL_DATE_COL, MATERIAL_CODE_OUTPUT_COL] if col in pipe_df.columns]
    if sort_cols:
        pipe_df = pipe_df.sort_values(sort_cols)

    pipe_df = pipe_df.reset_index(drop=True)
    pipe_df[PIPE_UNIQUE_CODE_COL] = range(1, len(pipe_df) + 1)
    pipe_df = pipe_df.rename(columns={STOCK_QTY_COL: PIPE_STOCK_QTY_COL})
    completed_mask = _is_anti_corrosion_completed_series(
        pipe_df.get(ANTI_CORROSION_STATUS_COL), pipe_df.index
    )
    pipe_df[ANTI_CORROSION_STOCK_QTY_COL] = pipe_df[PIPE_STOCK_QTY_COL].where(completed_mask, 0)
    pipe_df[LOCKED_QTY_COL] = 0
    pipe_df[COATED_LOCKED_QTY_COL] = 0
    pipe_df[UNCOATED_LOCKED_QTY_COL] = 0
    pipe_df[USED_QTY_COL] = 0
    pipe_df = pipe_df[[col for col in PIPE_OUTPUT_KEEP_COLS if col in pipe_df.columns]]
    return pipe_df


def build_fitting_flange_material_library(arrival_df):
    """构造管件法兰材料库，非管子按材料代码合并。"""
    if arrival_df is None or arrival_df.empty:
        return pd.DataFrame()

    non_pipe_df = arrival_df[~_is_pipe(arrival_df)].copy()
    if non_pipe_df.empty:
        return pd.DataFrame()

    non_pipe_df[CODE_COL] = non_pipe_df[CODE_COL].astype(str).str.strip()
    non_pipe_df = non_pipe_df[(non_pipe_df[CODE_COL] != "") & (non_pipe_df[CODE_COL].str.lower() != "nan")]
    if non_pipe_df.empty:
        return pd.DataFrame()

    non_pipe_df[STOCK_QTY_COL] = _normalize_qty(non_pipe_df)
    agg_map = {
        STOCK_QTY_COL: "sum",
        SOURCE_FILE_COL: lambda values: "、".join(pd.unique(values.astype(str))),
        ARRIVAL_DATE_COL: lambda values: "、".join(pd.unique(values.astype(str))),
    }
    for col in [
        MATERIAL_CATEGORY_COL,
        NAME_COL,
        MATERIAL_COL,
        SPEC_COL,
        THICKNESS_COL,
        UNIT_COL,
        DESCRIPTION_COL,
        MATERIAL_FULL_NAME_COL,
        NEED_ANTI_CORROSION_COL,
        ANTI_CORROSION_STATUS_COL,
    ]:
        if col in non_pipe_df.columns:
            agg_map[col] = "first"

    out = non_pipe_df.groupby(CODE_COL, as_index=False).agg(agg_map)
    out = out.rename(columns={CODE_COL: MATERIAL_CODE_OUTPUT_COL})
    completed_mask = _is_anti_corrosion_completed_series(
        out.get(ANTI_CORROSION_STATUS_COL), out.index
    )
    out[ANTI_CORROSION_STOCK_QTY_COL] = out[STOCK_QTY_COL].where(completed_mask, 0)
    out[LOCKED_QTY_COL] = 0
    out[COATED_LOCKED_QTY_COL] = 0
    out[UNCOATED_LOCKED_QTY_COL] = 0
    out[USED_QTY_COL] = 0
    out = out.drop(columns=[ANTI_CORROSION_STATUS_COL], errors='ignore')
    return out.sort_values(MATERIAL_CODE_OUTPUT_COL).reset_index(drop=True)


def add_anti_corrosion_area(material_df, quantity_col, precision=6):
    """按防腐委托总表的同一公式计算单位面积和本次入库防腐面积。"""
    if material_df is None or material_df.empty:
        return pd.DataFrame() if material_df is None else material_df.copy()

    out = material_df.copy()
    area_input = prepare_area_input_columns(out, SPEC_COL, THICKNESS_COL)
    out[UNIT_AREA_COL] = area_input.apply(calculate_unit_area, axis=1).round(precision)
    quantity_values = out[quantity_col] if quantity_col in out.columns else pd.Series(0, index=out.index)
    quantity = pd.to_numeric(quantity_values, errors='coerce').fillna(0)
    out[ANTI_CORROSION_AREA_COL] = (out[UNIT_AREA_COL] * quantity).round(precision)
    return out
