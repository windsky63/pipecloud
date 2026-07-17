from pathlib import Path
import sys

import pandas as pd
from django.test import SimpleTestCase


PREFAB_ROOT = Path(__file__).resolve().parents[2] / 'prefab_schedule'
if str(PREFAB_ROOT) not in sys.path:
    sys.path.insert(0, str(PREFAB_ROOT))

from cutting import weld_pre_schedule_matcher as cutting_matcher  # noqa: E402
from anti_corrosion.pre_schedule_matcher import (  # noqa: E402
    match_anti_corrosion_pre_schedule_dataframes,
)
from anti_corrosion.main import (  # noqa: E402
    build_anti_corrosion_commission_file_sheets,
    build_anti_corrosion_commission_from_pre_schedule,
)


def weld_row(seq, segment, quantity, paint='PA1', material_code='P001'):
    columns = cutting_matcher.COLUMNS
    return {
        columns['library_seq']: seq,
        columns['unit']: 'U1',
        columns['pipeline']: 'L1',
        columns['segment_no']: segment,
        columns['weld_no_start']: f'W{seq}',
        columns['weld_no_final']: f'W{seq}',
        columns['material_no_1']: 'P',
        columns['material_code_1']: material_code,
        columns['material_unique_1']: f'M-{seq}',
        columns['qty_1']: quantity,
        columns['paint_1']: paint,
        columns['material_no_2']: '',
        columns['material_code_2']: '',
        columns['material_unique_2']: '',
        columns['qty_2']: '',
        columns['paint_2']: '',
        columns['completed_flag']: False,
        columns['material_arrival_status']: True,
        columns['material_anti_corrosion_status']: True,
        columns['material_cutting_status']: False,
        columns['weld_method']: '手工焊',
        columns['weld_priority']: 1,
    }


def anti_corrosion_weld_row(seq, segment, quantity, paint='PA1', material_code='P001'):
    row = weld_row(seq, segment, quantity, paint=paint, material_code=material_code)
    row[cutting_matcher.COLUMNS['material_anti_corrosion_status']] = False
    return row


def pipe_library(length, material_code='P001', unit_area=2):
    return pd.DataFrame([{
        '材料代码': material_code,
        '管子序号': 'PIPE-1',
        '库存数量（米）': length,
        '单位面积': unit_area,
    }])


