# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

import re
import itertools
import markdown
from django.template.loader import render_to_string
# from django.utils.translation import ugettext as _
from six import string_types
from .. import settings

# See:
# http://stackoverflow.com/questions/430759/regex-for-managing-escaped-characters-for-items-like-string-literals
re_sq_short = r"'([^'\\]*(?:\\.[^'\\]*)*)'"

MACRO_RE = re.compile(
    r'(?P<prefix>.*?)\[\s*input(-(?P<variant>\w+))?(?P<kwargs>.*?)\](?P<suffix>.*)$',
    re.IGNORECASE
)

KWARG_RE = re.compile(
    r'\s*(?P<arg>[-a-z0-9_./]+)(:(?P<value>([^\'\s]+|%s)))?' %
    re_sq_short,
    re.IGNORECASE)


class InputExtension(markdown.Extension):
    """ Input plugin markdown extension for django-wiki. """

    def extendMarkdown(self, md, md_globals):
        """ Insert InputPreprocessor before ReferencePreprocessor. """
        md.preprocessors.add('dw-input', InputPreprocessor(md), '>html_block')



class InputPreprocessor(markdown.preprocessors.Preprocessor):

    """django-wiki input preprocessor - parse text for [input(-variant)?
    (args*)] references. """

    def __init__(self, *args, **kwargs):
        super(InputPreprocessor, self).__init__(*args, **kwargs)
        self.input_names = set()
        self.input_fields = list()

        if self.markdown:
            self.markdown.input_fields = self.input_fields


    def process_args(self, args, **kwargs):
        for m in KWARG_RE.finditer(args):
            arg = m.group('arg')
            value = m.group('value')

            if value is None:
                kwargs[arg] = None
            elif isinstance(value, string_types):
                # If value is enclosed with ': Remove and
                # remove escape sequences
                if value.startswith("'") and len(value) > 2:
                    value = value[1:-1]
                    value = value.replace("\\\\", "¤KEEPME¤")
                    value = value.replace("\\", "")
                    value = value.replace("¤KEEPME¤", "\\")
                kwargs[arg] = value

        return kwargs


    def process_line(self, line):
        m = MACRO_RE.match(line)
        if not m:
            return line

        variant = m.group('variant')
        args = self.process_args(m.group('kwargs'))
        if variant not in settings.INPUTS:
            variant = settings.INPUTS[0] if len(settings.INPUTS) else "text"

        for k in args:
            if args[k] is None:
                name = re.sub('[^-A-Za-z0-9_.]+', '', k)
                break
        else:
            for i in itertools.count():
                name = "input_{}".format(i)
                if i and name not in self.input_names:
                    break

        self.input_names.add(name)
        self.input_fields.append({'name': name})

        html = render_to_string(
            "wiki/plugins/forms/input-{}.html".format(variant),
            context=dict(
                preview=self.markdown.preview,
                variant=variant,
                args=args,
                input_id=len(self.input_fields)
            ),
        )

        out = self.process_line(m.group('prefix'))
        out += self.markdown.htmlStash.store(html, safe=True)
        out += self.process_line(m.group('suffix'))

        return out


    def run(self, lines):
        return [self.process_line(l) for l in lines]


# cmd_input.meta = dict(
#     short_description=_('Input Field'),
#     help_text=_('Input text field.'),
#     example_code='[input] or [input-type name]',
#     args={
#         'name': _('name of the input field.'),
#         'type': _('type of the field: {}').format(", ".join(settings.INPUTS)),
#
#        }
#    )


#                variant=variant,
#            )
#        )
#
#    cmd_display.meta = dict(
#        short_description=_('Get Field'),
#        help_text=_('Get a field value.'),
#        example_code='[get name] or [get:type path/name] ',
#        args={
#            'type': _('<i>all</i> to get all variants of the field'),
#            '[path/]name': _('name of the input to get'),
#        }
#    )
#
#
#    # try:
#    #     article = models.URLPath.get_by_path(path).article
#    # except models.URLPath.DoesNotExist:
#    #     continue
