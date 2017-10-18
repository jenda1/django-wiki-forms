from __future__ import absolute_import, unicode_literals

from django import template
from django_wiki_forms.mdx.input import InputPreprocessor
from django.template.defaultfilters import stringfilter
from django.utils.safestring import mark_safe
import pprint
import uuid

from pygments import highlight
from pygments.lexers import guess_lexer, TextLexer
from pygments.formatters import HtmlFormatter


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

@register.filter
@stringfilter
def codehilite(value):
    try:
        lexer = guess_lexer(value)
    except ValueError:
        lexer = TextLexer()

    formatter = HtmlFormatter(cssclass="codehilite")
    return mark_safe(highlight(value, lexer, formatter))
