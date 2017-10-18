# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

# from django.utils.translation import ugettext as _
from django.views.generic.base import View
from django.utils.decorators import method_decorator
from wiki.views.mixins import ArticleMixin
from wiki.decorators import get_article
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.mixins import LoginRequiredMixin
from wiki.core.markdown import ArticleMarkdown
from django.shortcuts import render
from collections import defaultdict
from django.db import transaction
from . import models
# from . import tasks

import logging
import json
import re
logger = logging.getLogger(__name__)

NAME_RE = re.compile(
    r'^\s*(?P<name>[-\w]+?)(?P<arr>\[(?P<query>.+?)\])?\s*$',
    re.IGNORECASE
)

class InputDataView(ArticleMixin, LoginRequiredMixin, View):
    http_method_names = ['get', 'post', ]

    @method_decorator(get_article(can_read=True))
    def dispatch(self, request, article, *args, **kwargs):
        self.md = ArticleMarkdown(article, preview=True)
        self.md.convert(article.current_revision.content)

        return super(InputDataView, self).dispatch(request, article, *args, **kwargs)

    def get(self, request, input_id, *args, **kwargs):
        try:
            field = self.md.input_fields[int(input_id)-1]
            name = field['name']
            val = models.Input.objects.filter(
                article=self.article,
                name=name,
                owner=request.user,
                newer__isnull=True).last()
        except Exception as e:
            logger.warning('broken get request: {}'.format(e))
            return HttpResponse(status=400)

        return JsonResponse({
            'val': json.loads(val.val) if val else "",
            'locked': self.article.current_revision.locked}, safe=False)


    def post(self, request, input_id, *args, **kwargs):
        if self.article.current_revision.locked:
            return HttpResponse(status=403)

        try:
            field = self.md.input_fields[int(input_id)-1]
            name = field['name']
            req = request.body.decode('utf-8')
            data = json.loads(req)
            data_json = json.dumps(data)
        except Exception as e:
            logger.warning('broken get request: {}'.format(e))
            return HttpResponse(status=500)

        curr = models.Input.objects.filter(article=self.article, name=name, owner=request.user).last()
        if curr and curr.val == data_json:
            return HttpResponse(status=204)

        new = models.Input(article=self.article, owner=request.user, name=name, val=data_json)

        with transaction.atomic():
            new.save()
            if curr:
                curr.newer = curr
                curr.save()

        return HttpResponse(status=204)


def evaluate_field(article, owner, f):
    out = None
    q = models.Input.objects.filter(
        article__pk=article.pk if f['article_pk'] == -1 else f['article_pk'],
        name=f['name'],
    )

    for m in f['methods']:
        if not out:
            if m['name'] == 'all':
                q = q.filter(newer__isnull=True)
                continue
            elif m['name'] == 'self':
                q = q.filter(newer__isnull=True, owner=owner)
                continue
            elif m['name'] == 'created':
                out = [(i, i.created) for i in q]
                continue
            else:
                out = [(i, json.loads(i.val)) for i in q]

        out = [(i, v.get(m['name'], None)) if v else None for i, v in out]

    return out if out else [(i, json.loads(i.val)) for i in q]



class DisplayDataView(ArticleMixin, LoginRequiredMixin, View):
    http_method_names = ['get', ]

    @method_decorator(get_article(can_read=True))
    def dispatch(self, request, article, *args, **kwargs):
        self.md = ArticleMarkdown(article, preview=True)
        self.md.convert(article.current_revision.content)

        return super(DisplayDataView, self).dispatch(request, article, *args, **kwargs)


    def get(self, request, display_id, *args, **kwargs):
        try:
            i = self.md.display_fields[int(display_id)-1]
            variant = i['variant'] if i['variant'] else "list"
            fields = i['fields']
        except:
            logger.warning('broken get request')
            return HttpResponse(status=400)

        if variant in ['list']:
            data = list()

            for i, f in enumerate(fields):
                for u, v in evaluate_field(self.article, request.user, f):
                    data.append(v)

            c = dict(data=data)

        elif variant in ['files']:
            data = list()
            for i, f in enumerate(fields):
                for u, v in evaluate_field(self.article, request.user, f):
                    data += v

            c = dict(data=data)

        elif variant == 'per-user':
            columns = list()
            data = defaultdict(lambda: [None] * len(fields))
            for i, f in enumerate(fields):
                columns.append(f['name'])

                for u, v in evaluate_field(self.article, request.user, f):
                    data[u.owner][i] = v

            c = dict(data=dict(data), columns=columns)

        else:
            c = dict()

        return render(request,
                      "wiki/plugins/forms/display-{}.html".format(variant),
                      context=c)
