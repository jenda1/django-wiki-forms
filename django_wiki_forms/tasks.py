import json
import operator
from wiki import models as wiki_models
import models
import logging
logger = logging.getLogger(__name__)


opn = {"+": operator.add,
       "-": operator.sub,
       "*": operator.mul,
       "/": operator.truediv,
       }


class DefEvaluate(object):
    def __init__(self, article_pk, key, owner_pk, exprStack):
        self.article_pk = article_pk
        self.key = key
        self.owner = owner_pk
        self.exprStack = exprStack
        self.data = dict()
        self.dataa = dict()

        ts = None

        for op, val in self.exprStack:
            if op == 'var':
                v = models.Input.objects.filter(article__pk=article_pk if val[0] == -1 else val[0],
                                                key=val[1], owner__pk=owner_pk).last()
                if not v:
                    return

                ts = ts if ts and ts >= v.created else v.created
                self.data[str(val)] = json.loads(v.val)

            elif op == 'vara':
                out = dict()

                for v in wiki_models.Input.objects.filter(
                        article__pk=article_pk if val[0] == -1 else val[0],
                        key=val[1]):
                    out[v.owner] = json.loads(v.val)
                    ts = ts if ts and ts >= v.created else v.created

                self.dataa[str(val)] = out

        if ts is None:
            article = wiki_models.Article.objects.get(pk=article_pk)
            self.ts = article.current_revision.created

        self.ts = ts


    def update(self):
        if not hasattr(self, 'ts'):
            # no update is possible (yet)
            return

        i = models.Input.objects.filter(article__pk=self.article_pk, key=self.key, owner__pk=self.owner_pk).last()
        if i and self.ts <= i.created:
            # no update is needed, i is up-to-date
            return

        val = self._evaluateStack(list(self.exprStack))
        val_json = json.dumps(val)

        if i and i.val == val_json:
            # no update is needed, new value is the same as the previous one
            return

        logger.warning("{}: update {}".format(self.article_pk, self.key))
        models.Input.objects.create(article__pk=self.article_pk, key=self.key, owner__pk=self.owner_pk, val=val_json, created=self.ts)



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
