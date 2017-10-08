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
from collections import defaultdict
from django.shortcuts import render


from . import models
from . import tasks

import logging
import json
import re
import ipdb

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
                owner=request.user).last()
        except Exception as e:
            logger.warning('broken get request: {}'.format(e))
            return HttpResponse(status=400)

        if val:
            return JsonResponse({
                'val': json.loads(val.val),
                'locked': self.article.current_revision.locked}, safe=False)
        else:
            return HttpResponse(status=204)


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

        curr = models.Input.objects.filter(article=self.article, name=name).last()
        if curr and curr.val == data_json:
            return HttpResponse(status=204)

        models.Input.objects.create(article=self.article, owner=request.user, name=name, val=data_json)

        return HttpResponse(status=204)


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
            variant = i['variant']
            fields = i['fields']
        except:
            logger.warning('broken get request')
            return HttpResponse(status=400)

        if variant is None or variant in ['files']:
            v = models.Input.objects.filter(
                article__pk=fields[0]['article_pk'],
                name=fields[0]['name'],
                owner=request.user).last()

            if v:
                data = json.loads(v.val)

        elif variant == 'all':
            data = dict()

            for i,f in enumerate(fields):
                q = models.Input.objects.filter(
                    article__pk=f['article_pk'],
                    name=f['name'])

                for o in q.values('owner__pk', 'owner__first_name', 'owner__last_name', 'owner__username').distinct():
                    v = q.filter(owner__pk=o['owner__pk']).last()
                    if v:
                        if o["owner__first_name"] and o['owner__last_name']:
                            uname = "{} {}".format(o["owner__first_name"],o['owner__last_name'])
                        else:
                            uname = o["owner__username"]

                        if uname not in data:
                            data[uname] = [None]*len(fields)

                        data[uname][i] = json.loads(v.val)

                    else:
                        idef = models.InputDefinition.objects.filter(
                            article__pk=f['article_pk'],
                            name=f['name']).last()
                        if idef:
                            tasks.evaluate_init(idef.pk, request.user.pk)

        c = dict(
            fields=[(f['article_pk'],f['name']) for f in fields],
            data=data)

        return render(request,
                      "wiki/plugins/forms/display-{}.html".format(variant if variant else "default"),
                      context=c)
