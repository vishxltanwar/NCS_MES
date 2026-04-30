# core/templatetags/core_tags.py
from django import template

register = template.Library()


@register.simple_tag
def user_initials(user):
    """
    Return uppercase initials for a user dict (e.g. 'VT' for 'Vishal Tanwar').
    Falls back to first 2 chars or 'OP'.
    Usage: {% user_initials user %}
    """
    if not user:
        return 'OP'

    full_name = user.get('full_name', '') if isinstance(user, dict) else getattr(user, 'full_name', '')

    if not full_name:
        return 'OP'

    parts = full_name.strip().split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    elif len(parts) == 1 and len(parts[0]) >= 2:
        return parts[0][:2].upper()
    else:
        return 'OP'
