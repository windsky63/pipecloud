# -*- coding: utf-8 -*-
"""下料管理及排产配置。"""

import os
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from project_config import *  # noqa: F401,F403


CUTTING_DIR = DATA_DIR / '下料排产单'
PRE_SCHEDULE_OUTPUT_DIR = INTERMEDIATE_DIR

def _env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return str(value).strip().lower() in {'1', 'true', 'yes', 'y', 'on'}


# 是否只将“自动焊”焊口纳入下料预排产。
PRE_SCHEDULE_ONLY_AUTO_WELD = _env_bool('PIPECLOUD_PRE_SCHEDULE_ONLY_AUTO_WELD', False)

CUTTING_FILES = {
    'prefab_weld_input': INTERMEDIATE_DIR / '可预制焊口初步过滤结果.xlsx',
    'weld_library': LIBRARY_DIR / '焊口库.xlsx',
    'init_material_input': INTERMEDIATE_DIR / '初始化数据材料明细表.xlsx',
    'pipe_library': LIBRARY_DIR / '管子材料库.xlsx',
    'fitting_library': LIBRARY_DIR / '管件法兰材料库.xlsx',
    'anti_corrosion_pipe_library': LIBRARY_DIR / '防腐管子材料库.xlsx',
    'anti_corrosion_fitting_library': LIBRARY_DIR / '防腐管件法兰材料库.xlsx',
    'pending_pipe_library': PRE_SCHEDULE_OUTPUT_DIR / '待确认管子材料库.xlsx',
    'pending_fitting_library': PRE_SCHEDULE_OUTPUT_DIR / '待确认管件法兰材料库.xlsx',
    'pending_anti_corrosion_pipe_library': PRE_SCHEDULE_OUTPUT_DIR / '待确认防腐管子材料库.xlsx',
    'pending_anti_corrosion_fitting_library': PRE_SCHEDULE_OUTPUT_DIR / '待确认防腐管件法兰材料库.xlsx',
    'weld_pre_schedule_output': PRE_SCHEDULE_OUTPUT_DIR / '焊口预排产匹配结果.xlsx',
}

MATERIAL_NO_COL = '材料代号'
MATERIAL_CODE_COL = '材料代码'
DESIGN_QTY_COL = '设计数量'
UNIT_COL = '单位'
MATERIAL_UNIQUE_COL = '材料唯一码'
PIPE_UNIQUE_CODE_COL = '管子序号'
PIPE_STOCK_QTY_COL = '库存数量（米）'
FITTING_STOCK_QTY_COL = '库存数量'

CUT_LENGTHS_COL = '已切割长度列表'
CUT_LOSSES_COL = '切割损耗列表'
CONSUMED_LENGTHS_COL = '实际占用长度列表'
REMAINING_LENGTH_COL = '剩余米数'
ORIGINAL_LENGTH_COL = '原始米数'

DEFAULT_PRIORITY = DEFAULT_WELD_PRIORITY
MATCHED_STATUS = '可预排产'
SHORTAGE_STATUS = '不可预排产'

STATUS_COL = '预排产状态'
REASON_COL = '不可预排产原因'
MATCH_SEQ_COL = '预排产序号'
MATCH_TYPE_COL = '材料类型'
MATCH_RESULT_COL = '匹配结果'
MATCH_REASON_COL = '匹配说明'
MATCHED_RESOURCE_COL = '匹配库存标识'

PRE_SCHEDULE_DETAIL_COLUMNS = [
    MATCH_SEQ_COL,
    COLUMNS['library_seq'],
    COLUMNS['weld_priority'],
    COLUMNS['unit'],
    COLUMNS['pipeline'],
    COLUMNS['segment_no'],
    COLUMNS['weld_no_start'],
    COLUMNS['weld_no_final'],
    MATCH_TYPE_COL,
    MATERIAL_CODE_COL,
    MATERIAL_UNIQUE_COL,
    '需求数量',
    '匹配数量',
    '缺料数量',
    MATCHED_RESOURCE_COL,
    MATCH_RESULT_COL,
    MATCH_REASON_COL,
]
