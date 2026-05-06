from django.core.cache import cache
from django.conf import settings

_CACHE_KEY = 'current_semester'
_CACHE_TTL = getattr(settings, 'CURRENT_SEMESTER_CACHE_TTL', 86400)


def get_current_semester():
    """Returns the current semester with caching."""
    semester = cache.get(_CACHE_KEY)
    if semester is None:
        from school.models import Semester
        semester = Semester.objects.order_by('-end_date').first()
        if semester:
            cache.set(_CACHE_KEY, semester, timeout=_CACHE_TTL)
    return semester


def invalidate_semester_cache():
    cache.delete(_CACHE_KEY)
