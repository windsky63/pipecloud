import pandas as pd
import numpy as np
from datetime import datetime
from 焊接管理及排产.自动焊排产.auto_weld_schedule_config import COLUMNS, VERBOSE
from common_utils import prepare_output_file


def _log(*args, **kwargs):
    if VERBOSE:
        print(*args, **kwargs)


def _collect_unique_values_for_order(series):
    vals = series.fillna('').astype(str).str.strip()
    vals = vals[(vals != '') & (vals.str.lower() != 'nan')]
    return list(pd.unique(vals))


def generate_schedule_order_no(extracted_df, extraction_index, unit_column=None, material_type_column=None, order_date=None):
    """
    排产单号规则：
    YZGD-单元号-材质代号-日期-k（第k次抽取）
    若存在多个单元/材质，使用 / 拼接。
    """
    unit_column = unit_column or COLUMNS['unit']
    material_type_column = material_type_column or COLUMNS['material_type']
    order_date = order_date or datetime.now().strftime('%Y%m%d')

    if extracted_df is None or extracted_df.empty:
        return f"YZGD-未知单元-未知材质-{order_date}-{extraction_index}"

    unit_values = _collect_unique_values_for_order(
        extracted_df[unit_column] if unit_column in extracted_df.columns else pd.Series(dtype=str)
    )
    material_values = []
    if material_type_column in extracted_df.columns:
        material_values.extend(_collect_unique_values_for_order(extracted_df[material_type_column]))
    material_values = list(dict.fromkeys(material_values))

    unit_part = '/'.join(unit_values) if unit_values else '未知单元'
    material_part = '/'.join(material_values) if material_values else '未知材质代号'
    return f"YZGD-{unit_part}-{material_part}-{order_date}-{extraction_index}"


def read_excel_file(file_path, sheet_name=0):
    try:
        df = pd.read_excel(file_path, sheet_name=sheet_name)
        _log(f"成功读取Excel文件：{file_path}")
        _log(f"数据维度：{df.shape[0]}行 x {df.shape[1]}列")
        return df
    except Exception as e:
        _log(f"读取Excel文件时出错：{e}")
        return None


def sort_and_clean_data(df, diameter_column=None, completed_flag_column=None):
    diameter_column = diameter_column or COLUMNS['diameter']
    completed_flag_column = completed_flag_column or COLUMNS['completed_flag']

    df = df.copy()

    df[diameter_column] = pd.to_numeric(df[diameter_column], errors='coerce')
    original_count = len(df)
    df_clean = df[df[diameter_column].notna()].copy()
    removed_count = original_count - len(df_clean)

    if removed_count > 0:
        _log(f"已删除{removed_count}行寸径无效的数据")

    df_clean['_run_picked'] = False

    if completed_flag_column not in df_clean.columns:
        df_clean[completed_flag_column] = False
    else:
        df_clean[completed_flag_column] = df_clean[completed_flag_column].fillna(False).astype(bool)

    return df_clean


def extract_welds_once(df, target_diameter=780, diameter_column=None, completed_flag_column=None):
    diameter_column = diameter_column or COLUMNS['diameter']
    completed_flag_column = completed_flag_column or COLUMNS['completed_flag']

    if '_run_picked' not in df.columns:
        df['_run_picked'] = False
    available_df = df.loc[(df['_run_picked'] == False) & (df[completed_flag_column] == False)]

    if available_df.empty:
        _log("没有可用的未完成数据")
        return None, 0, 0

    _log(f"当前可用数据：{len(available_df)}条")

    diameters = pd.to_numeric(available_df[diameter_column], errors='coerce').fillna(0).to_numpy()
    if diameters.size == 0:
        _log("无法抽取到足够数据")
        return None, 0, 0

    cumulative = np.cumsum(diameters)
    cutoff = np.searchsorted(cumulative, target_diameter, side='right')

    if cutoff == 0:
        cutoff = 0

    if cutoff >= diameters.size:
        cutoff = diameters.size - 1

    selected_df = available_df.iloc[:cutoff + 1].copy()
    actual_sum = float(selected_df[diameter_column].sum())
    n_count = len(selected_df)

    df.loc[selected_df.index, '_run_picked'] = True

    _log("\n========== 抽取结果 ==========")
    _log(f"抽取焊口数量：{n_count}条")
    _log(f"直径总和：{actual_sum:.2f}")
    _log(f"目标值：{target_diameter}")
    _log(f"超出：{actual_sum - target_diameter:.2f}")
    _log(f"超出率：{(actual_sum - target_diameter) / target_diameter * 100:.2f}%")
    _log("===============================\n")

    return selected_df, actual_sum, n_count


