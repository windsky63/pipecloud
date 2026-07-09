from pathlib import Path
import sys

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
CUTTING_DIR = ROOT_DIR / 'cutting'
for path in (ROOT_DIR, CUTTING_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from common_utils import prepare_output_file
from anti_corrosion.anti_corrosion_config import ANTI_CORROSION_FILES
from cutting import weld_pre_schedule_matcher as material_matcher


SEGMENT_SHORTAGE_REASON = '管段所需防腐材料未全部到货，整段暂不进入防腐预排产'
ANTI_CORROSION_AREA_COL = '防腐面积'
UNIT_AREA_COL = '单位面积'


def _anti_corrosion_demands(row):
    pipe_demands, fitting_demands = material_matcher._build_weld_material_demands(row)
    return (
        material_matcher._demands_for_pool(pipe_demands, material_matcher.ANTI_CORROSION_POOL),
        material_matcher._demands_for_pool(fitting_demands, material_matcher.ANTI_CORROSION_POOL),
    )


def _unit_area_by_material(dataframe):
    if dataframe is None or dataframe.empty or material_matcher.MATERIAL_CODE_COL not in dataframe.columns:
        return {}
    if UNIT_AREA_COL not in dataframe.columns:
        return {}
    work_df = dataframe.copy()
    work_df['_material_code'] = work_df[material_matcher.MATERIAL_CODE_COL].fillna('').astype(str).str.strip()
    work_df['_unit_area'] = pd.to_numeric(work_df[UNIT_AREA_COL], errors='coerce').fillna(0.0)
    return {
        str(row['_material_code']): float(row['_unit_area'])
        for _, row in work_df.drop_duplicates('_material_code', keep='first').iterrows()
        if str(row['_material_code'])
    }


def _anti_corrosion_area_for_demands(pipe_demands, fitting_demands, pipe_unit_areas, fitting_unit_areas, precision=6):
    total = 0.0
    for demand in pipe_demands:
        material_code = str(demand.get(material_matcher.MATERIAL_CODE_COL, '')).strip()
        qty = pd.to_numeric(demand.get('需求数量'), errors='coerce')
        if pd.notna(qty):
            total += float(qty) * float(pipe_unit_areas.get(material_code, 0.0))
    for demand in fitting_demands:
        material_code = str(demand.get(material_matcher.MATERIAL_CODE_COL, '')).strip()
        qty = pd.to_numeric(demand.get('需求数量'), errors='coerce')
        if pd.notna(qty):
            total += float(qty) * float(fitting_unit_areas.get(material_code, 0.0))
    return round(total, precision)


def _row_with_anti_corrosion_area(row, pipe_unit_areas, fitting_unit_areas):
    pipe_demands, fitting_demands = _anti_corrosion_demands(row)
    row_out = row.to_dict()
    row_out[ANTI_CORROSION_AREA_COL] = _anti_corrosion_area_for_demands(
        pipe_demands,
        fitting_demands,
        pipe_unit_areas,
        fitting_unit_areas,
    )
    return row_out


def _match_pipeline_segments(group_df, pipe_states, fitting_stock, sequence, pipe_unit_areas, fitting_unit_areas):
    segment_col = material_matcher.COLUMNS['segment_no']
    accepted_rows = []
    rejected_rows = []
    all_rows = []
    detail_rows = []
    segment_count = 0
    accepted_segment_count = 0
    working_pipeline_pipe_states = material_matcher._copy_all_pipe_states(pipe_states)
    working_pipeline_fitting_stock = fitting_stock.copy()
    next_sequence = sequence

    for _, segment_df in group_df.groupby(segment_col, sort=False, dropna=False):
        group_has_anti_material = False
        group_ok = True
        group_details = []
        working_pipe_states = material_matcher._copy_all_pipe_states(working_pipeline_pipe_states)
        working_fitting_stock = working_pipeline_fitting_stock.copy()

        for _, row in segment_df.iterrows():
            pipe_demands, fitting_demands = _anti_corrosion_demands(row)
            if not pipe_demands and not fitting_demands:
                continue
            group_has_anti_material = True

            pipe_ok, next_pipe_states, pipe_details = material_matcher._try_allocate_pipe_demands(
                row,
                next_sequence,
                pipe_demands,
                working_pipe_states,
            )
            group_details.extend(pipe_details)
            if pipe_ok:
                working_pipe_states.update(next_pipe_states)

            fitting_ok = False
            next_fitting_stock = {}
            fitting_details = []
            if pipe_ok:
                fitting_ok, next_fitting_stock, fitting_details = material_matcher._try_allocate_fitting_demands(
                    row,
                    next_sequence,
                    fitting_demands,
                    working_fitting_stock,
                )
            group_details.extend(fitting_details)
            if fitting_ok:
                working_fitting_stock.update(next_fitting_stock)
            if not pipe_ok or not fitting_ok:
                group_ok = False

        if not group_has_anti_material:
            continue

        segment_count += 1
        detail_rows.extend(group_details)
        shortage_reasons = [
            detail.get(material_matcher.MATCH_REASON_COL, '')
            for detail in group_details
            if detail.get(material_matcher.MATCH_RESULT_COL) == material_matcher.SHORTAGE_STATUS
        ]
        for _, row in segment_df.iterrows():
            row_out = _row_with_anti_corrosion_area(row, pipe_unit_areas, fitting_unit_areas)
            if group_ok:
                row_out[material_matcher.MATCH_SEQ_COL] = next_sequence
                row_out[material_matcher.STATUS_COL] = material_matcher.MATCHED_STATUS
                row_out[material_matcher.REASON_COL] = ''
                accepted_rows.append(row_out)
                all_rows.append(row_out.copy())
            else:
                row_out[material_matcher.MATCH_SEQ_COL] = ''
                row_out[material_matcher.STATUS_COL] = material_matcher.SHORTAGE_STATUS
                row_out[material_matcher.REASON_COL] = material_matcher._format_joined(
                    shortage_reasons + [SEGMENT_SHORTAGE_REASON]
                )
                rejected_rows.append(row_out)
                all_rows.append(row_out.copy())

        if group_ok:
            working_pipeline_pipe_states = working_pipe_states
            working_pipeline_fitting_stock = working_fitting_stock
            accepted_segment_count += 1
            next_sequence += 1

    return {
        'accepted_rows': accepted_rows,
        'rejected_rows': rejected_rows,
        'all_rows': all_rows,
        'detail_rows': detail_rows,
        'segment_count': segment_count,
        'accepted_segment_count': accepted_segment_count,
        'pipe_states': working_pipeline_pipe_states,
        'fitting_stock': working_pipeline_fitting_stock,
        'next_sequence': next_sequence,
    }


def match_anti_corrosion_pre_schedule_dataframes(
    weld_df,
    pipe_df,
    fitting_df,
    only_auto_weld=False,
    concentration_dimension=None,
    concentration_threshold_percent=None,
):
    concentration_dimension, concentration_threshold_percent = material_matcher.normalize_pipeline_concentration_options(
        concentration_dimension,
        concentration_threshold_percent,
    )
    pipe_df = material_matcher._normalize_pipe_library_or_empty(pipe_df)
    fitting_df = material_matcher._normalize_fitting_library_or_empty(fitting_df)
    pipe_unit_areas = _unit_area_by_material(pipe_df)
    fitting_unit_areas = _unit_area_by_material(fitting_df)
    pipe_states = material_matcher._build_pipe_states(pipe_df)
    fitting_stock = material_matcher._build_fitting_stock(fitting_df)
    candidate_df = material_matcher._prepare_uncompleted_welds(weld_df, only_auto_weld=only_auto_weld)
    candidate_df = material_matcher._filter_truthy_statuses(candidate_df, [
        material_matcher.COLUMNS['material_arrival_status'],
    ])

    segment_col = material_matcher.COLUMNS['segment_no']
    if segment_col not in candidate_df.columns:
        raise ValueError(f'预制焊口库缺少列：{segment_col}')
    candidate_df = candidate_df[
        candidate_df[segment_col].fillna('').astype(str).str.strip().ne('')
    ].copy()

    accepted_rows = []
    rejected_rows = []
    detail_rows = []
    segment_count = 0
    accepted_segment_count = 0
    sequence = 1
    group_cols = [material_matcher.COLUMNS['unit'], material_matcher.COLUMNS['pipeline']]

    for _, group_df in candidate_df.groupby(group_cols, sort=False, dropna=False):
        pipeline_result = _match_pipeline_segments(
            group_df,
            pipe_states,
            fitting_stock,
            sequence,
            pipe_unit_areas,
            fitting_unit_areas,
        )
        if pipeline_result['segment_count'] == 0:
            continue

        segment_count += pipeline_result['segment_count']
        detail_rows.extend(pipeline_result['detail_rows'])
        if not material_matcher._meets_pipeline_concentration(
            pipeline_result['all_rows'],
            concentration_dimension,
            concentration_threshold_percent,
        ):
            pipeline_rejected_rows, _ = material_matcher._reject_pipeline_rows(pipeline_result['all_rows'])
            rejected_rows.extend(pipeline_rejected_rows)
            continue

        accepted_rows.extend(pipeline_result['accepted_rows'])
        rejected_rows.extend(pipeline_result['rejected_rows'])
        pipe_states = pipeline_result['pipe_states']
        fitting_stock = pipeline_result['fitting_stock']
        accepted_segment_count += pipeline_result['accepted_segment_count']
        sequence = pipeline_result['next_sequence']

    result_df = pd.DataFrame(accepted_rows + rejected_rows)
    detail_df = pd.DataFrame(detail_rows, columns=material_matcher.PRE_SCHEDULE_DETAIL_COLUMNS)
    return {
        'result_df': result_df,
        'detail_df': detail_df,
        'candidate_segment_count': segment_count,
        'pre_schedule_segment_count': accepted_segment_count,
        'rejected_segment_count': segment_count - accepted_segment_count,
        'pre_schedule_weld_count': len(accepted_rows),
        'rejected_weld_count': len(rejected_rows),
    }


def match_anti_corrosion_pre_schedule(
    weld_library_file=ANTI_CORROSION_FILES['weld_library'],
    pipe_library_file=ANTI_CORROSION_FILES['pipe_library'],
    fitting_library_file=ANTI_CORROSION_FILES['fitting_library'],
    output_file=ANTI_CORROSION_FILES['pre_schedule_output'],
    only_auto_weld=False,
    concentration_dimension=None,
    concentration_threshold_percent=None,
):
    weld_df = material_matcher._read_excel_or_empty(weld_library_file)
    if weld_df.empty:
        raise ValueError(f'预制焊口库为空，无法生成防腐预排产：{weld_library_file}')
    pipe_df = material_matcher._read_excel_or_empty(pipe_library_file)
    fitting_df = material_matcher._read_excel_or_empty(fitting_library_file)
    result = match_anti_corrosion_pre_schedule_dataframes(
        weld_df,
        pipe_df,
        fitting_df,
        only_auto_weld=only_auto_weld,
        concentration_dimension=concentration_dimension,
        concentration_threshold_percent=concentration_threshold_percent,
    )

    prepare_output_file(output_file)
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        result['result_df'].to_excel(writer, sheet_name='预排产匹配结果', index=False)
        result['detail_df'].to_excel(writer, sheet_name='材料匹配明细', index=False)
    result['output_file'] = Path(output_file)
    return result


if __name__ == '__main__':
    result = match_anti_corrosion_pre_schedule()
    print(f"需防腐预制管段数：{result['candidate_segment_count']}")
    print(f"可预排产管段数：{result['pre_schedule_segment_count']}")
    print(f"不可预排产管段数：{result['rejected_segment_count']}")
    print(f"防腐预排产匹配结果：{result['output_file']}")
