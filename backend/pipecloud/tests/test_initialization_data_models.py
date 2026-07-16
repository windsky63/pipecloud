import pandas as pd
from django.test import TestCase

from pipecloud.models import (
    InitializationMaterialRow,
    InitializationWeldExtraData,
    InitializationWeldRow,
    Project,
    WeldCommonData,
)
from pipecloud.services.db_storage import (
    INITIALIZATION_MODELS,
    normalize_initialization_payload,
    replace_source_rows,
    table_payload,
    table_preview_payload,
)
from pipecloud.services.prefab_database import build_unified_weld_library


class InitializationDataModelTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(project_name='初始化模型测试')

    def _replace(self, payload):
        return replace_source_rows(
            self.project,
            'initialization',
            'welds',
            '初始化数据.xlsx',
            f'database://initialization/{self.project.id}/初始化数据.xlsx',
            payload,
            INITIALIZATION_MODELS,
        )

    def test_legacy_columns_are_split_and_sequence_is_generated_on_import(self):
        columns = [
            '单元号', '管线号', '最终焊口号', '寸径', '接头类型',
            '材料唯一码1', '材料唯一码2', '管段号', '壁厚', '焊接区域', '用户自定义列',
        ]
        row = {
            '单元号': 'U1',
            '管线号': 'L100',
            '最终焊口号': 'W-001',
            '寸径': '10',
            '接头类型': 'BW',
            '材料唯一码1': 'M1',
            '材料唯一码2': 'M2',
            '管段号': 'S1',
            '壁厚': '8',
            '焊接区域': 'S',
            '用户自定义列': '可自由增删',
        }

        source = self._replace({'Sheet1': {'columns': columns, 'rows': [row]}})
        weld = InitializationWeldRow.objects.get(project=self.project)
        original_sequence = weld.library_seq

        self.assertTrue(original_sequence.startswith(f'P{self.project.id}-W'))
        self.assertEqual(weld.weld_no_final, 'W-001')
        self.assertEqual(weld.joint_type, 'BW')
        self.assertEqual(weld.segment_no, 'S1')
        self.assertEqual(weld.wall_thickness, '8')
        self.assertEqual(weld.weld_area, 'S')
        self.assertIsNotNone(weld.common_data_id)
        common = WeldCommonData.objects.get(project=self.project, library_seq=original_sequence)
        self.assertEqual(weld.common_data, common)
        self.assertEqual(common.wall_thickness, '8')
        self.assertEqual(common.diameter, '10')
        self.assertEqual(common.material_unique_1, 'M1')
        extra = InitializationWeldExtraData.objects.get(weld=weld)
        self.assertEqual(extra.library_seq, original_sequence)
        self.assertNotIn('管段号', extra.custom_fields)
        self.assertEqual(extra.custom_fields['用户自定义列'], '可自由增删')

        _, _, _, visible_columns, visible_rows = table_payload(source, INITIALIZATION_MODELS)
        self.assertIn('用户自定义列', visible_columns)
        self.assertEqual(visible_rows[0]['用户自定义列'], '可自由增删')

        self._replace({
            'Sheet1': {
                'columns': columns,
                'rows': [{**row, '材料唯一码1': 'M1-REV', '用户自定义列': '已修改'}],
            },
        })
        weld = InitializationWeldRow.objects.get(project=self.project)
        self.assertNotEqual(weld.library_seq, original_sequence)
        self.assertEqual(weld.extra_data.custom_fields['用户自定义列'], '已修改')

    def test_prefab_library_keeps_incoming_sequence(self):
        prefab = pd.DataFrame([{
            '库序号': 'P1-W00000042',
            '单元号': 'U1',
            '管线号': 'L100',
            '最终焊口号': 'W-001',
            '寸径': '10',
        }])

        result = build_unified_weld_library(prefab, pd.DataFrame())

        self.assertEqual(result.loc[0, '库序号'], 'P1-W00000042')

        with self.assertRaisesRegex(ValueError, '缺少库序号'):
            build_unified_weld_library(prefab.drop(columns=['库序号']), pd.DataFrame())

    def test_initialization_table_preview_limits_rows_but_keeps_total(self):
        columns = ['单元号', '管线号', '最终焊口号', '寸径', '接头类型']
        rows = [
            {
                '单元号': 'U1',
                '管线号': 'L100',
                '最终焊口号': f'W-{index:03d}',
                '寸径': '10',
                '接头类型': 'BW',
            }
            for index in range(25)
        ]
        source = self._replace({'Sheet1': {'columns': columns, 'rows': rows}})

        _, _, total, preview_columns, preview_rows = table_preview_payload(
            source,
            INITIALIZATION_MODELS,
            limit=20,
        )

        self.assertEqual(total, 25)
        self.assertEqual(len(preview_rows), 20)
        self.assertIn('库序号', preview_columns)

    def test_initialization_preview_splits_fixed_and_extra_fields(self):
        payload = {
            'Sheet1': {
                'columns': [
                    '单元号', '管线号', '管段号', '最终焊口号', '寸径', '接头类型',
                    '壁厚', '用户自定义列',
                ],
                'rows': [{
                    '单元号': 'U1',
                    '管线号': 'L100',
                    '管段号': 'S1',
                    '最终焊口号': 'W-001',
                    '寸径': '10',
                    '接头类型': 'BW',
                    '壁厚': '8',
                    '用户自定义列': '扩展值',
                }],
            },
        }

        normalized = normalize_initialization_payload(self.project, payload)

        self.assertIn('管段号', normalized['fixedColumns'])
        self.assertIn('壁厚', normalized['fixedColumns'])
        self.assertEqual(normalized['coreRows'][0]['管段号'], 'S1')
        self.assertEqual(normalized['extraColumns'], ['用户自定义列'])
        self.assertEqual(normalized['extraRows'][0]['用户自定义列'], '扩展值')

    def test_segment_number_is_optional(self):
        payload = {
            'Sheet1': {
                'columns': ['单元号', '管线号', '最终焊口号', '寸径', '接头类型'],
                'rows': [{
                    '单元号': 'U1',
                    '管线号': 'L100',
                    '最终焊口号': 'W-001',
                    '寸径': '10',
                    '接头类型': 'BW',
                }],
            },
        }

        normalized = normalize_initialization_payload(self.project, payload)

        self.assertTrue(normalized['validation']['canImport'])
        self.assertEqual(normalized['coreRows'][0]['管段号'], '')

    def test_idf_material_sheet_is_stored_in_its_own_model(self):
        payload = {
            '材料表': {
                'columns': [
                    '单元号', '管线号', '材料描述', '材料代码', '规格', 'record id',
                    'skey', '序号', '数量', '单位', '不出料标识', '开口焊不计料',
                ],
                'rows': [{
                    '单元号': 'U1',
                    '管线号': 'L100',
                    '材料描述': 'PIPE',
                    '材料代码': 'P-001',
                    '规格': 'DN250',
                    'record id': '12',
                    'skey': 'PIPE',
                    '序号': '1',
                    '数量': '6',
                    '单位': 'm',
                    '不出料标识': '',
                    '开口焊不计料': '',
                }],
            },
            '焊口表': {
                'columns': ['库序号', '单元号', '管线号', '管段号', '焊口号', '寸径', '焊接类型'],
                'rows': [{
                    '库序号': 'IDF-ABC',
                    '单元号': 'U1',
                    '管线号': 'L100',
                    '管段号': 'S1',
                    '焊口号': 'W-001',
                    '寸径': '10',
                    '焊接类型': 'bw',
                }],
            },
        }

        self._replace(payload)

        self.assertEqual(InitializationWeldRow.objects.get().library_seq, 'IDF-ABC')
        material = InitializationMaterialRow.objects.get(project=self.project)
        self.assertEqual(material.material_code, 'P-001')
        self.assertEqual(material.record_id, '12')
        self.assertEqual(material.quantity, '6')
