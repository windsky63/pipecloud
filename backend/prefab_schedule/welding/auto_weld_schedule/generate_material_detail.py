import pandas as pd
from welding.weld_config import COLUMNS, VERBOSE
from common_utils import normalize_columns, prepare_output_file


def _log(*args, **kwargs):
    if VERBOSE:
        print(*args, **kwargs)


def read_all_sheets(file_path):
    try:
        all_sheets = pd.read_excel(file_path, sheet_name=None)
        _log(f"成功读取Excel文件：{file_path}")
        _log(f"找到 {len(all_sheets)} 个工作表：{list(all_sheets.keys())}")
        return {k: normalize_columns(v) for k, v in all_sheets.items()}
    except Exception as e:
        _log(f"读取文件时出错：{e}")
        return None


def _build_material_df(df, base_columns, column_map, unique_code_col, qty_col):
    if unique_code_col not in df.columns or qty_col not in df.columns:
        return pd.DataFrame()

    out = pd.DataFrame()
    for col in base_columns:
        out[col] = df[col] if col in df.columns else ''
    for new_col, old_col in column_map.items():
        out[new_col] = df[old_col] if old_col in df.columns else ''

    out['材料唯一码'] = df[unique_code_col].astype(str).str.strip()
    out['设计数量'] = pd.to_numeric(df[qty_col], errors='coerce').fillna(0)
    return out[(out['材料唯一码'] != '') & (out['材料唯一码'].str.lower() != 'nan') & (out['设计数量'] > 0)].copy()


def _join_unique_values(values):
    clean_values = values.fillna('').astype(str).str.strip()
    clean_values = clean_values[(clean_values != '') & (clean_values.str.lower() != 'nan')]
    return '、'.join(pd.unique(clean_values))


def _format_qty_values(values):
    formatted_values = []
    for value in sorted(values):
        formatted_values.append(format(float(value), 'g'))
    return '、'.join(formatted_values)


def _validate_unique_material_quantities(sheet_name, materials_df):
    qty_counts = materials_df.groupby('材料唯一码')['设计数量'].nunique(dropna=True)
    conflict_codes = qty_counts[qty_counts > 1].index.tolist()
    if not conflict_codes:
        return

    details = []
    for code in conflict_codes[:20]:
        values = set(materials_df.loc[materials_df['材料唯一码'] == code, '设计数量'])
        details.append(f"{code}: {_format_qty_values(values)}")

    message = (
        f"工作表'{sheet_name}'存在同一材料唯一码对应多个设计数量，"
        f"请先修正源数据后再生成材料明细：{'; '.join(details)}"
    )
    if len(conflict_codes) > 20:
        message += f"；另有 {len(conflict_codes) - 20} 个材料唯一码存在同类问题"
    raise ValueError(message)


def generate_material_details_for_sheet(sheet_name, df, extra_material_qty=0):
    base_columns = [COLUMNS['pipeline'], COLUMNS['weld_no_start'], COLUMNS['weld_no_final'], COLUMNS['segment_no'],
                    COLUMNS['material'], COLUMNS['diameter'], COLUMNS['thickness']]
    material1_columns = {'材料代码': COLUMNS['material_code_1'], '材料油漆': COLUMNS['paint_1'],
                         '材料代号': COLUMNS['material_no_1'], '描述': COLUMNS['desc_1']}
    material2_columns = {'材料代码': COLUMNS['material_code_2'], '材料油漆': COLUMNS['paint_2'],
                         '材料代号': COLUMNS['material_no_2'], '描述': COLUMNS['desc_2']}

    required_columns = [COLUMNS['material_unique_1'], COLUMNS['material_unique_2'], COLUMNS['qty_1'], COLUMNS['qty_2']]
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        _log(f"  警告：工作表'{sheet_name}'找不到以下列：{missing_columns}")
        return None

    m1 = _build_material_df(df, base_columns, material1_columns, COLUMNS['material_unique_1'], COLUMNS['qty_1'])
    m2 = _build_material_df(df, base_columns, material2_columns, COLUMNS['material_unique_2'], COLUMNS['qty_2'])
    materials_df = pd.concat([m1, m2], ignore_index=True)
    if materials_df.empty:
        return None

    if '材料代号' in materials_df.columns:
        materials_df['单位'] = materials_df['材料代号'].astype(str).str.upper().apply(
            lambda x: '米' if x == 'P' else '个'
        )
    else:
        materials_df['单位'] = '个'

    materials_df['需领料数量'] = materials_df['设计数量'].astype(float)

    if '材料代号' in materials_df.columns:
        p_mask = materials_df['材料代号'].astype(str).str.upper() == 'P'
        if p_mask.any():
            materials_df.loc[p_mask, '需领料数量'] += extra_material_qty
            _log(f"  为{p_mask.sum()}条材料代号为'P'的记录增加了{extra_material_qty}的额外领料数量")

    _validate_unique_material_quantities(sheet_name, materials_df)

    pipeline_col = COLUMNS['pipeline']
    materials_df[pipeline_col] = materials_df[pipeline_col].fillna('').astype(str).str.strip().replace('', '未知管线')
    key_cols = ['材料唯一码']

    agg_map = {
        '设计数量': 'first',
        '需领料数量': 'first',
        pipeline_col: _join_unique_values,
        COLUMNS['weld_no_start']: _join_unique_values,
        COLUMNS['weld_no_final']: _join_unique_values,
        COLUMNS['segment_no']: _join_unique_values,
        '材料代码': 'first',
        '材料油漆': 'first',
        '材料代号': 'first',
        '单位': 'first',
        '描述': 'first',
        COLUMNS['material']: 'first',
        COLUMNS['diameter']: 'first',
        COLUMNS['thickness']: 'first',
    }
    agg_map = {k: v for k, v in agg_map.items() if k in materials_df.columns}
    final_df = materials_df.groupby(key_cols, as_index=False).agg(agg_map)

    column_order = [COLUMNS['pipeline'], COLUMNS['weld_no_start'], COLUMNS['weld_no_final'], '材料唯一码', '设计数量',
                    '需领料数量', '单位', COLUMNS['segment_no'], '材料代码', '材料油漆', '材料代号', '描述', COLUMNS['material'],
                    COLUMNS['diameter'], COLUMNS['thickness']]
    final_df = final_df[[c for c in column_order if c in final_df.columns]]
    return final_df


