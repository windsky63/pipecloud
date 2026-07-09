# -*- coding: utf-8 -*-
"""初始化文件处理配置。"""

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from project_config import *  # noqa: F401,F403


def _resolve_input_file():
    env_file = os.environ.get('PIPECLOUD_INIT_WELD_FILE')
    if env_file:
        return Path(env_file)

    candidates = [
        file_path
        for file_path in DATA_DIR.glob('焊口初始化数据*.xlsx')
        if file_path.is_file() and not file_path.name.startswith('~$')
    ]
    if candidates:
        return sorted(candidates, key=lambda item: item.stat().st_mtime, reverse=True)[0]

    return DATA_DIR / '焊口初始化数据.xlsx'


FILES = {
    'input': _resolve_input_file(),
    'prefab_filtered_output': INTERMEDIATE_DIR / '可预制焊口初步过滤结果.xlsx',
    'filtered_output': INTERMEDIATE_DIR / '自动焊口初步过滤结果.xlsx',
    'link_output': INTERMEDIATE_DIR / '链路划分结果.xlsx',
    'final_output': INTERMEDIATE_DIR / '自动焊口数据.xlsx',
    'final_filter_stats_output': INTERMEDIATE_DIR / '自动焊口过滤统计.xlsx',
    'weld_library_source': INTERMEDIATE_DIR / '自动焊口数据.xlsx',
    'weld_library': LIBRARY_DIR / '焊口库.xlsx',
    'extract_output_data': SCHEDULE_DIR / '管段焊口表.xlsx',
    'init_material_output': INTERMEDIATE_DIR / '初始化数据材料明细表.xlsx',
}

PREFAB_WELD_FILTERS = {
    COLUMNS['weld_area']: 'S',
    COLUMNS['material_type']: 'CS',
}

AUTO_WELD_FILTERS = {
    COLUMNS['joint_type']: 'BW',
    COLUMNS['thickness']: ('between', 6, 25),
    COLUMNS['diameter']: ('between', 8, 24),
}

FILTERS = {
    **PREFAB_WELD_FILTERS,
    **AUTO_WELD_FILTERS,
}

READ_OPTIONS = {
    'init_skiprows': 0,
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
