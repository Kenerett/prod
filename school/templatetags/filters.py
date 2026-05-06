from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return getattr(dictionary, str(key), None)


@register.filter
def letter_grade(score):
    if score is None:
        return '—'
    score = float(score)
    if score >= 90:
        return 'A'
    elif score >= 80:
        return 'B'
    elif score >= 70:
        return 'C'
    elif score >= 60:
        return 'D'
    return 'F'


@register.filter
def grade_color(score):
    if score is None:
        return 'secondary'
    score = float(score)
    if score >= 80:
        return 'success'
    elif score >= 60:
        return 'warning'
    return 'danger'
