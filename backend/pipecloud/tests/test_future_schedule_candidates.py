import pandas as pd
from datetime import date
from django.test import TestCase
from unittest.mock import patch

from pipecloud.models import Project
from pipecloud.services.db_storage import LIBRARY_MODELS, sync_dataframes
from pipecloud.services.prefab_database import (
    _future_schedule_candidate_welds,
    generate_future_schedule_from_database,
)


class FutureScheduleCandidateTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(project_name='总排产候选测试项目')
        rows = pd.DataFrame([
            {'库序号': 'READY', '材料到货状态': True, '材料焊接状态': False},
            {'库序号': 'NOT-ARRIVED', '材料到货状态': False, '材料焊接状态': False},
            {'库序号': 'WELDED', '材料到货状态': True, '材料焊接状态': True},
        ])
        sync_dataframes(
            self.project,
            'library',
            'weld-library',
            '预制焊口库.xlsx',
            'database://library/weld-library/预制焊口库.xlsx',
            {'Sheet1': rows},
            LIBRARY_MODELS['weld-library'],
        )

    def test_auto_and_manual_selection_share_arrived_unwelded_filter(self):
        auto_rows = _future_schedule_candidate_welds(self.project)
        manual_rows = _future_schedule_candidate_welds(
            self.project,
            selected_library_seqs=['READY', 'WELDED'],
            selection_mode='manual',
        )

        self.assertEqual(auto_rows['库序号'].tolist(), ['READY'])
        self.assertEqual(manual_rows['库序号'].tolist(), ['READY'])

    def test_coating_first_preview_generates_three_stages_in_order(self):
        candidate_df = pd.DataFrame([{
            '库序号': 'READY',
            '寸径': 10,
            '材料防腐状态': False,
            '材料焊接状态': False,
            '_run_picked': False,
        }])
        anti_files = [
            {'plan_key': 'anti-corrosion', 'file_name': '防腐材料单.xlsx'},
            {'plan_key': 'anti-corrosion', 'file_name': '防腐焊口单.xlsx'},
        ]
        cutting_files = [{'plan_key': 'cutting', 'file_name': '下料排产单.xlsx'}]
        welding_files = [{'plan_key': 'welding', 'file_name': '管段焊口表.xlsx'}]

        def extract_once(work_df, **kwargs):
            self.assertFalse(work_df['材料防腐状态'].any())
            work_df.loc[:, '_run_picked'] = True
            return [{'info': {'抽取次数': 1}, 'data': work_df.copy()}]

        def append_master(rows, *args, **kwargs):
            rows.append({'焊口数量': 1})

        with (
            patch('pipecloud.services.prefab_database._future_schedule_candidate_welds', return_value=candidate_df.copy()),
            patch('pipecloud.services.prefab_database._completed_weld_keys_from_database', return_value=set()),
            patch('pipecloud.services.prefab_database.future_schedule._remove_completed_welds', return_value=(candidate_df.copy(), 0)),
            patch('pipecloud.services.prefab_database.future_schedule._ensure_completed_column', side_effect=lambda frame: frame),
            patch('pipecloud.services.prefab_database.sort_and_clean_data', side_effect=lambda frame, *args: frame),
            patch(
                'pipecloud.services.prefab_database.future_schedule._auto_weld_dates',
                return_value=(value for value in [date(2026, 7, 20)]),
            ),
            patch('pipecloud.services.prefab_database.match_anti_corrosion_pre_schedule_from_database', return_value={'_result_df': candidate_df.copy()}),
            patch('pipecloud.services.prefab_database.generate_anti_corrosion_schedule_from_database', return_value={'_output_files': anti_files.copy()}),
            patch('pipecloud.services.prefab_database.extract_welds_multiple_times', side_effect=extract_once),
            patch('pipecloud.services.prefab_database.future_schedule._append_master_rows', side_effect=append_master),
            patch('pipecloud.services.prefab_database._cutting_primary_output_files', return_value=cutting_files.copy()),
            patch('pipecloud.services.prefab_database._welding_primary_output_files', return_value=welding_files.copy()),
        ):
            result = generate_future_schedule_from_database(
                self.project,
                persist=False,
                dateMode='auto',
            )

        self.assertEqual(
            [item['plan_key'] for item in result['_output_files']],
            ['anti-corrosion', 'anti-corrosion', 'cutting', 'welding'],
        )
        self.assertEqual(
            [item['file_name'] for item in result['_output_files'][:2]],
            ['防腐材料单.xlsx', '防腐焊口单.xlsx'],
        )
        self.assertFalse(candidate_df['材料防腐状态'].all())

    def test_auto_dates_are_consumed_lazily_without_max_days(self):
        candidate_df = pd.DataFrame([{
            '库序号': 'READY',
            '寸径': 10,
            '材料防腐状态': True,
            '材料焊接状态': False,
            '_run_picked': False,
        }])

        class OneDayIterator:
            def __init__(self):
                self.calls = 0

            def __iter__(self):
                return self

            def __next__(self):
                self.calls += 1
                if self.calls > 1:
                    raise AssertionError('总排产不应预先耗尽无限日期迭代器')
                return date(2026, 7, 20)

        date_iter = OneDayIterator()

        def extract_once(work_df, **kwargs):
            work_df.loc[:, '_run_picked'] = True
            return [{'info': {'抽取次数': 1}, 'data': work_df.copy()}]

        with (
            patch('pipecloud.services.prefab_database._future_schedule_candidate_welds', return_value=candidate_df.copy()),
            patch('pipecloud.services.prefab_database._completed_weld_keys_from_database', return_value=set()),
            patch('pipecloud.services.prefab_database.future_schedule._remove_completed_welds', return_value=(candidate_df.copy(), 0)),
            patch('pipecloud.services.prefab_database.future_schedule._ensure_completed_column', side_effect=lambda frame: frame),
            patch('pipecloud.services.prefab_database.sort_and_clean_data', side_effect=lambda frame, *args: frame),
            patch('pipecloud.services.prefab_database.future_schedule._auto_weld_dates', return_value=date_iter),
            patch('pipecloud.services.prefab_database.extract_welds_multiple_times', side_effect=extract_once),
            patch('pipecloud.services.prefab_database.future_schedule._append_master_rows', side_effect=lambda rows, *args: rows.append({'焊口数量': 1})),
            patch('pipecloud.services.prefab_database._cutting_primary_output_files', return_value=[]),
            patch('pipecloud.services.prefab_database._welding_primary_output_files', return_value=[]),
        ):
            result = generate_future_schedule_from_database(self.project, persist=False, dateMode='auto')

        self.assertEqual(result['planned_day_count'], 1)
        self.assertEqual(date_iter.calls, 1)