class CuttingPreScheduleInventoryRoutingTests(SimpleTestCase):
    def test_pipe_match_uses_first_equal_candidate_without_mutating_input_states(self):
        group_df = pd.DataFrame([weld_row('W1', 'S1', 2, paint='/', material_code='P001')])
        pipe_df = cutting_matcher._normalize_pipe_library_or_empty(pd.DataFrame([
            {'材料代码': 'P001', '管子序号': 'PIPE-1', '库存数量（米）': 5},
            {'材料代码': 'P001', '管子序号': 'PIPE-2', '库存数量（米）': 5},
        ]))
        pipe_states = cutting_matcher._build_pipe_states(pipe_df)

        result = cutting_matcher._simulate_group_matches(group_df, pipe_states, {}, 1)

        self.assertEqual(
            result['detail_rows'][0][cutting_matcher.MATCHED_RESOURCE_COL],
            'PIPE-1',
        )
        self.assertEqual(pipe_states['P001'][0]['remaining'], 5)
        self.assertEqual(pipe_states['P001'][0]['cut_list'], [])

    def test_prepare_uncompleted_welds_keeps_prefab_library_sequence(self):
        source = pd.DataFrame([
            weld_row('P1-W00000042', 'S1', 2, paint='/', material_code='P001'),
        ])

        prepared = cutting_matcher._prepare_uncompleted_welds(source, only_auto_weld=False)

        self.assertEqual(prepared.iloc[0][cutting_matcher.COLUMNS['library_seq']], 'P1-W00000042')

    def test_cutting_candidates_require_arrival_and_anti_corrosion_status(self):
        columns = cutting_matcher.COLUMNS
        rows = [
            weld_row('READY', 'S1', 2),
            {**weld_row('NO-ARRIVAL', 'S1', 2), columns['material_arrival_status']: False},
            {**weld_row('NO-COATING', 'S1', 2), columns['material_anti_corrosion_status']: False},
        ]

        prepared = cutting_matcher._prepare_cutting_candidate_welds(pd.DataFrame(rows), only_auto_weld=False)

        self.assertEqual(prepared[columns['library_seq']].tolist(), ['READY'])

    def test_cutting_candidates_can_ignore_anti_corrosion_status(self):
        columns = cutting_matcher.COLUMNS
        rows = [
            {**weld_row('NO-COATING', 'S1', 2), columns['material_anti_corrosion_status']: False},
            {**weld_row('NO-ARRIVAL', 'S1', 2), columns['material_arrival_status']: False},
        ]

        prepared = cutting_matcher._prepare_cutting_candidate_welds(
            pd.DataFrame(rows),
            only_auto_weld=False,
            ignore_anti_corrosion_status=True,
        )

        self.assertEqual(prepared[columns['library_seq']].tolist(), ['NO-COATING'])

    def test_routes_pa_material_to_anti_corrosion_inventory(self):
        pipe_demands, _ = cutting_matcher._build_weld_material_demands(
            pd.Series(weld_row(1, 'S1', 2, paint=' pa2 '))
        )
        self.assertEqual(
            pipe_demands[0][cutting_matcher.INVENTORY_POOL_KEY],
            cutting_matcher.ANTI_CORROSION_POOL,
        )

    def test_routes_material_without_pa_prefix_to_ordinary_inventory(self):
        pipe_demands, _ = cutting_matcher._build_weld_material_demands(
            pd.Series(weld_row(1, 'S1', 2, paint='/'))
        )
        self.assertEqual(
            pipe_demands[0][cutting_matcher.INVENTORY_POOL_KEY],
            cutting_matcher.ORDINARY_POOL,
        )

    def test_routes_any_paint_requirement_to_anti_corrosion_inventory(self):
        pipe_demands, _ = cutting_matcher._build_weld_material_demands(
            pd.Series(weld_row(1, 'S1', 2, paint='FBE'))
        )
        self.assertEqual(
            pipe_demands[0][cutting_matcher.INVENTORY_POOL_KEY],
            cutting_matcher.ANTI_CORROSION_POOL,
        )

    def test_routes_empty_paint_requirement_to_ordinary_inventory(self):
        pipe_demands, _ = cutting_matcher._build_weld_material_demands(
            pd.Series(weld_row(1, 'S1', 2, paint=''))
        )
        self.assertEqual(
            pipe_demands[0][cutting_matcher.INVENTORY_POOL_KEY],
            cutting_matcher.ORDINARY_POOL,
        )

    def test_allocates_regular_and_pa_material_from_separate_pools(self):
        group_df = pd.DataFrame([
            weld_row(1, 'S1', 2, paint='/'),
            weld_row(2, 'S1', 2, paint='PA1'),
        ])
        ordinary_df = cutting_matcher._normalize_pipe_library_or_empty(pipe_library(5))
        anti_df = cutting_matcher._normalize_pipe_library_or_empty(pipe_library(5))

        result = cutting_matcher._simulate_group_matches_by_inventory(
            group_df,
            {
                cutting_matcher.ORDINARY_POOL: cutting_matcher._build_pipe_states(ordinary_df),
                cutting_matcher.ANTI_CORROSION_POOL: cutting_matcher._build_pipe_states(anti_df),
            },
            {
                cutting_matcher.ORDINARY_POOL: {},
                cutting_matcher.ANTI_CORROSION_POOL: {},
            },
            1,
        )

        self.assertEqual(len(result['accepted_rows']), 2)
        ordinary_remaining = result['pipe_state_updates_by_pool'][cutting_matcher.ORDINARY_POOL]['P001'][0]['remaining']
        anti_remaining = result['pipe_state_updates_by_pool'][cutting_matcher.ANTI_CORROSION_POOL]['P001'][0]['remaining']
        self.assertLess(ordinary_remaining, 5)
        self.assertEqual(ordinary_remaining, anti_remaining)

    def test_inventory_simulation_stages_only_demanded_codes_without_mutating_inputs(self):
        group_df = pd.DataFrame([weld_row(1, 'S1', 2, paint='/')])
        ordinary_df = cutting_matcher._normalize_pipe_library_or_empty(pipe_library(5))
        original_states = cutting_matcher._build_pipe_states(ordinary_df)
        untouched_state = original_states['P001'][0]['remaining']

        result = cutting_matcher._simulate_group_matches_by_inventory(
            group_df,
            {
                cutting_matcher.ORDINARY_POOL: original_states,
                cutting_matcher.ANTI_CORROSION_POOL: {},
            },
            {
                cutting_matcher.ORDINARY_POOL: {'UNRELATED': 99},
                cutting_matcher.ANTI_CORROSION_POOL: {'ANTI-UNRELATED': 88},
            },
            1,
        )

        self.assertEqual(original_states['P001'][0]['remaining'], untouched_state)
        self.assertEqual(
            set(result['pipe_state_updates_by_pool'][cutting_matcher.ORDINARY_POOL]),
            {'P001'},
        )
        self.assertEqual(result['pipe_state_updates_by_pool'][cutting_matcher.ANTI_CORROSION_POOL], {})
        self.assertEqual(result['fitting_stock_updates_by_pool'][cutting_matcher.ORDINARY_POOL], {})
        self.assertEqual(result['fitting_stock_updates_by_pool'][cutting_matcher.ANTI_CORROSION_POOL], {})

    def test_failed_mixed_weld_discards_successful_side_allocation(self):
        row = weld_row(1, 'S1', 2, paint='/')
        columns = cutting_matcher.COLUMNS
        row.update({
            columns['material_no_2']: 'E',
            columns['material_code_2']: 'F-MISSING',
            columns['material_unique_2']: 'F-1',
            columns['qty_2']: 1,
            columns['paint_2']: 'PA1',
        })
        ordinary_df = cutting_matcher._normalize_pipe_library_or_empty(pipe_library(5))
        original_states = cutting_matcher._build_pipe_states(ordinary_df)

        result = cutting_matcher._simulate_group_matches_by_inventory(
            pd.DataFrame([row]),
            {
                cutting_matcher.ORDINARY_POOL: original_states,
                cutting_matcher.ANTI_CORROSION_POOL: {},
            },
            {
                cutting_matcher.ORDINARY_POOL: {},
                cutting_matcher.ANTI_CORROSION_POOL: {},
            },
            1,
        )

        self.assertEqual(len(result['rejected_rows']), 1)
        self.assertEqual(result['pipe_state_updates_by_pool'][cutting_matcher.ORDINARY_POOL], {})
        self.assertEqual(original_states['P001'][0]['remaining'], 5)

    def test_pipeline_concentration_rejects_whole_pipeline_below_weld_threshold(self):
        group_df = pd.DataFrame([
            weld_row(1, 'S1', 2, paint='PA1'),
            weld_row(2, 'S2', 20, paint='PA1'),
        ])
        anti_df = cutting_matcher._normalize_pipe_library_or_empty(pipe_library(10))
        result = cutting_matcher._simulate_group_matches_by_inventory(
            group_df,
            {
                cutting_matcher.ORDINARY_POOL: {},
                cutting_matcher.ANTI_CORROSION_POOL: cutting_matcher._build_pipe_states(anti_df),
            },
            {
                cutting_matcher.ORDINARY_POOL: {},
                cutting_matcher.ANTI_CORROSION_POOL: {},
            },
            1,
        )

        self.assertFalse(cutting_matcher._meets_pipeline_concentration(result['all_rows'], 'weld', 60))
        rejected_rows, _ = cutting_matcher._reject_pipeline_rows(result['all_rows'])

        self.assertEqual(len(rejected_rows), 2)
        self.assertTrue(all(row['预排产状态'] == cutting_matcher.SHORTAGE_STATUS for row in rejected_rows))
        self.assertTrue(any(cutting_matcher.PIPELINE_CONCENTRATION_REASON in row['不可预排产原因'] for row in rejected_rows))


