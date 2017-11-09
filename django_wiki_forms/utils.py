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
from django.contrib.auth.models import User
import itertools

import logging
import ipdb  # NOQA

logger = logging.getLogger(__name__)

opn = {"+": operator.add,
       "-": operator.sub,
       "*": operator.mul,
       "/": operator.truediv,
       }

fident = pp.Word(pp.alphas, pp.alphas+pp.nums+"_")
fnumber = pp.Combine(pp.Word(pp.nums) + pp.Optional("." + pp.Optional(pp.Word(pp.nums))))

class Value(object):
    def __init__(self, data):
        self.data = data

class ValueFloat(Value):
    def getVal(self):
        return float(self.data)

class ValueInt(Value):
    def getVal(self):
        return int(self.data)

class ValueStr(Value):
    def getVal(self):
        return str(self.data)

class ValueInput(Value):
    def __init__(self, article_pk, name, owner, idefs):
        self.article_pk = article_pk
        self.name = name
        self.owner = owner
        self.idefs = idefs

        try:
            self.idef = models.InputDefinition.objects.get(article__pk=article_pk, name=name)
        except models.InputDefinition.DoesNotExist:
            self.idef = None

        return super(ValueInput, self).__init__(None)

    def getVal(self):
        if self.idef:
            return evaluate_idef(self.idef, self.owner, self.idefs)
        else:
            try:
                i = models.Input.objects.get(article__pk=self.article_pk, name=self.name, newer=None, owner=self.owner)
                return json.loads(i.val)
            except models.Input.DoesNotExist:
                return None


class ValueInputAll(Value):
    def getVal(self):
        out = dict()
        if self.data.idef:
            for u in User.objects.all():
                v = evaluate_idef(self.data.idef, u, self.data.idefs)
                if v:
                    out[u.pk] = v

        else:
            for i in models.Input.objects.filter(article__pk=self.data.article_pk, name=self.data.name, newer=None).all():
                out[i.owner.pk] = json.loads(i.val)

        return out


class ValueDocker(Value):
    def __init__(self, idef, owner, image, scenario, args):
        self.docker, created = models.InputDocker.objects.get_or_create(
            idef=idef, owner=owner if idef.per_user else None, image=image, scenario=scenario, args=json.dumps(args) if args else None)
        if created:
            tasks.run_docker.delay(self.docker.pk)
        return super(ValueDocker, self).__init__(None)

    def getVal(self):
        return "" if self.docker.val is None else json.loads(self.docker.val)


def evaluate_deps(expr):  # NOQA
    print(expr)
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

        if val in ['all', 'sum']:
            assert n == 1

            if type(args[0]) is list:
                return [(args[0][0][0], args[0][0][1], False)]
            else:
                return args[0]

        elif val == 'len':
            assert n == 1
            return args[0]

        elif val == 'ifdef':
            assert n == 3
            return list(itertools.chain.from_iterable(args))

        elif val == 'docker':
            assert n >= 1
            return list(itertools.chain.from_iterable(args))

        else:
            assert False

    elif op == 'op':
        op2 = evaluate_deps(expr)
        op1 = evaluate_deps(expr)
        return op1 + op2

    assert False


def evaluate_expr(expr, owner, idefs):  # NOQA
    op, val = expr.pop()

    if op == 'float':
        return ValueFloat(val)
    elif op == 'int':
        return ValueInt(val)
    elif op == 'str':
        return ValueStr(val)
    elif op == 'field':
        return ValueInput(val['article_pk'], val['name'], owner, idefs)

    elif op == 'fn':
        n = expr.pop()
        args = [evaluate_expr(expr, owner, idefs) for i in range(n)]

        if val == 'all':
            assert n == 1
            assert type(args[0]) == ValueInput
            return ValueInputAll(args[0])

        elif val == 'len':
            assert n == 1
            return Value('int', len(args[0].getVal()))

        elif val == 'ifdef':
            assert n == 3

            if args[2] is None or args[2].getVal() is None:
                return args[0]
            else:
                return args[1]

        elif val == 'docker':
            assert n >= 2
            return ValueDocker(idefs[0], owner, args[-1].getVal(), args[-2].getVal(), [x.getVal() for x in reversed(args[:-2])])

        assert False

    elif op == 'op':
        op2 = evaluate_expr(expr, owner, idefs)
        op1 = evaluate_expr(expr, owner, idefs)

        val1 = op1.getVal() if op1 else None
        val2 = op2.getVal() if op2 else None

        if val1 is None or val2 is None:
            return None

        try:
            out = opn[val](val1, val2)
        except Exception as e:
            logger.warning("evaluation failed {} {} {} : {}".format(val1, val, val2, e))
            return None

        if type(out) is int:
            return ValueInt(out)
        elif type(out) is float:
            return ValueFloat(out)
        else:
            return ValueStr(out)


def notify(article, name, owner):
    msg = RedisMessage("{}:{}:{}".format(article.pk, name, owner.pk if owner else ""))
    redis_publisher = RedisPublisher(facility="django-wiki-forms", broadcast=True)
    redis_publisher.publish_message(msg)



