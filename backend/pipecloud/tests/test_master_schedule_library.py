from django.test import TestCase

from pipecloud.models import DataSourceFile, MasterScheduleRow, PlanRecord, Project
from pipecloud.services.prefab_database import delete_plan_stage
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
            material_arrival_status='已到货',
            material_anti_corrosion_status='已防腐',
            material_cutting_status='未下料',
            anti_corrosion_date='20260710',
            cut_date='20260711',
            weld_date='20260712',
            completed_flag='未焊接',
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

    def test_master_schedule_library_is_visible_in_library_management(self):
        MasterScheduleRow.objects.create(
            project=self.project,
            library_seq='W1',
            priority='2',
            material_arrival_status='已到货',
            material_anti_corrosion_status='已防腐',
            material_cutting_status='未下料',
            anti_corrosion_date='20260710',
            completed_flag='未焊接',
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
        self.assertIn('防腐/材料油漆1', payload['columns'])
        self.assertIn('优先级', payload['columns'])
        self.assertIn('材料到货状态', payload['columns'])
        self.assertIn('材料防腐状态', payload['columns'])
        self.assertIn('材料下料状态', payload['columns'])
        self.assertIn('材料焊接状态', payload['columns'])
        self.assertNotIn('防腐/优先级', payload['columns'])
        self.assertNotIn('防腐/材料到货状态', payload['columns'])
        self.assertNotIn('防腐/管线号', payload['columns'])
        self.assertEqual(payload['stageColumns'], ['防腐/防腐面积', '防腐/材料油漆1'])

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