def generate_material_summary_by_code(material_details_df):
    if material_details_df is None or len(material_details_df) == 0:
        return None

    material_details_df = material_details_df.copy()
    for qty_col in ('设计数量', '需领料数量'):
        if qty_col in material_details_df.columns:
            material_details_df[qty_col] = pd.to_numeric(material_details_df[qty_col], errors='coerce').fillna(0)

    summary_df = material_details_df.groupby('材料代码').agg({
        '设计数量': 'sum',
        '需领料数量': 'sum',
        COLUMNS['pipeline']: lambda x: '、'.join(pd.unique(x.astype(str))),
        '材料唯一码': lambda x: '、'.join(pd.unique(x.astype(str))),
        '材料油漆': lambda x: x.iloc[0] if len(x) > 0 else '',
        '材料代号': lambda x: x.iloc[0] if len(x) > 0 else '',
        '单位': lambda x: x.iloc[0] if len(x) > 0 else '',
        '描述': lambda x: x.iloc[0] if len(x) > 0 else ''
    }).reset_index()
    summary_df.columns = ['材料代码', '设计总数量', '需领料总数量', '涉及管线号', '材料唯一码列表', '材料油漆',
                          '材料代号', '单位', '描述']
    summary_df['设计数量占比(%)'] = (summary_df['设计总数量'] / summary_df['设计总数量'].sum() * 100).round(2)
    summary_df['需领料数量占比(%)'] = (summary_df['需领料总数量'] / summary_df['需领料总数量'].sum() * 100).round(2)
    return summary_df.sort_values('材料代码').reset_index(drop=True)


def _aggregate_pick_list(material_details_df):
    if material_details_df is None or material_details_df.empty:
        return pd.DataFrame()

    material_details_df = material_details_df.copy()
    for qty_col in ('设计数量', '需领料数量'):
        if qty_col in material_details_df.columns:
            material_details_df[qty_col] = pd.to_numeric(material_details_df[qty_col], errors='coerce').fillna(0)

    group_cols = [c for c in ['材料代码', '材料油漆', '材料代号', '单位', '描述'] if c in material_details_df.columns]
    if not group_cols:
        return pd.DataFrame()

    agg_map = {}
    if '设计数量' in material_details_df.columns:
        agg_map['设计数量'] = 'sum'
    if '需领料数量' in material_details_df.columns:
        agg_map['需领料数量'] = 'sum'
    if COLUMNS['pipeline'] in material_details_df.columns:
        agg_map[COLUMNS['pipeline']] = lambda x: '、'.join(pd.unique(x.astype(str)))
    if COLUMNS['segment_no'] in material_details_df.columns:
        agg_map[COLUMNS['segment_no']] = lambda x: '、'.join(pd.unique(x.astype(str)))

    out = material_details_df.groupby(group_cols, as_index=False).agg(agg_map)
    if '材料代码' in out.columns:
        out = out.sort_values('材料代码')
    return out.reset_index(drop=True)


def save_material_detail_files(all_material_details, output_path, pipe_pick_output_path, fitting_pick_output_path):
    try:
        prepare_output_file(output_path)
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            for sheet_name, material_details_df in all_material_details.items():
                if material_details_df is not None and len(material_details_df) > 0:
                    material_details_df.to_excel(writer, sheet_name=str(sheet_name)[:31], index=False)

        prepare_output_file(pipe_pick_output_path)
        prepare_output_file(fitting_pick_output_path)
        with pd.ExcelWriter(pipe_pick_output_path, engine='openpyxl') as pipe_writer, \
                pd.ExcelWriter(fitting_pick_output_path, engine='openpyxl') as fitting_writer:
            for sheet_name, material_details_df in all_material_details.items():
                if material_details_df is None or material_details_df.empty or '材料代号' not in material_details_df.columns:
                    continue

                code_series = material_details_df['材料代号'].astype(str).str.upper().str.strip()
                pipe_df = _aggregate_pick_list(material_details_df[code_series == 'P'].copy())
                fitting_df = _aggregate_pick_list(material_details_df[code_series != 'P'].copy())

                if not pipe_df.empty:
                    pipe_df.to_excel(pipe_writer, sheet_name=str(sheet_name)[:31], index=False)
                if not fitting_df.empty:
                    fitting_df.to_excel(fitting_writer, sheet_name=str(sheet_name)[:31], index=False)
        return True
    except Exception as e:
        _log(f"保存文件时出错：{e}")
        return False

