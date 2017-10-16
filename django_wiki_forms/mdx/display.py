# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

import re
import markdown
from django.template.loader import render_to_string
import pyparsing as pp
from .. import utils
# from django.utils.translation import ugettext as _

MACRO_RE = re.compile(
    r'(?P<prefix>.*?)\[\s*display(-(?P<variant>\w(\w|-|_)*))?(\s+(?P<kwargs>.*?))\s*\](?P<suffix>.*)$',
    re.IGNORECASE
)


class DisplayExtension(markdown.Extension):

    """ Forms plugin markdown extension for django-wiki. """

    def extendMarkdown(self, md, md_globals):
        md.preprocessors.add('dw-show', DisplayPreprocessor(md), '>html_block')



fident = pp.Word(pp.alphas, pp.alphas+pp.nums+"_")
fvar = pp.Optional(pp.Word(pp.nums) + pp.Literal(":").suppress(), default="this") + fident
fmethod = (fident +
           pp.Group(pp.Optional(
               pp.Literal("(").suppress() +
               pp.delimitedList(pp.Word(pp.alphas+pp.nums+"_")) +
               pp.Literal(")").suppress()))
           ).setParseAction(lambda strg, loc, st: dict(
               name=st[0],
               args=list(st[1])))
ffield = (fvar +
          pp.Group(pp.Optional(
              pp.Literal(".").suppress() +
              pp.delimitedList(fmethod, delim="."), default={'name': "self", 'args': list()}))
          ).setParseAction(lambda strg, loc, st: dict(
              article_pk=-1 if st[0] == "this" else int(st[0]),
              name=st[1],
              methods=list(st[2])))

ffields = pp.ZeroOrMore(ffield) + pp.StringEnd()


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

        fields = ffields.parseString(m.group('kwargs')).asList() if m.group('kwargs') else list()

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
