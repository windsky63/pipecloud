from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
from django.test import SimpleTestCase

from pipecloud.services import prefab_database
from pipecloud.services.plan_rollover import (
    _prepare_plan_sheets,
    _rollover_project,
    pack_rollover_rows,
)


def plan_frame(rows, plan_date):
    dataframe = pd.DataFrame(rows)
    dataframe['_rollover_key'] = [
        f'{row[prefab_database.COLUMNS["weld_no_final"]]}-key'
        for row in rows
    ]
    dataframe['_rollover_from_date'] = plan_date
    return dataframe


class PackRolloverRowsTests(SimpleTestCase):
    def test_aims_for_260_without_crossing_300(self):
        diameter = prefab_database.COLUMNS['diameter']
        frame = plan_frame([
            {diameter: 100, prefab_database.COLUMNS['weld_no_final']: 'W1'},
            {diameter: 100, prefab_database.COLUMNS['weld_no_final']: 'W2'},
            {diameter: 60, prefab_database.COLUMNS['weld_no_final']: 'W3'},
            {diameter: 50, prefab_database.COLUMNS['weld_no_final']: 'W4'},
        ], '20260630')

        packed, overflow = pack_rollover_rows(frame, 260, 300, 3)

        self.assertEqual([sum(sheet[diameter]) for sheet in packed], [260, 50])
        self.assertTrue(overflow.empty)
        self.assertTrue(all(sum(sheet[diameter]) <= 300 for sheet in packed))

    def test_stops_below_target_when_next_weld_would_cross_maximum(self):
        diameter = prefab_database.COLUMNS['diameter']
        frame = plan_frame([
            {diameter: 250, prefab_database.COLUMNS['weld_no_final']: 'W1'},
            {diameter: 60, prefab_database.COLUMNS['weld_no_final']: 'W2'},
        ], '20260630')

        packed, overflow = pack_rollover_rows(frame, 260, 300, 1)

        self.assertEqual(sum(packed[0][diameter]), 250)
        self.assertEqual(list(overflow[diameter]), [60])

    def test_uses_later_fitting_weld_without_crossing_maximum(self):
        diameter = prefab_database.COLUMNS['diameter']
        frame = plan_frame([
            {diameter: 250, prefab_database.COLUMNS['weld_no_final']: 'W1'},
            {diameter: 60, prefab_database.COLUMNS['weld_no_final']: 'W2'},
            {diameter: 50, prefab_database.COLUMNS['weld_no_final']: 'W3'},
        ], '20260630')

        packed, overflow = pack_rollover_rows(frame, 260, 300, 1)

        self.assertEqual(sum(packed[0][diameter]), 300)
        self.assertEqual(list(overflow[diameter]), [60])

    def test_rejects_single_weld_above_rollover_maximum(self):
        diameter = prefab_database.COLUMNS['diameter']
        frame = plan_frame([
            {diameter: 301, prefab_database.COLUMNS['weld_no_final']: 'W1'},
        ], '20260630')

        with self.assertRaisesMessage(ValueError, '超过滚动上限'):
            pack_rollover_rows(frame, 260, 300, 3)

    def test_prepared_sheet_gets_new_plan_date_and_order_number(self):
        diameter = prefab_database.COLUMNS['diameter']
        weld_no = prefab_database.COLUMNS['weld_no_final']
        frame = plan_frame([{diameter: 260, weld_no: 'W1'}], '20260630')

        sheets = _prepare_plan_sheets([frame], 'welding', '20260701')

        self.assertEqual(sheets['1'].iloc[0][prefab_database.future_schedule.WELD_DATE_COL], '20260701')
        self.assertIn('20260701-1', sheets['1'].iloc[0][prefab_database.future_schedule.WELD_ORDER_NO_COL])


class ProjectRolloverTests(SimpleTestCase):
    @patch('pipecloud.services.plan_rollover.PlanRecord.objects')
    @patch('pipecloud.services.plan_rollover._load_plan_dataframe')
    def test_overflow_displaces_existing_future_weld_to_following_plan(
        self,
        load_plan_dataframe,
        plan_records,
    ):
        diameter = prefab_database.COLUMNS['diameter']
        completed = prefab_database.COLUMNS['completed_flag']
        weld_no = prefab_database.COLUMNS['weld_no_final']
        today = plan_frame([
            {diameter: 200, completed: False, weld_no: 'OVERDUE'},
        ], '20260630')
        next_plan = plan_frame([
            {diameter: 150, completed: False, weld_no: 'PLANNED'},
        ], '20260701')
        empty = pd.DataFrame()

        def load_side_effect(_project, _plan_key, plan_date):
            frames = {
                '20260630': today,
                '20260701': next_plan,
                '20260702': empty,
            }
            return None, frames.get(str(plan_date), empty)

        load_plan_dataframe.side_effect = load_side_effect
        values = MagicMock()
        values.distinct.return_value = ['20260701', '20260702']
        plan_records.filter.return_value.order_by.return_value.values_list.return_value = values
        policy = SimpleNamespace(
            target_diameter=260,
            rollover_max_diameter=300,
            orders_per_day=1,
            skip_holidays=False,
            holiday_dates=[],
            canceled_weekend_dates=[],
        )

        result = _rollover_project(
            SimpleNamespace(id=1),
            '20260630',
            policy,
            write=False,
        )

        self.assertEqual(result['affectedPlanDates'], ['20260701', '20260702'])
        self.assertEqual(result['rolledWeldCount'], 1)
        self.assertEqual(
            {(move['weldKey'], move['fromDate'], move['toDate']) for move in result['moves']},
            {
                ('OVERDUE-key', '20260630', '20260701'),
                ('PLANNED-key', '20260701', '20260702'),
            },
        )
