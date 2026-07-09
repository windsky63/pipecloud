from pathlib import Path
import sys
from decimal import Decimal, InvalidOperation

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
AUTO_WELD_DIR = ROOT_DIR / 'welding' / 'auto_weld_schedule'
if str(AUTO_WELD_DIR) not in sys.path:
    sys.path.insert(0, str(AUTO_WELD_DIR))

from common_utils import normalize_columns, prepare_output_file
from initialization.init_config import COLUMNS, DEFAULT_WELD_PRIORITY, EXTRA_MATERIAL_QTY_FOR_P, FILES, VERBOSE
from generate_material_detail import read_all_sheets


AUTO_WELD = '自动焊'
MANUAL_WELD = '手工焊'


def _log(*args, **kwargs):
    if VERBOSE:
        print(*args, **kwargs)


def to_bool_series(series):
    true_values = {'true', '1', 'yes', 'y', '完成', '已完成', 'done', 'finished'}
    false_values = {'false', '0', 'no', 'n', '未完成', '进行中', 'pending', ''}
    normalized = series.fillna('').astype(str).str.strip().str.lower()
    out = pd.Series(False, index=series.index)
    out.loc[normalized.isin(true_values)] = True
    out.loc[normalized.isin(false_values)] = False
    return out


def build_library_key(df):
    key_cols = [
        COLUMNS['weld_no_final'],
        COLUMNS['weld_no_start'],
        COLUMNS['pipeline'],
        COLUMNS['unit'],
        COLUMNS['diameter'],
    ]
    existing = [col for col in key_cols if col in df.columns]
    if not existing:
        seq_col = COLUMNS.get('library_seq')
        if seq_col and seq_col in df.columns:
            return df[seq_col].astype('string').fillna('').str.strip()
        return pd.Series(range(len(df)), index=df.index).astype(str)

    key_df = df[existing].copy()
    for col in existing:
        raw_series = key_df[col]
        numeric_series = pd.to_numeric(raw_series, errors='coerce')
        normalized = raw_series.astype('string')
        numeric_mask = numeric_series.notna()
        if numeric_mask.any():
            normalized.loc[numeric_mask] = numeric_series.loc[numeric_mask].map(lambda value: format(float(value), 'g'))
        key_df[col] = normalized.fillna('').str.strip()
    return key_df.agg('|'.join, axis=1)


def _read_excel_normalized(file_path, sheet_name=0, required=True):
    file_path = Path(file_path)
    if not file_path.exists():
        if required:
            raise FileNotFoundError(f'焊口库来源文件不存在：{file_path}')
        return pd.DataFrame()
    return normalize_columns(pd.read_excel(file_path, sheet_name=sheet_name))


def _read_prefab_welds(prefab_source_file):
    return _read_excel_normalized(prefab_source_file, sheet_name='可预制焊口')


def _read_auto_welds(auto_source_file):
    return _read_excel_normalized(auto_source_file)


def _prepare_source_df(df, weld_method):
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    out[COLUMNS['weld_method']] = weld_method
    return out


def ensure_priority_column(library_df):
    priority_col = COLUMNS['weld_priority']
    if priority_col not in library_df.columns:
        library_df[priority_col] = DEFAULT_WELD_PRIORITY
    else:
        priority = pd.to_numeric(library_df[priority_col], errors='coerce').fillna(DEFAULT_WELD_PRIORITY)
        library_df[priority_col] = priority.astype(int)
    return library_df


def _decimal_text(value, precision=6):
    text = str(value or '').strip()
    if not text or text.lower() == 'nan':
        return text
    try:
        number = Decimal(text)
    except InvalidOperation:
        return text
    quantum = Decimal(1).scaleb(-precision)
    return format(number.quantize(quantum).normalize(), 'f')


def _add_decimal_text(value, increment):
    text = str(value or '').strip()
    if not text or text.lower() == 'nan':
        return text
    try:
        result = Decimal(text) + Decimal(str(increment))
    except InvalidOperation:
        return text
    return _decimal_text(result)


