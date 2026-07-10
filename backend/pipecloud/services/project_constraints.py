from django.db import transaction

from pipecloud.models import ProjectConstraint


PROCESS_SEQUENCE_RULE = 'coating_welding_sequence'
DEFAULT_PROCESS_SEQUENCE = 'coating_before_welding'

CONSTRAINT_DEFINITIONS = {
    PROCESS_SEQUENCE_RULE: {
        'parameter': 'sequence',
        'options': (
            'coating_before_welding',
            'welding_before_coating',
        ),
    },
}


def project_constraints_payload(project):
    stored_rules = {
        constraint.rule_key: constraint
        for constraint in ProjectConstraint.objects.filter(project=project)
    }
    rules = []
    for rule_key, definition in CONSTRAINT_DEFINITIONS.items():
        constraint = stored_rules.get(rule_key)
        default_value = DEFAULT_PROCESS_SEQUENCE if rule_key == PROCESS_SEQUENCE_RULE else ''
        stored_value = str((constraint.parameters or {}).get(definition['parameter']) or '').strip() if constraint else ''
        value = stored_value if stored_value in definition['options'] else default_value
        rules.append({
            'key': rule_key,
            'enabled': True,
            'parameters': {definition['parameter']: value},
            'options': list(definition['options']),
            'required': True,
        })
    return {
        'projectId': project.id,
        'projectName': project.project_name,
        'rules': rules,
        'appliedToScheduling': False,
    }


def project_process_sequence(project, default=DEFAULT_PROCESS_SEQUENCE):
    constraint = ProjectConstraint.objects.filter(
        project=project,
        rule_key=PROCESS_SEQUENCE_RULE,
        enabled=True,
    ).first()
    value = str((constraint.parameters or {}).get('sequence') or '').strip() if constraint else ''
    options = CONSTRAINT_DEFINITIONS[PROCESS_SEQUENCE_RULE]['options']
    return value if value in options else default


@transaction.atomic
def update_project_constraints(project, rules):
    if not isinstance(rules, list):
        raise ValueError('项目约束规则必须是列表')

    seen_keys = set()
    for rule in rules:
        if not isinstance(rule, dict):
            raise ValueError('项目约束规则格式无效')
        rule_key = str(rule.get('key') or '').strip()
        if rule_key not in CONSTRAINT_DEFINITIONS:
            raise ValueError(f'不支持的项目约束规则：{rule_key or "空规则"}')
        if rule_key in seen_keys:
            raise ValueError(f'项目约束规则重复：{rule_key}')
        seen_keys.add(rule_key)

        enabled = bool(rule.get('enabled'))
        parameters = rule.get('parameters') or {}
        if not isinstance(parameters, dict):
            raise ValueError(f'项目约束规则参数格式无效：{rule_key}')

        definition = CONSTRAINT_DEFINITIONS[rule_key]
        parameter_name = definition['parameter']
        value = str(parameters.get(parameter_name) or '').strip()
        if not enabled:
            raise ValueError(f'项目约束规则为必选项：{rule_key}')
        if value not in definition['options']:
            raise ValueError(f'项目约束规则选项无效：{rule_key}')

        ProjectConstraint.objects.update_or_create(
            project=project,
            rule_key=rule_key,
            defaults={
                'enabled': True,
                'parameters': {parameter_name: value},
            },
        )

    if PROCESS_SEQUENCE_RULE not in seen_keys:
        raise ValueError(f'项目约束规则为必选项：{PROCESS_SEQUENCE_RULE}')

    return project_constraints_payload(project)
