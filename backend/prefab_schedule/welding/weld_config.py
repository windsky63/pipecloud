# -*- coding: utf-8 -*-
"""焊接管理及排产配置。"""

from pathlib import Path
import sys
from datetime import datetime

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from project_config import *  # noqa: F401,F403
from initialization.init_config import FILES as INIT_FILES, PATTERN_CONFIG


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
    **INIT_FILES,
    'extract_input': WELD_PRE_SCHEDULE_INPUT,
    'extract_output_data': SCHEDULE_DIR / '管段焊口表.xlsx',
    'extract_output_stats': SCHEDULE_DIR / '抽取统计信息.xlsx',
    'material_input': SCHEDULE_DIR / '管段焊口表.xlsx',
    'segment_list_output': SCHEDULE_DIR / '管段清单.xlsx',
    'material_output': SCHEDULE_DIR / '材料明细表.xlsx',
    'pipe_pick_list_output': SCHEDULE_DIR / '管子领料单.xlsx',
    'fitting_pick_list_output': SCHEDULE_DIR / '管件法兰领料单.xlsx',
}

EXTRACT = {
    'target_diameter': 260,
    'num_extractions': 3,
    'save_extract_stats': False,
}
