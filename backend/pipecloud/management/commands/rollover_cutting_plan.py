from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from pipecloud.services.plan_rollover import execute_all_project_rollovers


class Command(BaseCommand):
    help = '将未完成下料计划滚动到后续计划日期'

    def add_arguments(self, parser):
        parser.add_argument('--date', dest='business_date', help='业务日期，格式 YYYYMMDD 或 YYYY-MM-DD')
        parser.add_argument('--project-id', type=int, help='仅处理指定项目')
        parser.add_argument('--dry-run', action='store_true', help='只计算滚动结果，不写入数据库')
        parser.add_argument('--force', action='store_true', help='强制重新执行已成功的同日任务')

    def handle(self, *args, **options):
        business_date = options.get('business_date') or timezone.localdate()
        try:
            results = execute_all_project_rollovers(
                plan_key='cutting',
                business_date=business_date,
                project_id=options.get('project_id'),
                dry_run=options.get('dry_run', False),
                force=options.get('force', False),
            )
        except (TypeError, ValueError) as error:
            raise CommandError(str(error)) from error

        failed = 0
        for result in results:
            label = f'[{result["projectId"]}] {result["projectName"]}'
            if result.get('error'):
                failed += 1
                self.stderr.write(self.style.ERROR(f'{label} 失败：{result["error"]}'))
                continue
            if result.get('skipped'):
                self.stdout.write(self.style.WARNING(f'{label} 已跳过：{result.get("reason", "")}'))
                continue
            self.stdout.write(self.style.SUCCESS(
                f'{label} 当日 {result.get("todayCuttingCount", 0)} 条，'
                f'完成 {result.get("completedCuttingCount", 0)} 条，'
                f'滚动 {result.get("rolledCuttingCount", 0)} 条，'
                f'影响计划 {len(result.get("affectedPlanDates", []))} 天'
            ))
        if failed:
            raise CommandError(f'{failed} 个项目执行失败')
