from __future__ import absolute_import, unicode_literals

import operator
import json
from pyparsing import Literal, Word, Combine, Group, Optional, ZeroOrMore, Forward, nums, alphas, delimitedList, QuotedString
from django.core.exceptions import PermissionDenied
from . import models

import logging
logger = logging.getLogger(__name__)

# FIELD_RE = re.compile(
#    r'\s*((?P<article>[-a-z0-9_./]+)/)?(?P<field>\w+?)\s*$'
# )

# def parse_input(article, val):
#    m = FIELD_RE.match(val)
#    if not m:
#        return None
#
#    path = article.get_absolute_url()
#    if m.group('article'):
#        path = os.path.normpath(os.path.join(path, m.group('article')))
#
#    return path.strip('/') + '/', m.group('field')



opn = {"+": operator.add,
       "-": operator.sub,
       "*": operator.mul,
       "/": operator.truediv,
       }


class DefEvaluate(object):
    def __init__(self, idef, owner):
        self.idef = idef
        self.owner = owner
        self.data = dict()
        self.dataa = dict()
        self.ts = idef.article.current_revision.created

        expr = json.loads(idef.expr)
        if self._initData(expr) is None:
            return

        i = models.Input.objects.filter(article=self.idef.article, name=self.idef.name, owner=owner).last()
        if i and self.ts <= i.created:
            # no update is needed, i is up-to-date
            return

        val = self._evaluateStack(expr)
        val_json = json.dumps(val)

        if i and i.val == val_json:
            # no update is needed, new value is the same as the previous one
            return

        logger.warning("update {}".format(self.idef))
        models.Input.objects.create(article=self.idef.article, name=self.idef.name, owner=owner, val=val_json, created=self.ts)


    def _initData(self, s):
        for op, val in s:
            if op == 'var':
                v = models.Input.objects.filter(
                    article=self.idef.article if val[0] == -1 else val[0],
                    name=val[1], owner=self.owner).last()
                if not v:
                    return

                self.ts = self.ts if self.ts and self.ts >= v.created else v.created
                self.data[str(val)] = json.loads(v.val)

            elif op == 'vara':
                out = dict()

                for v in models.Input.objects.filter(
                        article=self.idef.article if val[0] == -1 else val[0],
                        name=val[1]):
                    out[v.owner] = json.loads(v.val)
                    self.ts = self.ts if self.ts and self.ts >= v.created else v.created

                self.dataa[str(val)] = out

        return True


    def _evaluateStack(self, s):
        op, val = s.pop()

        if op == 'number':
            return float(val)

        elif op == 'string':
            return str(val)

        elif op == 'var':
            return self.data[str(val)]

        elif op == 'vara':
            return self.dataa[str(val)]

        elif op == 'op':
            op2 = self._evaluateStack(s)
            op1 = self._evaluateStack(s)

            return opn[val](op1, op2)

        elif op == 'fn':
            n = self._evaluateStack(s)
            assert n[0] == '#'

            args = list()
            for i in range(n):
                args.insert(self._evaluateStack(s), 0)

            return len(args)

        else:
            raise Exception



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
            name = arr[1] if len(arr) == 2 else arr[0]

            self.exprStack.append((op, (article_pk, name)))

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



def get_allowed_channels(request, channels):
    if not request.user.is_authenticated():
        raise PermissionDenied('Not allowed to subscribe nor to publish on the Websocket!')
