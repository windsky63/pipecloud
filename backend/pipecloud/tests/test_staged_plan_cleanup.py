from datetime import timedelta

import pandas as pd
from django.test import TestCase

from pipecloud.models import DataSourceFile, Project
from pipecloud.services.prefab_database import (
    ANTI_CORROSION_WELD_ORDER_FILE_NAME,
    STAGED_PLAN_WORKBOOKS,
    cleanup_expired_staged_plan_outputs,
    discard_staged_plan_outputs,
    stage_plan_output_files,
)


class StagedPlanCleanupTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(project_name='暂存计划清理测试项目')

    def stage_plan(self):
        return stage_plan_output_files(self.project, [{
            'plan_key': 'anti-corrosion',
            'plan_name': '防腐',
            'plan_date': '20260717',
            'file_name': ANTI_CORROSION_WELD_ORDER_FILE_NAME,
            'sheets': {'防腐焊口单': pd.DataFrame([{'防腐委托单号': 'FF-1'}])},
        }])

    def test_discard_removes_database_rows_and_in_memory_workbook(self):
        token, files = self.stage_plan()
        source_key = files[0]['sourceKey']

        self.assertTrue(DataSourceFile.objects.filter(source_key=source_key).exists())
        self.assertIn(source_key, STAGED_PLAN_WORKBOOKS)

        self.assertEqual(discard_staged_plan_outputs(self.project, token), 1)
        self.assertFalse(DataSourceFile.objects.filter(source_key=source_key).exists())
        self.assertNotIn(source_key, STAGED_PLAN_WORKBOOKS)

    def test_expired_cleanup_removes_abandoned_stage(self):
        _, files = self.stage_plan()
        source_key = files[0]['sourceKey']
        DataSourceFile.objects.filter(source_key=source_key).update(file_updated_at=1)

        self.assertEqual(
            cleanup_expired_staged_plan_outputs(self.project, ttl=timedelta(hours=2)),
            1,
        )
        self.assertFalse(DataSourceFile.objects.filter(source_key=source_key).exists())
        self.assertNotIn(source_key, STAGED_PLAN_WORKBOOKS)
