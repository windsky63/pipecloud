import pandas as pd
from django.test import TestCase

from pipecloud.models import Project, WeldPreScheduleRow
from pipecloud.services.db_storage import LIBRARY_MODELS, sync_dataframes
from pipecloud.services.prefab_database import (
    generate_welding_schedule_from_database,
    match_welding_pre_schedule_from_database,
)


def weld_row(seq, arrival=True, anti=True, cutting=True, completed=False):
    return {
        '库序号': seq,
        '单元号': 'U1',
        '管线号': 'P1',
        '管段号': f'S-{seq}',
        '初始焊口号': f'W-{seq}',
        '最终焊口号': f'W-{seq}',
        '寸径': '8',
        '焊接方式': '手工焊',
        '材料到货状态': arrival,
        '材料防腐状态': anti,
        '材料下料状态': cutting,
        '材料焊接状态': completed,
        '优先级': '1',
    }


class WeldingPreScheduleTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(project_name='焊接预排产测试项目')

    def sync_weld_library(self, rows):
        sync_dataframes(
            self.project,
            'library',
            'weld-library',
            '预制焊口库.xlsx',
            'database://library/weld-library/预制焊口库.xlsx',
            {'Sheet1': pd.DataFrame(rows)},
            LIBRARY_MODELS['weld-library'],
        )

    def test_welding_pre_schedule_extracts_ready_unwelded_rows(self):
        self.sync_weld_library([
            weld_row('READY'),
            weld_row('NO-CUT', cutting=False),
            weld_row('DONE', completed=True),
        ])

        result = match_welding_pre_schedule_from_database(self.project)
        rows = list(
            WeldPreScheduleRow.objects
            .filter(project=self.project, source_file__source_key='welding-pre-schedule')
            .order_by('row_index')
        )

        self.assertEqual(result['pre_schedule_count'], 1)
        self.assertEqual([row.library_seq for row in rows], ['READY'])
        self.assertEqual(rows[0].pre_schedule_seq, '1')
        self.assertEqual(rows[0].pre_schedule_status, '可预排产')

        schedule = generate_welding_schedule_from_database(
            self.project,
            weld_date='20260709',
            target_diameter=1,
            orders_per_day=1,
        )
        self.assertEqual(schedule['plan_date'], '20260709')
        self.assertEqual(schedule['weld_count'], 1)

    def test_welding_schedule_requires_welding_pre_schedule_source(self):
        self.sync_weld_library([weld_row('READY')])

        with self.assertRaisesMessage(ValueError, '请先生成焊接预排产'):
            generate_welding_schedule_from_database(self.project, weld_date='20260709')
