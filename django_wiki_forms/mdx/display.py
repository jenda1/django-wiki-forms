# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

import re
import markdown
from django.template.loader import render_to_string
# from django.utils.translation import ugettext as _
import ipdb

MACRO_RE = re.compile(
    r'(?P<prefix>.*?)\[\s*display(-(?P<variant>\w+))?\s*(?P<kwargs>.*?)\s*\](?P<suffix>.*)$',
    re.IGNORECASE
)

NAME_RE = re.compile(
    r'((?P<article>\d+):)?(?P<name>[-\w]+)',
    re.IGNORECASE)


class DisplayExtension(markdown.Extension):

    """ Forms plugin markdown extension for django-wiki. """

    def extendMarkdown(self, md, md_globals):
        md.preprocessors.add('dw-show', DisplayPreprocessor(md), '>html_block')


class DisplayPreprocessor(markdown.preprocessors.Preprocessor):

    def __init__(self, *args, **kwargs):
        super(DisplayPreprocessor, self).__init__(*args, **kwargs)
        self.display_fields = list()
        if self.markdown:
            self.markdown.display_fields = self.display_fields


    def process_line(self, line):
        m = MACRO_RE.match(line)
        if not m:
            return line

        fields = list()
        for m2 in NAME_RE.finditer(m.group('kwargs')):
            fields.append(dict(
                article_pk=m2.group('article') if m2.group('article') else self.markdown.article.pk,
                name=m2.group('name'),
            ))

        self.display_fields.append(dict(
            variant=m.group('variant'),
            fields=fields,
        ))

        html = render_to_string(
            "wiki/plugins/forms/display.html",
            context=dict(
                preview=self.markdown.preview,
                display_id=len(self.display_fields),
                fields=fields,
                variant=m.group('variant')
            )
        )

        out = m.group('prefix')
        out += self.markdown.htmlStash.store(html, safe=True)
        out += self.process_line(m.group('suffix'))

        return out


    def run(self, lines):
        return [self.process_line(l) for l in lines]

#        cmd_display.meta = dict(
#        short_description=_('Get Field'),
#        help_text=_('Get a field value.'),
#        example_code='[get name] or [get:type path/name] ',
#        args={
#            'type': _('<i>all</i> to get all variants of the field'),
#            '[path/]name': _('name of the input to get'),
#        }
#    )


# try:
#     article = models.URLPath.get_by_path(path).article
# except models.URLPath.DoesNotExist:
#     continue
