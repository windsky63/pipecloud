from django.core.management.base import BaseCommand
from django.db import connection, transaction

from pipecloud.models import Project
from pipecloud.services.project_tables import (
    PROJECT_SCOPED_MODELS,
    ensure_project_tables,
    project_table_name,
    using_project_tables,
)
from pipecloud.views.common import _project_root
from pipecloud.views.workflow import _sync_project_database_tables


def copy_model_rows(project, model):
    source_rows = list(model.objects.filter(project=project).order_by('id'))
    if not source_rows:
        return 0

    field_names = [field.name for field in model._meta.fields]
    table_name = project_table_name(project, model)
    with using_project_tables(project):
        with connection.cursor() as cursor:
            cursor.execute(
                f'SELECT COUNT(*) FROM {connection.ops.quote_name(table_name)} WHERE project_id = %s',
                [project.id],
            )
            existing_count = cursor.fetchone()[0]
        if existing_count:
            return 0
        copies = []
        for row in source_rows:
            values = {field_name: getattr(row, field_name) for field_name in field_names}
            copies.append(model(**values))
        model.objects.bulk_create(copies, batch_size=500)
    return len(source_rows)


class Command(BaseCommand):
    help = 'Create project-scoped tables and migrate existing project data into them.'

    def add_arguments(self, parser):
        parser.add_argument('--project-id', type=int, help='Only migrate one project.')
        parser.add_argument(
            '--skip-file-sync',
            action='store_true',
            help='Only copy legacy database rows; do not resync Excel files from the project folder.',
        )

    def handle(self, *args, **options):
        projects = Project.objects.all().order_by('id')
        if options.get('project_id'):
            projects = projects.filter(id=options['project_id'])

        migrated_projects = 0
        for project in projects:
            migrated_projects += 1
            ensure_project_tables(project)
            self.stdout.write(f'Project {project.id} tables ready:')
            for model in PROJECT_SCOPED_MODELS:
                self.stdout.write(f'  {model.__name__}: {project_table_name(project, model)}')

            copied_total = 0
            with transaction.atomic():
                for model in PROJECT_SCOPED_MODELS:
                    copied = copy_model_rows(project, model)
                    copied_total += copied
                    if copied:
                        self.stdout.write(f'  copied {copied} rows from {model.__name__}')

            if not options.get('skip_file_sync'):
                data_root = _project_root(project)
                _sync_project_database_tables(project, data_root)
                self.stdout.write(f'  synced files from {data_root}')

            self.stdout.write(f'Project {project.id} migrated, legacy rows copied: {copied_total}')

        self.stdout.write(self.style.SUCCESS(f'Migrated {migrated_projects} project(s).'))
