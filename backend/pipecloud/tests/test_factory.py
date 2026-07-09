from types import SimpleNamespace

from django.test import SimpleTestCase

from pipecloud.views.factory import _today_welding_plan


class TodayWeldingPlanTests(SimpleTestCase):
    def test_builds_factory_welding_overview(self):
        rows = [
            SimpleNamespace(
                weld_order_no='HJ-01',
                sheet_name='1',
                segment_no='S-01',
                pipeline='L-01',
                diameter='6',
                completed_flag='已完成',
            ),
            SimpleNamespace(
                weld_order_no='HJ-01',
                sheet_name='1',
                segment_no='S-01',
                pipeline='L-01',
                diameter='8.5',
                completed_flag='未完成',
            ),
            SimpleNamespace(
                weld_order_no='HJ-02',
                sheet_name='2',
                segment_no='S-02',
                pipeline='L-02',
                diameter='4',
                completed_flag='true',
            ),
        ]

        payload = _today_welding_plan(rows, '20260630')

        self.assertTrue(payload['available'])
        self.assertEqual(payload['orderNumbers'], ['HJ-01', 'HJ-02'])
        self.assertEqual(payload['orderCount'], 2)
        self.assertEqual(payload['weldCount'], 3)
        self.assertEqual(payload['completedCount'], 2)
        self.assertEqual(payload['diameterTotal'], 18.5)
        self.assertEqual(payload['segmentCount'], 2)
        self.assertEqual(payload['pipelineCount'], 2)
        self.assertEqual(payload['selectedSheet'], '1')
        self.assertEqual([sheet['name'] for sheet in payload['sheets']], ['1', '2'])
        self.assertEqual(payload['sheets'][0]['total'], 2)
