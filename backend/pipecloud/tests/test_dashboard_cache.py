import os
from unittest.mock import Mock, patch

from django.core.cache import cache
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from pipecloud.management.commands.runserver import Command as RunserverCommand
from pipecloud.middleware import OperationLogMiddleware
from pipecloud.services.dashboard_cache import dashboard_payload, invalidate_dashboard_cache


TEST_CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'pipecloud-dashboard-cache-tests',
    },
}


@override_settings(CACHES=TEST_CACHES, DASHBOARD_CACHE_TIMEOUT=60)
class DashboardCacheTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_reuses_payload_until_forced_or_invalidated(self):
        builder = Mock(side_effect=[{'value': 1}, {'value': 2}, {'value': 3}])

        first, first_hit = dashboard_payload(7, 'welding', builder)
        second, second_hit = dashboard_payload(7, 'welding', builder)
        forced, forced_hit = dashboard_payload(7, 'welding', builder, force_refresh=True)
        invalidate_dashboard_cache(7)
        rebuilt, rebuilt_hit = dashboard_payload(7, 'welding', builder)

        self.assertEqual(first, {'value': 1})
        self.assertEqual(second, {'value': 1})
        self.assertEqual(forced, {'value': 2})
        self.assertEqual(rebuilt, {'value': 3})
        self.assertFalse(first_hit)
        self.assertTrue(second_hit)
        self.assertFalse(forced_hit)
        self.assertFalse(rebuilt_hit)
        self.assertEqual(builder.call_count, 3)

    def test_project_invalidation_does_not_remove_other_projects(self):
        dashboard_payload(7, 'arrival', lambda: {'project': 7})
        dashboard_payload(8, 'arrival', lambda: {'project': 8})

        invalidate_dashboard_cache(7)

        project_seven, seven_hit = dashboard_payload(7, 'arrival', lambda: {'project': 'rebuilt'})
        project_eight, eight_hit = dashboard_payload(8, 'arrival', lambda: {'project': 'rebuilt'})
        self.assertEqual(project_seven, {'project': 'rebuilt'})
        self.assertFalse(seven_hit)
        self.assertEqual(project_eight, {'project': 8})
        self.assertTrue(eight_hit)

    @patch('pipecloud.services.dashboard_cache.invalidate_dashboard_cache')
    def test_successful_project_write_invalidates_its_dashboards(self, invalidate):
        request = RequestFactory().post('/api/pipecloud/save/?project_id=7', data={})
        middleware = OperationLogMiddleware(lambda _request: HttpResponse(status=204))

        middleware(request)

        invalidate.assert_called_once_with('7')

    @patch('pipecloud.services.dashboard_cache.invalidate_dashboard_cache')
    def test_failed_project_write_keeps_dashboard_cache(self, invalidate):
        request = RequestFactory().post('/api/pipecloud/save/?project_id=7', data={})
        middleware = OperationLogMiddleware(lambda _request: HttpResponse(status=400))

        middleware(request)

        invalidate.assert_not_called()


@override_settings(SCHEDULER_AUTOSTART_WITH_RUNSERVER=True)
class RunserverSchedulerTests(SimpleTestCase):
    @patch.dict(os.environ, {'RUN_MAIN': 'true'}, clear=False)
    @patch('django.contrib.staticfiles.management.commands.runserver.Command.handle', return_value=None)
    def test_reloader_child_starts_and_stops_one_scheduler(self, parent_handle):
        command = RunserverCommand()
        scheduler_process = Mock()
        with (
            patch.object(command, '_start_scheduler', return_value=scheduler_process) as start_scheduler,
            patch.object(command, '_stop_scheduler') as stop_scheduler,
        ):
            command.handle(use_reloader=True)

        start_scheduler.assert_called_once_with()
        stop_scheduler.assert_called_once_with(scheduler_process)
        parent_handle.assert_called_once()

    @patch.dict(os.environ, {}, clear=True)
    @patch('django.contrib.staticfiles.management.commands.runserver.Command.handle', return_value=None)
    def test_reloader_parent_does_not_start_scheduler(self, parent_handle):
        command = RunserverCommand()
        with (
            patch.object(command, '_start_scheduler') as start_scheduler,
            patch.object(command, '_stop_scheduler') as stop_scheduler,
        ):
            command.handle(use_reloader=True)

        start_scheduler.assert_not_called()
        stop_scheduler.assert_called_once_with(None)
        parent_handle.assert_called_once()
