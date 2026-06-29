from pathlib import Path
import sys
import pandas as pd
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from 初始化文件处理.自动焊划分.auto_weld_split_config import FILES
from link_process import process_all_groups, save_link_division_results
from link_result_filter import post_process_filter


def read_initial_filter_result(filtered_output_file):
    try:
        df = pd.read_excel(filtered_output_file)
        print(f'成功读取自动焊初步过滤结果: {filtered_output_file}')
        print(f'数据行数: {len(df)}')
        return df
    except FileNotFoundError:
        print(f'未找到自动焊初步过滤结果文件: {filtered_output_file}')
        print('请先运行 初始化文件处理/main.py 生成中间结果')
        return None
    except Exception as error:
        print(f'读取自动焊初步过滤结果失败: {error}')
        return None


def main_step1():
    filtered_output_file = FILES['filtered_output']
    sorted_valid_df = read_initial_filter_result(filtered_output_file)

    if sorted_valid_df is None or sorted_valid_df.empty:
        print('没有可用于链路划分的自动焊初步过滤数据')
        return False, None, None

    link_division_results = process_all_groups(sorted_valid_df)
    link_output_file = FILES['link_output']
    save_link_division_results(link_division_results, link_output_file)

    return True, filtered_output_file, link_output_file


def main_step2(filtered_data_file, link_division_file, final_output_file, final_filter_stats_file):
    return post_process_filter(link_division_file, filtered_data_file, final_output_file, final_filter_stats_file)


def main():
    final_output_file = FILES['final_output']
    final_filter_stats_file = FILES['final_filter_stats_output']

    success_step1, filtered_data_file, link_division_file = main_step1()
    if not success_step1:
        print('第一步处理失败')
        return False

    success_step2 = main_step2(filtered_data_file, link_division_file, final_output_file, final_filter_stats_file)
    if success_step2:
        print(f'处理完成，输出文件: {final_output_file}')
        print(f'过滤统计文件: {final_filter_stats_file}')
        return True
    else:
        print('第二步处理失败')
        return False


if __name__ == '__main__':
    main()
