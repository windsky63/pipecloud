import shutil
from datetime import datetime
from pathlib import Path

from project_config import BACKUP, COLUMN_ALIASES


def normalize_columns(df):
    """重命名DF中的列"""
    rename_map = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        if canonical in df.columns:
            continue
        for alias in aliases:
            if alias in df.columns:
                rename_map[alias] = canonical
                break
    return df.rename(columns=rename_map)


def backup_file(file_path):
    """按配置在覆盖已有文件前备份。"""
    if not BACKUP.get('enabled', True):
        return None

    source_path = Path(file_path)
    if not source_path.exists() or not source_path.is_file():
        return None

    backup_dir = Path(BACKUP['backup_dir'])
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f"{source_path.stem}_{timestamp}{source_path.suffix}"
    backup_path = backup_dir / backup_name

    counter = 1
    while backup_path.exists():
        backup_name = f"{source_path.stem}_{timestamp}_{counter}{source_path.suffix}"
        backup_path = backup_dir / backup_name
        counter += 1

    shutil.copy2(source_path, backup_path)
    return backup_path


def prepare_output_file(file_path):
    """创建输出目录，并在覆盖已有文件前备份。"""
    output_path = Path(file_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return backup_file(output_path)


def calculate_unit_area(row):
    """
    根据材料代码和物理属性计算单位面积 (m^2)。
    逻辑已根据您的最新反馈进行最终精化。
    """
    material_code = str(row.get('材料代码', '')).strip().upper()

    # 获取所有可能的尺寸
    od1 = row.get('外径1', 0)
    wt1 = row.get('壁厚1', 0)
    od2 = row.get('外径2', 0)
    # wt2 = row.get('壁厚2', 0)

    # 将尺寸强制转换为数值
    try:
        od1 = float(od1)
    except (ValueError, TypeError):
        od1 = 0
    try:
        wt1 = float(wt1)
    except (ValueError, TypeError):
        wt1 = 0
    try:
        od2 = float(od2)
    except (ValueError, TypeError):
        od2 = 0

    # 管道
    if material_code.startswith('P'):
        return 3.14 * od1 / 1000

    # 45度弯头
    elif material_code.startswith('45EL'):
        return (3.14 * od1 / 1000) * (1.5 * od1 / 1000) * 0.75

    # 90度弯头
    elif material_code.startswith('90EL'):
        return (3.14 * od1 / 1000) * (1.5 * od1 / 1000) * 1.5

    # 45度短半径弯头 (新增)
    elif material_code.startswith('45ES'):
        # 短半径(SR)弯头的中心线长度估算系数为1.0
        return (3.14 * od1 / 1000) * (1.0 * od1 / 1000) * 0.75

    # 90度短半径弯头 (新增)
    elif material_code.startswith('90ES'):
        return (3.14 * od1 / 1000) * (1.0 * od1 / 1000) * 1.5

    # 法兰类
    elif material_code.startswith('B') or material_code.startswith('F'):
        if wt1 > 0:
            return 3.14 * (od1 / 1000) * (wt1 / 1000) * 2
        else:
            estimated_wt = od1 / 10 if od1 > 0 else 0
            inner_diameter = od1 - 2 * estimated_wt
            if inner_diameter < 0: inner_diameter = 0
            return (3.14 / 4) * ((od1 / 1000) ** 2 - (inner_diameter / 1000) ** 2) * 2

    # 三通类 (逻辑细化)
    elif material_code.startswith(('T', 'LT', '45T', '45LT')):  # 等径三通
        main_pipe_area = (3.14 * od1 / 1000) * (od1 / 1000)
        branch_pipe_area = (3.14 * od1 / 1000) * (od1 / 2 / 1000)
        return main_pipe_area + branch_pipe_area
    elif material_code.startswith(('RT', 'RLT', '45RT', '45RLT')):  # 异径三通
        main_pipe_area = (3.14 * od1 / 1000) * (od1 / 1000)
        # 增加od2回退逻辑
        branch_od = od2 if od2 > 0 else od1
        branch_pipe_area = (3.14 * branch_od / 1000) * (branch_od / 2 / 1000)
        return main_pipe_area + branch_pipe_area

    # 大小头
    elif material_code.startswith('RC') or material_code.startswith('RE'):
        if od1 > 0 and od2 > 0:
            avg_diameter = (od1 + od2) / 2
            length_L = 1.5 * avg_diameter
            return 3.14 * (avg_diameter / 1000) * (length_L / 1000)
        else:
            return 3.14 * (od1 / 1000) ** 2 * 1.5

    # 管台 (逻辑细化)
    elif material_code.startswith(('O', 'CP', 'HC', '45HC')):
        # 基于支管外径od2计算, 如果od2无效则回退到od1
        outlet_od = od2 if od2 > 0 else od1
        return 3.14 * (outlet_od / 1000) ** 2

        # 管帽 (新增)
    elif material_code.startswith('CAP'):
        # 估算为圆形平板面积 π*D^2/4
        return 3.14 * (od1 / 1000) ** 2 / 4

    # 无匹配则返回0
    return 0
