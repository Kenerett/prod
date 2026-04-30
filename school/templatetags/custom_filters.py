# school/templatetags/custom_filters.py
import logging
from django import template

logger = logging.getLogger(__name__)
register = template.Library()

@register.filter
def get_item(dictionary, key):
    """
    Safely retrieves an item from a dictionary-like object.
    ... (остальной docstring) ...
    """
    try:
        # Check if the object is a dictionary and has the 'get' method
        if hasattr(dictionary, 'get') and callable(getattr(dictionary, 'get')):
            return dictionary.get(key, '')
        # If it's a list/tuple and key is an integer, try indexing
        elif isinstance(dictionary, (list, tuple)) and isinstance(key, int):
            try:
                return dictionary[key]
            except IndexError:
                return ''
        # If it's an object with attributes, try getattr
        elif hasattr(dictionary, str(key)):
            return getattr(dictionary, str(key))
        else:
            # If it's not a dict-like object or list/tuple, log a warning if it's not None/empty
            if dictionary is not None and dictionary != '':
                 logger.debug(
                    f"get_item: Object of type {type(dictionary)} passed, "
                    f"does not support 'get', '[]', or attribute access for key '{key}'. "
                    f"Returning empty string. Object repr: {repr(dictionary)}"
                )
            return ''
    except (TypeError, AttributeError) as e:
        # Catch any other unexpected errors during access
        logger.warning(
            f"get_item: Unexpected error accessing key '{key}' "
            f"on object of type {type(dictionary)}. Error: {e}. "
            f"Returning empty string. Object repr: {repr(dictionary)}"
        )
        return ''

# --- Остальные фильтры ---
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
    """
    Фильтр для получения значения из словаря по ключу.
    Использование в шаблоне: {{ my_dict|lookup:my_key }}
    """
    if dictionary is None:
        return None
    return dictionary.get(key, [])

@register.filter  
def dict_key(dictionary, key):
    """
    Альтернативный фильтр для доступа к ключам словаря.
    """
    if dictionary is None:
        return None
    return dictionary.get(key)

@register.filter
def range_filter(value):
    """
    Создает диапазон от 0 до value-1.
    Использование: {% for i in 5|range_filter %}
    """
    return range(value)


@register.filter(name='get_item')
def get_item(dictionary, key):
    return dictionary.get(key)

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

















