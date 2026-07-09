import json

import pandas as pd
from django.test import TestCase

from pipecloud.models import ParserJob, ParserSubtask
from pipecloud.services.idf_model_storage import (
    finalize_idf_model,
    initialize_idf_model,
    store_idf_model_part,
)
from spool_analysis.project_spool_info import _spool_idf_components


class IdfModelStorageTests(TestCase):
    def setUp(self):
        from pipecloud.models import Project

        self.project = Project.objects.create(project_name='IDF数据库测试')
        self.job = ParserJob.objects.create(
            job_id='idf-database-test',
            project=self.project,
            file_type='idf',
            status='running',
            input_hash='idf-database-test-hash',
        )

    def test_spool_components_are_queried_from_database_lookup(self):
        model = initialize_idf_model(self.job)
        store_idf_model_part(model.id, 1, {
            'projectName': self.project.project_name,
            'components': [
                {
                    'id': 'pipe-1',
                    'type': 'pipe',
                    'pipelineName': 'LINE-100',
                    'pipelineId': 'line-100.idf',
                },
                {
                    'id': 'weld-1',
                    'type': 'weld',
                    'pipelineName': 'LINE-100',
                    'pipelineId': 'line-100.idf',
                    'weldNo': 'W-001',
                    'connectedComponentIds': ['pipe-1'],
                },
            ],
        })
        model = finalize_idf_model(model.id)

        spool = pd.DataFrame([{
            '管线号': 'LINE-100',
            '最终焊口号': 'W-001',
            '初始焊口号': '',
        }])
        components, issues, matched = _spool_idf_components(spool, model)

        self.assertEqual(matched, 1)
        self.assertEqual(issues, [])
        self.assertEqual({item['id'] for item in components}, {'pipe-1', 'weld-1'})

    def test_model_metadata_is_stored_without_duplicate_components_array(self):
        model = initialize_idf_model(self.job)
        part = store_idf_model_part(model.id, 1, {
            'projectName': self.project.project_name,
            'nodes': [{'id': 'node-1'}],
            'components': [{'id': 'pipe-1', 'type': 'pipe'}],
        })

        self.assertNotIn('components', part.metadata)
        self.assertEqual(part.metadata['nodes'], [{'id': 'node-1'}])
        self.assertEqual(part.components.count(), 1)

    def test_preview_and_confirmation_use_database_model_data(self):
        model = initialize_idf_model(self.job)
        store_idf_model_part(model.id, 1, {
            'projectName': self.project.project_name,
            'nodes': [{'id': 'node-1', 'position': [1, 2, 3]}],
            'components': [{
                'id': 'pipe-1',
                'type': 'pipe',
                'start': [1, 2, 3],
                'end': [4, 5, 6],
            }],
        })
        ParserSubtask.objects.create(
            job=self.job,
            index=1,
            status='completed',
            result_payload={'modelPartIndex': 1},
        )
        self.job.status = 'completed'
        self.job.total = 1
        self.job.completed = 1
        self.job.results = [{'fileType': 'idf', 'modelPartIndex': 1}]
        self.job.save()

        preview_response = self.client.get(
            '/api/pipecloud/file-parser/model-preview/',
            {
                'project_id': self.project.id,
                'jobId': self.job.job_id,
                'partIndex': 1,
            },
        )

        self.assertEqual(preview_response.status_code, 200)
        preview = preview_response.json()
        self.assertEqual(preview['nodes'][0]['position'], [1, 2, 3])
        self.assertEqual(preview['components'][0]['start'], [1, 2, 3])

        confirm_response = self.client.post(
            f'/api/pipecloud/file-parser/model-confirm/?project_id={self.project.id}',
            data=json.dumps({'jobId': self.job.job_id}),
            content_type='application/json',
        )

        self.assertEqual(confirm_response.status_code, 200)
        model.refresh_from_db()
        self.assertEqual(model.status, 'ready')
