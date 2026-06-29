# -*- coding: utf-8 -*-
"""防腐管理及排产配置。"""

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from project_config import *  # noqa: F401,F403


ANTI_CORROSION_DIR = DATA_DIR / '防腐委托单'

ANTI_CORROSION_FILES = {
    'pipe_library': LIBRARY_DIR / '防腐管子材料库.xlsx',
    'fitting_library': LIBRARY_DIR / '防腐管件法兰材料库.xlsx',
    'commission_summary_output': ANTI_CORROSION_DIR / '防腐委托总表.xlsx',
}
