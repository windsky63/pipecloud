import sqlite3
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from pipecloud.models import Project
from pipecloud.services.project_tables import (
    PROJECT_SCOPED_MODELS,
    drop_project_tables,
    ensure_project_tables,
    project_table_name,
    using_project_tables,
)


def sqlite_rows(database_path, table_name, where='', params=()):
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        sql = f'SELECT * FROM {table_name}'
        if where:
            sql = f'{sql} WHERE {where}'
        return [dict(row) for row in connection.execute(sql, params).fetchall()]
    finally:
        connection.close()


def row_values_for_model(model, row):
    values = {}
    for field in model._meta.fields:
        column = field.column
        if column in row:
            values[field.attname] = row[column]
    return values


def copy_rows(database_path, project_id, model, source_table_name):
    rows = sqlite_rows(database_path, source_table_name, 'project_id = ?', (project_id,))
    if not rows:
        return 0
    instances = [model(**row_values_for_model(model, row)) for row in rows]
    model.objects.bulk_create(instances, batch_size=500)
    return len(instances)


def clear_project_tables(project):
    with connection.cursor() as cursor:
        cursor.execute('SET FOREIGN_KEY_CHECKS = 0')
        try:
            for model in reversed(PROJECT_SCOPED_MODELS):
                table_name = project_table_name(project, model)
                quoted_name = connection.ops.quote_name(table_name)
                cursor.execute(f'DELETE FROM {quoted_name}')
        finally:
            cursor.execute('SET FOREIGN_KEY_CHECKS = 1')


class Command(BaseCommand):
    help = 'Import one legacy SQLite project into the current MySQL project-scoped table layout.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--sqlite-path',
            default='db.sqlite3',
            help='Legacy SQLite database path. Defaults to backend/db.sqlite3.',
        )
        parser.add_argument('--project-id', type=int, help='Legacy project id to import.')
        parser.add_argument(
            '--replace',
            action='store_true',
            help='Replace the target MySQL project and its project-scoped tables if they already exist.',
        )

    def handle(self, *args, **options):
        database_path = Path(options['sqlite_path'])
        if not database_path.is_absolute():
            database_path = Path.cwd() / database_path
        if not database_path.exists():
            raise CommandError(f'Legacy SQLite database does not exist: {database_path}')

        project_rows = sqlite_rows(database_path, 'pipecloud_project')
        if options.get('project_id'):
            project_rows = [row for row in project_rows if row.get('id') == options['project_id']]
        if not project_rows:
            raise CommandError('No legacy project found to import.')
        if len(project_rows) > 1:
            raise CommandError('Multiple legacy projects found; pass --project-id.')

        project_row = project_rows[0]
        project_id = project_row['id']
        source_table_names = {
            model: model._meta.db_table
            for model in PROJECT_SCOPED_MODELS
        }

        if options['replace'] and Project.objects.filter(id=project_id).exists():
            drop_project_tables(project_id)
            Project.objects.filter(id=project_id).delete()

        project, _ = Project.objects.update_or_create(
            id=project_id,
            defaults=row_values_for_model(Project, project_row),
        )
        ensure_project_tables(project)

        with transaction.atomic():
            copied = {}
            clear_project_tables(project)
            with using_project_tables(project):
                for model in PROJECT_SCOPED_MODELS:
                    copied[model.__name__] = copy_rows(
                        database_path,
                        project_id,
                        model,
                        source_table_names[model],
                    )

        self.stdout.write(f'Imported project {project.id}: {project.project_name}')
        for model in PROJECT_SCOPED_MODELS:
            self.stdout.write(
                f'{project_table_name(project, model)} ({model.__name__}): {copied[model.__name__]} rows'
            )
        self.stdout.write(self.style.SUCCESS('Legacy SQLite project import complete.'))
