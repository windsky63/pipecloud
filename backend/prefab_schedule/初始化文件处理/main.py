from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from 初始化文件处理.init_config import AUTO_WELD_FILTERS, COLUMNS, FILES, PREFAB_WELD_FILTERS
from data_utils import filter_data, read_excel_file, save_to_excel_with_sheets, sort_grouped_pipelines


def _drop_empty_segment_no(df):
    segment_no_col = COLUMNS['segment_no']
    if df is None or df.empty or segment_no_col not in df.columns:
        return df

    mask = df[segment_no_col].notna() & (df[segment_no_col].astype(str).str.strip() != '')
    return df[mask].copy()


def _save_prefab_filter_result(valid_df):
    sheets_dict = {
        '可预制焊口': valid_df,
    }
    return save_to_excel_with_sheets(sheets_dict, FILES['prefab_filtered_output'])


def _save_auto_weld_filter_result(valid_df):
    sorted_valid_df, summary_stats, pipeline_total_stats = sort_grouped_pipelines(valid_df)
    sheets_dict = {
        '自动焊口': sorted_valid_df,
    }
    success = save_to_excel_with_sheets(sheets_dict, FILES['filtered_output'])
    return success, sorted_valid_df


def process_initial_files():
    df = read_excel_file(FILES['input'])
    if df is None:
        return False

    print('\n开始可预制焊口初步过滤')
    prefab_valid_df, prefab_invalid_df = filter_data(df, PREFAB_WELD_FILTERS)
    _save_prefab_filter_result(prefab_valid_df)

    if prefab_valid_df is None or prefab_valid_df.empty:
        print('没有满足可预制焊口规则的有效数据')
        return False

    print('\n开始自动焊口初步过滤')
    auto_valid_df, auto_invalid_df = filter_data(prefab_valid_df, AUTO_WELD_FILTERS)
    auto_valid_df = _drop_empty_segment_no(auto_valid_df)

    success, sorted_valid_df = _save_auto_weld_filter_result(auto_valid_df)
    if not success:
        return False

    if sorted_valid_df is None or sorted_valid_df.empty:
        print('没有满足自动焊口规则的有效数据')
        return False

    return True


def main():
    success = process_initial_files()
    if success:
        print(f'初始化文件处理完成，可预制输出文件: {FILES["prefab_filtered_output"]}')
        print(f'初始化文件处理完成，自动焊输出文件: {FILES["filtered_output"]}')
    else:
        print('初始化文件处理失败')


if __name__ == '__main__':
    main()
