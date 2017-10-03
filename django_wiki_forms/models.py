from __future__ import absolute_import, unicode_literals

from django.db.models import signals
from django.db import models
from wiki import models as wiki_models
from wiki.decorators import disable_signal_for_loaddata
from wiki.core.markdown import ArticleMarkdown
from django.utils.translation import ugettext_lazy as _
from wiki.models.pluginbase import ArticlePlugin
from wiki.core import compat
from wiki.core.compat import get_user_model

import json
import logging

from . import tasks

logger = logging.getLogger(__name__)



User = get_user_model()


class Input(ArticlePlugin):
    owner = models.ForeignKey(
        compat.USER_MODEL, verbose_name=_('owner'),
        null=True, related_name='owned_inputs',
        help_text=_('The author of the input. The owner always has both read access.'),
        on_delete=models.SET_NULL)

    key = models.CharField(max_length=28)
    val = models.TextField()

    def can_write(self, user):
        return user.pk == self.owner.pk  # FIXME: !!!

    def can_delete(self, user):
        return False

    class Meta:
        verbose_name = _('Input')
        verbose_name_plural = _('Inputs')
        get_latest_by = 'created'

    def __str__(self):
        return _('{}: {}').format(self.key, (self.val[:75] + '..') if len(self.val) > 75 else self.val)


class InputDefinition(models.Model):
    article = models.ForeignKey(wiki_models.Article, on_delete=models.CASCADE)
    key = models.CharField(max_length=28)

    expr = models.TextField()

    class Meta:
        unique_together = ('article', 'key')

    def __str__(self):
        return '{}:{}'.format(self.article, self.key)


class InputDependency(models.Model):
    definition = models.ForeignKey(InputDefinition, on_delete=models.CASCADE)

    article = models.ForeignKey(wiki_models.Article, on_delete=models.CASCADE)
    key = models.CharField(max_length=28)
    per_owner = models.BooleanField()


    def __str__(self):
        return '{}:{} <- {}:{}{}'.format(
            self.definition.article,
            self.definition.key,
            self.article,
            self.key,
            "" if self.per_owner else "[]")


@disable_signal_for_loaddata
def post_article_revision_save(**kwargs):
    arev = kwargs['instance']

    md = ArticleMarkdown(arev.article, preview=True)
    md.convert(arev.content)

    old = InputDefinition.objects.filter(article=arev.article).exclude(key__in=md.defs)
    if old.exists():
        logger.warning("delete definition(s) {}: {}".format(arev.article, [str(o) for o in old]))
        old.delete()

    for key, val in md.defs.items():
        expr = val.getExprStack()
        expr_json = json.dumps(expr)

        idef = InputDefinition.objects.filter(article=arev.article, key=key).last()
        if idef:
            if idef.expr == expr_json:
                continue
            else:
                idef.delete()

        idef = InputDefinition.objects.create(article=arev.article, key=key, expr=expr_json)
        logger.warning("create/update definition {}".format(idef))

        for op, val in expr:
            if op in ['var', 'vara']:
                article = arev.article if val[0] == -1 else wiki_models.Article.objects.get(pk=val[0])

                InputDependency.objects.create(
                    definition=idef,
                    article=article,
                    key=val[1],
                    per_owner=True if op == 'var' else False)

        for i in Input.objects.filter(article=arev.article, key=key):
            tasks.evaluate.delay(idef.pk, i.owner.pk)



@disable_signal_for_loaddata
def post_input_save(**kwargs):
    i = kwargs['instance']

    for idef in InputDependency.objects.filter(article=i.article, key=i.key):
        if idef.per_owner:
            tasks.evaluate.delay(idef.pk, i.owner.pk)
        else:
            for uid in Input.objects.filter(article=idef.article, key=idef.key).values('owner').distinct():
                tasks.evaluate.delay(idef.pk, uid)


signals.post_save.connect(post_article_revision_save, wiki_models.ArticleRevision)
signals.post_save.connect(post_input_save, Input)
