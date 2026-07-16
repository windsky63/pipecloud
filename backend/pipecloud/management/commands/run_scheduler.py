import logging
import signal

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand


logger = logging.getLogger(__name__)


def completion_sync_job(command_name, job_name):
    logger.info('开始执行%s', job_name)
    call_command(command_name)
    logger.info('%s执行完毕', job_name)


class Command(BaseCommand):
    help = '启动 PipeCloud APScheduler 定时任务进程'

    def handle(self, *args, **options):
        scheduler = BlockingScheduler(timezone=settings.TIME_ZONE)
        enabled_jobs = []
        for config in settings.SCHEDULED_MAINTENANCE_JOBS:
            if not config.get('enabled', True):
                continue
            scheduler.add_job(
                completion_sync_job,
                args=[config['command'], config['name']],
                trigger=CronTrigger(
                    hour=config['hour'],
                    minute=config['minute'],
                    timezone=settings.TIME_ZONE,
                ),
                id=f'pipecloud-{config["key"]}',
                name=config['name'],
                replace_existing=True,
                coalesce=True,
                max_instances=1,
                misfire_grace_time=settings.PLAN_COMPLETION_SYNC_MISFIRE_GRACE_SECONDS,
            )
            enabled_jobs.append(config)

        def stop_scheduler(*_args):
            if scheduler.running:
                scheduler.shutdown(wait=False)

        signal.signal(signal.SIGINT, stop_scheduler)
        signal.signal(signal.SIGTERM, stop_scheduler)
        if enabled_jobs:
            lines = [
                f'{item["name"]}：每天 {item["hour"]:02d}:{item["minute"]:02d} ({settings.TIME_ZONE})'
                for item in enabled_jobs
            ]
            self.stdout.write(self.style.SUCCESS('定时任务已启动：\n' + '\n'.join(lines)))
        else:
            self.stdout.write(self.style.WARNING('没有启用的定时任务'))
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            stop_scheduler()
