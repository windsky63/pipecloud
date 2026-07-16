from unittest.mock import patch
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from pipecloud.models import Project, ScheduledTaskRun


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


class DeveloperScheduledTaskCsrfTests(TestCase):
    def test_get_returns_persisted_task_logs(self):
        project = Project.objects.create(project_name='日志项目')
        task_run = ScheduledTaskRun.objects.create(
            project=project,
            task_name='sync_cutting_completion',
            business_date=timezone.localdate(),
            status='succeeded',
            stats={'planName': '下料', 'matchedCount': 3, 'completedCount': 2},
            finished_at=timezone.now(),
        )

        response = self.client.get(reverse('pipecloud-developer-scheduled-tasks'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['logs'][0]['id'], task_run.pk)
        self.assertEqual(response.json()['logs'][0]['projectName'], '日志项目')
        self.assertEqual(response.json()['logs'][0]['status'], 'succeeded')

    @patch('pipecloud.views.developer.execute_all_completion_syncs', return_value=[])
    def test_local_vite_origin_can_run_scheduled_task(self, execute_syncs):
        client = Client(enforce_csrf_checks=True)
        url = reverse('pipecloud-developer-scheduled-tasks')
        client.get(url)
        csrf_token = client.cookies['csrftoken'].value

        response = client.post(
            url,
            data='{"key":"sync-anti-corrosion-completion"}',
            content_type='application/json',
            HTTP_ORIGIN='http://localhost:5173',
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(response.status_code, 200)
        execute_syncs.assert_called_once_with('anti-corrosion', force=False)


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
