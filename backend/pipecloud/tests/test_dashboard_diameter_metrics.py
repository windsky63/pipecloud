from pathlib import Path

from django.test import TestCase

from pipecloud.models import DataSourceFile, InitializationWeldRow, Project, WeldLibraryRow
from pipecloud.views.common import _initialization_stats_payload, _welding_dashboard_payload


class DashboardDiameterMetricTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(project_name='看板寸径统计测试项目')
        self.initialization_source = DataSourceFile.objects.create(
            project=self.project,
            source_type='initialization',
            source_key='welds',
            display_name='焊口初始化数据.xlsx',
            relative_path='database://initialization/welds',
        )
        self.library_source = DataSourceFile.objects.create(
            project=self.project,
            source_type='library',
            source_key='weld-library',
            display_name='预制焊口库.xlsx',
            relative_path='database://library/weld-library',
        )

    def test_initialization_ratios_use_diameter_totals(self):
        for index, diameter in enumerate(('10', '20', '30'), start=1):
            InitializationWeldRow.objects.create(
                project=self.project,
                source_file=self.initialization_source,
                library_seq=f'I{index}',
                unit='U1',
                diameter=diameter,
            )
        WeldLibraryRow.objects.create(
            project=self.project,
            source_file=self.library_source,
            library_seq='P1',
            unit='U1',
            diameter='10',
            welding_mode='手工焊',
        )
        WeldLibraryRow.objects.create(
            project=self.project,
            source_file=self.library_source,
            library_seq='P2',
            unit='U1',
            diameter='20',
            welding_mode='自动焊',
        )

        payload = _initialization_stats_payload(self.project, Path('unused'))

        self.assertEqual(payload['totalDiameter'], 60)
        self.assertEqual(payload['prefabDiameter'], 30)
        self.assertEqual(payload['autoDiameter'], 20)
        self.assertEqual(payload['prefabRate'], 50)
        self.assertEqual(payload['autoRate'], 66.67)
        self.assertEqual(payload['units'][0]['totalDiameter'], 60)

    def test_welding_total_completion_uses_all_prefab_library_diameter(self):
        WeldLibraryRow.objects.create(
            project=self.project,
            source_file=self.library_source,
            library_seq='P1',
            unit='U1',
            diameter='10',
            completed_flag=True,
        )
        WeldLibraryRow.objects.create(
            project=self.project,
            source_file=self.library_source,
            library_seq='P2',
            unit='U1',
            diameter='20',
            completed_flag=False,
        )

        payload = _welding_dashboard_payload(self.project, Path('unused'))

        self.assertEqual(payload['totalRows'], 2)
        self.assertEqual(payload['completedRows'], 1)
        self.assertEqual(payload['totalDiameter'], 30)
        self.assertEqual(payload['completedDiameter'], 10)
        self.assertEqual(payload['completionRate'], 33.33)