class AntiCorrosionPreScheduleTests(SimpleTestCase):
    def test_requires_material_arrival_status_and_keeps_library_sequence(self):
        columns = cutting_matcher.COLUMNS
        weld_df = pd.DataFrame([
            anti_corrosion_weld_row('P1-W00000042', 'S-OK', 2),
            {**anti_corrosion_weld_row('NOT-ARRIVED', 'S-NO', 2), columns['material_arrival_status']: False},
        ])

        result = match_anti_corrosion_pre_schedule_dataframes(
            weld_df,
            pipe_library(10),
            pd.DataFrame(),
        )

        self.assertEqual(result['candidate_segment_count'], 1)
        self.assertEqual(result['result_df'].iloc[0][columns['library_seq']], 'P1-W00000042')
        self.assertEqual(result['result_df'].iloc[0]['防腐面积'], 4)

    def test_arrived_whole_segment_does_not_rematch_material_stock(self):
        weld_df = pd.DataFrame([
            anti_corrosion_weld_row(1, 'S-OK-1', 4),
            anti_corrosion_weld_row(2, 'S-OK-1', 7),
            anti_corrosion_weld_row(3, 'S-OK', 10),
        ])

        result = match_anti_corrosion_pre_schedule_dataframes(
            weld_df,
            pipe_library(10),
            pd.DataFrame(),
        )

        self.assertEqual(result['candidate_segment_count'], 2)
        self.assertEqual(result['pre_schedule_segment_count'], 2)
        self.assertEqual(result['rejected_segment_count'], 0)
        self.assertNotIn('detail_df', result)
        status_by_segment = (
            result['result_df']
            .groupby('管段号')['预排产状态']
            .first()
            .to_dict()
        )
        self.assertEqual(status_by_segment['S-OK-1'], cutting_matcher.MATCHED_STATUS)
        self.assertEqual(status_by_segment['S-OK'], cutting_matcher.MATCHED_STATUS)

    def test_ignores_segment_without_anti_corrosion_material(self):
        weld_df = pd.DataFrame([anti_corrosion_weld_row(1, 'S1', 2, paint='/')])

        result = match_anti_corrosion_pre_schedule_dataframes(
            weld_df,
            pipe_library(10),
            pd.DataFrame(),
        )

        self.assertEqual(result['candidate_segment_count'], 0)
        self.assertTrue(result['result_df'].empty)

    def test_only_auto_weld_filter_defaults_off_and_can_be_enabled(self):
        columns = cutting_matcher.COLUMNS
        weld_df = pd.DataFrame([
            anti_corrosion_weld_row(1, 'S1', 2),
            {**anti_corrosion_weld_row(2, 'S2', 2), columns['weld_method']: '自动焊'},
        ])

        default_result = match_anti_corrosion_pre_schedule_dataframes(
            weld_df,
            pipe_library(20),
            pd.DataFrame(),
        )
        auto_result = match_anti_corrosion_pre_schedule_dataframes(
            weld_df,
            pipe_library(20),
            pd.DataFrame(),
            only_auto_weld=True,
        )

        self.assertEqual(default_result['candidate_segment_count'], 2)
        self.assertEqual(auto_result['candidate_segment_count'], 1)
        self.assertEqual(auto_result['result_df'].iloc[0][columns['library_seq']], '2')

    def test_excludes_welds_whose_anti_corrosion_status_is_already_true(self):
        columns = cutting_matcher.COLUMNS
        weld_df = pd.DataFrame([
            anti_corrosion_weld_row('PENDING', 'S-PENDING', 2),
            weld_row('SATISFIED', 'S-SATISFIED', 2),
        ])

        result = match_anti_corrosion_pre_schedule_dataframes(
            weld_df,
            pipe_library(10),
            pd.DataFrame(),
        )

        self.assertEqual(result['candidate_segment_count'], 1)
        self.assertEqual(result['result_df'][columns['library_seq']].tolist(), ['PENDING'])

    def test_builds_daily_commission_from_pre_schedule_area_limit(self):
        source = pd.DataFrame([
            {'预排产序号': 1, '库序号': 'W1', '预排产状态': cutting_matcher.MATCHED_STATUS, '防腐面积': 4},
            {'预排产序号': 2, '库序号': 'W2', '预排产状态': cutting_matcher.MATCHED_STATUS, '防腐面积': 7},
            {'预排产序号': 3, '库序号': 'W3', '预排产状态': cutting_matcher.SHORTAGE_STATUS, '防腐面积': 2},
        ])

        result = build_anti_corrosion_commission_from_pre_schedule(
            source,
            commission_area=10,
            commission_date='20260707',
        )

        self.assertEqual(result['库序号'].tolist(), ['W1'])
        self.assertEqual(result['防腐委托单号'].tolist(), ['FFWT-20260707-001'])
        self.assertNotIn('委托单防腐面积', result.columns)

    def test_daily_commission_includes_first_row_when_area_exceeds_limit(self):
        source = pd.DataFrame([
            {'预排产序号': 1, '库序号': 'W1', '预排产状态': cutting_matcher.MATCHED_STATUS, '防腐面积': 12},
            {'预排产序号': 2, '库序号': 'W2', '预排产状态': cutting_matcher.MATCHED_STATUS, '防腐面积': 1},
        ])

        result = build_anti_corrosion_commission_from_pre_schedule(
            source,
            commission_area=10,
            commission_date='20260707',
        )

        self.assertEqual(result['库序号'].tolist(), ['W1'])

    def test_daily_commission_splits_selected_rows_by_area_limit_and_max_count(self):
        source = pd.DataFrame([
            {'预排产序号': 1, '库序号': 'W1', '预排产状态': cutting_matcher.MATCHED_STATUS, '防腐面积': 4},
            {'预排产序号': 2, '库序号': 'W2', '预排产状态': cutting_matcher.MATCHED_STATUS, '防腐面积': 7},
            {'预排产序号': 3, '库序号': 'W3', '预排产状态': cutting_matcher.MATCHED_STATUS, '防腐面积': 3},
            {'预排产序号': 4, '库序号': 'W4', '预排产状态': cutting_matcher.MATCHED_STATUS, '防腐面积': 6},
        ])

        result = build_anti_corrosion_commission_from_pre_schedule(
            source,
            commission_area=10,
            commission_date='20260707',
            split_by_area=True,
            max_commission_count=2,
        )

        self.assertEqual(result['库序号'].tolist(), ['W1', 'W2', 'W3'])
        self.assertEqual(
            result['防腐委托单号'].tolist(),
            ['FFWT-20260707-001', 'FFWT-20260707-002', 'FFWT-20260707-002'],
        )

    def test_commission_file_sheets_include_only_commission_preview_table(self):
        commission_df = pd.DataFrame([
            {'防腐委托单号': 'FFWT-20260707-001', '委托日期': '20260707', '预排产序号': 1, '库序号': 'W1', '防腐面积': 4},
        ])

        sheets = build_anti_corrosion_commission_file_sheets(commission_df)

        self.assertEqual(list(sheets.keys()), ['防腐委托单'])
        self.assertNotIn('委托单防腐面积', sheets['防腐委托单'].columns)
