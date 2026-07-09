from django.core.management.base import BaseCommand

from pipecloud.models import Project
from pipecloud.services.prefab_database import backfill_plan_record_summaries


class Command(BaseCommand):
    help = '根据已保存的焊接计划行回填下料、焊接计划悬浮摘要。'

    def add_arguments(self, parser):
        parser.add_argument('--project-id', type=int, help='只回填指定项目')

    def handle(self, *args, **options):
        projects = Project.objects.all()
        if options.get('project_id'):
            projects = projects.filter(pk=options['project_id'])
        updated = 0
        for project in projects:
            count = backfill_plan_record_summaries(project)
            updated += count
            self.stdout.write(f'{project.id} {project.project_name}: {count} 条')
        self.stdout.write(self.style.SUCCESS(f'计划摘要回填完成：{updated} 条'))
