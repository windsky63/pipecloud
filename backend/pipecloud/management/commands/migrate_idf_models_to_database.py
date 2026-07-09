import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from pipecloud.models import ParserJob
from pipecloud.services.idf_model_storage import (
    fail_idf_model,
    finalize_idf_model,
    initialize_idf_model,
    store_idf_model_part,
)


FILE_PARSER_ROOT = Path(__file__).resolve().parents[3] / 'file' / 'parser'
LEGACY_MODEL_NAME = 'IDF模型数据.json'


def legacy_model_paths(job):
    paths = []
    seen = set()
    for result in job.results or []:
        staged_path = result.get('stagedPath')
        if not staged_path:
            continue
        path = (FILE_PARSER_ROOT / staged_path).resolve().parent / LEGACY_MODEL_NAME
        if path in seen or not path.is_file():
            continue
        try:
            path.relative_to(FILE_PARSER_ROOT.resolve())
        except ValueError:
            continue
        seen.add(path)
        paths.append(path)
    return paths


class Command(BaseCommand):
    help = '将历史 IDF 模型 JSON 导入数据库，并在成功后删除对应 JSON 文件。'

    def add_arguments(self, parser):
        parser.add_argument('--job-id', help='指定 ParserJob.job_id；默认迁移每个项目最新的已完成 IDF 任务')
        parser.add_argument('--keep-files', action='store_true', help='导入成功后保留历史 JSON')

    def handle(self, *args, **options):
        queryset = ParserJob.objects.filter(file_type='idf', status='completed').select_related('project')
        if options.get('job_id'):
            queryset = queryset.filter(job_id=options['job_id'])
        else:
            latest_ids = []
            for project_id in queryset.values_list('project_id', flat=True).distinct():
                job_id = (
                    queryset.filter(project_id=project_id)
                    .order_by('-updated_at', '-id')
                    .values_list('id', flat=True)
                    .first()
                )
                if job_id:
                    latest_ids.append(job_id)
            queryset = queryset.filter(id__in=latest_ids)

        jobs = list(queryset.order_by('project_id', 'id'))
        if not jobs:
            raise CommandError('没有找到可迁移的已完成 IDF 解析任务')

        migrated = 0
        deleted = 0
        for job in jobs:
            paths = legacy_model_paths(job)
            if not paths:
                self.stdout.write(self.style.WARNING(f'{job.job_id}: 未找到历史模型 JSON，已跳过'))
                continue

            model = initialize_idf_model(job)
            try:
                for index, path in enumerate(paths, start=1):
                    with path.open('r', encoding='utf-8') as model_file:
                        store_idf_model_part(model.id, index, json.load(model_file))
                finalize_idf_model(model.id)
            except Exception:
                fail_idf_model(model.id)
                raise

            migrated += 1
            if not options.get('keep_files'):
                for path in paths:
                    path.unlink(missing_ok=True)
                    deleted += 1
            self.stdout.write(self.style.SUCCESS(
                f'{job.job_id}: 已导入 {len(paths)} 个模型分片，删除 {0 if options.get("keep_files") else len(paths)} 个 JSON'
            ))

        self.stdout.write(self.style.SUCCESS(f'迁移完成：{migrated} 个任务，删除 {deleted} 个历史 JSON'))
