from __future__ import absolute_import, unicode_literals

from django import template
from django_wiki_forms.mdx.input import InputPreprocessor
from django.template.defaultfilters import stringfilter
from django.utils.safestring import mark_safe
from django.contrib.auth.models import User
import pprint
import uuid

import pygments


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
def codehilite(value, arg):
    try:
        lexer = pygments.lexers.get_lexer_for_mimetype(arg)
    except ValueError:
        try:
            lexer = pygments.lexers.guess_lexer(value)
        except ValueError:
            lexer = pygments.lexers.TextLexer()

    return mark_safe(pygments.highlight(value, lexer, pygments.formatters.HtmlFormatter(cssclass="codehilite")))


@register.simple_tag
def get_user_from_userid(user_id):
    try:
        u = User.objects.get(id=user_id)
        return "{} {}".format(u.first_name, u.last_name)
    except User.DoesNotExist:
        return 'Unknown'
