import logging
import signal

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand


logger = logging.getLogger(__name__)
JOB_ID = 'pipecloud-update-plan-completion'


def update_plan_completion_job():
    logger.info('开始执行焊接计划完成情况更新任务')
    call_command('update_plan_completion')
    logger.info('焊接计划完成情况更新任务执行完毕')


class Command(BaseCommand):
    help = '启动 PipeCloud APScheduler 定时任务进程'

    def handle(self, *args, **options):
        scheduler = BlockingScheduler(timezone=settings.TIME_ZONE)
        scheduler.add_job(
            update_plan_completion_job,
            trigger=CronTrigger(
                hour=settings.PLAN_ROLLOVER_HOUR,
                minute=settings.PLAN_ROLLOVER_MINUTE,
                timezone=settings.TIME_ZONE,
            ),
            id=JOB_ID,
            name='每日更新计划完成情况并滚动未完成焊口',
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=settings.PLAN_ROLLOVER_MISFIRE_GRACE_SECONDS,
        )

        def stop_scheduler(*_args):
            if scheduler.running:
                scheduler.shutdown(wait=False)

        signal.signal(signal.SIGINT, stop_scheduler)
        signal.signal(signal.SIGTERM, stop_scheduler)
        self.stdout.write(self.style.SUCCESS(
            f'定时任务已启动：每天 '
            f'{settings.PLAN_ROLLOVER_HOUR:02d}:{settings.PLAN_ROLLOVER_MINUTE:02d} '
            f'({settings.TIME_ZONE})'
        ))
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            stop_scheduler()