def extract_welds_multiple_times(df, num_extractions=1, target_diameter=780,
                                 diameter_column=None, completed_flag_column=None, order_date=None):
    diameter_column = diameter_column or COLUMNS['diameter']
    completed_flag_column = completed_flag_column or COLUMNS['completed_flag']

    all_extractions = []

    for i in range(num_extractions):
        _log(f"\n{'=' * 50}")
        _log(f"第{i + 1}次抽取")
        _log(f"{'=' * 50}")

        selected_df, actual_sum, n_count = extract_welds_once(
            df, target_diameter, diameter_column, completed_flag_column
        )

        if selected_df is None or selected_df.empty:
            _log(f"第{i + 1}次抽取失败，数据不足")
            break

        selected_df = selected_df.drop(columns=['_run_picked'], errors='ignore')

        order_no = generate_schedule_order_no(
            selected_df,
            extraction_index=i + 1,
            unit_column=COLUMNS['unit'],
            material_type_column=COLUMNS['material_type'],
            order_date=order_date,
        )
        selected_df['排产单号'] = order_no

        extraction_info = {
            '抽取次数': i + 1,
            '焊口数量': n_count,
            '直径总和': round(actual_sum, 2),
            '目标值': target_diameter,
            '超出值': round(actual_sum - target_diameter, 2),
            '超出率(%)': round((actual_sum - target_diameter) / target_diameter * 100, 2),
            '排产单号': order_no,
        }

        all_extractions.append({'data': selected_df, 'info': extraction_info})

        remaining_count = int(((df['_run_picked'] == False) & (df[completed_flag_column] == False)).sum())
        _log(f"剩余未完成数据：{remaining_count}条")
        if remaining_count == 0:
            _log("所有可用数据已抽取完毕")
            break

    return all_extractions


def save_extractions_to_excel(all_extractions, output_path):
    try:
        prepare_output_file(output_path)
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            for extraction in all_extractions:
                sheet_name = str(extraction['info']['抽取次数'])
                extraction['data'].to_excel(writer, sheet_name=sheet_name, index=False)
        _log(f"\n成功保存抽取数据到：{output_path}")
        _log(f"共保存了{len(all_extractions)}次抽取结果")
        return True
    except Exception as e:
        _log(f"保存文件时出错：{e}")
        return False


def generate_segment_list_for_sheet(df, unit_col=None, pipeline_col=None, segment_no_col=None, diameter_col=None):
    unit_col = unit_col or COLUMNS['unit']
    pipeline_col = pipeline_col or COLUMNS['pipeline']
    segment_no_col = segment_no_col or COLUMNS['segment_no']
    diameter_col = diameter_col or COLUMNS['diameter']

    if df is None or df.empty:
        return pd.DataFrame(columns=[unit_col, pipeline_col, segment_no_col, '管段总寸径'])

    required_cols = [unit_col, pipeline_col, segment_no_col, diameter_col]
    missing_cols = [c for c in required_cols if c not in df.columns]
    if missing_cols:
        raise KeyError(f'生成管段清单缺少列: {missing_cols}')

    work_df = df.copy()
    work_df[diameter_col] = pd.to_numeric(work_df[diameter_col], errors='coerce').fillna(0)

    segment_df = (
        work_df.groupby([unit_col, pipeline_col, segment_no_col], dropna=False, as_index=False)[diameter_col]
        .sum()
        .rename(columns={diameter_col: '管段总寸径'})
        .sort_values(by=[unit_col, pipeline_col, segment_no_col], ascending=[True, True, True])
    )
    return segment_df


def save_segment_list_to_excel(all_extractions, output_path):
    try:
        prepare_output_file(output_path)
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            for extraction in all_extractions:
                sheet_name = str(extraction['info']['抽取次数'])
                segment_df = generate_segment_list_for_sheet(extraction['data'])
                segment_df.to_excel(writer, sheet_name=sheet_name[:31], index=False)

        _log(f"\n成功保存管段清单到：{output_path}")
        _log(f"共保存了{len(all_extractions)}个清单sheet")
        return True
    except Exception as e:
        _log(f"保存管段清单时出错：{e}")
        return False


