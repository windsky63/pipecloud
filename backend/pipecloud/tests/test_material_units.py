import pandas as pd
from django.test import TestCase

from pipecloud.models import Project, WeldCommonData
from pipecloud.services.db_storage import INITIALIZATION_MODELS, sync_dataframes
from pipecloud.services.prefab_database import (
    _fill_material_units,
    strip_welding_plan_columns,
)


class MaterialUnitFlowTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(project_name='材料单位字段测试项目')

    def test_fill_material_units_uses_material_mark_type(self):
        dataframe = pd.DataFrame([
            {'材料代号1': 'P', '材料代号2': 'F'},
            {'材料代号1': 'V', '材料代号2': 'P'},
        ])

        result = _fill_material_units(dataframe)

        self.assertEqual(result['单位1'].tolist(), ['米', '个'])
        self.assertEqual(result['单位2'].tolist(), ['个', '米'])

    def test_welding_plan_keeps_empty_units_as_common_fields(self):
        columns = ['库序号', '单位1', '单位2', '计划文件夹', '计划日期']
        rows = [{'库序号': 'W1', '单位1': '', '单位2': '', '计划文件夹': '20260716', '计划日期': '20260716'}]

        visible_columns, visible_rows = strip_welding_plan_columns(self.project, columns, rows)

        self.assertEqual(visible_columns, ['库序号', '单位1', '单位2'])
        self.assertEqual(visible_rows, [{'库序号': 'W1', '单位1': '', '单位2': ''}])

    def test_welding_plan_keeps_common_units_when_project_uses_them(self):
        WeldCommonData.objects.create(
            project=self.project,
            library_seq='W1',
            material_unit_1='米',
            material_unit_2='个',
        )
        columns = ['库序号', '单位1', '单位2', '计划文件夹', '计划日期']
        rows = [{'库序号': 'W1', '单位1': '米', '单位2': '个', '计划文件夹': '20260716', '计划日期': '20260716'}]

        visible_columns, visible_rows = strip_welding_plan_columns(self.project, columns, rows)

        self.assertEqual(visible_columns, ['库序号', '单位1', '单位2'])
        self.assertEqual(visible_rows[0]['单位1'], '米')
        self.assertNotIn('计划文件夹', visible_rows[0])
        self.assertNotIn('计划日期', visible_rows[0])

    def test_initialization_units_are_synced_to_common_data(self):
        sync_dataframes(
            self.project,
            'initialization',
            'welds',
            '焊口初始化数据.xlsx',
            'database://initialization/welds/焊口初始化数据.xlsx',
            {
                'Sheet1': pd.DataFrame([{
                    '库序号': 'W1',
                    '材料代号1': 'P',
                    '材料代号2': 'F',
                    '单位1': '米',
                    '单位2': '个',
                }]),
            },
            INITIALIZATION_MODELS,
        )

        common = WeldCommonData.objects.get(project=self.project, library_seq='W1')
        self.assertEqual(common.material_unit_1, '米')
        self.assertEqual(common.material_unit_2, '个')
