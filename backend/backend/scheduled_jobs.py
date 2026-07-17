"""Configuration builders for scheduler-managed maintenance commands."""

from .env import env_bool, env_int


def _job(key, kind, command, name, env_prefix, default_hour, default_minute):
    """Build one validated job definition from a consistent variable prefix."""

    return {
        'key': key,
        'kind': kind,
        'command': command,
        'name': name,
        'hour': env_int(f'{env_prefix}_HOUR', default_hour, minimum=0, maximum=23),
        'minute': env_int(f'{env_prefix}_MINUTE', default_minute, minimum=0, maximum=59),
        'enabled': env_bool(f'{env_prefix}_ENABLED', True),
    }


def build_scheduled_maintenance_jobs():
    """Return all recurring jobs in execution order.

    Completion synchronization must run before plan rollover, so the order and
    default minutes below are part of the scheduling contract.
    """

    return [
        _job(
            'sync-anti-corrosion-completion',
            'completion-sync',
            'sync_anti_corrosion_completion',
            '同步防腐计划中防腐完成情况',
            'PIPECLOUD_ANTI_CORROSION_COMPLETION_SYNC',
            21,
            0,
        ),
        _job(
            'sync-cutting-completion',
            'completion-sync',
            'sync_cutting_completion',
            '同步下料计划中下料完成情况',
            'PIPECLOUD_CUTTING_COMPLETION_SYNC',
            21,
            5,
        ),
        _job(
            'sync-welding-completion',
            'completion-sync',
            'sync_welding_completion',
            '同步焊接计划中焊接完成情况',
            'PIPECLOUD_WELDING_COMPLETION_SYNC',
            21,
            10,
        ),
        _job(
            'rollover-cutting-plan',
            'plan-rollover',
            'rollover_cutting_plan',
            '滚动未完成下料计划',
            'PIPECLOUD_CUTTING_PLAN_ROLLOVER',
            21,
            20,
        ),
        _job(
            'rollover-welding-plan',
            'plan-rollover',
            'rollover_welding_plan',
            '滚动未完成焊接计划',
            'PIPECLOUD_WELDING_PLAN_ROLLOVER',
            21,
            30,
        ),
    ]
