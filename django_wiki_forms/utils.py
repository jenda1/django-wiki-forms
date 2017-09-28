from __future__ import absolute_import, unicode_literals

from pyparsing import Literal, Word, Combine, Group, Optional, ZeroOrMore, Forward, nums, alphas, delimitedList, QuotedString
import re
import os
from . import models

import logging
logger = logging.getLogger(__name__)

FIELD_RE = re.compile(
    r'\s*((?P<article>[-a-z0-9_./]+)/)?(?P<field>\w+?)\s*$'
)

def parse_input(article, val):
    m = FIELD_RE.match(val)
    if not m:
        return None

    path = article.get_absolute_url()
    if m.group('article'):
        path = os.path.normpath(os.path.join(path, m.group('article')))

    return path.strip('/') + '/', m.group('field')



class DefFn(object):
    def __init__(self, args):
        self.args = [x.strip() for x in args.split(",")]
        self.expr = ""

    def append(self, expr):
        self.expr += expr

    def get_deps(self):
        return list()


ident = Word(alphas, alphas+nums+"_")
plus = Literal("+")
minus = Literal("-")
mult = Literal("*")
div = Literal("/")
lpar = Literal("(").suppress()
rpar = Literal(")").suppress()
addop = (plus | minus).setResultsName('op')
multop = (mult | div).setResultsName('op')

fnumber = Combine(Word("+-"+nums, nums) + Optional("." + Optional(Word(nums))))

# fvar = ((Literal(".") + OneOrMore(ident + Literal(".").suppress())) |
#        ZeroOrMore((Literal("..") | ident) + Literal(".").suppress())) + ident
#                path = v.asList()
#
#                if path[0] == '.' || path[0] == '..':
#                    path = os.path.normpath(os.path.join(curr_path, *path[:-1]))
#                else:
#                    path = os.path.join(path)

fvar = Optional(Word(nums) + Literal(":").suppress()) + ident
fvara = Optional(Word(nums) + Literal(":").suppress()) + ident + Literal("[]").suppress()



class DefVarExpr(object):
    def __init__(self, expr):
        self._parse(expr)

    def _push(self, strg, loc, args):
        op = args.getName()

        if op in ['var', 'vara']:
            arr = args[0].asList()
            article_pk = arr[0] if len(arr) == 2 else -1
            key = arr[1] if len(arr) == 2 else arr[0]

            self.exprStack.append((op, (article_pk, key)))

        elif op == 'number':
            self.exprStack.append((op, float(args[0])))

        else:
            self.exprStack.append((op, str(args[0])))

    def _pushLen(self, strg, loc, args):
        self.exprStack.append(('#', len(args)))

    def _parse(self, expr):
        self.exprStack = []

        parser = Forward()
        ffn = ident + lpar + delimitedList(parser).setParseAction(self._pushLen) + rpar
        atom = ((ffn.setResultsName('fn') |
                 Group(fvara).setResultsName('vara') |
                 Group(fvar).setResultsName('var') |
                 QuotedString('"').setResultsName('string') |
                 fnumber.setResultsName('number')).setParseAction(self._push) |
                Group(lpar+parser+rpar))
        term = atom + ZeroOrMore((multop + atom).setParseAction(self._push))
        parser << term + ZeroOrMore((addop + term).setParseAction(self._push))

        parser.parseString(expr, True)


    def getExprStack(self):
        return self.exprStack

    def __str__(self):
        return str(self.getExprStack())


class DefVarStr(object):
    def __init__(self):
        self.s = ""

    def append(self, s):
        self.s += s

    def getExprStack(self):
        return [('string', self.s), ]

    def __str__(self):
        return str(self.getExprStack())


def tryEval(article, key, owner, knownDeps=dict()):
    df = models.InputDefinition.objects.filter(article=article, key=key).last()

    if not df:
        return

    knownDeps[(article.pk, key)] = True

    deps = df.inputdependency_set.all()
    # if len(deps) == 0:
    #    d = DefEvaluate(article, key, owner, json.loads(df.expr))
    #    d.update()
    #    return

    for d in deps:
        if (d.article.pk, d.key) in knownDeps:
            continue

        tryEval(d.article, d.key, owner, knownDeps)
