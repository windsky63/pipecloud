import pandas as pd
from django.test import TestCase

from pipecloud.models import DataSourceFile, MasterScheduleRow, Project
from pipecloud.services.db_storage import (
    PLAN_FILE_MODELS,
    replace_source_sheet_rows,
    sync_dataframes,
    table_payload,
)
from pipecloud.services.prefab_database import (
    CUTTING_PRIMARY_PLAN_FILE_NAME,
    cutting_primary_plan_payload_from_master,
)


class PlanFileSheetTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(project_name='计划工作表测试项目')
        self.source_key = f'cutting:20260716:{CUTTING_PRIMARY_PLAN_FILE_NAME}'
        self.models = PLAN_FILE_MODELS[CUTTING_PRIMARY_PLAN_FILE_NAME]

    def test_replacing_one_sheet_preserves_other_sheets(self):
        sync_dataframes(
            self.project,
            'plan',
            self.source_key,
            CUTTING_PRIMARY_PLAN_FILE_NAME,
            'database://plan/cutting/20260716/下料排产单.xlsx',
            {
                '1': pd.DataFrame([{'库序号': 'W1', '下料排产单号': 'QG-1'}]),
                '2': pd.DataFrame([{'库序号': 'W2', '下料排产单号': 'QG-2'}]),
                '3': pd.DataFrame([{'库序号': 'W3', '下料排产单号': 'QG-3'}]),
            },
            self.models,
        )

        replace_source_sheet_rows(
            self.project,
            'plan',
            self.source_key,
            CUTTING_PRIMARY_PLAN_FILE_NAME,
            'database://plan/cutting/20260716/下料排产单.xlsx',
            '2',
            {
                'columns': ['库序号', '下料排产单号'],
                'rows': [{'库序号': 'W2', '下料排产单号': 'QG-2-UPDATED'}],
            },
            self.models,
        )

        source = DataSourceFile.objects.get(project=self.project, source_key=self.source_key)
        self.assertEqual(source.sheet_names, ['1', '2', '3'])
        self.assertEqual(table_payload(source, self.models, '1')[4][0]['库序号'], 'W1')
        self.assertEqual(table_payload(source, self.models, '2')[4][0]['下料排产单号'], 'QG-2-UPDATED')
        self.assertEqual(table_payload(source, self.models, '3')[4][0]['库序号'], 'W3')

    def test_master_schedule_recovers_all_cutting_sheet_names(self):
        for sheet_name in ('1', '2', '3'):
            MasterScheduleRow.objects.create(
                project=self.project,
                library_seq=f'W{sheet_name}',
                cut_order_no=f'QG-20260716-{sheet_name}',
                cut_date='20260716',
                source_sheet=sheet_name,
                stage_payload={'cutting': {'单位1': '米'}},
            )

        payload = cutting_primary_plan_payload_from_master(
            self.project,
            '20260716',
            '3',
        )

        self.assertEqual(payload['sheets'], ['1', '2', '3'])
        self.assertEqual(payload['sheet'], '3')
        self.assertEqual(payload['total'], 1)
        self.assertEqual(payload['rows'][0]['库序号'], 'W3')
        self.assertEqual(payload['rows'][0]['下料排产单号'], 'QG-20260716-3')
        self.assertEqual(payload['rows'][0]['单位1'], '米')

    def test_cutting_plan_api_exposes_recovered_missing_sheets(self):
        sync_dataframes(
            self.project,
            'plan',
            self.source_key,
            CUTTING_PRIMARY_PLAN_FILE_NAME,
            'database://plan/cutting/20260716/下料排产单.xlsx',
            {'2': pd.DataFrame([{'库序号': 'W2', '下料排产单号': 'QG-20260716-2'}])},
            self.models,
        )
        for sheet_name in ('1', '2', '3'):
            MasterScheduleRow.objects.create(
                project=self.project,
                library_seq=f'W{sheet_name}',
                cut_order_no=f'QG-20260716-{sheet_name}',
                cut_date='20260716',
                source_sheet=sheet_name,
            )

        response = self.client.get('/api/pipecloud/plans/cutting/file/', {
            'project_id': self.project.id,
            'planFolder': '20260716',
            'file': CUTTING_PRIMARY_PLAN_FILE_NAME,
        })

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['sheets'], ['1', '2', '3'])
        self.assertEqual(payload['sheet'], '1')
        self.assertEqual(payload['rows'][0]['库序号'], 'W1')
