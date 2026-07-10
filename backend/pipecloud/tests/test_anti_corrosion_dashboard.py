from pathlib import Path

import pandas as pd
from django.test import TestCase

from pipecloud.models import MasterScheduleRow, Project
from pipecloud.services.prefab_database import derived_plan_file_payload
from pipecloud.views.common import _anti_corrosion_dashboard_payload
from anti_corrosion.main import split_commission_files


class AntiCorrosionDashboardTests(TestCase):
    def test_dashboard_counts_commission_plan_rows(self):
        project = Project.objects.create(project_name='防腐看板测试项目')

        MasterScheduleRow.objects.create(
            project=project,
            library_seq='W1',
            anti_corrosion_order_no='FFWT-20260709-001',
            anti_corrosion_date='20260709',
            unit='U1',
            pipeline='P1',
            segment_no='S1',
            stage_payload={
                'anti-corrosion': {
                    '防腐委托单号': 'FFWT-20260709-001',
                    '委托日期': '20260709',
                    '防腐面积': '123.45',
                    '库序号': 'W1',
                    '单元号': 'U1',
                    '管线号': 'P1',
                    '管段号': 'S1',
                }
            },
        )

        payload = _anti_corrosion_dashboard_payload(project, Path('unused'))

        self.assertEqual(payload['commissionCount'], 1)
        self.assertEqual(payload['segmentCount'], 1)
        self.assertEqual(payload['totalArea'], 123.45)
        self.assertEqual(payload['rows'][0]['totalArea'], 123.45)

    def test_commission_file_name_does_not_include_order_number(self):
        summary_df = pd.DataFrame([
            {'防腐委托单号': 'FFWT-20260709-001', '委托日期': '20260709', '库序号': 'W1'},
            {'防腐委托单号': 'FFWT-20260709-002', '委托日期': '20260709', '库序号': 'W2'},
        ])

        files = split_commission_files(summary_df)

        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]['file_name'], '防腐委托单.xlsx')
        self.assertEqual(len(files[0]['dataframe']), 2)

    def test_commission_plan_file_payload_uses_master_schedule_rows(self):
        project = Project.objects.create(project_name='防腐委托单计划页测试项目')
        MasterScheduleRow.objects.create(
            project=project,
            library_seq='W1',
            anti_corrosion_order_no='FFWT-20260709-001',
            anti_corrosion_date='20260709',
            stage_payload={
                'anti-corrosion': {
                    '防腐面积': '123.45',
                    '材料油漆1': 'P1',
                }
            },
        )

        payload = derived_plan_file_payload(project, 'anti-corrosion', '20260709', '防腐委托单.xlsx')

        self.assertIsNotNone(payload)
        self.assertEqual(payload['total'], 1)
        self.assertEqual(payload['rows'][0]['防腐委托单号'], 'FFWT-20260709-001')
        self.assertEqual(payload['rows'][0]['防腐面积'], '123.45')
