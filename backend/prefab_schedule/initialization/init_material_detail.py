# -*- coding: utf-8 -*-
from pathlib import Path
import sys

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from initialization.init_config import COLUMNS
from common_utils import prepare_output_file


COL_UNIQUE = '材料唯一码'
COL_QTY = '设计数量'
COL_SIDE = '材料侧'
COL_CODE = '材料代码'
COL_PAINT = '材料油漆'
COL_NO = '材料代号'
COL_DESC = '描述'
COL_UNIT = '单位'
COL_DIAMETER_LIST = '寸径列表'
COL_OUTER_LIST = '外径列表'
COL_OUTER_COUNT = '外径种类数'
COL_THICKNESS_LIST = '壁厚列表'
COL_WELD_ROW_COUNT = '涉及焊口行数'


def _format_number(value):
    try:
        return format(float(value), 'g')
    except (TypeError, ValueError):
        return str(value).strip()


def _max_numeric_text(values_text):
    values = []
    for item in str(values_text).split('、'):
        item = item.strip()
        if not item or item.lower() == 'nan':
            continue
        numeric_value = pd.to_numeric(item, errors='coerce')
        if pd.notna(numeric_value):
            values.append(float(numeric_value))

    if not values:
        return str(values_text).strip()
    return _format_number(max(values))


def _apply_pipe_outer_diameter_rule(df):
    if df is None or df.empty or COL_NO not in df.columns or COL_OUTER_LIST not in df.columns:
        return df

    out = df.copy()
    pipe_mask = out[COL_NO].fillna('').astype(str).str.upper().str.strip().eq('P')
    out.loc[pipe_mask, COL_OUTER_LIST] = out.loc[pipe_mask, COL_OUTER_LIST].apply(_max_numeric_text)
    return out


def _text_column(df, column):
    if column not in df.columns:
        return pd.Series('', index=df.index, dtype='string')
    return df[column].fillna('').astype(str).str.strip()


def _valid_text_df(df, columns):
    existing_columns = [col for col in columns if col in df.columns]
    if not existing_columns:
        return pd.DataFrame(index=df.index)

    out = df[existing_columns].copy()
    for col in existing_columns:
        out[col] = out[col].fillna('').astype(str).str.strip()
    return out


def _join_unique_from_frame(df, group_cols, value_col, output_col):
    if value_col not in df.columns:
        return pd.DataFrame(columns=group_cols + [output_col])

    values_df = _valid_text_df(df, group_cols + [value_col])
    values_df = values_df[values_df[value_col].ne('') & values_df[value_col].str.lower().ne('nan')]
    if values_df.empty:
        return pd.DataFrame(columns=group_cols + [output_col])

    values_df = values_df.drop_duplicates(group_cols + [value_col])
    return (
        values_df.groupby(group_cols, as_index=False)[value_col]
        .agg(lambda values: '、'.join(values))
        .rename(columns={value_col: output_col})
    )


def _expand_side_materials(group_df, side):
    unique_col = COLUMNS[f'material_unique_{side}']
    qty_col = COLUMNS[f'qty_{side}']
    if unique_col not in group_df.columns or qty_col not in group_df.columns:
        return pd.DataFrame()

    material_df = pd.DataFrame({
        COLUMNS['unit']: _text_column(group_df, COLUMNS['unit']),
        COLUMNS['pipeline']: _text_column(group_df, COLUMNS['pipeline']),
        COLUMNS['segment_no']: _text_column(group_df, COLUMNS['segment_no']),
        COLUMNS['weld_no_start']: _text_column(group_df, COLUMNS['weld_no_start']),
        COLUMNS['weld_no_final']: _text_column(group_df, COLUMNS['weld_no_final']),
        COLUMNS['material']: _text_column(group_df, COLUMNS['material']),
        COLUMNS['diameter']: _text_column(group_df, COLUMNS['diameter']),
        COLUMNS['outer_diameter']: _text_column(group_df, COLUMNS['outer_diameter']),
        COLUMNS['thickness']: _text_column(group_df, COLUMNS['thickness']),
        COL_UNIQUE: _text_column(group_df, unique_col),
        COL_QTY: pd.to_numeric(group_df[qty_col], errors='coerce').fillna(0),
        COL_SIDE: str(side),
        COL_NO: _text_column(group_df, COLUMNS[f'material_no_{side}']),
        COL_CODE: _text_column(group_df, COLUMNS[f'material_code_{side}']),
        COL_PAINT: _text_column(group_df, COLUMNS[f'paint_{side}']),
        COL_DESC: _text_column(group_df, COLUMNS[f'desc_{side}']),
    })

    valid_unique = material_df[COL_UNIQUE].ne('') & material_df[COL_UNIQUE].str.lower().ne('nan')
    return material_df[valid_unique & material_df[COL_QTY].gt(0)].copy()


