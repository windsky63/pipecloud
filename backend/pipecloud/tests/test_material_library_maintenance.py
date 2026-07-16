from pathlib import Path
import sys
from unittest.mock import Mock, patch

import pandas as pd
from django.test import SimpleTestCase, TestCase
from pipecloud.models import (
    ArrivalMaterialRow,
    ArrivalOrderRow,
    DataSourceFile,
    FittingMaterialRow,
    PipeMaterialRow,
    Project,
    WeldLibraryRow,
    WeldCommonData,
    WeldPreScheduleRow,
    WeldStatusRow,
)
from pipecloud.services import prefab_database
from pipecloud.views.common import _arrival_material_dashboard_payload


PREFAB_ROOT = Path(__file__).resolve().parents[2] / 'prefab_schedule'
if str(PREFAB_ROOT) not in sys.path:
    sys.path.insert(0, str(PREFAB_ROOT))

from arrival.material_library_maintenance import (  # noqa: E402
    ANTI_CORROSION_STATUS_COL,
    ANTI_CORROSION_AREA_COL,
    MATERIAL_CODE_OUTPUT_COL,
    NEED_ANTI_CORROSION_COL,
    SPEC_COL,
    UNIT_AREA_COL,
    add_anti_corrosion_area,
    split_arrival_materials_by_anti_corrosion,
)


class MaterialAntiCorrosionSplitTests(SimpleTestCase):
    def test_pa_materials_only_enter_anti_corrosion_library(self):
        arrival_df = pd.DataFrame({
            '行号': [1, 2, 3, 4, 5],
            NEED_ANTI_CORROSION_COL: ['PA1', ' pa2 ', '', '/', None],
            ANTI_CORROSION_STATUS_COL: ['已完成', '防腐未完成', '已防腐', '', None],
        })

        ordinary_df, anti_corrosion_df = split_arrival_materials_by_anti_corrosion(arrival_df)

        self.assertEqual(ordinary_df['行号'].tolist(), [3, 4, 5])
        self.assertEqual(anti_corrosion_df['行号'].tolist(), [1, 2])
        self.assertEqual(anti_corrosion_df[NEED_ANTI_CORROSION_COL].tolist(), ['PA1', ' pa2 '])

    def test_removes_existing_area_columns_from_ordinary_materials(self):
        arrival_df = pd.DataFrame({
            '行号': [1, 2],
            NEED_ANTI_CORROSION_COL: ['/', 'PA1'],
            ANTI_CORROSION_STATUS_COL: ['不应保留', '已完成'],
            UNIT_AREA_COL: [1, 1],
            ANTI_CORROSION_AREA_COL: [2, 2],
        })

        ordinary_df, anti_corrosion_df = split_arrival_materials_by_anti_corrosion(arrival_df)

        self.assertIn(ANTI_CORROSION_STATUS_COL, ordinary_df.columns)
        self.assertNotIn(UNIT_AREA_COL, ordinary_df.columns)
        self.assertNotIn(ANTI_CORROSION_AREA_COL, ordinary_df.columns)
        self.assertEqual(anti_corrosion_df[ANTI_CORROSION_STATUS_COL].tolist(), ['已完成'])

    def test_missing_anti_corrosion_column_is_treated_as_non_anti_corrosion(self):
        arrival_df = pd.DataFrame({'行号': [1]})

        ordinary_df, anti_corrosion_df = split_arrival_materials_by_anti_corrosion(arrival_df)

        self.assertEqual(ordinary_df['行号'].tolist(), [1])
        self.assertTrue(anti_corrosion_df.empty)

    def test_calculates_pipe_anti_corrosion_area_from_length(self):
        material_df = pd.DataFrame([{
            MATERIAL_CODE_OUTPUT_COL: 'P001',
            SPEC_COL: '100',
            '库存数量（米）': 6,
        }])

        result = add_anti_corrosion_area(material_df, '库存数量（米）')

        self.assertEqual(result[UNIT_AREA_COL].tolist(), [0.314])
        self.assertEqual(result[ANTI_CORROSION_AREA_COL].tolist(), [1.884])

    def test_calculates_fitting_anti_corrosion_area_from_quantity(self):
        material_df = pd.DataFrame([{
            MATERIAL_CODE_OUTPUT_COL: '90EL001',
            SPEC_COL: '100',
            '库存数量': 2,
        }])

        result = add_anti_corrosion_area(material_df, '库存数量')

        self.assertEqual(result[UNIT_AREA_COL].tolist(), [0.07065])
        self.assertEqual(result[ANTI_CORROSION_AREA_COL].tolist(), [0.1413])


