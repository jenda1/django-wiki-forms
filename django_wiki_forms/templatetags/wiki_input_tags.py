from __future__ import absolute_import, unicode_literals

from django import template
from django_wiki_forms.mdx.input import InputPreprocessor

register = template.Library()


@register.assignment_tag
def allowed_input_types():
    for m in dir(InputPreprocessor):
        try:
            yield getattr(InputPreprocessor, m).meta
        except AttributeError:
            pass
