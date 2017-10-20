from __future__ import absolute_import, unicode_literals

import operator
import json
import pyparsing as pp
from django.core.exceptions import PermissionDenied
from django.db import transaction
from wiki import models as wiki_models
from wiki.core.markdown import ArticleMarkdown
from . import models
from . import tasks
from django.utils import timezone
from ws4redis.publisher import RedisPublisher
from ws4redis.redis_store import RedisMessage

import logging
import ipdb  # NOQA

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

fident = pp.Word(pp.alphas, pp.alphas+pp.nums+"_")
fnumber = pp.Combine(pp.Word(pp.nums) + pp.Optional("." + pp.Optional(pp.Word(pp.nums))))

# fmethod = (fident +
#           pp.Group(pp.Optional(
#               pp.Literal("(").suppress() +
#               pp.delimitedList(pp.Word(pp.alphas+pp.nums+"_")) +
#               pp.Literal(")").suppress()))
#           ).setParseAction(lambda strg, loc, st: dict(
#               name=st[0],
#               args=list(st[1])))
# ffield = (fvar +
#          pp.Group(pp.Optional(
#              pp.Literal(".").suppress() +
#              pp.delimitedList(fmethod, delim="."), default={'name': "self", 'args': list()}))
#          ).setParseAction(lambda strg, loc, st: dict(
#              article_pk=st[0],
#              name=st[1],
#              methods=list(st[2])))

class Value(object):
    def __init__(self, vtype, data):
        self.vtype = vtype
        self.data = data

    def getVal(self):
        if self.vtype == 'float':
            return float(self.data)
        elif self.vtype == 'int':
            return int(self.data)
        elif self.vtype == 'str':
            return str(self.data)
        elif self.vtype == 'input':
            try:
                i = models.Input.objects.get(**self.data)
                return json.loads(i.val)
            except models.Input.DoesNotExist:
                return None

        elif self.vtype == 'input_list':
            i = models.Input.objects.filter(**self.data)
            return {x.owner.pk: json.loads(x.val) for x in i.all()}


def evaluate_deps(expr):
    op, val = expr.pop()

    if op in ['float', 'int', 'str']:
        return []

    elif op == 'field':
        return [(val['article_pk'], val['name'], True)]

    elif op == 'fn':
        n = expr.pop()

        args = list()
        for i in range(n):
            args.insert(0, evaluate_deps(expr))

        if val == 'all':
            assert n == 1

            if len(args[0]):
                return [(args[0][0][0], args[0][0][1], False)]
            else:
                return args[0]

        if val == 'len':
            assert n == 1
            return args[0]

    elif op == 'op':
        op2 = evaluate_deps(expr)
        op1 = evaluate_deps(expr)
        return op1 + op2

    assert False


def evaluate_expr(expr, owner):
    op, val = expr.pop()

    if op in ['float', 'int', 'str']:
        return Value(op, val)

    elif op == 'field':
        return Value('input', dict(
            article__pk=val['article_pk'],
            name=val['name'],
            owner=owner,
            newer__isnull=True))

    elif op == 'fn':
        n = expr.pop()

        args = list()
        for i in range(n):
            args.insert(0, evaluate_expr(expr, owner))

        if val == 'all':
            assert n == 1
            assert args[0].vtype == 'input'

            return Value('input_list', dict(
                article__pk=args[0].data['article__pk'],
                name=args[0].data['name'],
                newer__isnull=True))

        elif val == 'len':
            assert n == 1
            return Value('int', len(args[0].getVal()))

        elif val == 'sum':
            out = 0

            for arg in args:
                v = arg.getVal()
                if type(v) in [int, float]:
                    out += v
                elif type(v) in [str]:
                    out += len(v)
                else:
                    logger.info("==== TYPE ===" + str(type(v)))

            return Value('int' if type(out) is int else 'float', out)

        assert False

    elif op == 'op':
        op2 = evaluate_expr(expr, owner)
        op1 = evaluate_expr(expr, owner)

        out = opn[val](op1.getVal(), op2.getVal())
        if type(out) is int:
            return Value('int', out)
        elif type(out) is float:
            return Value('float', out)
        else:
            return Value('str', out)


def evaluate_idef(idef, owner):  # NOQA
    q = models.Input.objects.filter(article=idef.article, name=idef.name, newer__isnull=True, created__gte=idef.created)
    try:
        curr = q.get(owner=owner) if idef.per_user else q.get(owner__isnull=True)
        curr_ts = curr.created
    except models.Input.DoesNotExist:
        curr = None
        curr_ts = None

    for dep in idef.inputdependency_set.all():
        q = models.Input.objects.filter(article=dep.article, name=dep.name, newer__isnull=True)

        if dep.per_user:
            try:
                ts = q.get(owner=owner).created
                if not curr_ts or ts > curr_ts:
                    curr_ts = ts
            except models.Input.DoesNotExist:
                return curr
        else:
            v = q.filter(owner__isnull=True).order_by('created').last()
            if v and (not curr_ts or v.created > curr_ts):
                curr_ts = v.created

    if curr and curr_ts <= curr.created:
        return curr

    expr = json.loads(idef.expr)
    val = evaluate_expr(expr, owner).getVal()

    if val:
        update_input(idef.article, idef.name, owner if idef.per_user else None, json.dumps(val), ts, curr)

    return val


def get_input_val(article, name, owner):
    try:
        idef = models.InputDefinition.objects.get(article=article, name=name)
    except models.InputDefinition.DoesNotExist:
        idef = None

    try:
        if idef and not idef.per_user:
            i = models.Input.objects.get(article=article, name=name, newer__isnull=True, owner__isnull=True)
        else:
            i = models.Input.objects.get(article=article, name=name, newer__isnull=True, owner=owner)

        return json.loads(i.val)

    except models.Input.DoesNotExist:
        if idef:
            tasks.evaluate_idef.delay(idef.pk, owner.pk)


