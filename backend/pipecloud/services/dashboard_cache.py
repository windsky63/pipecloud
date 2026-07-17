"""Project-scoped cache helpers for home dashboard payloads."""

from django.conf import settings
from django.core.cache import cache


DASHBOARD_NAMES = ('initialization', 'welding', 'arrival', 'anti-corrosion', 'cutting')


def _cache_key(project_id, dashboard_name):
    return f'pipecloud:dashboard:v1:{int(project_id)}:{dashboard_name}'


def dashboard_payload(project_id, dashboard_name, builder, force_refresh=False):
    """Return one cached dashboard payload, rebuilding it when requested."""

    timeout = settings.DASHBOARD_CACHE_TIMEOUT
    key = _cache_key(project_id, dashboard_name)
    if timeout > 0 and not force_refresh:
        cached = cache.get(key)
        if cached is not None:
            return cached, True

    payload = builder()
    if timeout > 0:
        cache.set(key, payload, timeout=timeout)
    return payload, False


def invalidate_dashboard_cache(project_id=None):
    """Invalidate all dashboard payloads for one project or the whole cache."""

    if project_id in (None, ''):
        cache.clear()
        return
    cache.delete_many([_cache_key(project_id, name) for name in DASHBOARD_NAMES])
