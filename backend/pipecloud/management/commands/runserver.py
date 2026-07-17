"""Development server that owns a matching scheduler child process."""

import os
import subprocess
import sys

from django.conf import settings
from django.contrib.staticfiles.management.commands.runserver import Command as DjangoRunserverCommand


class Command(DjangoRunserverCommand):
    help = '启动 Django 开发服务器，并同时启动 PipeCloud 定时任务进程'

    def handle(self, *args, **options):
        use_reloader = options.get('use_reloader', True)
        in_reloader_child = os.environ.get('RUN_MAIN') == 'true'
        should_start_scheduler = (
            settings.SCHEDULER_AUTOSTART_WITH_RUNSERVER
            and os.environ.get('PIPECLOUD_SCHEDULER_CHILD') != '1'
            and (not use_reloader or in_reloader_child)
        )
        scheduler_process = self._start_scheduler() if should_start_scheduler else None
        try:
            return super().handle(*args, **options)
        finally:
            self._stop_scheduler(scheduler_process)

    def _start_scheduler(self):
        env = os.environ.copy()
        env['PIPECLOUD_SCHEDULER_CHILD'] = '1'
        command = [sys.executable, str(settings.BASE_DIR / 'manage.py'), 'run_scheduler']
        process = subprocess.Popen(command, cwd=settings.BASE_DIR, env=env)
        self.stdout.write(self.style.SUCCESS(f'定时任务进程已随后端启动（PID {process.pid}）'))
        return process

    def _stop_scheduler(self, process):
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        self.stdout.write(self.style.SUCCESS('定时任务进程已随后端停止'))