# plus = Literal("+")
# minus = Literal("-")
# mult = Literal("*")
# div = Literal("/")
# dot = Literal(".").suppress()
# lpar = Literal("(").suppress()
# rpar = Literal(")").suppress()
# addop = (plus | minus).setResultsName('op')
# multop = (mult | div).setResultsName('op')



class DefFn(object):
    def __init__(self, args):
        self.args = [x.strip() for x in args.split(",")]
        self.expr = ""

    def append(self, expr):
        self.expr += expr

    def get_deps(self):
        return list()


# fvar = ((Literal(".") + OneOrMore(ident + Literal(".").suppress())) |
#        ZeroOrMore((Literal("..") | ident) + Literal(".").suppress())) + ident
#                path = v.asList()
#
#                if path[0] == '.' || path[0] == '..':
#                    path = os.path.normpath(os.path.join(curr_path, *path[:-1]))
#                else:
#                    path = os.path.join(path)

# fvar = Optional(Word(nums) + Literal(":").suppress(), default="-1") + ident
# fvara = Optional(Word(nums) + Literal(":").suppress()) + ident + Literal("[]").suppress()


class DefVarExpr(object):
    def __init__(self, article, expr):
        self.article = article
        self._parse(expr)

    def _push(self, strg, loc, args):
        self.exprStack.append((args.getName(), args[0]))

    def _pushLen(self, strg, loc, args):
        self.exprStack.append(len(args))

    def _parse(self, expr):
        self.exprStack = []

        parser = pp.Forward()
        ffn = (fident + pp.Literal('(').suppress() +
               pp.delimitedList(parser).setParseAction(self._pushLen) +
               pp.Literal(')').suppress())

        ffield = (pp.Optional(pp.Word(pp.nums) + pp.Literal(":").suppress(), default=self.article.pk) + fident
                  ).setParseAction(lambda strg, loc, st: dict(
                      article_pk=st[0],
                      name=st[1],
                  ))

        atom = ((ffn.setResultsName('fn') |
                 ffield.setResultsName('field') |
                 pp.QuotedString('"').setResultsName('str') |
                 fnumber.setResultsName('float')
                 ).setParseAction(self._push) |
                pp.Group(pp.Literal('(').suppress() + parser + pp.Literal(')').suppress()))

        term = atom + pp.ZeroOrMore((pp.Combine(pp.Literal("*") | pp.Literal("/")).setResultsName('op') + atom).setParseAction(self._push))
        parser << term + pp.ZeroOrMore((pp.Combine(pp.Literal("+") | pp.Literal("-")).setResultsName('op') + term).setParseAction(self._push))

        parser.parseString(expr, True)


    def getExprStack(self):
        return list(self.exprStack)

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

def update_input(article, name, owner, val, ts=None, curr=None):
    if ts is None:
        ts = timezone.now()

    try:
        if curr is None:
            curr = models.Input.objects.get(article=article, name=name, owner=owner, newer__isnull=True)

        if curr.val == val:
            return

        logger.debug("update Input {}:{} '{}' -> '{}'".format(article.pk, name, trims(curr.val), trims(val)))
        with transaction.atomic():
            curr.newer = models.Input.objects.create(article=article, name=name, owner=owner, val=val, created=ts)
            curr.save()

    except models.Input.DoesNotExist:
        logger.info("create Input {}:{} '{}'".format(article.pk, name, utils.trims(val)))
        models.Input.objects.create(article=article, name=name, owner=owner, val=val, created=ts)

    # run related tasks
    for dep in models.InputDependency.objects.filter(article=article, name=name):
        tasks.evaluate_idef.delay(dep.idef.pk, owner.pk if owner else None)

    # send notification to displays
    msg = RedisMessage("{}:{}:{}".format(article.pk, name, owner.pk if owner else -1))
    redis_publisher = RedisPublisher(facility="django-wiki-forms", broadcast=True)
    redis_publisher.publish_message(msg)



def update_inputdef(article, name, expr):
    expr_json = json.dumps(expr)

    try:
        curr = models.InputDefinition.objects.get(article=article, name=name)
        if curr.expr == expr_json:
            return

        logger.info("updated idef {}:{}".format(article.pk, name))
        curr.delete()
    except models.InputDefinition.DoesNotExist:
        logger.info("create idef {}:{}".format(article.pk, name))
        pass

    deps = evaluate_deps(expr)

    with transaction.atomic():
        per_user = False
        for a, n, p in deps:
            per_user |= p

        idef = models.InputDefinition.objects.create(article=article, name=name, expr=expr_json, per_user=per_user, created=article.modified)

        for article_pk, name, per_user in deps:
            models.InputDependency.objects.create(
                idef=idef,
                article=wiki_models.Article.objects.get(pk=article_pk),
                name=name,
                per_user=per_user)

    for i in models.Input.objects.filter(article=article, name=name):
        tasks.evaluate_idef.delay(idef.pk, i.owner.pk)



def fix_idef():
    models.InputDefinition.objects.all().delete()

    for article in wiki_models.Article.objects.all():
        md = ArticleMarkdown(article, preview=True)
        md.convert(article.current_revision.content)

        for name, val in md.defs.items():
            update_inputdef(article, name, val.getExprStack())


def fix_input_newer():
    for i in models.Input.objects.all():
        n = models.Input.objects.filter(article=i.article, owner=i.owner, name=i.name, created__gt=i.created).order_by('created').first()
        if i.newer != n:
            logger.warn("{}: set newer to {}".format(i, n))
            i.newer = n
            i.save()



def trims(s):
    s=str(s)
    return (s[:25] + '..') if len(s) > 25 else s
