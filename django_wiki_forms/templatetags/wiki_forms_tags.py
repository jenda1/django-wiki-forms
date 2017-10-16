from __future__ import absolute_import, unicode_literals

from django import template
from django_wiki_forms.mdx.input import InputPreprocessor
import pprint
import uuid

register = template.Library()

@register.filter
def get_data_type(obj):
    return type(obj).__name__

@register.filter
def ppprint(obj):
    return pprint.PrettyPrinter(indent=4).pprint(obj)

@register.simple_tag
def get_uuid():
    return str(uuid.uuid4())


@register.assignment_tag
def allowed_input_types():
    for m in dir(InputPreprocessor):
        try:
            yield getattr(InputPreprocessor, m).meta
        except AttributeError:
            pass
