from importlib import import_module
import json
from unittest.mock import Mock, patch

from django.test import RequestFactory, SimpleTestCase

from pipecloud.models import WeldLibraryRow
from pipecloud.services.db_storage import model_field_labels


library_views = import_module('pipecloud.views.libraries')


class LibraryRowsTests(SimpleTestCase):
    def test_library_list_tolerates_single_library_info_failure(self):
        request = RequestFactory().get('/api/libraries/')
        project = Mock()
        catalog = {
            'weld-library': {'name': '预制焊口库'},
            'pipe-library': {'name': '管子材料库'},
        }

        def info_side_effect(_project, key, library):
            if key == 'pipe-library':
                raise RuntimeError('missing table')
            return {
                'key': key,
                'name': library['name'],
                'path': 'database://library/weld-library/预制焊口库.xlsx',
                'exists': True,
                'size': 0,
                'updatedAt': None,
                'rowCount': 1,
            }

        with (
            patch.object(
                library_views,
                '_request_project_context',
                return_value=(project, None, None),
            ),
            patch.object(library_views, '_library_catalog', return_value=catalog),
            patch.object(library_views, '_database_library_info', side_effect=info_side_effect),
        ):
            response = library_views.libraries(request)

        payload = json.loads(response.content)
        fallback = payload['libraries'][1]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(fallback['key'], 'pipe-library')
        self.assertFalse(fallback['exists'])
        self.assertEqual(fallback['rowCount'], 0)

    def test_weld_library_response_only_contains_model_columns(self):
        request = RequestFactory().get('/api/libraries/weld-library/')
        project = Mock()
        source = Mock(relative_path='database://library/weld-library/预制焊口库.xlsx')
        library = {'name': '预制焊口库'}

        with (
            patch.object(
                library_views,
                '_request_project_context',
                return_value=(project, None, None),
            ),
            patch.object(
                library_views,
                '_library_catalog',
                return_value={'weld-library': library},
            ),
            patch.object(
                library_views,
                'latest_source',
                return_value=source,
            ),
            patch.object(
                library_views,
                'table_payload',
                return_value=(
                    'Sheet1',
                    ['Sheet1'],
                    1,
                    ['库序号', '非模型字段'],
                    [{'库序号': 'W-001', '非模型字段': '不应显示'}],
                ),
            ),
        ):
            response = library_views.library_rows(request, 'weld-library')

        payload = json.loads(response.content)
        expected_columns = list(model_field_labels(WeldLibraryRow).values())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload['columns'], expected_columns)
        self.assertEqual(payload['primaryKeyColumns'], ['库序号'])
        self.assertEqual(payload['readonlyColumns'], ['库序号'])
        self.assertNotIn('非模型字段', payload['rows'][0])
        self.assertEqual(payload['rows'][0]['库序号'], 'W-001')

    def test_preserve_primary_key_values_keeps_existing_sequence(self):
        rows = [
            {'库序号': 'CHANGED', '单元号': 'U1'},
            {'库序号': '', '单元号': 'U2'},
        ]
        current_rows = [
            {'库序号': 'W-001', '单元号': 'OLD1'},
        ]

        preserved = library_views._preserve_primary_key_values(rows, current_rows, ['库序号'])

        self.assertEqual(preserved[0]['库序号'], 'W-001')
        self.assertEqual(preserved[0]['单元号'], 'U1')
        self.assertEqual(preserved[1]['库序号'], '')

    def test_preserve_primary_key_values_keeps_remaining_sequence_after_delete(self):
        rows = [
            {'库序号': 'W-002', '单元号': 'U2'},
        ]
        current_rows = [
            {'库序号': 'W-001', '单元号': 'U1'},
            {'库序号': 'W-002', '单元号': 'OLD2'},
        ]

        preserved = library_views._preserve_primary_key_values(rows, current_rows, ['库序号'])

        self.assertEqual(preserved[0]['库序号'], 'W-002')
        self.assertEqual(preserved[0]['单元号'], 'U2')
