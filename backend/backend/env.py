"""Small, typed environment-variable helpers used by Django settings.

The project intentionally keeps this module dependency-free so management
commands can start in a fresh virtual environment before optional packages are
installed. Operating-system variables always win over values from ``.env``.
"""

import os
import re
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured


TRUE_VALUES = frozenset({'1', 'true', 'yes', 'on'})
FALSE_VALUES = frozenset({'0', 'false', 'no', 'off'})
ENV_NAME_PATTERN = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def load_env_file(path):
    """Load a simple KEY=VALUE file without overwriting process variables.

    This parser deliberately supports the subset used by this project: blank
    lines, comments, optional ``export`` prefixes, and matching single/double
    quotes. Shell interpolation is not performed, which keeps secret values
    predictable across Windows and Linux.
    """

    env_path = Path(path)
    if not env_path.is_file():
        return

    for line_number, raw_line in enumerate(env_path.read_text(encoding='utf-8-sig').splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[7:].lstrip()

        name, separator, value = line.partition('=')
        name = name.strip()
        if not separator or not ENV_NAME_PATTERN.fullmatch(name):
            raise ImproperlyConfigured(f'Invalid environment entry at {env_path}:{line_number}')

        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(name, value)


def env(name, default=None, *, required=False):
    """Read a string variable and optionally require a non-empty value."""

    value = os.environ.get(name, default)
    if required and (value is None or str(value).strip() == ''):
        raise ImproperlyConfigured(f'Missing required environment variable: {name}')
    return value


def env_bool(name, default=False):
    """Read a boolean variable and reject ambiguous spellings."""

    raw_value = str(os.environ.get(name, str(default))).strip().lower()
    if raw_value in TRUE_VALUES:
        return True
    if raw_value in FALSE_VALUES:
        return False
    raise ImproperlyConfigured(
        f'{name} must be one of: {", ".join(sorted(TRUE_VALUES | FALSE_VALUES))}',
    )


def env_int(name, default, *, minimum=None, maximum=None):
    """Read a bounded integer and fail fast during application startup."""

    raw_value = os.environ.get(name, str(default))
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ImproperlyConfigured(f'{name} must be an integer, got {raw_value!r}') from exc
    if minimum is not None and value < minimum:
        raise ImproperlyConfigured(f'{name} must be at least {minimum}')
    if maximum is not None and value > maximum:
        raise ImproperlyConfigured(f'{name} must be at most {maximum}')
    return value


def env_list(name, default=()):
    """Read a comma-separated list, trimming whitespace and empty entries."""

    raw_value = os.environ.get(name)
    if raw_value is None:
        return list(default)
    return [item.strip() for item in raw_value.split(',') if item.strip()]