def apply_extra_pipe_material_qty(library_df):
    out = library_df.copy()
    changed_count = 0

    for side in (1, 2):
        material_no_col = COLUMNS[f'material_no_{side}']
        qty_col = COLUMNS[f'qty_{side}']
        if qty_col not in out.columns:
            continue

        out[qty_col] = out[qty_col].map(_decimal_text)
        if material_no_col not in out.columns:
            continue

        p_mask = out[material_no_col].fillna('').astype(str).str.upper().str.strip().eq('P')
        qty_text = out[qty_col].fillna('').astype(str).str.strip()
        valid_mask = p_mask & qty_text.ne('') & qty_text.str.lower().ne('nan')
        if not valid_mask.any():
            continue

        out.loc[valid_mask, qty_col] = out.loc[valid_mask, qty_col].map(
            lambda value: _add_decimal_text(value, EXTRA_MATERIAL_QTY_FOR_P)
        )
        changed_count += int(valid_mask.sum())

    return out, changed_count


def build_unified_weld_library(prefab_df, auto_df):
    prefab_df = _prepare_source_df(prefab_df, MANUAL_WELD)
    auto_df = _prepare_source_df(auto_df, AUTO_WELD)
    source_frames = [df for df in [prefab_df, auto_df] if df is not None and not df.empty]
    if not source_frames:
        return pd.DataFrame()

    library_df = pd.concat(source_frames, ignore_index=True, sort=False)
    library_df['_key'] = build_library_key(library_df)
    library_df = library_df.drop_duplicates('_key', keep='last').drop(columns=['_key'])

    seq_col = COLUMNS['library_seq']
    if seq_col not in library_df.columns:
        raise ValueError('焊口数据缺少库序号，请重新导入初始化数据或解析 IDF 文件')
    sequence = library_df.pop(seq_col).fillna('').astype(str).str.strip()
    if sequence.eq('').any():
        raise ValueError('焊口数据存在空库序号，请重新导入初始化数据或解析 IDF 文件')
    if sequence.duplicated().any():
        duplicates = sorted(sequence.loc[sequence.duplicated(keep=False)].unique())
        raise ValueError(f'焊口数据存在重复库序号：{", ".join(duplicates[:10])}')
    library_df.insert(0, seq_col, sequence)
    return library_df.reset_index(drop=True)


def load_priority_adjustments(priority_adjustment_file):
    priority_path = Path(priority_adjustment_file)
    if not priority_path.exists():
        _log(f'未找到焊口优先级调整表，使用默认优先级：{priority_path}')
        return pd.DataFrame()

    priority_df = normalize_columns(pd.read_excel(priority_path))
    priority_col = COLUMNS['weld_priority']
    if priority_col not in priority_df.columns:
        _log(f'焊口优先级调整表缺少列：{priority_col}，已跳过')
        return pd.DataFrame()

    priority_df[priority_col] = pd.to_numeric(priority_df[priority_col], errors='coerce')
    priority_df = priority_df[priority_df[priority_col].notna()].copy()
    priority_df[priority_col] = priority_df[priority_col].astype(int)
    return priority_df


def apply_priority_to_library(library_df, priority_df):
    library_df = ensure_priority_column(library_df)
    if priority_df is None or priority_df.empty:
        return library_df, 0

    priority_col = COLUMNS['weld_priority']
    lib = library_df.copy()
    lib['_key'] = build_library_key(lib)
    priority_work_df = priority_df.copy()
    priority_work_df['_key'] = build_library_key(priority_work_df)
    priority_map = (
        priority_work_df.dropna(subset=['_key'])
        .drop_duplicates('_key', keep='last')
        .set_index('_key')[priority_col]
        .to_dict()
    )

    matched_mask = lib['_key'].isin(priority_map)
    matched_count = int(matched_mask.sum())
    if matched_count > 0:
        lib.loc[matched_mask, priority_col] = lib.loc[matched_mask, '_key'].map(priority_map).astype(int)

    return lib.drop(columns=['_key']), matched_count


def load_completed_orders(work_order_file):
    work_order_path = Path(work_order_file)
    if not work_order_path.exists():
        return pd.DataFrame()

    all_sheets = read_all_sheets(str(work_order_path))
    if not all_sheets:
        return pd.DataFrame()

    completed_col = COLUMNS['completed_flag']
    completed_frames = []
    for _, df in all_sheets.items():
        if df is None or df.empty or completed_col not in df.columns:
            continue

        completed = df.loc[to_bool_series(df[completed_col])].copy()
        if not completed.empty:
            completed_frames.append(completed)

    if not completed_frames:
        return pd.DataFrame()
    return pd.concat(completed_frames, ignore_index=True)


