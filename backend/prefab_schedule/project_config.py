# -*- coding: utf-8 -*-
"""项目公共配置：目录、通用列名、列别名和全局开关。"""

from pathlib import Path
import os


BASE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BASE_DIR.parent
FILE_ROOT = BACKEND_DIR / 'file'

DATA_DIR = Path(os.environ.get('PIPECLOUD_DATA_ROOT', FILE_ROOT / 'projects'))
INTERMEDIATE_DIR = DATA_DIR / '中间结果'
LIBRARY_DIR = DATA_DIR / '库管理'
SCHEDULE_DIR = DATA_DIR / '焊接排产单'
ARRIVAL_DIR = DATA_DIR / '入库单'
BACKUP_DIR = Path(os.environ.get('PIPECLOUD_BACKUP_ROOT', FILE_ROOT / 'backups' / DATA_DIR.name))

BACKUP = {
    'enabled': True,
    'backup_dir': BACKUP_DIR,
}

INIT_DATA_COLUMNS = {
    'unit': '单元号',
    'pipeline': '管线号',
    'segment_no': '管段号',
    'joint_type': '接头类型',
    'thickness': '壁厚',
    'diameter': '寸径',
    'outer_diameter': '外径',
    'weld_area': '焊接区域',
    'material_unique_1': '材料唯一码1',
    'material_unique_2': '材料唯一码2',
    'material_no_1': '材料代号1',
    'material_no_2': '材料代号2',
    'qty_1': '数量1',
    'qty_2': '数量2',
    'weld_no_start': '初始焊口号',
    'weld_no_final': '最终焊口号',
    'material': '材质',
    'material_type': '材质代号',
    'material_code_1': '材料代码1',
    'material_code_2': '材料代码2',
    'paint_1': '材料油漆1',
    'paint_2': '材料油漆2',
    'desc_1': '描述1',
    'desc_2': '描述2',
}

GENERATED_COLUMNS = {
    'picked_flag': '已抽取',
    'completed_flag': '是否完成',
    'library_seq': '库序号',
    'weld_method': '焊接方式',
    'weld_priority': '优先级',
}

COLUMNS = {
    **INIT_DATA_COLUMNS,
    **GENERATED_COLUMNS,
}

INIT_DATA_COLUMN_KEYS = list(INIT_DATA_COLUMNS.keys())
GENERATED_COLUMN_KEYS = list(GENERATED_COLUMNS.keys())

COLUMN_ALIASES = {
    COLUMNS['unit']: ['单元号(必填)', '单元号'],
    COLUMNS['pipeline']: ['管线号(必填)', '管线号'],
    COLUMNS['segment_no']: ['预制组件', '管段号', '预制管段', '预制段'],
    COLUMNS['joint_type']: ['接头类型', '连接方式'],
    COLUMNS['thickness']: ['壁厚', '壁厚尺寸'],
    COLUMNS['diameter']: ['英制', '英制尺寸'],
    COLUMNS['outer_diameter']: ['外径', '公制外径'],
    COLUMNS['weld_area']: ['焊接区域', '焊接区'],
    COLUMNS['material_no_1']: ['材料代号1', '材料编号1'],
    COLUMNS['material_no_2']: ['材料代号2', '材料编号2'],
    COLUMNS['qty_1']: ['数量1', '数量_1'],
    COLUMNS['qty_2']: ['数量2', '数量_2'],
    COLUMNS['material_unique_1']: ['材料唯一码1', '材料唯一码_1', '材料唯一编码1'],
    COLUMNS['material_unique_2']: ['材料唯一码2', '材料唯一码_2', '材料唯一编码2'],
    COLUMNS['picked_flag']: ['已抽取', '是否抽取', '抽取标记', '抽取标志'],
    COLUMNS['completed_flag']: ['是否完成', '完成状态', '状态', '完工状态'],
    COLUMNS['weld_no_start']: ['初始焊口号', '起始焊口号', '焊口起始号', '开始焊口号'],
    COLUMNS['weld_no_final']: ['最终焊口号', '结束焊口号', '焊口结束号', '完成焊口号'],
    COLUMNS['material']: ['材质', '材质名称'],
    COLUMNS['material_type']: ['材质代号', '材质类型'],
    COLUMNS['material_code_1']: ['材料代码1'],
    COLUMNS['material_code_2']: ['材料代码2'],
    COLUMNS['paint_1']: ['材料油漆1', '油漆1'],
    COLUMNS['paint_2']: ['材料油漆2', '油漆2'],
    COLUMNS['desc_1']: ['描述1', '材料描述1'],
    COLUMNS['desc_2']: ['描述2', '材料描述2'],
    COLUMNS['library_seq']: ['库序号', '序号', '行号'],
    COLUMNS['weld_method']: ['焊接方式', '焊接方法', '焊口类型'],
    COLUMNS['weld_priority']: ['优先级', '焊口优先级', '排产优先级'],
}

EXTRA_MATERIAL_QTY_FOR_P = 0.1
DEFAULT_WELD_PRIORITY = 1
VERBOSE = True