def save_statistics_to_excel(all_extractions, output_path, diameter_column=None):
    diameter_column = diameter_column or COLUMNS['diameter']
    try:
        prepare_output_file(output_path)
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            for extraction in all_extractions:
                extraction_num = extraction['info']['抽取次数']
                data = extraction['data']

                diameters = pd.to_numeric(data[diameter_column], errors='coerce').dropna()

                stats_data = {
                    '统计项': ['抽取次数', '焊口数量', '直径总和', '平均直径', '最小直径', '最大直径', '直径中位数',
                               '标准差', '目标值', '超出值', '超出率(%)'],
                    '数值': [
                        extraction_num,
                        len(data),
                        round(float(diameters.sum()), 2),
                        round(float(diameters.mean()), 2),
                        float(diameters.min()),
                        float(diameters.max()),
                        round(float(diameters.median()), 2),
                        round(float(diameters.std()), 2),
                        extraction['info']['目标值'],
                        extraction['info']['超出值'],
                        extraction['info']['超出率(%)']
                    ]
                }
                pd.DataFrame(stats_data).to_excel(writer, sheet_name=f"第{extraction_num}次统计"[:31], index=False)

                diameter_stats = diameters.value_counts().sort_index()
                if len(diameters) > 0:
                    ratio_values = np.round(diameter_stats.values / len(diameters) * 100, 2)
                else:
                    ratio_values = np.array([], dtype=float)
                pd.DataFrame({
                    '直径值': diameter_stats.index,
                    '出现次数': diameter_stats.values,
                    '占比(%)': ratio_values
                }).to_excel(writer, sheet_name=f"第{extraction_num}次分布"[:31], index=False)

            summary_data = []
            for extraction in all_extractions:
                summary_data.append({
                    '抽取次数': extraction['info']['抽取次数'],
                    '焊口数量': extraction['info']['焊口数量'],
                    '直径总和': extraction['info']['直径总和'],
                    '目标值': extraction['info']['目标值'],
                    '超出值': extraction['info']['超出值'],
                    '超出率(%)': extraction['info']['超出率(%)']
                })
            pd.DataFrame(summary_data).to_excel(writer, sheet_name='抽取汇总信息', index=False)

            total_welds = int(sum(ext['info']['焊口数量'] for ext in all_extractions))
            total_diameter = float(sum(ext['info']['直径总和'] for ext in all_extractions))

            all_diameter_series = []
            for ext in all_extractions:
                if diameter_column in ext['data'].columns:
                    diameters_clean = pd.to_numeric(ext['data'][diameter_column], errors='coerce').dropna()
                    all_diameter_series.append(diameters_clean)

            all_diameters = pd.concat(all_diameter_series, ignore_index=True) if all_diameter_series else pd.Series(dtype=float)

            overall_stats = {
                '统计项': ['总抽取次数', '总焊口数量', '总直径总和', '平均每次焊口数', '平均每次直径总和',
                           '总体平均直径', '总体最小直径', '总体最大直径', '总体直径中位数', '总体标准差'],
                '数值': [
                    len(all_extractions),
                    total_welds,
                    round(total_diameter, 2),
                    round(total_welds / len(all_extractions), 2) if all_extractions else 0,
                    round(total_diameter / len(all_extractions), 2) if all_extractions else 0,
                    round(float(all_diameters.mean()), 2) if not all_diameters.empty else 0,
                    float(all_diameters.min()) if not all_diameters.empty else 0,
                    float(all_diameters.max()) if not all_diameters.empty else 0,
                    round(float(all_diameters.median()), 2) if not all_diameters.empty else 0,
                    round(float(all_diameters.std()), 2) if not all_diameters.empty else 0
                ]
            }
            pd.DataFrame(overall_stats).to_excel(writer, sheet_name='总体统计', index=False)

            if not all_diameters.empty:
                overall_dist = all_diameters.value_counts().sort_index()
                pd.DataFrame({
                    '直径值': overall_dist.index,
                    '出现次数': overall_dist.values,
                    '占比(%)': np.round(overall_dist.values / len(all_diameters) * 100, 2)
                }).to_excel(writer, sheet_name='总体直径分布', index=False)

        _log(f"成功保存统计信息到：{output_path}")
        return True
    except Exception as e:
        _log(f"保存统计文件时出错：{e}")
        import traceback
        traceback.print_exc()
        return False
