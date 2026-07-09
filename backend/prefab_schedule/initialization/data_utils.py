import pandas as pd
from initialization.init_config import COLUMNS, COLUMN_ALIASES, INIT_DATA_COLUMN_KEYS, READ_OPTIONS
from common_utils import normalize_columns, prepare_output_file


def _required_columns_for_init_data():
    return [COLUMNS[key] for key in INIT_DATA_COLUMN_KEYS]


def _required_alias_pool(column_keys=None):
    pool = set()
    required_columns = None
    if column_keys is not None:
        required_columns = {COLUMNS[key] for key in column_keys}

    for canonical, aliases in COLUMN_ALIASES.items():
        if required_columns is not None and canonical not in required_columns:
            continue
        pool.add(canonical)
        pool.update(aliases)
    return pool


def read_excel_file(file_path, sheet_name=0, skiprows=None):
    try:
        if skiprows is None:
            skiprows = READ_OPTIONS.get('init_skiprows', 1)
        df = pd.read_excel(file_path, sheet_name=sheet_name, skiprows=skiprows)

        alias_pool = _required_alias_pool(INIT_DATA_COLUMN_KEYS)
        pre_cols = [c for c in df.columns if c in alias_pool]
        if pre_cols:
            df = df[pre_cols].copy()

        df = normalize_columns(df)

        required_cols = _required_columns_for_init_data()
        existing_required = [c for c in required_cols if c in df.columns]
        missing_required = [c for c in required_cols if c not in df.columns]

        df = df[existing_required].copy()

        print(f"成功读取Excel文件：{file_path}")
        print(f"数据维度：{df.shape[0]}行 x {df.shape[1]}列")
        print(f"保留列数量：{len(existing_required)}")
        if missing_required:
            print(f"警告：缺失列 {missing_required}")
        return df
    except Exception as e:
        print(f"读取Excel文件时出错：{e}")
        return None


def filter_data(df, filters=None):
    if df is None:
        return None, None
    if not filters:
        return df, None

    original_count = len(df)
    df_valid = df.copy()
    df_valid['_is_valid'] = True

    for column, condition in filters.items():
        if column not in df_valid.columns:
            print(f"警告：列 '{column}' 不存在，跳过")
            continue

        before = int(df_valid['_is_valid'].sum())
        if isinstance(condition, tuple) and len(condition) == 3 and condition[0] == 'between':
            min_val, max_val = condition[1], condition[2]
            mask = (df_valid[column] >= min_val) & (df_valid[column] <= max_val)
        else:
            if df_valid[column].dtype == 'object':
                mask = df_valid[column].astype(str).str.upper().str.strip() == str(condition).upper().strip()
            else:
                mask = df_valid[column] == condition

        df_valid['_is_valid'] = df_valid['_is_valid'] & mask
        after = int(df_valid['_is_valid'].sum())
        print(f"过滤 {column}: 满足{after}，新增不满足{before - after}")

    valid_df = df_valid[df_valid['_is_valid']].copy().drop(columns=['_is_valid'], errors='ignore')
    invalid_df = df_valid[~df_valid['_is_valid']].copy().drop(columns=['_is_valid'], errors='ignore')

    print(f"过滤总结：原始{original_count}，有效{len(valid_df)}，无效{len(invalid_df)}")
    return valid_df, invalid_df


def sort_grouped_pipelines(df):
    if df is None or df.empty:
        return None, None, None

    unit_col = COLUMNS['unit']
    pipeline_col = COLUMNS['pipeline']
    segment_no_col = COLUMNS['segment_no']

    sorted_df = df.sort_values(by=[unit_col, pipeline_col, segment_no_col], ascending=[True, True, True])

    summary_stats = (
        df.groupby([unit_col, pipeline_col, segment_no_col]).size().reset_index(name='焊口数量')
        .sort_values(by=[unit_col, pipeline_col, segment_no_col], ascending=[True, True, True])
    )

    pipeline_total_stats = (
        df.groupby([unit_col, pipeline_col]).size().reset_index(name='该管线总焊口数')
        .sort_values(by=[unit_col, pipeline_col], ascending=[True, True])
    )

    return sorted_df, summary_stats, pipeline_total_stats


def save_to_excel_with_sheets(df_dict, output_file_path):
    if not df_dict:
        return False

    try:
        prepare_output_file(output_file_path)
        with pd.ExcelWriter(output_file_path, engine='openpyxl') as writer:
            for sheet_name, df in df_dict.items():
                if df is not None and not df.empty:
                    df.to_excel(writer, sheet_name=sheet_name[:31], index=False)
        print(f"数据已保存到: {output_file_path}")
        return True
    except Exception as e:
        print(f"保存文件失败: {e}")
        return False