def evaluate_idef(idef, owner, idefs=list()):  # NOQA
    assert idef not in idefs
    try:
        return json.loads(idef.values.get(owner=owner if idef.per_user else None).val)
    except models.InputDefValue.DoesNotExist:
        pass

    expr = json.loads(idef.expr)
    val = evaluate_expr(expr, owner if idef.per_user else None, [idef] + idefs)
    if not val:
        return

    val = val.getVal()
    if val:
        # check if another thread create the value already
        obj, created = models.InputDefValue.objects.update_or_create(
            idef=idef, owner=owner if idef.per_user else None,
            defaults={'val': json.dumps(val)})

        if created:
            notify(idef.article, idef.name, owner if idef.per_user else None)

        return val


def get_input_val(article, name, owner):
    try:
        idef = models.InputDefinition.objects.get(article=article, name=name)

        try:
            idv = idef.values.get(owner=owner if idef.per_user else None)
            return json.loads(idv.val) if idv.val else None
        except models.InputDefValue.DoesNotExist:
            tasks.evaluate_idef.delay(idef.pk, owner.pk)
    except models.InputDefinition.DoesNotExist:

        try:
            i = models.Input.objects.get(article=article, name=name, newer=None, owner=owner)
            return json.loads(i.val)

        except models.Input.DoesNotExist:
            return None


class DefVarStr(object):
    def __init__(self, article, expr):
        self.article = article
        self.expr = expr

    def getExprStack(self):
        return [('str', self.expr)]

    def __str__(self):
        return str(self.getExprStack())


class DefVarExpr(object):
    def __init__(self, article, expr):
        self.article = article
        self._parse(expr)

    def _push(self, strg, loc, args):
        self.exprStack.append((args.getName(), args[0]))

    def _pushLen(self, strg, loc, args):
        self.exprStack.append(len([x for x in args[0] if not isinstance(x, pp.ParseResults)]))

    def _parse(self, expr):
        self.exprStack = []

        parser = pp.Forward()
        ffn = (fident + pp.Literal('(').suppress() +
               pp.Group(pp.Optional(pp.delimitedList(parser))).setParseAction(self._pushLen) +
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


def get_allowed_channels(request, channels):
    if not request.user.is_authenticated():
        raise PermissionDenied('Not allowed to subscribe nor to publish on the Websocket!')


def update_input(article, name, owner, val=None, ts=None):
    if ts is None:
        ts = timezone.now()

    with transaction.atomic():
        tmp = models.Input.objects.filter(article=article, name=name, owner=owner, newer=None)

        if len(tmp) == 1:
            curr = tmp[0]
            if tmp[0].val == val:
                return
        else:
            assert len(tmp) == 0

        logger.debug("update Input {} -> '{}'".format(curr, trims(val)))

        new = models.Input.objects.create(article=article, name=name, owner=owner, val=val, created=ts)
        if curr:
            curr.newer = new
            curr.save()

    # delete obsolete results
    for dep in models.InputDependency.objects.filter(article=article, name=name):
        dep.idef.values.filter(owner=owner if dep.idef.per_user else None).delete()

    notify(article, name, owner)



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
    per_user = False
    for a, n, p in deps:
        per_user |= p


    with transaction.atomic():
        idef = models.InputDefinition.objects.create(article=article, name=name, expr=expr_json, per_user=per_user)

        for article_pk, name, per_user in deps:
            models.InputDependency.objects.create(
                idef=idef,
                article=wiki_models.Article.objects.get(pk=article_pk),
                name=name,
                per_user=per_user)


def fix_idef():
    models.InputDefinition.objects.all().delete()

    for article in wiki_models.Article.objects.all():
        md = ArticleMarkdown(article, preview=True)
        md.convert(article.current_revision.content)

        for name, val in md.defs.items():
            update_inputdef(article, name, val.getExprStack())


def fix_number_val():
    for i in models.Input.objects.all():
        try:
            old = i.val
            new = json.dumps(int(json.loads(i.val)))

            if old != new:
                logger.warn("{}: change to number {} -> {}".format(i, old, new))
                i.val = new
                i.save()
        except:
            pass


def fix_files(article_pk, name):
    for i in models.Input.objects.filter(article__pk=article_pk, name=name, newer=None):
        v = json.loads(i.val)
        if type(v) == str:
            logger.warn("{}: convert to java file(s)".format(i))
            v = [dict(name="Unknown.java", size=len(v), type='text/x-java', content=v)]
            i.val = json.dumps(v)
            i.save()



def fix_input_newer():
    for i in models.Input.objects.all():
        n = models.Input.objects.filter(article=i.article, owner=i.owner, name=i.name, created__gt=i.created).order_by('created').first()
        if i.newer != n:
            logger.warn("{}: set newer to {}".format(i, n))
            i.newer = n
            i.save()


def trims(s):
    if s:
        s = str(s)
        return (s[:25] + '..') if len(s) > 25 else s
