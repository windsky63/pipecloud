from django.test import TestCase
import pandas as pd

from pipecloud.models import DataSourceFile, MasterScheduleRow, PlanRecord, Project, WeldCommonData, WeldLibraryRow, WeldStatusRow
from pipecloud.services.prefab_database import _sync_master_schedule_rows, delete_plan_stage
from pipecloud.views.libraries import _database_library_info, library_rows
from django.test import RequestFactory
from unittest.mock import patch
import json


class MasterScheduleLibraryTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(project_name='统一计划库测试项目')

    def create_plan_record(self, plan_key, plan_date):
        return PlanRecord.objects.create(
            project=self.project,
            plan_key=plan_key,
            plan_name={'anti-corrosion': '防腐', 'cutting': '下料', 'welding': '焊接'}[plan_key],
            plan_date=plan_date,
            plan_folder=plan_date,
            relative_path=f'database://plan/{plan_key}/{plan_date}',
            files=[{'name': '计划.xlsx'}],
        )

    def create_source(self, plan_key, plan_date):
        return DataSourceFile.objects.create(
            project=self.project,
            source_type='plan',
            source_key=f'{plan_key}:{plan_date}:计划.xlsx',
            display_name='计划.xlsx',
            relative_path=f'database://plan/{plan_key}/{plan_date}/计划.xlsx',
            sheet_names=['Sheet1'],
            sheet_columns={'Sheet1': []},
        )

    def test_master_schedule_rows_are_batch_created_and_updated(self):
        rows = pd.DataFrame([
            {
                '库序号': 'W1',
                '优先级': '1',
                '材料到货状态': '已到货',
                '防腐委托单号': 'AC-001',
                '防腐面积': '12.5',
                '材料油漆1': 'P1',
            },
            {
                '库序号': 'W2',
                '优先级': '2',
                '防腐委托单号': 'AC-002',
                '防腐面积': '8',
            },
        ])

        self.assertEqual(
            _sync_master_schedule_rows(self.project, 'anti-corrosion', '20260715', rows),
            2,
        )
        self.assertEqual(MasterScheduleRow.objects.filter(project=self.project).count(), 2)
        self.assertEqual(WeldStatusRow.objects.filter(project=self.project).count(), 2)

        changed_rows = pd.DataFrame([
            {
                '库序号': 'W1',
                '优先级': '3',
                '防腐委托单号': 'AC-003',
                '防腐面积': '20',
            },
            {
                '库序号': 'W1',
                '优先级': '4',
                '防腐委托单号': 'AC-004',
                '防腐面积': '21',
            },
        ])

        self.assertEqual(
            _sync_master_schedule_rows(self.project, 'anti-corrosion', '20260716', changed_rows),
            2,
        )
        master = MasterScheduleRow.objects.get(project=self.project, library_seq='W1')
        status = WeldStatusRow.objects.get(project=self.project, library_seq='W1')
        self.assertEqual(master.anti_corrosion_order_no, 'AC-004')
        self.assertEqual(master.anti_corrosion_date, '20260716')
        self.assertEqual(master.stage_payload['anti-corrosion']['防腐面积'], '21')
        self.assertEqual(status.priority, '4')

    def test_deleting_stage_only_clears_that_stage_from_master_plan(self):
        for plan_key, plan_date in [
            ('anti-corrosion', '20260710'),
            ('cutting', '20260711'),
            ('welding', '20260712'),
        ]:
            self.create_plan_record(plan_key, plan_date)
            self.create_source(plan_key, plan_date)
        MasterScheduleRow.objects.create(
            project=self.project,
            library_seq='W1',
            production_start_stage='anti-corrosion',
            production_start_date='20260710',
            priority='1',
            material_arrival_status=True,
            material_anti_corrosion_status=True,
            material_cutting_status=False,
            anti_corrosion_date='20260710',
            cut_date='20260711',
            weld_date='20260712',
            completed_flag=False,
            stage_payload={
                'anti-corrosion': {'防腐面积': '12.5', '材料油漆1': 'P1'},
                'cutting': {'切割长度': '100'},
                'welding': {'焊接班组': 'A'},
            },
        )

        result = delete_plan_stage(self.project, 'cutting', '20260711')

        self.assertEqual(result['librarySeqs'], ['W1'])
        self.assertEqual(
            set(PlanRecord.objects.filter(project=self.project).values_list('plan_key', flat=True)),
            {'anti-corrosion', 'welding'},
        )
        self.assertEqual(DataSourceFile.objects.filter(project=self.project, source_type='plan').count(), 2)
        master = MasterScheduleRow.objects.get(project=self.project, library_seq='W1')
        self.assertEqual(master.anti_corrosion_date, '20260710')
        self.assertEqual(master.cut_date, '')
        self.assertEqual(master.weld_date, '20260712')
        self.assertIn('anti-corrosion', master.stage_payload)
        self.assertNotIn('cutting', master.stage_payload)
        self.assertIn('welding', master.stage_payload)

    def test_deleting_only_cutting_stage_preserves_master_common_fields(self):
        self.create_plan_record('cutting', '20260711')
        self.create_source('cutting', '20260711')
        MasterScheduleRow.objects.create(
            project=self.project,
            library_seq='W1',
            priority='1',
            unit='U1',
            pipeline='LINE-1',
            segment_no='SEG-1',
            cut_order_no='QG-001',
            cut_date='20260711',
            stage_payload={'cutting': {'切割长度': '100'}},
        )

        result = delete_plan_stage(self.project, 'cutting', '20260711')

        master = MasterScheduleRow.objects.get(project=self.project, library_seq='W1')
        self.assertEqual(master.cut_order_no, '')
        self.assertEqual(master.cut_date, '')
        self.assertEqual(master.priority, '1')
        self.assertEqual(master.unit, 'U1')
        self.assertEqual(master.pipeline, 'LINE-1')
        self.assertEqual(master.segment_no, 'SEG-1')
        self.assertEqual(result['deletedMasterRows'], 0)

    def test_master_schedule_library_is_visible_in_library_management(self):
        common_data = WeldCommonData.objects.create(
            project=self.project,
            library_seq='W1',
            material_paint_1='P1',
            material_code_1='MAT-1',
        )
        MasterScheduleRow.objects.create(
            project=self.project,
            common_data=common_data,
            library_seq='W1',
            priority='2',
            material_arrival_status=True,
            material_anti_corrosion_status=True,
            material_cutting_status=False,
            anti_corrosion_date='20260710',
            completed_flag=False,
            stage_payload={
                'anti-corrosion': {
                    '防腐面积': '12.5',
                    '材料油漆1': 'P1',
                    '优先级': '旧阶段优先级',
                    '材料到货状态': '旧阶段状态',
                    '管线号': 'P-OLD',
                },
            },
        )
        library = {
            'name': '排产计划库',
            'plan_key': 'all',
            'file_name': '排产计划库.xlsx',
        }

        info = _database_library_info(self.project, 'master-schedule-library', library)

        self.assertTrue(info['exists'])
        self.assertEqual(info['rowCount'], 1)

        request = RequestFactory().get('/api/libraries/master-schedule-library/')
        with patch(
            'pipecloud.views.libraries._request_project_context',
            return_value=(self.project, None, None),
        ):
            response = library_rows(request, 'master-schedule-library')

        payload = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload['key'], 'master-schedule-library')
        self.assertEqual(payload['rows'][0]['库序号'], 'W1')
        self.assertNotIn('防腐计划文件夹', payload['columns'])
        self.assertNotIn('工序顺序', payload['columns'])
        self.assertNotIn('阶段计划数据', payload['columns'])
        self.assertIn('防腐/防腐面积', payload['columns'])
        self.assertIn('材料油漆1', payload['columns'])
        self.assertIn('材料代码1', payload['columns'])
        self.assertNotIn('防腐/材料油漆1', payload['columns'])
        self.assertIn('优先级', payload['columns'])
        self.assertIn('材料到货状态', payload['columns'])
        self.assertIn('材料防腐状态', payload['columns'])
        self.assertIn('材料下料状态', payload['columns'])
        self.assertIn('材料焊接状态', payload['columns'])
        self.assertEqual(
            payload['statusColumns'],
            ['优先级', '材料到货状态', '材料防腐状态', '材料下料状态', '材料焊接状态'],
        )
        self.assertNotIn('防腐/优先级', payload['columns'])
        self.assertNotIn('防腐/材料到货状态', payload['columns'])
        self.assertNotIn('防腐/管线号', payload['columns'])
        self.assertEqual(payload['stageColumns'], ['防腐/防腐面积'])

    def test_cutting_stage_does_not_duplicate_master_or_linked_common_fields(self):
        _sync_master_schedule_rows(self.project, 'cutting', '20260715', pd.DataFrame([{
            '库序号': 'W1',
            '下料排产单号': 'QG-001',
            '下料日期': '20260715',
            '单元号': 'U1',
            '材料代码1': 'MAT-1',
            '材料油漆1': 'P1',
            '切割批次': 'B1',
            '计划文件夹': '20260715',
            '计划日期': '20260715',
        }]))

        master = MasterScheduleRow.objects.get(project=self.project, library_seq='W1')
        self.assertEqual(master.stage_payload['cutting'], {'切割批次': 'B1'})

        # 旧数据即使仍保留这两个键，读取排产计划库时也不再展示。
        master.stage_payload['cutting'].update({
            '计划文件夹': '20260715',
            '计划日期': '20260715',
        })
        master.save(update_fields=['stage_payload'])

        request = RequestFactory().get('/api/libraries/master-schedule-library/')
        with patch(
            'pipecloud.views.libraries._request_project_context',
            return_value=(self.project, None, None),
        ):
            response = library_rows(request, 'master-schedule-library')
        payload = json.loads(response.content)

        self.assertIn('下料排产单号', payload['columns'])
        self.assertIn('材料代码1', payload['columns'])
        self.assertIn('材料油漆1', payload['columns'])
        self.assertIn('下料/切割批次', payload['columns'])
        self.assertNotIn('下料/计划文件夹', payload['columns'])
        self.assertNotIn('下料/计划日期', payload['columns'])
        self.assertNotIn('下料/下料排产单号', payload['columns'])
        self.assertNotIn('下料/下料日期', payload['columns'])
        self.assertNotIn('下料/材料代码1', payload['columns'])
        self.assertNotIn('下料/材料油漆1', payload['columns'])

    def test_welding_stage_omits_plan_folder_and_date(self):
        self.create_plan_record('welding', '20260716')
        self.create_source('welding', '20260716')

        _sync_master_schedule_rows(self.project, 'welding', '20260716', pd.DataFrame([{
            '库序号': 'W-WELD',
            '焊接排产单号': 'HJ-001',
            '焊接日期': '20260716',
            '焊接班组': '一班',
            '计划文件夹': '20260716',
            '计划日期': '20260716',
        }]))

        master = MasterScheduleRow.objects.get(project=self.project, library_seq='W-WELD')
        self.assertEqual(master.stage_payload['welding'], {'焊接班组': '一班'})

    def test_shared_weld_status_is_read_by_library_sequence(self):
        source = DataSourceFile.objects.create(
            project=self.project,
            source_type='library',
            source_key='weld-library',
            display_name='预制焊口库.xlsx',
            relative_path='database://library/weld-library/预制焊口库.xlsx',
            sheet_names=['Sheet1'],
            sheet_columns={'Sheet1': []},
        )
        WeldLibraryRow.objects.create(
            project=self.project,
            source_file=source,
            sheet_name='Sheet1',
            row_index=1,
            library_seq='W1',
            priority='旧预制优先级',
            material_arrival_status=False,
            material_anti_corrosion_status=False,
            material_cutting_status=False,
            completed_flag=False,
        )
        MasterScheduleRow.objects.create(
            project=self.project,
            library_seq='W1',
            priority='旧排产优先级',
            material_arrival_status=False,
            material_anti_corrosion_status=False,
            material_cutting_status=False,
            completed_flag=False,
        )
        WeldStatusRow.objects.create(
            project=self.project,
            library_seq='W1',
            priority='中心优先级',
            material_arrival_status=True,
            material_anti_corrosion_status=True,
            material_cutting_status=True,
            completed_flag=True,
        )

        request = RequestFactory().get('/api/libraries/master-schedule-library/')
        with patch(
            'pipecloud.views.libraries._request_project_context',
            return_value=(self.project, None, None),
        ):
            master_response = library_rows(request, 'master-schedule-library')

        master_payload = json.loads(master_response.content)
        master_row = master_payload['rows'][0]
        self.assertEqual(master_row['优先级'], '中心优先级')
        self.assertIs(master_row['材料到货状态'], True)
        self.assertIs(master_row['材料防腐状态'], True)
        self.assertIs(master_row['材料下料状态'], True)
        self.assertIs(master_row['材料焊接状态'], True)

        weld_request = RequestFactory().get('/api/libraries/weld-library/')
        with patch(
            'pipecloud.views.libraries._request_project_context',
            return_value=(self.project, None, None),
        ):
            weld_response = library_rows(weld_request, 'weld-library')

        weld_payload = json.loads(weld_response.content)
        weld_row = weld_payload['rows'][0]
        self.assertEqual(set(weld_payload['statusColumns']), set(master_payload['statusColumns']))
        self.assertEqual(weld_row['优先级'], '中心优先级')
        self.assertIs(weld_row['材料到货状态'], True)
        self.assertIs(weld_row['材料防腐状态'], True)
        self.assertIs(weld_row['材料下料状态'], True)
        self.assertIs(weld_row['材料焊接状态'], True)

    def test_empty_master_schedule_library_returns_columns_without_rows(self):
        request = RequestFactory().get('/api/libraries/master-schedule-library/')
        with patch(
            'pipecloud.views.libraries._request_project_context',
            return_value=(self.project, None, None),
        ):
            response = library_rows(request, 'master-schedule-library')

        payload = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload['key'], 'master-schedule-library')
        self.assertIn('库序号', payload['columns'])
        self.assertEqual(payload['primaryKeyColumns'], ['库序号'])
        self.assertEqual(payload['total'], 0)
        self.assertEqual(payload['rows'], [])
