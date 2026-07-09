import json

from django.test import TestCase
from django.urls import reverse

from pipecloud.models import Project, ProjectConstraint


class ProjectConstraintApiTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(project_name='约束测试项目')
        self.url = reverse('pipecloud-project-constraints', args=[self.project.id])

    def test_returns_supported_rule_without_assuming_a_default_sequence(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload['appliedToScheduling'])
        self.assertEqual(payload['rules'], [{
            'key': 'coating_welding_sequence',
            'enabled': False,
            'parameters': {},
            'options': [
                'coating_before_welding',
                'welding_before_coating',
            ],
        }])

    def test_saves_process_sequence_for_the_selected_project(self):
        response = self.client.put(
            self.url,
            data=json.dumps({
                'rules': [{
                    'key': 'coating_welding_sequence',
                    'enabled': True,
                    'parameters': {'sequence': 'welding_before_coating'},
                }],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        constraint = ProjectConstraint.objects.get(
            project=self.project,
            rule_key='coating_welding_sequence',
        )
        self.assertTrue(constraint.enabled)
        self.assertEqual(constraint.parameters, {'sequence': 'welding_before_coating'})

    def test_rejects_an_unknown_process_sequence(self):
        response = self.client.put(
            self.url,
            data=json.dumps({
                'rules': [{
                    'key': 'coating_welding_sequence',
                    'enabled': True,
                    'parameters': {'sequence': 'paint_everything_blue'},
                }],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(ProjectConstraint.objects.filter(project=self.project).exists())
