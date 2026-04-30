from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key, default=None):
    """Get item from dictionary with optional default value"""
    if default is not None:
        return dictionary.get(key, default)
    return dictionary.get(key)

# Или отдельный фильтр для значения по умолчанию
@register.filter
def get_item_default(dictionary, key_and_default):
    """Get item from dictionary with default value: key:default"""
    try:
        key, default = key_and_default.split(':', 1)
        return dictionary.get(key.strip(), default.strip())
    except (ValueError, AttributeError):
        return dictionary.get(key_and_default)