class MaterialLibraryDatabaseSyncTests(SimpleTestCase):
    def test_uses_model_columns_for_library_display(self):
        dataframe = pd.DataFrame([{'材料代码': 'M1', '库存数量': 1}])
        source = Mock()

        with patch.object(prefab_database, 'sync_dataframes', return_value=source):
            result = prefab_database._sync_library_dataframe(
                Mock(),
                'fitting-library',
                '管件法兰材料库.xlsx',
                dataframe,
            )

        self.assertIs(result, source)
        self.assertEqual(source.sheet_columns, {
            'Sheet1': list(
                prefab_database.model_field_labels(
                    prefab_database.FittingMaterialRow,
                ).values()
            ),
        })
        source.save.assert_called_once_with(update_fields=['sheet_columns'])

    def test_batch_pipe_release_matches_sequential_release_order(self):
        matcher = prefab_database.pre_matcher
        pipe_df = pd.DataFrame([{
            matcher.MATERIAL_CODE_COL: 'P001',
            matcher.PIPE_UNIQUE_CODE_COL: 'PIPE-1',
            '库存数量（米）': 12,
            matcher.REMAINING_LENGTH_COL: 1.7,
            matcher.CUT_LENGTHS_COL: '[2, 2, 5]',
            matcher.CUT_LOSSES_COL: '[0.1, 0.1, 0.1]',
            matcher.CONSUMED_LENGTHS_COL: '[2.1, 2.1, 5.1]',
        }])
        details = pd.DataFrame([
            {
                matcher.MATCH_TYPE_COL: '管子',
                matcher.MATCHED_RESOURCE_COL: 'PIPE-1',
                matcher.MATERIAL_CODE_COL: 'P001',
                '需求数量': 2,
                '匹配数量': 2,
                matcher.MATCH_REASON_COL: '占用2.1米，余量0.1米',
            },
            {
                matcher.MATCH_TYPE_COL: '管子',
                matcher.MATCHED_RESOURCE_COL: 'PIPE-1',
                matcher.MATERIAL_CODE_COL: 'P001',
                '需求数量': 5,
                '匹配数量': 5,
                matcher.MATCH_REASON_COL: '占用5.1米，余量0.1米',
            },
        ])

        expected_row = matcher._normalize_pipe_library_or_empty(pipe_df).iloc[0].copy()
        expected_released = 0
        for demand, consumed in ((2, 2.1), (5, 5.1)):
            expected_row, restored = prefab_database._remove_pipe_allocation_from_row(
                expected_row,
                demand,
                consumed,
            )
            expected_released += int(restored > 0)

        actual_pipe_df, _, actual_released, _ = prefab_database._restore_locked_materials_from_details(
            pipe_df,
            pd.DataFrame(),
            details,
        )

        actual_row = actual_pipe_df.iloc[0]
        self.assertEqual(actual_released, expected_released)
        for column in (
            matcher.CUT_LENGTHS_COL,
            matcher.CUT_LOSSES_COL,
            matcher.CONSUMED_LENGTHS_COL,
            matcher.REMAINING_LENGTH_COL,
        ):
            self.assertEqual(actual_row[column], expected_row[column])


class ArrivalMaterialDashboardTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(project_name='到货看板测试')
        self.sources = {
            key: DataSourceFile.objects.create(
                project=self.project,
                source_type='library',
                source_key=key,
                display_name=key,
                relative_path=f'database://library/{key}.xlsx',
            )
            for key in (
                'pipe-library',
                'anti-pipe-library',
                'fitting-library',
                'anti-fitting-library',
                'weld-library',
            )
        }

    def test_material_locking_rows_is_empty_before_first_run(self):
        response = self.client.get(
            '/api/pipecloud/material-locking/pre-schedule/',
            {'project_id': self.project.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            'path': '',
            'sheet': '',
            'sheets': [],
            'total': 0,
            'columns': [],
            'rows': [],
        })

    def test_differential_result_sync_keeps_identity_and_skips_common_status_updates(self):
        source = DataSourceFile.objects.create(
            project=self.project,
            source_type='pre-schedule',
            source_key='material-locking',
            display_name='材料匹配锁定结果.xlsx',
            relative_path='database://pre-schedule/material-locking/材料匹配锁定结果.xlsx',
            sheet_names=['预排产匹配结果'],
        )
        common = WeldCommonData.objects.create(
            project=self.project,
            library_seq='W-1',
            material='公共字段原值',
        )
        status = WeldStatusRow.objects.create(
            project=self.project,
            library_seq='W-1',
            material_arrival_status=True,
        )
        row = WeldPreScheduleRow.objects.create(
            project=self.project,
            source_file=source,
            common_data=common,
            sheet_name='预排产匹配结果',
            row_index=1,
            library_seq='W-1',
            material='旧派生值',
        )

        prefab_database.sync_dataframes(
            self.project,
            'pre-schedule',
            'material-locking',
            '材料匹配锁定结果.xlsx',
            'database://pre-schedule/material-locking/材料匹配锁定结果.xlsx',
            {'预排产匹配结果': pd.DataFrame([{
                '库序号': 'W-1',
                '材质': '新派生值',
                '材料到货状态': False,
            }])},
            {'预排产匹配结果': WeldPreScheduleRow},
            differential=True,
            update_common_data=False,
            sync_status=False,
        )

        row.refresh_from_db()
        common.refresh_from_db()
        status.refresh_from_db()
        self.assertEqual(row.pk, WeldPreScheduleRow.objects.get(library_seq='W-1').pk)
        self.assertEqual(row.material, '新派生值')
        self.assertEqual(row.common_data_id, common.pk)
        self.assertEqual(common.material, '公共字段原值')
        self.assertIs(status.material_arrival_status, True)

    def test_actual_quantity_uses_official_libraries_and_caps_rate(self):
        WeldLibraryRow.objects.create(
            project=self.project,
            source_file=self.sources['weld-library'],
            library_seq='W-1',
            material_mark_1='P',
            material_code_1='P001',
            quantity_1='10',
            material_mark_2='E',
            material_code_2='F001',
            quantity_2='5',
        )
        PipeMaterialRow.objects.create(
            project=self.project,
            source_file=self.sources['pipe-library'],
            material_code='P001',
            stock_qty='8',
        )
        PipeMaterialRow.objects.create(
            project=self.project,
            source_file=self.sources['anti-pipe-library'],
            material_code='P001',
            stock_qty='7',
        )
        FittingMaterialRow.objects.create(
            project=self.project,
            source_file=self.sources['fitting-library'],
            material_code='F001',
            stock_qty='3',
        )
        FittingMaterialRow.objects.create(
            project=self.project,
            source_file=self.sources['anti-fitting-library'],
            material_code='F001',
            stock_qty='4',
        )
        payload = _arrival_material_dashboard_payload(self.project)

        self.assertEqual(payload['summaries']['pipe']['actualQty'], 15)
        self.assertEqual(payload['summaries']['pipe']['requiredActualQty'], 10)
        self.assertEqual(payload['summaries']['pipe']['extraQty'], 5)
        self.assertEqual(payload['summaries']['pipe']['differenceQty'], 0)
        self.assertEqual(payload['summaries']['pipe']['arrivalRate'], 100)
        self.assertEqual(payload['summaries']['other']['actualQty'], 7)
        self.assertEqual(payload['summaries']['other']['requiredActualQty'], 5)
        self.assertEqual(payload['summaries']['other']['extraQty'], 2)
        self.assertEqual(payload['summaries']['other']['differenceQty'], 0)
        self.assertEqual(payload['summaries']['other']['arrivalRate'], 100)

    def test_arrival_rate_does_not_use_excess_to_cover_other_shortage(self):
        WeldLibraryRow.objects.create(
            project=self.project,
            source_file=self.sources['weld-library'],
            library_seq='W-1',
            material_mark_1='P',
            material_code_1='P001',
            quantity_1='10',
        )
        WeldLibraryRow.objects.create(
            project=self.project,
            source_file=self.sources['weld-library'],
            library_seq='W-2',
            material_mark_1='P',
            material_code_1='P002',
            quantity_1='10',
        )
        PipeMaterialRow.objects.create(
            project=self.project,
            source_file=self.sources['pipe-library'],
            material_code='P001',
            stock_qty='15',
        )

        payload = _arrival_material_dashboard_payload(self.project)

        self.assertEqual(payload['summaries']['pipe']['expectedQty'], 20)
        self.assertEqual(payload['summaries']['pipe']['actualQty'], 15)
        self.assertEqual(payload['summaries']['pipe']['requiredActualQty'], 10)
        self.assertEqual(payload['summaries']['pipe']['extraQty'], 5)
        self.assertEqual(payload['summaries']['pipe']['differenceQty'], 10)
        self.assertEqual(payload['summaries']['pipe']['arrivalRate'], 50)

    def test_dashboard_groups_arrival_orders_by_date_and_material_type(self):
        source = DataSourceFile.objects.create(
            project=self.project,
            source_type='arrival',
            source_key='arrival:20260714.xlsx',
            display_name='20260714.xlsx',
            relative_path='database://arrival/20260714.xlsx',
        )
        ArrivalOrderRow.objects.create(
            project=self.project,
            source_file=source,
            sheet_name='Sheet1',
            row_index=1,
            arrival_time='2026-07-14 08:30',
        )
        ArrivalMaterialRow.objects.create(
            project=self.project,
            source_file=source,
            sheet_name='Sheet2',
            row_index=1,
            material_code_ncc='P001',
            actual_arrival_qty='12.5',
            actual_arrival_count='2',
            unit='根',
            name='管子',
            material_category='管材',
        )
        ArrivalMaterialRow.objects.create(
            project=self.project,
            source_file=source,
            sheet_name='Sheet2',
            row_index=2,
            material_code_ncc='F001',
            shipment_qty='3',
            actual_arrival_qty='',
            unit='个',
            name='弯头',
            material_category='管件',
        )

        payload = _arrival_material_dashboard_payload(self.project)
        date_stats = {
            (row['date'], row['materialType']): row
            for row in payload['dateStats']
        }

        self.assertEqual(date_stats[('2026-07-14', 'pipe')]['quantity'], 12.5)
        self.assertEqual(date_stats[('2026-07-14', 'pipe')]['rowCount'], 1)
        self.assertEqual(date_stats[('2026-07-14', 'pipe')]['pipeCount'], 2)
        self.assertEqual(date_stats[('2026-07-14', 'other')]['quantity'], 3)
        self.assertEqual(date_stats[('2026-07-14', 'other')]['rowCount'], 1)

    def test_updates_weld_material_arrival_status_with_sequential_stock(self):
        WeldLibraryRow.objects.create(
            project=self.project,
            source_file=self.sources['weld-library'],
            row_index=1,
            library_seq='W-1',
            material_mark_1='P',
            material_code_1='P001',
            quantity_1='10',
            material_mark_2='E',
            material_code_2='F001',
            quantity_2='1',
        )
        WeldLibraryRow.objects.create(
            project=self.project,
            source_file=self.sources['weld-library'],
            row_index=2,
            library_seq='W-2',
            material_mark_1='P',
            material_code_1='P001',
            quantity_1='10',
            material_mark_2='E',
            material_code_2='F001',
            quantity_2='1',
        )
        PipeMaterialRow.objects.create(
            project=self.project,
            source_file=self.sources['pipe-library'],
            material_code='P001',
            stock_qty='15',
        )
        FittingMaterialRow.objects.create(
            project=self.project,
            source_file=self.sources['fitting-library'],
            material_code='F001',
            stock_qty='2',
        )

        result = prefab_database.update_weld_material_arrival_status_from_database(self.project)
        statuses = dict(
            WeldStatusRow.objects
            .filter(project=self.project)
            .values_list('library_seq', 'material_arrival_status')
        )

        self.assertEqual(result['arrived_count'], 1)
        self.assertEqual(result['pending_count'], 1)
        self.assertEqual(statuses, {'W-1': True, 'W-2': False})
        matched = WeldPreScheduleRow.objects.get(
            project=self.project,
            source_file__source_key='material-locking',
            library_seq='W-1',
        )
        self.assertEqual(matched.anti_corrosion_order_no, '/')
        self.assertEqual(matched.anti_corrosion_date, '/')

    def test_anti_corrosion_demand_only_locks_anti_corrosion_library(self):
        WeldLibraryRow.objects.create(
            project=self.project,
            source_file=self.sources['weld-library'],
            library_seq='W-PA',
            material_mark_1='P',
            material_code_1='P001',
            material_paint_1='PA1',
            quantity_1='10',
        )
        ordinary = PipeMaterialRow.objects.create(
            project=self.project,
            source_file=self.sources['pipe-library'],
            pipe_no='ORD-1',
            material_code='P001',
            stock_qty='10',
        )
        anti = PipeMaterialRow.objects.create(
            project=self.project,
            source_file=self.sources['anti-pipe-library'],
            pipe_no='ANTI-1',
            material_code='P001',
            stock_qty='10',
            anti_corrosion_status='防腐未完成',
        )

        result = prefab_database.match_and_lock_materials_from_database(self.project)

        ordinary = PipeMaterialRow.objects.get(
            project=self.project, source_file__source_key='pipe-library', pipe_no='ORD-1'
        )
        anti = PipeMaterialRow.objects.get(
            project=self.project, source_file__source_key='anti-pipe-library', pipe_no='ANTI-1'
        )
        self.assertEqual(result['locked_count'], 1)
        self.assertIn(ordinary.locked_qty, ['', '0'])
        self.assertEqual(anti.locked_qty, '10')
        self.assertEqual(anti.uncoated_locked_qty, '10')
        self.assertIn(anti.coated_locked_qty, ['', '0'])

    def test_rerun_material_locking_releases_reusable_previous_locks(self):
        for index, seq in enumerate(('W-1', 'W-2'), start=1):
            WeldLibraryRow.objects.create(
                project=self.project,
                source_file=self.sources['weld-library'],
                row_index=index,
                library_seq=seq,
                material_mark_1='P',
                material_code_1='P001',
                quantity_1='10',
            )
        PipeMaterialRow.objects.create(
            project=self.project,
            source_file=self.sources['pipe-library'],
            material_code='P001',
            stock_qty='10',
        )

        first = prefab_database.match_and_lock_materials_from_database(self.project)
        second = prefab_database.match_and_lock_materials_from_database(
            self.project,
            selection_mode='manual',
            selected_library_seqs=['W-2'],
        )
        statuses = dict(
            WeldStatusRow.objects
            .filter(project=self.project)
            .values_list('library_seq', 'material_arrival_status')
        )

        self.assertEqual(first['locked_count'], 1)
        self.assertEqual(second['released_previous_lock_count'], 1)
        self.assertEqual(second['locked_count'], 1)
        self.assertEqual(statuses, {'W-1': False, 'W-2': True})

    def test_rerun_material_locking_keeps_locks_that_entered_cutting(self):
        for index, seq in enumerate(('W-1', 'W-2'), start=1):
            WeldLibraryRow.objects.create(
                project=self.project,
                source_file=self.sources['weld-library'],
                row_index=index,
                library_seq=seq,
                material_mark_1='P',
                material_code_1='P001',
                quantity_1='10',
            )
        PipeMaterialRow.objects.create(
            project=self.project,
            source_file=self.sources['pipe-library'],
            material_code='P001',
            stock_qty='10',
        )

        first = prefab_database.match_and_lock_materials_from_database(self.project)
        WeldStatusRow.objects.filter(project=self.project, library_seq='W-1').update(
            material_cutting_status=True,
        )
        second = prefab_database.match_and_lock_materials_from_database(
            self.project,
            selection_mode='manual',
            selected_library_seqs=['W-2'],
        )

        self.assertEqual(first['locked_count'], 1)
        self.assertEqual(second['released_previous_lock_count'], 0)
        self.assertEqual(second['skipped_cutting_started_lock_count'], 1)
        self.assertEqual(second['locked_count'], 0)
