from django import template
register = template.Library()

@register.filter
def split(value, arg):
    return value.split(arg)

@register.filter
def get_item(dictionary, key):
    if dictionary is None:
        return None
    return dictionary.get(key)

@register.filter
def get_id(obj):
    if obj is None:
        return ''
    return obj.id