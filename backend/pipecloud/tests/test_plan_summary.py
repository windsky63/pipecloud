import pandas as pd
from django.test import SimpleTestCase

from pipecloud.services.prefab_database import _schedule_plan_summary


class PlanSummaryTests(SimpleTestCase):
    def setUp(self):
        self.extractions = [
            {
                'info': {
                    '抽取次数': 1,
                    '排产单号': 'HJ-20260630-01',
                    '焊口数量': 2,
                    '直径总和': 18.5,
                },
                'data': pd.DataFrame([{}, {}]),
            },
            {
                'info': {
                    '抽取次数': 2,
                    '排产单号': 'HJ-20260630-02',
                    '焊口数量': 1,
                    '直径总和': 6,
                },
                'data': pd.DataFrame([{}]),
            },
        ]

    def test_welding_summary_uses_welding_order_numbers(self):
        summary = _schedule_plan_summary('welding', '20260630', self.extractions)

        self.assertEqual(summary['orderNumbers'], ['HJ-20260630-01', 'HJ-20260630-02'])
        self.assertEqual(summary['weldCount'], 3)
        self.assertEqual(summary['diameterTotal'], 24.5)

    def test_cutting_summary_uses_cutting_and_related_welding_orders(self):
        summary = _schedule_plan_summary('cutting', '20260629', self.extractions)

        self.assertEqual(summary['orderNumbers'], ['QG-20260629-1', 'QG-20260629-2'])
        self.assertEqual(summary['relatedOrderNumbers'], ['HJ-20260630-01', 'HJ-20260630-02'])
