from __future__ import absolute_import, unicode_literals

from django.db.models import signals
from django.db import models
from wiki import models as wiki_models
from wiki.decorators import disable_signal_for_loaddata
from wiki.core.markdown import ArticleMarkdown
from django.utils.translation import ugettext_lazy as _
from wiki.models import Article
from wiki.core import compat
from django.db import transaction

import logging
from . import utils
import ipdb  # NOQA


logger = logging.getLogger(__name__)


class Input(models.Model):
    article = models.ForeignKey(Article, on_delete=models.CASCADE, verbose_name=_('article'))
    owner = models.ForeignKey(
        compat.USER_MODEL, verbose_name=_('owner'),
        related_name='owned_inputs',
        help_text=_('The author of the input. The owner always has both read access.'),
        on_delete=models.CASCADE)

    created = models.DateTimeField(auto_now_add=True, verbose_name=_('created'),)
    created_by = models.ForeignKey(compat.USER_MODEL, null=True, related_name='created_inputs', on_delete=models.SET_NULL)

    name = models.CharField(max_length=28)
    val = models.TextField(blank=True, null=True)

    newer = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        verbose_name = _('Input')
        verbose_name_plural = _('Inputs')
        get_latest_by = 'created'
        unique_together = ('article', 'owner', 'name', 'newer')

    def __str__(self):
        return _('{}{}:{}{}: {}').format(
            "" if self.newer is None else "#",
            self.article.pk,
            self.name,
            "" if self.owner is None else "@{}".format(self.owner),
            utils.trims(self.val))


class InputDefinition(models.Model):
    article = models.ForeignKey(wiki_models.Article, on_delete=models.CASCADE)
    name = models.CharField(max_length=28)
    expr = models.TextField()

    per_user = models.BooleanField()

    class Meta:
        unique_together = ('article', 'name')

    def __str__(self):
        return '{}:{}'.format(self.article, self.name)


class InputDefValue(models.Model):
    idef = models.ForeignKey(InputDefinition, related_name='values', on_delete=models.CASCADE)

    owner = models.ForeignKey(
        compat.USER_MODEL, verbose_name=_('owner'),
        blank=True, null=True,
        help_text=_('The author of the input. The owner always has both read access.'),
        on_delete=models.CASCADE)

    created = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('created'),
    )

    val = models.TextField(blank=True, null=True)

    def __str__(self):
        return _('{}:{}{}: {}').format(
            self.idef.article.pk,
            self.idef.name,
            "" if self.owner is None else "@{}".format(self.owner),
            utils.trims(self.val))

    class Meta:
        unique_together = ('idef', 'owner')
        verbose_name = _('Calculated Input')
        verbose_name_plural = _('Calculated Inputs')
        get_latest_by = 'created'



class InputDependency(models.Model):
    idef = models.ForeignKey(InputDefinition, related_name='dependencies', on_delete=models.CASCADE)

    article = models.ForeignKey(wiki_models.Article, on_delete=models.CASCADE)
    name = models.CharField(max_length=28)

    per_user = models.BooleanField()

    def __str__(self):
        return '{}:{}: {}:{}{}'.format(
            self.idef.article.pk,
            self.idef.name,
            self.article.pk,
            self.name)


class InputDocker(models.Model):
    value = models.OneToOneField(InputDefValue)

    # FIXME: add image name validators!!!!
    image = models.CharField(max_length=255)
    scenario = models.CharField(max_length=255)
    args = models.TextField(blank=True, null=True)

    container_id = models.CharField(max_length=64, unique=True, blank=True, null=True)

    def __str__(self):
        return self.container_id[:12] if self.container_id else "$({})".format(self.value)



@disable_signal_for_loaddata
def post_article_revision_save(**kwargs):
    arev = kwargs['instance']

    md = ArticleMarkdown(arev.article, preview=True)
    md.convert(arev.content)

    with transaction.atomic():
        old = InputDefinition.objects.filter(article=arev.article).exclude(name__in=md.defs)
        if old.exists():
            logger.info("delete definition(s) {}".format([str(o) for o in old]))
            old.delete()

        for idef in [utils.update_inputdef(arev.article, name, val.getExprStack()) for name, val in md.defs.items()]:
            utils.expand_inputdef(idef)


signals.post_save.connect(post_article_revision_save, wiki_models.ArticleRevision)
