from django import template
from .filters import get_item  # noqa: F401 — canonical implementation

register = template.Library()

# Re-export canonical get_item
register.filter('get_item', get_item)


@register.filter
def get_item_default(dictionary, key_and_default):
    """Get item from dictionary with default value: {{ dict|get_item_default:"key:default" }}"""
    try:
        key, default = key_and_default.split(':', 1)
        return dictionary.get(key.strip(), default.strip())
    except (ValueError, AttributeError):
        return dictionary.get(key_and_default)
