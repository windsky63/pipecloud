from pathlib import Path
import sys

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from arrival.arrival_config import ARRIVAL_COLUMNS, ARRIVAL_FILES, ARRIVAL_LIBRARY_COLUMNS, ARRIVAL_PIPE_RULES
from common_utils import calculate_unit_area, prepare_area_input_columns, prepare_output_file


DEFAULT_ARRIVAL_DIR = ARRIVAL_FILES['arrival_dir']
DEFAULT_PIPE_OUTPUT_FILE = ARRIVAL_FILES['pipe_output']
DEFAULT_FITTING_OUTPUT_FILE = ARRIVAL_FILES['fitting_output']
DEFAULT_ANTI_PIPE_OUTPUT_FILE = ARRIVAL_FILES['anti_pipe_output']
DEFAULT_ANTI_FITTING_OUTPUT_FILE = ARRIVAL_FILES['anti_fitting_output']

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
UNIT_AREA_COL = ARRIVAL_LIBRARY_COLUMNS['unit_area']
ANTI_CORROSION_AREA_COL = ARRIVAL_LIBRARY_COLUMNS['anti_corrosion_area']

PIPE_UNIT = ARRIVAL_PIPE_RULES['unit']
PIPE_NAME = ARRIVAL_PIPE_RULES['name']
PIPE_CATEGORY = ARRIVAL_PIPE_RULES['category']
PIPE_OUTPUT_KEEP_COLS = ARRIVAL_PIPE_RULES['pipe_output_keep_cols']

ANTI_CORROSION_UNFINISHED = '防腐未完成'
ANTI_CORROSION_PREFIX = 'pa'


def _read_arrival_detail_files(arrival_dir=DEFAULT_ARRIVAL_DIR):
    arrival_dir = Path(arrival_dir)
    frames = []

    for file_path in sorted(arrival_dir.glob("*.xlsx")):
        if file_path.name.startswith("~$"):
            continue

        detail_df = pd.read_excel(file_path, sheet_name="Sheet2")
        detail_df[SOURCE_FILE_COL] = file_path.name
        detail_df[ARRIVAL_DATE_COL] = file_path.stem
        frames.append(detail_df)

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)


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
    """将入库明细分为普通材料与待防腐材料。

    “是否需防腐”以 PA 开头的记录进入待防腐材料库；空值、斜杠及其他
    非 PA 标记进入普通材料库。
    """
    if arrival_df is None or arrival_df.empty:
        empty = pd.DataFrame() if arrival_df is None else arrival_df.copy()
        return empty.copy(), empty.copy()

    out = arrival_df.copy()
    if NEED_ANTI_CORROSION_COL in out.columns:
        normalized = out[NEED_ANTI_CORROSION_COL].fillna('').astype(str).str.strip().str.lower()
        anti_corrosion_mask = normalized.str.startswith(ANTI_CORROSION_PREFIX)
    else:
        anti_corrosion_mask = pd.Series(False, index=out.index)

    ordinary_df = out[~anti_corrosion_mask].copy()
    anti_corrosion_df = out[anti_corrosion_mask].copy()
    ordinary_df = ordinary_df.drop(
        columns=[ANTI_CORROSION_STATUS_COL, UNIT_AREA_COL, ANTI_CORROSION_AREA_COL],
        errors='ignore',
    )
    ordinary_df[NEED_ANTI_CORROSION_COL] = '否'
    anti_corrosion_df[NEED_ANTI_CORROSION_COL] = '是'
    anti_corrosion_df[ANTI_CORROSION_STATUS_COL] = ANTI_CORROSION_UNFINISHED
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


def maintain_material_libraries(
    arrival_dir=DEFAULT_ARRIVAL_DIR,
    pipe_output_file=DEFAULT_PIPE_OUTPUT_FILE,
    fitting_output_file=DEFAULT_FITTING_OUTPUT_FILE,
    anti_pipe_output_file=DEFAULT_ANTI_PIPE_OUTPUT_FILE,
    anti_fitting_output_file=DEFAULT_ANTI_FITTING_OUTPUT_FILE,
):
    """读取入库单，按防腐要求输出普通材料库和待防腐材料库。"""
    arrival_df = _read_arrival_detail_files(arrival_dir)
    ordinary_df, anti_corrosion_df = split_arrival_materials_by_anti_corrosion(arrival_df)
    pipe_library_df = build_pipe_material_library(ordinary_df)
    fitting_library_df = build_fitting_flange_material_library(ordinary_df)
    anti_pipe_library_df = add_anti_corrosion_area(
        build_pipe_material_library(anti_corrosion_df),
        PIPE_STOCK_QTY_COL,
    )
    anti_fitting_library_df = add_anti_corrosion_area(
        build_fitting_flange_material_library(anti_corrosion_df),
        STOCK_QTY_COL,
    )

    pipe_output_file = Path(pipe_output_file)
    fitting_output_file = Path(fitting_output_file)
    anti_pipe_output_file = Path(anti_pipe_output_file)
    anti_fitting_output_file = Path(anti_fitting_output_file)
    outputs = [
        (pipe_output_file, pipe_library_df),
        (fitting_output_file, fitting_library_df),
        (anti_pipe_output_file, anti_pipe_library_df),
        (anti_fitting_output_file, anti_fitting_library_df),
    ]
    for output_file, dataframe in outputs:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        prepare_output_file(output_file)
        dataframe.to_excel(output_file, index=False)
    return pipe_library_df, fitting_library_df, anti_pipe_library_df, anti_fitting_library_df


if __name__ == "__main__":
    pipe_df, fitting_df, anti_pipe_df, anti_fitting_df = maintain_material_libraries()
    print(f"已生成管子材料库：{DEFAULT_PIPE_OUTPUT_FILE}")
    print(f"管子材料库记录数：{len(pipe_df)}")
    print(f"已生成管件法兰材料库：{DEFAULT_FITTING_OUTPUT_FILE}")
    print(f"管件法兰材料库记录数：{len(fitting_df)}")
    print(f"已生成防腐管子材料库：{DEFAULT_ANTI_PIPE_OUTPUT_FILE}")
    print(f"防腐管子材料库记录数：{len(anti_pipe_df)}")
    print(f"已生成防腐管件法兰材料库：{DEFAULT_ANTI_FITTING_OUTPUT_FILE}")
    print(f"防腐管件法兰材料库记录数：{len(anti_fitting_df)}")
