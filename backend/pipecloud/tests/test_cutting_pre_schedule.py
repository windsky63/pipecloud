import pandas as pd
from django.test import TestCase

from pipecloud.models import MasterScheduleRow, Project, WeldPreScheduleRow
from pipecloud.services.db_storage import LIBRARY_MODELS, sync_dataframes
from pipecloud.services.prefab_database import (
    CUTTING_PRIMARY_PLAN_FILE_NAME,
    derived_plan_file_payload,
    _cutting_schedule_source_from_master,
    _cutting_primary_output_files,
    _enrich_extractions_with_anti_corrosion_references,
    _sync_plan_output_files,
    _sync_master_schedule_rows,
    match_weld_pre_schedule_from_database,
    strip_welding_plan_columns,
)


def ready_weld(seq):
    return {
        '库序号': seq,
        '单元号': 'U1',
        '管线号': 'P1',
        '管段号': f'S-{seq}',
        '初始焊口号': f'W-{seq}',
        '最终焊口号': f'W-{seq}',
        '材料到货状态': True,
        '材料防腐状态': True,
        '材料下料状态': False,
        '材料焊接状态': False,
    }


class CuttingPreScheduleTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(project_name='下料预排产测试项目')

    def test_uses_all_ready_welds_not_only_welds_in_anti_corrosion_plans(self):
        sync_dataframes(
            self.project,
            'library',
            'weld-library',
            '预制焊口库.xlsx',
            'database://library/weld-library/预制焊口库.xlsx',
            {'Sheet1': pd.DataFrame([ready_weld('PLANNED'), ready_weld('READY')])},
            LIBRARY_MODELS['weld-library'],
        )
        MasterScheduleRow.objects.create(
            project=self.project,
            library_seq='PLANNED',
            anti_corrosion_date='20260715',
        )

        result = match_weld_pre_schedule_from_database(self.project)
        sequences = list(
            WeldPreScheduleRow.objects
            .filter(project=self.project, source_file__source_key='weld-pre-schedule')
            .order_by('row_index')
            .values_list('library_seq', flat=True)
        )

        self.assertEqual(result['pre_schedule_count'], 2)
        self.assertEqual(sequences, ['PLANNED', 'READY'])

    def test_cutting_preview_builds_only_primary_plan_file(self):
        extractions = [{
            'info': {'抽取次数': 1},
            'data': pd.DataFrame([{'库序号': 'READY'}]),
        }]
        output_files = _cutting_primary_output_files('20260715', '20260715', extractions)

        self.assertEqual(len(output_files), 1)
        self.assertEqual(output_files[0]['file_name'], CUTTING_PRIMARY_PLAN_FILE_NAME)
        self.assertEqual(list(output_files[0]['sheets']), ['1'])
        columns = list(output_files[0]['sheets']['1'].columns)
        self.assertIn('下料排产单号', columns)
        self.assertIn('下料日期', columns)
        self.assertNotIn('焊接排产单号', columns)
        self.assertNotIn('焊接日期', columns)
        self.assertNotIn('计划文件夹', columns)
        self.assertNotIn('计划日期', columns)

    def test_welding_plan_hides_internal_source_sheet(self):
        columns, rows = strip_welding_plan_columns(
            self.project,
            ['库序号', '来源工作表', '材料焊接状态'],
            [{'库序号': 'READY', '来源工作表': '1', '材料焊接状态': False}],
        )

        self.assertEqual(columns, ['库序号', '材料焊接状态'])
        self.assertNotIn('来源工作表', rows[0])

    def test_existing_welding_plan_fills_missing_anti_corrosion_references(self):
        MasterScheduleRow.objects.create(
            project=self.project,
            library_seq='READY',
            anti_corrosion_order_no='FFWT-20260714-001',
            anti_corrosion_date='20260714',
        )
        columns, rows = strip_welding_plan_columns(
            self.project,
            ['库序号', '防腐委托单号', '防腐日期'],
            [{'库序号': 'READY', '防腐委托单号': '', '防腐日期': ''}],
        )

        self.assertEqual(columns, ['库序号', '防腐委托单号', '防腐日期'])
        self.assertEqual(rows[0]['防腐委托单号'], 'FFWT-20260714-001')
        self.assertEqual(rows[0]['防腐日期'], '20260714')

    def test_welding_plan_receives_anti_corrosion_references_from_master(self):
        MasterScheduleRow.objects.create(
            project=self.project,
            library_seq='READY',
            anti_corrosion_order_no='FFWT-20260714-001',
            anti_corrosion_date='20260714',
        )
        extractions = [{
            'info': {'抽取次数': 1},
            'data': pd.DataFrame([{'库序号': 'READY'}]),
        }]

        enriched = _enrich_extractions_with_anti_corrosion_references(self.project, extractions)

        row = enriched[0]['data'].iloc[0]
        self.assertEqual(row['防腐委托单号'], 'FFWT-20260714-001')
        self.assertEqual(row['防腐日期'], '20260714')

    def test_cutting_detail_and_summary_are_derived_from_independent_cutting_plan(self):
        extractions = [{
            'info': {'抽取次数': 1},
            'data': pd.DataFrame([{
                '库序号': 'READY',
                '材料代号1': 'P',
                '材料唯一码1': 'PIPE-001',
                '材料代码1': 'MAT-001',
                '数量1': '6.5',
                '材料油漆1': 'PAINT',
                '描述1': 'PIPE',
                '管线号': 'LINE-1',
                '管段号': 'SEG-1',
            }]),
        }]
        _sync_plan_output_files(
            self.project,
            _cutting_primary_output_files('20260715', '20260715', extractions),
        )

        detail = derived_plan_file_payload(
            self.project, 'cutting', '20260715', '切管明细表.xlsx'
        )
        summary = derived_plan_file_payload(
            self.project, 'cutting', '20260715', '切管汇总表.xlsx'
        )

        self.assertEqual(detail['total'], 1)
        self.assertEqual(detail['rows'][0]['材料代码'], 'MAT-001')
        self.assertNotIn('焊接排产单号', detail['columns'])
        self.assertNotIn('焊接日期', detail['columns'])
        self.assertEqual(summary['total'], 1)
        self.assertEqual(float(summary['rows'][0]['设计切割长度']), 6.5)
        self.assertNotIn('焊接排产单号', summary['columns'])
        self.assertNotIn('焊接日期', summary['columns'])

    def test_cutting_source_prefers_master_schedule_and_fills_missing_fields(self):
        MasterScheduleRow.objects.create(
            project=self.project,
            library_seq='READY',
            anti_corrosion_order_no='AC-001',
            anti_corrosion_date='20260714',
            unit='MASTER-U',
        )
        pre_schedule = pd.DataFrame([{
            '库序号': 'READY',
            '单元号': 'PRE-U',
            '材料代码1': 'PIPE-001',
            '材料到货状态': True,
            '材料防腐状态': True,
            '材料下料状态': False,
            '材料焊接状态': False,
        }])

        source = _cutting_schedule_source_from_master(self.project, pre_schedule)

        self.assertEqual(source.iloc[0]['单元号'], 'MASTER-U')
        self.assertEqual(source.iloc[0]['防腐委托单号'], 'AC-001')
        self.assertEqual(source.iloc[0]['材料代码1'], 'PIPE-001')
        self.assertTrue(source.iloc[0]['材料到货状态'])

    def test_cutting_plan_updates_only_cutting_fields_in_master_schedule(self):
        dataframe = pd.DataFrame([{
            '库序号': 'READY',
            '下料排产单号': 'QG-20260715-1',
            '下料日期': '20260715',
            '单元号': 'U1',
        }])

        _sync_master_schedule_rows(self.project, 'cutting', '20260715', dataframe)
        row = MasterScheduleRow.objects.get(project=self.project, library_seq='READY')

        self.assertEqual(row.cut_order_no, 'QG-20260715-1')
        self.assertEqual(row.cut_date, '20260715')
        self.assertEqual(row.weld_order_no, '')
        self.assertEqual(row.weld_date, '')
