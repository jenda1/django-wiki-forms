# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

import re
import markdown

from .. import utils
#
DEFFN_RE = re.compile(
    r'(?P<prefix>.*?)\[\s*def\s+(?P<target>\w+?)\((?P<args>.*)\)(?P<inline>\s*:\s*(?P<expr>.+?))\s*\](?P<suffix>.*)$',
    re.IGNORECASE
)

LETVAR_RE = re.compile(
    r'(?P<prefix>.*?)\[\s*let\s+(?P<target>\w+?)\s*\](?P<suffix>.*)$',
    re.IGNORECASE
)

LETVAR_INLINE_RE = re.compile(
    r'(?P<prefix>.*?)\[\s*let\s+(?P<target>\w+?)\s*=\s*(?P<expr>.+?)\s*\](?P<suffix>.*)$',
    re.IGNORECASE
)


LET_END_RE = re.compile(
    r'(?P<prefix>.*?)\[\s*endlet\s*\](?P<suffix>.*)$',
    re.IGNORECASE
)


class DefExtension(markdown.Extension):

    """ Defs plugin markdown extension for django-wiki. """

    def extendMarkdown(self, md, md_globals):
        md.preprocessors.add('dw-def', DefPreprocessor(md), '<dw-input')


class DefPreprocessor(markdown.preprocessors.Preprocessor):

    def __init__(self, *args, **kwargs):
        super(DefPreprocessor, self).__init__(*args, **kwargs)
        self.in_let = None

        if self.markdown:
            self.markdown.defs = dict()


    def process_line(self, line):
        if self.in_let:
            m = LET_END_RE.match(line)
            if m:
                self.in_let.append(m.group('prefix'))
                self.markdown.defs[self.in_let_target] = utils.DefVarExpr(self.markdown.article, self.in_let)
                self.in_let = None

                return self.process_line(m.group('suffix'))

            else:
                self.in_let.append(line+"\n")
                return ""

        m = LETVAR_INLINE_RE.match(line)
        if m:
            self.markdown.defs[m.group('target')] = utils.DefVarExpr(self.markdown.article, m.group('expr'))

            return m.group('prefix') + self.process_line(m.group('suffix'))

        m = LETVAR_RE.match(line)
        if m:
            self.in_let = utils.DefVarStr()
            self.in_let_target = m.group('target')

            return m.group('prefix') + self.process_line(m.group('suffix'))

        return line

        return m.group('prefix') + self.process_line(m.group('suffix'))


    def run(self, lines):
        return [self.process_line(l) for l in lines]
