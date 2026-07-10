import json

from django.test import TestCase
from django.urls import reverse

from pipecloud.models import Project, ProjectConstraint
from pipecloud.services.project_constraints import project_process_sequence, update_project_constraints
from pipecloud.views.common import _modules_for_project


class ProjectConstraintApiTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(project_name='约束测试项目')
        self.url = reverse('pipecloud-project-constraints', args=[self.project.id])

    def test_returns_required_rule_with_default_sequence(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload['appliedToScheduling'])
        self.assertEqual(payload['rules'], [{
            'key': 'coating_welding_sequence',
            'enabled': True,
            'parameters': {'sequence': 'coating_before_welding'},
            'options': [
                'coating_before_welding',
                'welding_before_coating',
            ],
            'required': True,
        }])

    def test_creating_project_writes_default_process_sequence(self):
        response = self.client.post(
            reverse('pipecloud-projects'),
            data=json.dumps({'project_name': '默认工序项目'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        project = Project.objects.get(project_name='默认工序项目')
        self.assertEqual(project_process_sequence(project), 'coating_before_welding')
        self.assertTrue(ProjectConstraint.objects.filter(
            project=project,
            rule_key='coating_welding_sequence',
            enabled=True,
            parameters={'sequence': 'coating_before_welding'},
        ).exists())

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

    def test_rejects_disabled_process_sequence(self):
        response = self.client.put(
            self.url,
            data=json.dumps({
                'rules': [{
                    'key': 'coating_welding_sequence',
                    'enabled': False,
                    'parameters': {},
                }],
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(ProjectConstraint.objects.filter(project=self.project).exists())

    def test_rejects_missing_required_process_sequence(self):
        response = self.client.put(
            self.url,
            data=json.dumps({'rules': []}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(ProjectConstraint.objects.filter(project=self.project).exists())

    def test_process_sequence_defaults_to_coating_before_welding(self):
        self.assertEqual(project_process_sequence(self.project), 'coating_before_welding')

    def test_modules_keep_default_order_for_coating_before_welding(self):
        keys = [module['key'] for module in _modules_for_project(self.project)]

        self.assertLess(keys.index('antiCorrosion'), keys.index('cutting'))
        self.assertLess(keys.index('antiCorrosion'), keys.index('welding'))

    def test_modules_move_anti_corrosion_after_welding_for_welding_before_coating(self):
        update_project_constraints(self.project, [{
            'key': 'coating_welding_sequence',
            'enabled': True,
            'parameters': {'sequence': 'welding_before_coating'},
        }])

        keys = [module['key'] for module in _modules_for_project(self.project)]

        self.assertLess(keys.index('welding'), keys.index('antiCorrosion'))
        self.assertLess(keys.index('antiCorrosion'), keys.index('schedule'))
