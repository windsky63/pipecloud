from pathlib import Path

import pandas as pd
from django.test import TestCase

from pipecloud.models import MasterScheduleRow, PlanRecord, Project
from pipecloud.services import prefab_database
from pipecloud.services.prefab_database import (
    _anti_corrosion_plan_summary,
    derived_plan_file_payload,
    reconcile_anti_corrosion_material_order_plan,
    _sync_plan_record,
)
from pipecloud.views.common import _plan_record_payload
from pipecloud.views.common import _anti_corrosion_dashboard_payload


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
            diameter='10',
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
        MasterScheduleRow.objects.create(
            project=project,
            library_seq='W2',
            anti_corrosion_order_no='FFWT-20260709-001',
            anti_corrosion_date='20260709',
            unit='U1',
            pipeline='P1',
            segment_no='S1',
            diameter='8',
            stage_payload={
                'anti-corrosion': {
                    '防腐委托单号': 'FFWT-20260709-001',
                    '委托日期': '20260709',
                    '防腐面积': '2',
                    '库序号': 'W2',
                    '单元号': 'U1',
                    '管线号': 'P1',
                    '管段号': 'S1',
                }
            },
        )

        payload = _anti_corrosion_dashboard_payload(project, Path('unused'))
        summary = _anti_corrosion_plan_summary(project, '20260709')

        self.assertEqual(payload['commissionCount'], 1)
        self.assertEqual(payload['weldCount'], 2)
        self.assertEqual(payload['segmentCount'], 1)
        self.assertEqual(payload['totalArea'], 125.45)
        self.assertEqual(payload['rows'][0]['weldCount'], 2)
        self.assertEqual(payload['rows'][0]['segmentCount'], 1)
        self.assertEqual(payload['rows'][0]['totalArea'], 125.45)
        self.assertEqual(payload['rows'][0]['diameterTotal'], 18)
        self.assertEqual(summary['commissionArea'], 125.45)
        self.assertEqual(summary['weldCount'], 2)
        self.assertEqual(summary['diameterTotal'], 18)

    def test_weld_order_plan_file_payload_uses_master_schedule_rows(self):
        project = Project.objects.create(project_name='防腐焊口单计划页测试项目')
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

        payload = derived_plan_file_payload(project, 'anti-corrosion', '20260709', '防腐焊口单.xlsx')

        self.assertIsNotNone(payload)
        self.assertEqual(payload['name'], '防腐焊口单.xlsx')
        self.assertEqual(payload['sheet'], '防腐焊口单')
        self.assertEqual(payload['total'], 1)
        self.assertIn('防腐委托单号', payload['columns'])
        self.assertNotIn('计划文件夹', payload['columns'])
        self.assertNotIn('计划日期', payload['columns'])
        self.assertEqual(payload['rows'][0]['防腐委托单号'], 'FFWT-20260709-001')
        self.assertEqual(payload['rows'][0]['防腐面积'], '123.45')

    def test_anti_corrosion_plan_record_uses_material_and_weld_orders_only(self):
        project = Project.objects.create(project_name='防腐计划记录新版文件项目')
        record = _sync_plan_record(
            project,
            plan_key='anti-corrosion',
            plan_name='防腐',
            plan_date='20260709',
            file_names=['防腐焊口单.xlsx', '防腐材料单.xlsx'],
        )

        payload = _plan_record_payload(record)

        self.assertEqual([item['name'] for item in payload['files']], ['防腐材料单.xlsx', '防腐焊口单.xlsx'])

    def test_clearing_material_order_cascades_anti_corrosion_plan_summary(self):
        project = Project.objects.create(project_name='防腐材料单清空测试项目')
        _sync_plan_record(
            project,
            plan_key='anti-corrosion',
            plan_name='防腐',
            plan_date='20260709',
            file_names=['防腐材料单.xlsx', '防腐焊口单.xlsx'],
        )
        MasterScheduleRow.objects.create(
            project=project,
            library_seq='W1',
            anti_corrosion_order_no='FFWT-20260709-001',
            anti_corrosion_date='20260709',
            stage_payload={
                'anti-corrosion': {
                    '防腐委托单号': 'FFWT-20260709-001',
                    '委托日期': '20260709',
                    '防腐面积': '10',
                    '库序号': 'W1',
                }
            },
        )

        result = reconcile_anti_corrosion_material_order_plan(project, '20260709', [])
        payload = _anti_corrosion_dashboard_payload(project, Path('unused'))

        self.assertEqual(result['deletedRecords'], 1)
        self.assertFalse(PlanRecord.objects.filter(project=project, plan_key='anti-corrosion').exists())
        self.assertFalse(MasterScheduleRow.objects.filter(project=project, anti_corrosion_date='20260709').exists())
        self.assertEqual(payload['planCount'], 0)
        self.assertEqual(payload['commissionCount'], 0)
        self.assertEqual(payload['segmentCount'], 0)

    def test_material_order_skips_pipe_already_in_anti_corrosion_library(self):
        pre_df = pd.DataFrame([
            {
                '预排产序号': 1,
                '库序号': 'W1',
                '预排产状态': '可预排产',
                '单元号': 'U1',
                '管线号': 'L1',
                '管段号': 'S1',
                '初始焊口号': 'A',
                '最终焊口号': 'A',
                '材料代号1': 'P',
                '材料代码1': 'P001',
                '材料唯一码1': 'M1',
                '材料油漆1': 'PA1',
                '数量1': 2,
            },
            {
                '预排产序号': 2,
                '库序号': 'W2',
                '预排产状态': '可预排产',
                '单元号': 'U1',
                '管线号': 'L1',
                '管段号': 'S1',
                '初始焊口号': 'B',
                '最终焊口号': 'B',
                '材料代号1': 'P',
                '材料代码1': 'P001',
                '材料唯一码1': 'M2',
                '材料油漆1': 'PA1',
                '数量1': 3,
            },
        ])
        detail_df = pd.DataFrame([
            {
                '预排产序号': 1,
                '库序号': 'W1',
                '材料类型': '管子',
                '材料代码': 'P001',
                '需求数量': 2,
                '匹配数量': 2,
                '匹配库存标识': 'PIPE-001',
                '匹配结果': '可预排产',
            },
            {
                '预排产序号': 2,
                '库序号': 'W2',
                '材料类型': '管子',
                '材料代码': 'P001',
                '需求数量': 3,
                '匹配数量': 3,
                '匹配库存标识': 'PIPE-002',
                '匹配结果': '可预排产',
            },
        ])
        pipe_df = pd.DataFrame([
            {'管子序号': 'PIPE-001', '材料代码': 'P001', '规格': '100', '原始米数': 10, '库存数量（米）': 8},
            {'管子序号': 'PIPE-002', '材料代码': 'P001', '规格': '100', '原始米数': 12, '库存数量（米）': 9},
        ])
        anti_pipe_df = pd.DataFrame([
            {'管子序号': 'PIPE-001', '材料代码': 'P001'},
        ])

        material_df, weld_df, missing_count = prefab_database._build_anti_corrosion_material_and_weld_orders(
            pre_df,
            detail_df,
            pipe_df,
            pd.DataFrame(),
            anti_pipe_df,
            pd.DataFrame(),
            commission_area=100,
            options={'dateMode': 'manual', 'manualWeldDates': '20260709'},
        )

        self.assertEqual(missing_count, 0)
        self.assertNotIn('管子序号', material_df.columns)
        self.assertNotIn('管子唯一编号', material_df.columns)
        self.assertEqual(material_df['匹配库存标识'].tolist(), ['PIPE-002'])
        self.assertEqual(material_df['委托数量'].tolist(), ['12'])
        self.assertEqual(weld_df['库序号'].tolist(), ['W2'])
        self.assertEqual(weld_df['防腐委托单号'].tolist(), ['FFWT-20260709-001'])

    def test_material_order_deduplicates_repeated_material_unique_code(self):
        pre_df = pd.DataFrame([
            {
                '预排产序号': 1,
                '库序号': 'W1',
                '预排产状态': '可预排产',
                '单元号': 'U1',
                '管线号': 'L1',
                '管段号': 'S1',
                '初始焊口号': 'A',
                '最终焊口号': 'A',
                '材料代号1': 'E',
                '材料代码1': 'F001',
                '材料唯一码1': 'FIT-001',
                '材料油漆1': 'PA1',
                '数量1': 1,
                '材料代号2': 'E',
                '材料代码2': 'F001',
                '材料唯一码2': 'FIT-001',
                '材料油漆2': 'PA1',
                '数量2': 1,
            },
        ])
        detail_df = pd.DataFrame([
            {
                '预排产序号': 1,
                '库序号': 'W1',
                '材料类型': '管件法兰',
                '材料代码': 'F001',
                '材料唯一码': 'FIT-001',
                '需求数量': 1,
                '匹配数量': 1,
                '匹配库存标识': 'F001',
                '匹配结果': '可预排产',
            },
            {
                '预排产序号': 1,
                '库序号': 'W1',
                '材料类型': '管件法兰',
                '材料代码': 'F001',
                '材料唯一码': 'FIT-001',
                '需求数量': 1,
                '匹配数量': 1,
                '匹配库存标识': 'F001',
                '匹配结果': '可预排产',
            },
        ])
        fitting_df = pd.DataFrame([
            {'材料代码': 'F001', '规格': '100'},
        ])

        material_df, weld_df, missing_count = prefab_database._build_anti_corrosion_material_and_weld_orders(
            pre_df,
            detail_df,
            pd.DataFrame(),
            fitting_df,
            pd.DataFrame(),
            pd.DataFrame(),
            commission_area=100,
            options={'dateMode': 'manual', 'manualWeldDates': '20260709'},
        )

        self.assertEqual(missing_count, 0)
        self.assertEqual(material_df['材料唯一码'].tolist(), ['FIT-001'])
        self.assertEqual(material_df['委托数量'].tolist(), ['1'])
        self.assertEqual(weld_df['库序号'].tolist(), ['W1'])

    def test_material_order_aggregates_fitting_demand_quantity(self):
        pre_df = pd.DataFrame([
            {
                '预排产序号': 1,
                '库序号': 'W1',
                '预排产状态': '可预排产',
                '单元号': 'U1',
                '管线号': 'L1',
                '管段号': 'S1',
                '初始焊口号': 'A',
                '最终焊口号': 'A',
                '材料代号1': 'E',
                '材料代码1': 'F001',
                '材料唯一码1': 'FIT-001',
                '材料油漆1': 'PA1',
                '数量1': 1,
            },
            {
                '预排产序号': 2,
                '库序号': 'W2',
                '预排产状态': '可预排产',
                '单元号': 'U1',
                '管线号': 'L1',
                '管段号': 'S1',
                '初始焊口号': 'B',
                '最终焊口号': 'B',
                '材料代号1': 'E',
                '材料代码1': 'F001',
                '材料唯一码1': 'FIT-002',
                '材料油漆1': 'PA1',
                '数量1': 2,
            },
        ])
        detail_df = pd.DataFrame([
            {
                '预排产序号': 1,
                '库序号': 'W1',
                '材料类型': '管件法兰',
                '材料代码': 'F001',
                '材料唯一码': 'FIT-001',
                '需求数量': 1,
                '匹配数量': 1,
                '匹配库存标识': 'F001',
                '匹配结果': '可预排产',
            },
            {
                '预排产序号': 2,
                '库序号': 'W2',
                '材料类型': '管件法兰',
                '材料代码': 'F001',
                '材料唯一码': 'FIT-002',
                '需求数量': 2,
                '匹配数量': 2,
                '匹配库存标识': 'F001',
                '匹配结果': '可预排产',
            },
        ])
        fitting_df = pd.DataFrame([
            {'材料代码': 'F001', '规格': '100'},
        ])

        material_df, weld_df, missing_count = prefab_database._build_anti_corrosion_material_and_weld_orders(
            pre_df,
            detail_df,
            pd.DataFrame(),
            fitting_df,
            pd.DataFrame(),
            pd.DataFrame(),
            commission_area=100,
            options={'dateMode': 'manual', 'manualWeldDates': '20260709'},
        )

        self.assertEqual(missing_count, 0)
        self.assertEqual(material_df['材料代码'].tolist(), ['F001'])
        self.assertEqual(material_df['委托数量'].tolist(), ['3'])
        self.assertEqual(material_df['焊口需求数量'].tolist(), ['3'])
        self.assertEqual(material_df['匹配数量'].tolist(), ['3'])
        self.assertEqual(weld_df['库序号'].tolist(), ['W1', 'W2'])

    def test_material_order_normalizes_decimal_quantity_precision(self):
        pre_df = pd.DataFrame([
            {
                '预排产序号': 1,
                '库序号': 'W1',
                '预排产状态': '可预排产',
                '单元号': 'U1',
                '管线号': 'L1',
                '管段号': 'S1',
                '初始焊口号': 'A',
                '最终焊口号': 'A',
                '材料代号1': 'E',
                '材料代码1': 'F001',
                '材料唯一码1': 'FIT-001',
                '材料油漆1': 'PA1',
                '数量1': '9.15909999999',
            },
        ])
        detail_df = pd.DataFrame([
            {
                '预排产序号': 1,
                '库序号': 'W1',
                '材料类型': '管件法兰',
                '材料代码': 'F001',
                '材料唯一码': 'FIT-001',
                '需求数量': '9.15909999999',
                '匹配数量': '9.15909999999',
                '匹配库存标识': 'F001',
                '匹配结果': '可预排产',
            },
        ])
        fitting_df = pd.DataFrame([
            {'材料代码': 'F001', '规格': '100'},
        ])

        material_df, _, _ = prefab_database._build_anti_corrosion_material_and_weld_orders(
            pre_df,
            detail_df,
            pd.DataFrame(),
            fitting_df,
            pd.DataFrame(),
            pd.DataFrame(),
            commission_area=100,
            options={'dateMode': 'manual', 'manualWeldDates': '20260709'},
        )

        self.assertEqual(material_df['委托数量'].tolist(), ['9.1591'])
        self.assertEqual(material_df['焊口需求数量'].tolist(), ['9.1591'])
        self.assertEqual(material_df['匹配数量'].tolist(), ['9.1591'])
