from pathlib import Path
import sys

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
CUTTING_DIR = ROOT_DIR / 'cutting'
for path in (ROOT_DIR, CUTTING_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from cutting import weld_pre_schedule_matcher as material_matcher


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


def _segment_has_anti_corrosion_material(segment_df):
    for _, row in segment_df.iterrows():
        pipe_demands, fitting_demands = _anti_corrosion_demands(row)
        if pipe_demands or fitting_demands:
            return True
    return False


def _pre_schedule_arrived_pipeline_segments(group_df, sequence, pipe_unit_areas, fitting_unit_areas):
    segment_col = material_matcher.COLUMNS['segment_no']
    accepted_rows = []
    all_rows = []
    segment_count = 0
    next_sequence = sequence

    for _, segment_df in group_df.groupby(segment_col, sort=False, dropna=False):
        if not _segment_has_anti_corrosion_material(segment_df):
            continue

        segment_count += 1
        for _, row in segment_df.iterrows():
            row_out = _row_with_anti_corrosion_area(row, pipe_unit_areas, fitting_unit_areas)
            row_out[material_matcher.MATCH_SEQ_COL] = next_sequence
            row_out[material_matcher.STATUS_COL] = material_matcher.MATCHED_STATUS
            row_out[material_matcher.REASON_COL] = ''
            accepted_rows.append(row_out)
            all_rows.append(row_out.copy())
        next_sequence += 1

    return {
        'accepted_rows': accepted_rows,
        'all_rows': all_rows,
        'segment_count': segment_count,
        'accepted_segment_count': segment_count,
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
    candidate_df = material_matcher._prepare_uncompleted_welds(weld_df, only_auto_weld=only_auto_weld)
    candidate_df = material_matcher._filter_truthy_statuses(candidate_df, [
        material_matcher.COLUMNS['material_arrival_status'],
    ])
    anti_corrosion_status_col = material_matcher.COLUMNS['material_anti_corrosion_status']
    if anti_corrosion_status_col in candidate_df.columns:
        candidate_df = candidate_df.loc[
            ~material_matcher._to_bool_series(candidate_df[anti_corrosion_status_col])
        ].copy()

    segment_col = material_matcher.COLUMNS['segment_no']
    if segment_col not in candidate_df.columns:
        raise ValueError(f'预制焊口库缺少列：{segment_col}')
    candidate_df = candidate_df[
        candidate_df[segment_col].fillna('').astype(str).str.strip().ne('')
    ].copy()

    accepted_rows = []
    rejected_rows = []
    segment_count = 0
    accepted_segment_count = 0
    sequence = 1
    group_cols = [material_matcher.COLUMNS['unit'], material_matcher.COLUMNS['pipeline']]

    for _, group_df in candidate_df.groupby(group_cols, sort=False, dropna=False):
        pipeline_result = _pre_schedule_arrived_pipeline_segments(
            group_df,
            sequence,
            pipe_unit_areas,
            fitting_unit_areas,
        )
        if pipeline_result['segment_count'] == 0:
            continue

        segment_count += pipeline_result['segment_count']
        if not material_matcher._meets_pipeline_concentration(
            pipeline_result['all_rows'],
            concentration_dimension,
            concentration_threshold_percent,
        ):
            pipeline_rejected_rows, _ = material_matcher._reject_pipeline_rows(pipeline_result['all_rows'])
            rejected_rows.extend(pipeline_rejected_rows)
            continue

        accepted_rows.extend(pipeline_result['accepted_rows'])
        accepted_segment_count += pipeline_result['accepted_segment_count']
        sequence = pipeline_result['next_sequence']

    result_df = pd.DataFrame(accepted_rows + rejected_rows)
    return {
        'result_df': result_df,
        'candidate_segment_count': segment_count,
        'pre_schedule_segment_count': accepted_segment_count,
        'rejected_segment_count': segment_count - accepted_segment_count,
        'pre_schedule_weld_count': len(accepted_rows),
        'rejected_weld_count': len(rejected_rows),
    }