def expand_group_material_rows(group_df):
    expanded_df = pd.concat(
        [_expand_side_materials(group_df, 1), _expand_side_materials(group_df, 2)],
        ignore_index=True,
    )
    if expanded_df.empty:
        return expanded_df

    expanded_df[COL_UNIT] = expanded_df[COL_NO].astype(str).str.upper().str.strip().apply(
        lambda value: '米' if value == 'P' else '个'
    )
    return expanded_df


def merge_same_material_in_group(expanded_df):
    if expanded_df is None or expanded_df.empty:
        return pd.DataFrame()

    group_cols = [COLUMNS['unit'], COLUMNS['pipeline'], COL_UNIQUE]

    first_cols = [
        COL_QTY, COL_UNIT, COL_CODE, COL_PAINT, COL_NO, COL_DESC,
        COLUMNS['material'],
    ]
    first_cols = [col for col in first_cols if col in expanded_df.columns]
    base_df = (
        expanded_df[group_cols + first_cols]
        .drop_duplicates(group_cols)
        .copy()
    )

    for value_col, output_col in [
        (COLUMNS['diameter'], COL_DIAMETER_LIST),
        (COLUMNS['outer_diameter'], COL_OUTER_LIST),
        (COLUMNS['thickness'], COL_THICKNESS_LIST),
    ]:
        list_df = _join_unique_from_frame(expanded_df, group_cols, value_col, output_col)
        base_df = base_df.merge(list_df, on=group_cols, how='left')
        if output_col in base_df.columns:
            base_df[output_col] = base_df[output_col].fillna('')

    outer_count_df = (
        _valid_text_df(expanded_df, group_cols + [COLUMNS['outer_diameter']])
        .query(f"`{COLUMNS['outer_diameter']}` != ''")
        .drop_duplicates(group_cols + [COLUMNS['outer_diameter']])
        .groupby(group_cols, as_index=False)
        .size()
        .rename(columns={'size': COL_OUTER_COUNT})
    )
    base_df = base_df.merge(outer_count_df, on=group_cols, how='left')
    base_df[COL_OUTER_COUNT] = base_df[COL_OUTER_COUNT].fillna(0).astype(int)

    weld_count_df = (
        expanded_df.groupby(group_cols, as_index=False)
        .size()
        .rename(columns={'size': COL_WELD_ROW_COUNT})
    )
    base_df = base_df.merge(weld_count_df, on=group_cols, how='left')

    return base_df


def build_init_material_detail(df):
    if df is None or df.empty:
        return pd.DataFrame()

    unit_col = COLUMNS['unit']
    pipeline_col = COLUMNS['pipeline']
    if unit_col not in df.columns or pipeline_col not in df.columns:
        return pd.DataFrame()

    group_results = []
    for _, group_df in df.groupby([unit_col, pipeline_col], dropna=False, sort=True):
        expanded_df = expand_group_material_rows(group_df)
        merged_df = merge_same_material_in_group(expanded_df)
        if not merged_df.empty:
            group_results.append(merged_df)

    if not group_results:
        return pd.DataFrame()

    material_detail_df = pd.concat(group_results, ignore_index=True)
    column_order = [
        COLUMNS['unit'], COLUMNS['pipeline'], COL_UNIQUE,
        COL_QTY, COL_UNIT,
        COL_CODE, COL_PAINT, COL_NO, COL_DESC,
        COLUMNS['material'], COL_DIAMETER_LIST, COL_OUTER_LIST, COL_OUTER_COUNT,
        COL_THICKNESS_LIST, COL_WELD_ROW_COUNT,
    ]
    existing_order = [col for col in column_order if col in material_detail_df.columns]
    return material_detail_df[existing_order].sort_values(
        [COLUMNS['unit'], COLUMNS['pipeline'], COL_CODE, COL_UNIQUE],
        na_position='last',
    ).reset_index(drop=True)


def build_multi_outer_diameter_detail(material_detail_df):
    if material_detail_df is None or material_detail_df.empty or COL_OUTER_COUNT not in material_detail_df.columns:
        return pd.DataFrame()
    return material_detail_df.loc[material_detail_df[COL_OUTER_COUNT].gt(1)].copy().reset_index(drop=True)


def save_init_material_detail(df, output_path):
    material_detail_df = build_init_material_detail(df)
    if material_detail_df.empty:
        print('未生成初始化数据材料明细表：没有可用材料数据')
        return False

    output_detail_df = _apply_pipe_outer_diameter_rule(material_detail_df)
    output_detail_df = output_detail_df.drop(columns=[COL_SIDE, COL_OUTER_COUNT], errors='ignore')
    try:
        prepare_output_file(output_path)
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            output_detail_df.to_excel(writer, sheet_name='按单元管线材料汇总', index=False)
        print(f'初始化数据材料明细表已生成：{output_path}')
        print(f'材料汇总行数：{len(output_detail_df)}')
        return True
    except Exception as error:
        print(f'保存初始化数据材料明细表失败：{error}')
        return False
