import logging
from django import template
from .filters import get_item  # noqa: F401 — canonical implementation

logger = logging.getLogger(__name__)
register = template.Library()

# Re-export canonical get_item
register.filter('get_item', get_item)


@register.filter
def attr(obj, attr_name):
    return getattr(obj, attr_name, None)


@register.filter
def average(value):
    if not value:
        return 0
    return round(sum(value) / len(value), 2)


@register.filter(name='filter_by_student')
def filter_by_student(queryset, student_id):
    return queryset.filter(student_id=student_id)


@register.filter
def lookup(dictionary, key):
    if dictionary is None:
        return None
    return dictionary.get(key, [])


@register.filter
def dict_key(dictionary, key):
    if dictionary is None:
        return None
    return dictionary.get(key)


@register.filter
def range_filter(value):
    return range(value)


@register.filter(name='ru_plural')
def ru_plural(value, variants):
    variants = variants.split(',')
    value = abs(int(value))
    if value % 10 == 1 and value % 100 != 11:
        variant = 0
    elif 2 <= value % 10 <= 4 and (value % 100 < 10 or value % 100 >= 20):
        variant = 1
    else:
        variant = 2
    return variants[variant]
