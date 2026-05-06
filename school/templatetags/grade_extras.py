from django import template
from .filters import get_item  # noqa: F401 — re-export for templates using {% load grade_extras %}

register = template.Library()


@register.filter
def get_attr(obj, attr_name):
    return getattr(obj, attr_name, '')


@register.filter
def get_sg_score(grade_obj, sg_key):
    if grade_obj and hasattr(grade_obj, 'get_sg_scores'):
        sg_scores = grade_obj.get_sg_scores()
        if isinstance(sg_scores, dict):
            return sg_scores.get(sg_key, 0)
    return 0


@register.filter
def mul(value, arg):
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def sum_attribute(objects_list, attribute_name):
    total = 0
    for obj in objects_list:
        try:
            value = getattr(obj, attribute_name, 0)
            total += value if isinstance(value, (int, float)) else 0
        except (TypeError, ValueError):
            pass
    return total


# Re-export get_item so {% load grade_extras %}|get_item still works
register.filter('get_item', get_item)