def apply_completed_to_library(library_df, completed_df):
    if completed_df is None or completed_df.empty:
        return library_df, 0

    completed_col = COLUMNS['completed_flag']
    if completed_col in completed_df.columns:
        completed_df = completed_df.loc[to_bool_series(completed_df[completed_col])].copy()
        if completed_df.empty:
            return library_df, 0
    else:
        return library_df, 0

    if completed_col not in library_df.columns:
        library_df[completed_col] = False

    lib = library_df.copy()
    lib[completed_col] = to_bool_series(lib[completed_col]).astype(object)
    lib['_key'] = build_library_key(lib)
    completed_keys = set(build_library_key(completed_df))

    completed_mask = lib['_key'].isin(completed_keys)
    completed_count = int(completed_mask.sum())
    if completed_count > 0:
        lib.loc[completed_mask, completed_col] = True

    return lib.drop(columns=['_key']), completed_count


def _load_existing_completed_library(library_file):
    library_path = Path(library_file)
    completed_col = COLUMNS['completed_flag']
    if not library_path.exists():
        return pd.DataFrame()

    library_df = normalize_columns(pd.read_excel(library_path))
    if completed_col not in library_df.columns:
        return pd.DataFrame()
    return library_df.loc[to_bool_series(library_df[completed_col])].copy()


def _load_existing_priority_library(library_file):
    library_path = Path(library_file)
    priority_col = COLUMNS['weld_priority']
    if not library_path.exists():
        return pd.DataFrame()

    library_df = normalize_columns(pd.read_excel(library_path))
    if priority_col not in library_df.columns:
        return pd.DataFrame()

    priority = pd.to_numeric(library_df[priority_col], errors='coerce')
    priority_df = library_df.loc[priority.notna()].copy()
    if priority_df.empty:
        return pd.DataFrame()

    priority_df[priority_col] = priority.loc[priority.notna()].astype(int)
    return priority_df


def save_weld_library(library_df, library_file):
    output_path = Path(library_file)
    prepare_output_file(output_path)
    library_df.to_excel(output_path, index=False)
    _log(f'已更新焊口库：{output_path}')


def maintain_weld_library(
    prefab_source_file=None,
    auto_source_file=None,
    library_file=None,
    work_order_file=None,
):
    prefab_source_file = Path(prefab_source_file or FILES['prefab_filtered_output'])
    auto_source_file = Path(auto_source_file or FILES['weld_library_source'])
    library_file = Path(library_file or FILES['weld_library'])
    work_order_file = Path(work_order_file or FILES['extract_output_data'])

    prefab_df = _read_prefab_welds(prefab_source_file)
    auto_df = _read_auto_welds(auto_source_file)
    library_df = build_unified_weld_library(prefab_df, auto_df)
    if library_df.empty:
        raise ValueError('可预制焊口初步过滤结果和自动焊口数据均为空，无法生成焊口库')

    library_df, extra_qty_count = apply_extra_pipe_material_qty(library_df)

    completed_col = COLUMNS['completed_flag']
    default_status_cols = [
        COLUMNS['material_arrival_status'],
        COLUMNS['material_anti_corrosion_status'],
        COLUMNS['material_cutting_status'],
    ]
    for status_col in default_status_cols:
        if status_col not in library_df.columns:
            library_df[status_col] = False
        else:
            library_df[status_col] = to_bool_series(library_df[status_col]).astype(bool)
    if completed_col not in library_df.columns:
        library_df[completed_col] = False
    else:
        library_df[completed_col] = to_bool_series(library_df[completed_col])

    library_df = ensure_priority_column(library_df)

    existing_priority_df = _load_existing_priority_library(library_file)
    library_df, existing_priority_count = apply_priority_to_library(library_df, existing_priority_df)

    existing_completed_df = _load_existing_completed_library(library_file)
    library_df, existing_completed_count = apply_completed_to_library(library_df, existing_completed_df)

    completed_orders_df = load_completed_orders(work_order_file)
    library_df, order_completed_count = apply_completed_to_library(library_df, completed_orders_df)

    if existing_priority_count > 0:
        _log(f'已从既有焊口库保留优先级：{existing_priority_count} 条')
    if existing_completed_count > 0:
        _log(f'已从既有焊口库保留完成状态：{existing_completed_count} 条')
    if order_completed_count > 0:
        _log(f'已从排产单回写完成状态：{order_completed_count} 条')
    if extra_qty_count > 0:
        _log(f"已在焊口库中为 {extra_qty_count} 条材料代号为 'P' 的记录增加额外领料量：{EXTRA_MATERIAL_QTY_FOR_P}")

    save_weld_library(library_df, library_file)
    return library_df


if __name__ == '__main__':
    maintain_weld_library()



