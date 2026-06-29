"""
Create the PipeCloud database and apply Django migrations.

Usage:
    python create_pipecloud_database.py

MySQL settings are read from backend/settings.py.
"""

from __future__ import annotations

import argparse
import os

from backend import settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create PipeCloud database.")
    parser.add_argument(
        "--no-migrate",
        action="store_true",
        help="Only create the database file/schema, do not run Django migrations.",
    )
    return parser.parse_args()


def create_mysql_database() -> str:
    import pymysql

    database = settings.MYSQL_DATABASE
    connection = pymysql.connect(
        host=settings.MYSQL_HOST,
        port=int(settings.MYSQL_PORT),
        user=settings.MYSQL_USER,
        password=settings.MYSQL_PASSWORD,
        charset="utf8mb4",
        autocommit=True,
    )

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{database}` "
                "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    finally:
        connection.close()

    return database


def run_migrations() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")

    import django
    from django.core.management import call_command

    django.setup()
    call_command("migrate", interactive=False)


def main() -> None:
    args = parse_args()

    database = create_mysql_database()
    print(f"MySQL database ready: {database}")

    if not args.no_migrate:
        run_migrations()
        print("Django migrations applied.")


if __name__ == "__main__":
    main()
