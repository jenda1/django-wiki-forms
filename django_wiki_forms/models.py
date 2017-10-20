from __future__ import absolute_import, unicode_literals

from django.db.models import signals
from django.db import models
from django.core.exceptions import ValidationError
from wiki import models as wiki_models
from wiki.decorators import disable_signal_for_loaddata
from wiki.core.markdown import ArticleMarkdown
from django.utils.translation import ugettext_lazy as _
from wiki.models.pluginbase import ArticlePlugin
from wiki.core import compat
from django.contrib.auth import get_user_model

import logging
from . import tasks
from . import utils
import ipdb  # NOQA


logger = logging.getLogger(__name__)

User = get_user_model()


class Input(ArticlePlugin):
    owner = models.ForeignKey(
        compat.USER_MODEL, verbose_name=_('owner'),
        null=True, related_name='owned_inputs',
        help_text=_('The author of the input. The owner always has both read access.'),
        on_delete=models.SET_NULL)

    created_by = models.ForeignKey(compat.USER_MODEL, null=True, related_name='created_inputs', on_delete=models.SET_NULL)

    name = models.CharField(max_length=28)
    val = models.TextField(blank=True, null=True)

    newer = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL)

    def can_write(self, user):
        return user.pk == self.owner.pk  # FIXME: !!!

    def can_delete(self, user):
        return False

    def validate_unique(self, exclude=None):
        if self.newer and Input.objects.exclude(id=self.id).filter(newer=self.newer).exists():
            raise ValidationError("data consistency error")

        super(Input, self).validate_unique(exclude)

    class Meta:
        verbose_name = _('Input')
        verbose_name_plural = _('Inputs')
        get_latest_by = 'created'

    def __str__(self):
        return _('{}{}:{}{}: {}').format("" if self.newer is None else "#", self.article.pk, self.name, "" if self.owner is None else "@{}".format(self.owner), (self.val[:75] + '..') if len(self.val) > 75 else self.val)


class InputDefinition(models.Model):
    created = models.DateTimeField()

    article = models.ForeignKey(wiki_models.Article, on_delete=models.CASCADE)
    name = models.CharField(max_length=28)
    expr = models.TextField()

    per_user = models.BooleanField()

    class Meta:
        unique_together = ('article', 'name')

    def __str__(self):
        return '{}:{}'.format(self.article, self.name)


class InputDependency(models.Model):
    idef = models.ForeignKey(InputDefinition, on_delete=models.CASCADE)

    article = models.ForeignKey(wiki_models.Article, on_delete=models.CASCADE)
    name = models.CharField(max_length=28)

    per_user = models.BooleanField()


    def __str__(self):
        return '{}:{}: {}:{}{}'.format(
            self.idef.article.pk,
            self.idef.name,
            self.article.pk,
            self.name,
            "" if self.per_user else "*")


@disable_signal_for_loaddata
def post_article_revision_save(**kwargs):
    arev = kwargs['instance']

    md = ArticleMarkdown(arev.article, preview=True)
    md.convert(arev.content)

    old = InputDefinition.objects.filter(article=arev.article).exclude(name__in=md.defs)
    if old.exists():
        logger.info("delete definition(s) {}: {}".format(arev.article, [str(o) for o in old]))
        old.delete()

    for name, val in md.defs.items():
        utils.update_inputdef(arev.article, name, val.getExprStack())


signals.post_save.connect(post_article_revision_save, wiki_models.ArticleRevision)
