from pathlib import Path
import sys
from unittest.mock import Mock, patch

import pandas as pd
from django.test import SimpleTestCase, TestCase
from pipecloud.models import (
    DataSourceFile,
    FittingMaterialRow,
    PipeMaterialRow,
    Project,
    WeldLibraryRow,
)
from pipecloud.services import prefab_database
from pipecloud.views.common import _arrival_material_dashboard_payload


PREFAB_ROOT = Path(__file__).resolve().parents[2] / 'prefab_schedule'
if str(PREFAB_ROOT) not in sys.path:
    sys.path.insert(0, str(PREFAB_ROOT))

from arrival.material_library_maintenance import (  # noqa: E402
    ANTI_CORROSION_STATUS_COL,
    ANTI_CORROSION_UNFINISHED,
    ANTI_CORROSION_AREA_COL,
    MATERIAL_CODE_OUTPUT_COL,
    NEED_ANTI_CORROSION_COL,
    SPEC_COL,
    UNIT_AREA_COL,
    add_anti_corrosion_area,
    split_arrival_materials_by_anti_corrosion,
)


class MaterialAntiCorrosionSplitTests(SimpleTestCase):
    def test_splits_materials_by_pa_prefix(self):
        arrival_df = pd.DataFrame({
            '行号': [1, 2, 3, 4, 5],
            NEED_ANTI_CORROSION_COL: ['PA1', ' pa2 ', '', '/', None],
        })

        ordinary_df, anti_corrosion_df = split_arrival_materials_by_anti_corrosion(arrival_df)

        self.assertEqual(ordinary_df['行号'].tolist(), [3, 4, 5])
        self.assertEqual(anti_corrosion_df['行号'].tolist(), [1, 2])
        self.assertNotIn(ANTI_CORROSION_STATUS_COL, ordinary_df.columns)
        self.assertTrue(
            anti_corrosion_df[ANTI_CORROSION_STATUS_COL]
            .eq(ANTI_CORROSION_UNFINISHED)
            .all()
        )

    def test_removes_existing_anti_corrosion_status_from_ordinary_materials(self):
        arrival_df = pd.DataFrame({
            '行号': [1, 2],
            NEED_ANTI_CORROSION_COL: ['/', 'PA1'],
            ANTI_CORROSION_STATUS_COL: ['不应保留', '原状态'],
            UNIT_AREA_COL: [1, 1],
            ANTI_CORROSION_AREA_COL: [2, 2],
        })

        ordinary_df, anti_corrosion_df = split_arrival_materials_by_anti_corrosion(arrival_df)

        self.assertNotIn(ANTI_CORROSION_STATUS_COL, ordinary_df.columns)
        self.assertNotIn(UNIT_AREA_COL, ordinary_df.columns)
        self.assertNotIn(ANTI_CORROSION_AREA_COL, ordinary_df.columns)
        self.assertEqual(
            anti_corrosion_df[ANTI_CORROSION_STATUS_COL].tolist(),
            [ANTI_CORROSION_UNFINISHED],
        )

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
                'pending-pipe-library',
                'fitting-library',
                'anti-fitting-library',
                'pending-fitting-library',
                'weld-library',
            )
        }

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
        PipeMaterialRow.objects.create(
            project=self.project,
            source_file=self.sources['pending-pipe-library'],
            material_code='P001',
            stock_qty='100',
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
        FittingMaterialRow.objects.create(
            project=self.project,
            source_file=self.sources['pending-fitting-library'],
            material_code='F001',
            stock_qty='100',
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
            WeldLibraryRow.objects
            .filter(project=self.project)
            .values_list('library_seq', 'material_arrival_status')
        )

        self.assertEqual(result['arrived_count'], 1)
        self.assertEqual(result['pending_count'], 1)
        self.assertEqual(statuses, {'W-1': True, 'W-2': False})
