from unittest.mock import patch
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

from django.test import Client, SimpleTestCase
from django.urls import reverse


class DeveloperPlanRolloverTests(SimpleTestCase):
    @patch('pipecloud.views.developer.execute_all_project_rollovers')
    def test_runs_rollover_and_summarizes_results(self, execute_rollovers):
        execute_rollovers.return_value = [
            {'projectId': 1, 'projectName': 'A', 'rolledWeldCount': 2},
            {'projectId': 2, 'projectName': 'B', 'alreadyExecuted': True},
            {'projectId': 3, 'projectName': 'C', 'error': 'boom'},
        ]
        self.client.get(reverse('pipecloud-developer-plan-rollover'))
        csrf_token = self.client.cookies['csrftoken'].value

        response = self.client.post(
            reverse('pipecloud-developer-plan-rollover'),
            data='{}',
            content_type='application/json',
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['summary'], {
            'succeeded': 1,
            'skipped': 1,
            'failed': 1,
        })
        execute_rollovers.assert_called_once_with()

    @patch('pipecloud.views.developer.execute_all_project_rollovers')
    def test_get_only_prepares_csrf_cookie(self, execute_rollovers):
        response = self.client.get(reverse('pipecloud-developer-plan-rollover'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ready'])
        self.assertIn('csrftoken', response.cookies)
        execute_rollovers.assert_not_called()


class DeveloperDatabaseTests(SimpleTestCase):
    def test_clear_database_is_not_blocked_by_csrf(self):
        model = Mock()
        model.__name__ = 'ExampleRow'
        model._meta = SimpleNamespace(db_table='pipecloud_example_row', verbose_name='示例表')
        model.objects.all.return_value.delete.return_value = (3, {})

        with (
            patch('pipecloud.views.developer._pipecloud_models', return_value=[model]),
            patch('pipecloud.views.developer.transaction.atomic', return_value=nullcontext()),
        ):
            response = Client(enforce_csrf_checks=True).post(
                reverse('pipecloud-developer-database-clear'),
                data='{"tables":["pipecloud_example_row"]}',
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['deletedRows'], 3)
        model.objects.all.return_value.delete.assert_called_once_with()
