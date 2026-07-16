import pandas as pd
from django.test import SimpleTestCase

from pipecloud.views.common import _prefab_segment_count


class PrefabSegmentCountTests(SimpleTestCase):
    def test_counts_segment_by_unit_pipeline_and_segment_number(self):
        dataframe = pd.DataFrame([
            {'单元号': 'U1', '管线号': 'P1', '管段号': 'S1'},
            {'单元号': 'U1', '管线号': 'P1', '管段号': 'S1'},
            {'单元号': 'U1', '管线号': 'P2', '管段号': 'S1'},
            {'单元号': 'U2', '管线号': 'P1', '管段号': 'S1'},
            {'单元号': 'U2', '管线号': 'P1', '管段号': '  '},
        ])

        self.assertEqual(_prefab_segment_count(dataframe), 3)

    def test_falls_back_to_segment_number_when_context_columns_are_missing(self):
        dataframe = pd.DataFrame([
            {'管段号': 'S1'},
            {'管段号': 'S1'},
            {'管段号': 'S2'},
        ])

        self.assertEqual(_prefab_segment_count(dataframe), 2)

