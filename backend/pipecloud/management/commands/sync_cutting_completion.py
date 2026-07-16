from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from pipecloud.services.plan_completion import execute_all_completion_syncs


class Command(BaseCommand):
    help = '同步下料计划中的下料完成情况'

    def add_arguments(self, parser):
        parser.add_argument('--date', dest='business_date', help='业务日期，格式 YYYYMMDD 或 YYYY-MM-DD')
        parser.add_argument('--project-id', type=int, help='仅处理指定项目')
        parser.add_argument('--force', action='store_true', help='强制重新执行已成功的同日任务')

    def handle(self, *args, **options):
        business_date = options.get('business_date') or timezone.localdate()
        results = execute_all_completion_syncs(
            'cutting',
            business_date=business_date,
            project_id=options.get('project_id'),
            force=options.get('force', False),
        )
        failed = 0
        for result in results:
            label = f'[{result["projectId"]}] {result["projectName"]}'
            if result.get('error'):
                failed += 1
                self.stderr.write(self.style.ERROR(f'{label} 失败：{result["error"]}'))
                continue
            if result.get('alreadyExecuted'):
                self.stdout.write(self.style.WARNING(f'{label} 今日已执行'))
                continue
            self.stdout.write(self.style.SUCCESS(
                f'{label} 同步完成：来源 {result.get("sourceCount", 0)} 个，'
                f'匹配 {result.get("matchedCount", 0)} 条，'
                f'完成 {result.get("completedCount", 0)} 条'
            ))
        if failed:
            raise CommandError(f'{failed} 个项目执行失败')
