# -*- coding: utf-8 -*-
"""到货管理配置。"""

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from project_config import *  # noqa: F401,F403


ARRIVAL_FILES = {
    'arrival_dir': ARRIVAL_DIR,
}

ARRIVAL_COLUMNS = {
    'code': '材料代码（NCC文本）',
    'warranty_no': '质保书编号',
    'heat_no': '炉批号',
    'send_qty': '发货数量（米/根）',
    'actual_qty': '实际到货数量',
    'inspection_result': '共检结果',
    'unqualified_qty': '不合格数量',
    'qualified_qty': '合格数量',
    'rectification_qty': '整改数量',
    'issue_category': '问题分类',
    'issue_description': '问题描述',
    'remark': '备注',
    'material_category': '材料分类',
    'name': '名称',
    'material': '材质',
    'spec': '规格',
    'thickness': '壁厚',
    'material_standard_no': '材质标准号',
    'spec_thickness': '规格*壁厚',
    'unit': '单位',
    'anti_corrosion': '是否需防腐',
    'description': '材料描述',
    'material_full_name': '材质全称',
    'pipe_count': '管子支数',
    'actual_pipe_count': '实际到货支数',
}

ARRIVAL_LIBRARY_COLUMNS = {
    'source_file': '来源入库单文件',
    'arrival_date': '入库日期',
    'stock_qty': '库存数量',
    'pipe_stock_qty': '库存数量（米）',
    'pipe_unique_code': '管子序号',
    'material_code_output': '材料代码',
    'anti_corrosion_status': '防腐状态',
    'anti_corrosion_stock_qty': '防腐库存数量',
    'locked_qty': '锁定数量',
    'coated_locked_qty': '已防腐锁定数量',
    'uncoated_locked_qty': '未防腐锁定数量',
    'used_qty': '已使用数量',
    'unit_area': '单位面积',
    'anti_corrosion_area': '防腐面积',
}

ARRIVAL_PIPE_RULES = {
    'unit': '米',
    'name': '管子',
    'category': '直管',
    'pipe_output_keep_cols': [
        ARRIVAL_LIBRARY_COLUMNS['pipe_unique_code'],
        ARRIVAL_LIBRARY_COLUMNS['material_code_output'],
        ARRIVAL_COLUMNS['description'],
        ARRIVAL_COLUMNS['inspection_result'],
        ARRIVAL_COLUMNS['material_category'],
        ARRIVAL_COLUMNS['name'],
        ARRIVAL_COLUMNS['material'],
        ARRIVAL_COLUMNS['spec'],
        ARRIVAL_COLUMNS['thickness'],
        ARRIVAL_COLUMNS['material_full_name'],
        ARRIVAL_COLUMNS['material_standard_no'],
        ARRIVAL_COLUMNS['spec_thickness'],
        ARRIVAL_COLUMNS['unit'],
        ARRIVAL_COLUMNS['anti_corrosion'],
        ARRIVAL_LIBRARY_COLUMNS['anti_corrosion_status'],
        ARRIVAL_LIBRARY_COLUMNS['unit_area'],
        ARRIVAL_LIBRARY_COLUMNS['anti_corrosion_area'],
        ARRIVAL_LIBRARY_COLUMNS['source_file'],
        ARRIVAL_LIBRARY_COLUMNS['arrival_date'],
        ARRIVAL_LIBRARY_COLUMNS['pipe_stock_qty'],
        ARRIVAL_LIBRARY_COLUMNS['anti_corrosion_stock_qty'],
        ARRIVAL_LIBRARY_COLUMNS['locked_qty'],
        ARRIVAL_LIBRARY_COLUMNS['coated_locked_qty'],
        ARRIVAL_LIBRARY_COLUMNS['uncoated_locked_qty'],
        ARRIVAL_LIBRARY_COLUMNS['used_qty'],
    ],
}
