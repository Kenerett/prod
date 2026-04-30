# school/templatetags/grade_extras.py
from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Получает значение из словаря по ключу."""
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None

@register.filter
def get_attr(obj, attr_name):
    """Получает атрибут объекта по имени."""
    return getattr(obj, attr_name, '')

@register.filter
def get_sg_score(grade_obj, sg_key):
    """
    Получает оценку SG по ключу из объекта Grade.
    """
    if grade_obj and hasattr(grade_obj, 'get_sg_scores'):
        sg_scores = grade_obj.get_sg_scores()
        if isinstance(sg_scores, dict):
            return sg_scores.get(sg_key, 0)
    return 0

@register.filter
def mul(value, arg):
    """Умножает value на arg."""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0
    



@register.filter
def sum_attribute(objects_list, attribute_name):
    """
    Суммирует значения атрибута для списка объектов.
    objects_list: список объектов Django
    attribute_name: имя атрибута (строка)
    """
    total = 0
    for obj in objects_list:
        try:
            value = getattr(obj, attribute_name, 0)
            total += value if isinstance(value, (int, float)) else 0
        except (TypeError, ValueError):
            pass # Игнорируем ошибки
    return total