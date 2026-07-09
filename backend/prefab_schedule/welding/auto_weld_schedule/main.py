from pathlib import Path
import os
import sys

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from common_utils import normalize_columns
from welding.weld_config import (
    FILES,
    COLUMNS,
    EXTRACT,
    VERBOSE,
    get_weld_schedule_date,
    get_weld_schedule_output_files,
)
from extract_welds import (
    sort_and_clean_data,
    extract_welds_multiple_times,
    save_extractions_to_excel,
    save_segment_list_to_excel,
    save_statistics_to_excel,
)
from generate_material_detail import (
    read_all_sheets,
    generate_material_details_for_sheet,
    save_material_detail_files,
)


def _log(*args, **kwargs):
    if VERBOSE:
        print(*args, **kwargs)


def _env_number(name, default, caster):
    value = os.environ.get(name)
    if value in (None, ''):
        return default
    try:
        parsed = caster(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def read_auto_weld_pre_schedule(pre_schedule_file, sheet_name='预排产匹配结果'):
    pre_schedule_path = Path(pre_schedule_file)
    if not pre_schedule_path.exists():
        raise FileNotFoundError(f'预排产结果不存在：{pre_schedule_path}，请先运行 cutting/weld_pre_schedule_matcher.py')

    library_df = normalize_columns(pd.read_excel(pre_schedule_path, sheet_name=sheet_name))
    weld_method_col = COLUMNS['weld_method']
    if weld_method_col not in library_df.columns:
        raise ValueError(f'预排产结果缺少列：{weld_method_col}')

    status_col = '预排产状态'
    if status_col not in library_df.columns:
        raise ValueError(f'预排产结果缺少列：{status_col}')

    return library_df.loc[
        library_df[weld_method_col].fillna('').astype(str).str.strip().eq('自动焊')
        & library_df[status_col].fillna('').astype(str).str.strip().eq('可预排产')
    ].copy()


def run():
    pre_schedule_file = FILES['extract_input']
    schedule_date = get_weld_schedule_date(os.environ.get('PIPECLOUD_WELD_SCHEDULE_DATE'))
    output_files = get_weld_schedule_output_files(schedule_date)
    extract_data_file = output_files['extract_output_data']
    segment_list_file = output_files['segment_list_output']
    extract_stats_file = output_files['extract_output_stats']
    material_output_file = output_files['material_output']
    pipe_pick_output_file = output_files['pipe_pick_list_output']
    fitting_pick_output_file = output_files['fitting_pick_list_output']

    target_diameter = _env_number('PIPECLOUD_WELD_TARGET_DIAMETER', EXTRACT['target_diameter'], float)
    num_extractions = _env_number('PIPECLOUD_WELD_ORDERS_PER_DAY', EXTRACT['num_extractions'], int)
    save_extract_stats = EXTRACT.get('save_extract_stats', True)
    diameter_col = COLUMNS['diameter']
    completed_col = COLUMNS['completed_flag']

    auto_library_df = read_auto_weld_pre_schedule(pre_schedule_file)
    work_df = sort_and_clean_data(auto_library_df, diameter_col, completed_col)
    all_extractions = extract_welds_multiple_times(
        work_df,
        num_extractions=num_extractions,
        target_diameter=target_diameter,
        diameter_column=diameter_col,
        completed_flag_column=completed_col,
        order_date=schedule_date,
    )
    if not all_extractions:
        _log('没有可抽取焊口，流程结束')
        return

    save_extractions_to_excel(all_extractions, extract_data_file)
    save_segment_list_to_excel(all_extractions, segment_list_file)
    if save_extract_stats:
        save_statistics_to_excel(all_extractions, extract_stats_file, diameter_col)

    all_extracted_data = read_all_sheets(extract_data_file)
    all_material_details = {}
    if all_extracted_data:
        for sheet_name, df in all_extracted_data.items():
            try:
                material_df = generate_material_details_for_sheet(sheet_name, df)
            except ValueError as error:
                raise ValueError(f'材料明细生成失败：{error}') from error
            if material_df is not None and not material_df.empty:
                all_material_details[sheet_name] = material_df

    if all_material_details:
        save_material_detail_files(
            all_material_details,
            material_output_file,
            pipe_pick_output_file,
            fitting_pick_output_file,
        )
        _log(f'已生成材料明细：{material_output_file}')
        _log(f'已生成管子领料单：{pipe_pick_output_file}')
        _log(f'已生成管件法兰领料单：{fitting_pick_output_file}')
    else:
        _log('未生成材料明细：抽取结果中没有可用材料数据')

    _log(f'焊接排产日期：{schedule_date}')
    _log(f'焊接排产输出目录：{Path(extract_data_file).parent}')


if __name__ == '__main__':
    run()
