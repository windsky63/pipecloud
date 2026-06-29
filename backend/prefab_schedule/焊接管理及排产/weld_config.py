# -*- coding: utf-8 -*-
"""焊接管理及排产配置。"""

from pathlib import Path
import sys
from datetime import datetime

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from project_config import *  # noqa: F401,F403


WELD_SCHEDULE_DATE_FORMAT = '%Y%m%d'
WELD_PRE_SCHEDULE_INPUT = INTERMEDIATE_DIR / '焊口预排产匹配结果.xlsx'


def get_weld_schedule_date(date_value=None):
    if date_value:
        return str(date_value)
    return datetime.now().strftime(WELD_SCHEDULE_DATE_FORMAT)


def get_weld_schedule_output_dir(date_value=None):
    return SCHEDULE_DIR / get_weld_schedule_date(date_value)


def get_weld_schedule_output_files(date_value=None):
    output_dir = get_weld_schedule_output_dir(date_value)
    return {
        'extract_output_data': output_dir / '管段焊口表.xlsx',
        'extract_output_stats': output_dir / '抽取统计信息.xlsx',
        'material_input': output_dir / '管段焊口表.xlsx',
        'segment_list_output': output_dir / '管段清单.xlsx',
        'material_output': output_dir / '材料明细表.xlsx',
        'pipe_pick_list_output': output_dir / '管子领料单.xlsx',
        'fitting_pick_list_output': output_dir / '管件法兰领料单.xlsx',
    }


FILES = {
    'prefab_filtered_output': INTERMEDIATE_DIR / '可预制焊口初步过滤结果.xlsx',
    'filtered_output': INTERMEDIATE_DIR / '自动焊口初步过滤结果.xlsx',
    'link_output': INTERMEDIATE_DIR / '链路划分结果.xlsx',
    'final_output': INTERMEDIATE_DIR / '自动焊口数据.xlsx',
    'final_filter_stats_output': INTERMEDIATE_DIR / '自动焊口过滤统计.xlsx',
    'weld_library_source': INTERMEDIATE_DIR / '自动焊口数据.xlsx',
    'weld_library': LIBRARY_DIR / '焊口库.xlsx',
    'extract_input': WELD_PRE_SCHEDULE_INPUT,
    'extract_output_data': SCHEDULE_DIR / '管段焊口表.xlsx',
    'extract_output_stats': SCHEDULE_DIR / '抽取统计信息.xlsx',
    'material_input': SCHEDULE_DIR / '管段焊口表.xlsx',
    'segment_list_output': SCHEDULE_DIR / '管段清单.xlsx',
    'material_output': SCHEDULE_DIR / '材料明细表.xlsx',
    'pipe_pick_list_output': SCHEDULE_DIR / '管子领料单.xlsx',
    'fitting_pick_list_output': SCHEDULE_DIR / '管件法兰领料单.xlsx',
}

PATTERN_CONFIG = {
    'original_patterns': {
        'P-P',
        'P-E',
        'E-P-E',
        'P-F',
        'F-P-F',
        'F-P-E',
        'P-T-P',
        'P-T',
        'P-R-P',
        'P-R',
        'P-C',
        'P-T-P-E',
        'P-R-P-E',
        'E-P-C',
        'E-P-T-P-E',
        'E-P-R-P-E',
        'P-T-P-F',
        'P-R-P-F',
        'F-P-C',
        'F-P-T-P-F',
        'F-P-R-P-F',
        'F-P-T-P-E',
        'F-P-R-P-E',
        'F-E',
        'F-R',
        'F-T',
        'T-E',
        'F-T-E',
        'F-T-R',
        'R-T-E',
        'F-T-R-E',
        'T-C',
    }
}

EXTRACT = {
    'target_diameter': 260,
    'num_extractions': 3,
    'save_extract_stats': False,
}
